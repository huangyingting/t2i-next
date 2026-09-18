from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import t2i_pose_geometry
from t2i_pose_geometry.kinematics import forward_kinematics
from t2i_pose_geometry.models import ActorPose, Box, Contact, JointAngles, Scene
from t2i_pose_geometry.validation import validate_scene
from t2i_spatial_pipeline.cli import app
from t2i_spatial_pipeline.pose_reference import (
    NeutralPose,
    NeutralPoseLibrary,
    PoseReferenceBatch,
    PoseReferenceScene,
    render_pose_reference,
    sample_pose_references,
)
from t2i_spatial_pipeline.pose_reference_catalog import build_neutral_pose_library
from t2i_spatial_pipeline.pose_reference_geometry import (
    ReferenceGeometryError,
    compile_reference_geometry,
    reference_geometry_report,
    reference_joint_positions,
)

LIBRARY = build_neutral_pose_library()
POSES = {pose.pose_id: pose for pose in LIBRARY.poses}


@pytest.mark.parametrize("pose_id", tuple(POSES))
@pytest.mark.parametrize("subject", LIBRARY.subjects, ids=lambda item: item.subject_id)
def test_each_recipe_passes_for_each_subject(pose_id, subject) -> None:
    geometry = compile_reference_geometry(
        POSES[pose_id], subject, LIBRARY.presentations[0]
    )
    assert validate_scene(geometry).passed
    assert reference_geometry_report(geometry).passed
    assert Scene.model_validate_json(geometry.model_dump_json()) == geometry
    assert geometry.actors[0].body == ActorPose(actor_id="reference").body.scaled(
        subject.body_scale
    )


def test_a_declared_palm_contact_does_not_hide_forearm_slab_penetration() -> None:
    actor = ActorPose(
        actor_id="person",
        angles=JointAngles(
            left_elbow_flex=150,
            left_wrist_flex=-60,
            left_wrist_rotation=180,
        ),
    )
    palm = forward_kinematics(actor).anchors["left_palm"]
    table = Box(
        object_id="table",
        center=(palm.position[0], palm.position[1], palm.position[2] - 0.025),
        size=(0.35, 0.35, 0.05),
    )
    scene = Scene(
        actors=(actor,),
        objects=(table,),
        contacts=(Contact(actor_id="person", anchor="left_palm", object_id="table"),),
    )
    report = validate_scene(scene)
    assert not report.passed
    assert not any(
        issue.code in {"contact_distance", "contact_normal"} for issue in report.issues
    )
    assert any(
        issue.code == "object_collision"
        and issue.parts == ("person", "left_forearm", "table")
        for issue in report.issues
    )


def _unreachable_pose() -> NeutralPose:
    return NeutralPose.model_validate(
        POSES["standing_parallel_relaxed"].model_dump()
        | {
            "pose_id": "unreachable_knee",
            "family": "unreachable_reference",
            "left_hand": "on_knee",
        }
    )


def test_symbolically_valid_but_unreachable_pose_cannot_render() -> None:
    pose = _unreachable_pose()
    with pytest.raises(ReferenceGeometryError) as failure:
        render_pose_reference(
            pose, LIBRARY.cameras[0], LIBRARY.subjects[0], LIBRARY.presentations[0]
        )
    assert not failure.value.report.passed
    assert any(
        issue.code == "body_contact_distance"
        and "left_knee_top" in issue.parts
        and issue.error_m is not None
        and issue.error_m > 0.002
        for issue in failure.value.report.issues
    )


def test_sampler_reports_rejections_and_never_falls_back_to_invalid_pose() -> None:
    good = POSES["standing_parallel_relaxed"]
    bad = _unreachable_pose()
    library = NeutralPoseLibrary(
        poses=(good, bad),
        cameras=LIBRARY.cameras,
        presentations=LIBRARY.presentations,
        subjects=LIBRARY.subjects,
    )
    batch = sample_pose_references(library, seed=42, count=1, subject_id="mara")
    assert [scene.pose.pose_id for scene in batch.scenes] == [good.pose_id]
    assert batch.geometry_rejections
    assert all(
        rejection.pose_id == bad.pose_id and not rejection.report.passed
        for rejection in batch.geometry_rejections
    )
    with pytest.raises(ValueError, match="between 1 and 1") as failure:
        sample_pose_references(library, seed=42, count=2, subject_id="mara")
    assert bad.pose_id in str(failure.value)
    invalid_library = NeutralPoseLibrary(
        poses=(bad,),
        cameras=LIBRARY.cameras,
        presentations=LIBRARY.presentations,
        subjects=LIBRARY.subjects,
    )
    with pytest.raises(ValueError, match="unreachable_knee"):
        sample_pose_references(invalid_library, seed=42, count=1, subject_id="mara")


@pytest.mark.parametrize("command", ["audit", "preview"])
def test_invalid_geometry_cli_exports_diagnostics_and_exits_nonzero(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _unreachable_pose()
    library = NeutralPoseLibrary(
        poses=(bad,),
        cameras=LIBRARY.cameras,
        presentations=LIBRARY.presentations,
        subjects=LIBRARY.subjects,
    )
    monkeypatch.setattr(
        "t2i_spatial_pipeline.pose_reference_cli.build_neutral_pose_library",
        lambda: library,
    )
    output = tmp_path / ("invalid.svg" if command == "preview" else "invalid.json")
    arguments = ["poses", command]
    if command == "preview":
        arguments.append(bad.pose_id)
    result = CliRunner().invoke(app, [*arguments, "--output", str(output)])
    assert result.exit_code == 1, result.output
    if command == "preview":
        assert "FAIL" in output.read_text()
        assert bad.pose_id in result.output
    else:
        payload = json.loads(output.read_text())
        assert payload["geometry_checked_scenes"] == 0
        assert payload["geometry_rejections"]
        assert all(
            item["pose_id"] == bad.pose_id and not item["report"]["passed"]
            for item in payload["geometry_rejections"]
        )


def test_scene_exports_match_checked_geometry_and_reject_forged_evidence() -> None:
    batch = sample_pose_references(
        LIBRARY,
        seed=42,
        count=1,
        family="standing_parallel",
        subject_id="mara",
    )
    scene = batch.scenes[0]
    assert scene.geometry_report.passed
    assert scene.geometry_joints == reference_joint_positions(scene.geometry)
    assert PoseReferenceScene.model_validate_json(scene.model_dump_json()) == scene
    payload = scene.model_dump(mode="json")
    payload["geometry_joints"][0]["position"][0] += 0.1
    with pytest.raises(ValidationError, match="joints differ"):
        PoseReferenceScene.model_validate(payload)
    payload = scene.model_dump(mode="json")
    payload["geometry"]["actors"][0]["root_position"][2] += 0.1
    with pytest.raises(ValidationError, match="geometry differs"):
        PoseReferenceScene.model_validate(payload)
    payload = scene.model_dump(mode="json")
    payload["geometry_report"] = {
        "passed": False,
        "issues": [{"code": "forged", "parts": [], "details": "not from validation"}],
    }
    with pytest.raises(ValidationError, match="geometry report differs"):
        PoseReferenceScene.model_validate(payload)
    payload = scene.model_dump(mode="json")
    payload["geometry_tolerances"]["penetration_m"] = 0.001
    with pytest.raises(ValidationError, match="tolerances differ"):
        PoseReferenceScene.model_validate(payload)


def test_preview_cli_exports_checked_three_view_svg_without_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "table.svg"
    arguments = [
        "poses",
        "preview",
        "table_supported_both",
        "--output",
        str(output),
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    original = output.read_bytes()
    assert b"<svg" in original
    assert b"PASS" in original
    again = CliRunner().invoke(app, arguments)
    assert again.exit_code == 1
    assert "File exists" in again.output
    assert output.read_bytes() == original


def test_geometry_kernel_has_no_pipeline_dependency() -> None:
    assert t2i_pose_geometry.__file__ is not None
    folder = Path(t2i_pose_geometry.__file__).parent
    forbidden = {
        "t2i_spatial_pipeline",
        "t2i_story_pipeline",
        "t2i_film_style_pipeline",
        "t2i_prompt_pipeline",
        "t2i_model_provider",
    }
    for path in folder.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {n.name.split(".")[0] for n in node.names} & forbidden
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                assert node.module.split(".")[0] not in forbidden


def test_current_batch_json_includes_world_geometry_and_joint_coordinates() -> None:
    result = CliRunner().invoke(
        app, ["poses", "sample", "--count", "1", "--family", "standing_gesture"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    batch = PoseReferenceBatch.model_validate(payload)
    assert payload["schema_version"] == "4.0"
    assert batch.report.geometry_checked_scenes == 1
    assert payload["scenes"][0]["geometry"]["actors"]
    assert payload["scenes"][0]["geometry_joints"]
    assert payload["scenes"][0]["geometry_report"]["passed"] is True
    assert payload["scenes"][0]["geometry_tolerances"]["penetration_m"] == 0.00001
