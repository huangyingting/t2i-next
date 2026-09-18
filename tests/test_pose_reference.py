from __future__ import annotations

import ast
import json
import os
import random
import subprocess
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import t2i_spatial_pipeline.pose_reference_cli as reference_cli
from t2i_spatial_pipeline.cli import app
from t2i_spatial_pipeline.pose_reference import (
    NeutralPose,
    NeutralPoseLibrary,
    PoseReferenceBatch,
    PoseReferenceScene,
    ReferenceLibraryAudit,
    SupportContact,
    audit_reference_library,
    describe_reference_poses,
    describe_reference_scenes,
    render_pose_reference,
    sample_pose_references,
    structural_distance,
)
from t2i_spatial_pipeline.pose_reference_catalog import build_neutral_pose_library
from t2i_spatial_pipeline.pose_reference_geometry import (
    compile_reference_geometry,
    reference_geometry_report,
    reference_joint_positions,
)
from t2i_spatial_pipeline.pose_reference_presentation import (
    presentation_accepts_camera,
    presentation_supports,
    render_reference_camera,
    render_reference_presentation,
    render_reference_subject,
)

LIBRARY = build_neutral_pose_library()
POSES = {pose.pose_id: pose for pose in LIBRARY.poses}


def test_library_has_curated_structural_coverage() -> None:
    assert len(LIBRARY.poses) == 48
    families = Counter(pose.family for pose in LIBRARY.poses)
    assert len(families) == 16
    assert set(families.values()) == {3}
    report = describe_reference_poses(LIBRARY.poses)
    assert set(report.body_level_counts) == {
        "standing",
        "seated",
        "kneeling",
        "crouched",
        "lying",
    }
    assert set(report.spine_counts) == {
        "upright",
        "forward_inclined",
        "reclined",
        "gentle_twist",
        "neutral_horizontal",
    }
    assert report.pair_count == 48 * 47 // 2
    assert report.minimum_structural_distance is not None
    assert report.minimum_structural_distance > 0
    assert report.evidence == "symbolic_structure_only"
    assert report.visual_validation is False
    assert LIBRARY.scope == "clothed_adult_figure_study"
    assert LIBRARY == NeutralPoseLibrary.model_validate_json(LIBRARY.model_dump_json())


@pytest.mark.parametrize("pose_id", tuple(POSES))
def test_every_pose_compiles_all_declared_geometry(pose_id: str) -> None:
    pose = POSES[pose_id]
    assert pose == NeutralPose.model_validate_json(pose.model_dump_json())
    for camera in LIBRARY.cameras:
        if camera.camera_id not in pose.compatible_camera_ids:
            continue
        subject = LIBRARY.subjects[0]
        presentation = next(
            item
            for item in LIBRARY.presentations
            if presentation_supports(
                item, tuple(contact.surface for contact in pose.supports)
            )
            and presentation_accepts_camera(item, camera)
        )
        prompt = render_pose_reference(pose, camera, subject, presentation)
        geometry = compile_reference_geometry(pose, subject, presentation)
        scene = PoseReferenceScene(
            pose=pose,
            camera=camera,
            subject=subject,
            presentation=presentation,
            prompt=prompt,
            geometry=geometry,
            geometry_report=reference_geometry_report(geometry),
            geometry_joints=reference_joint_positions(geometry),
        )
        assert scene.prompt.isascii()
        assert "\n" not in prompt
        assert "exactly one fully clothed adult" in prompt
        assert render_reference_subject(subject) in prompt
        assert render_reference_camera(camera) in prompt
        assert render_reference_presentation(presentation) in prompt
        assert "non-sexual figure-study" in prompt
        for value in (
            pose.body_level,
            pose.spine,
            pose.facing,
            pose.silhouette,
            pose.pelvis_facing,
            pose.legs,
            pose.gaze,
        ):
            assert value.replace("_", " ") in prompt
        for side, placement in (("left", pose.left_hand), ("right", pose.right_hand)):
            if placement == "on_mat_forward":
                assert f"The {side} palm rests on the mat" in prompt
            elif placement == "relaxed_in_front":
                assert f"The {side} hand is held loosely" in prompt
            elif placement == "on_knee":
                assert f"own {side} knee" in prompt
            elif placement == "across_forearm":
                opposite = "right" if side == "left" else "left"
                assert f"own {opposite} forearm" in prompt
            elif placement == "on_floor":
                assert f"The {side} palm rests flat on the floor" in prompt
            else:
                assert f"The {side} hand is {placement.replace('_', ' ')}" in prompt
        for contact in pose.supports:
            description = next(
                support.description
                for support in presentation.supports
                if support.surface == contact.surface
            )
            suffix = " bears weight" if contact.load_bearing else " makes light contact"
            expected = f"{contact.body_part.replace('_', ' ')} on {description}{suffix}"
            assert expected in prompt


@pytest.mark.parametrize(
    ("pose_id", "changes", "error"),
    [
        (
            "standing_parallel_relaxed",
            {"spine": "impossible_spine"},
            "Input should be",
        ),
        (
            "standing_parallel_relaxed",
            {"body_level": "seated"},
            "leg configuration contradicts body level",
        ),
        (
            "standing_parallel_relaxed",
            {"legs": "floor_seated_bent_knees"},
            "leg configuration contradicts body level",
        ),
        (
            "table_supported_left",
            {"left_hand": "forward_gesture"},
            "supported hand cannot also perform",
        ),
        (
            "table_supported_left",
            {"left_hand": "on_wall"},
            "hand placement lacks",
        ),
        (
            "standing_parallel_relaxed",
            {"left_hand": "on_table"},
            "hand placement lacks",
        ),
        (
            "half_kneeling_left",
            {"weight_distribution": "both_knees"},
            "Extra inputs",
        ),
        (
            "half_kneeling_left",
            {"legs": "right_half_kneel"},
            "declared support surface",
        ),
        (
            "standing_parallel_relaxed",
            {"legs": "right_foot_on_step"},
            "declared support surface",
        ),
        (
            "standing_parallel_relaxed",
            {"spine": "reclined"},
            "reclined references require",
        ),
        (
            "standing_parallel_relaxed",
            {"spine": "neutral_horizontal"},
            "reserved for lying",
        ),
        (
            "side_lying_rest_left",
            {"spine": "upright"},
            "lying reference requires",
        ),
        (
            "floor_seated_centered",
            {"balance_bias": "left"},
            "standing load-bearing foot",
        ),
        (
            "standing_parallel_relaxed",
            {"compatible_camera_ids": ["front_eye", "front_eye"]},
            "compatible cameras must be unique",
        ),
        (
            "standing_parallel_relaxed",
            {"activity_id": "unsupported"},
            "Extra inputs",
        ),
    ],
)
def test_pose_rejects_inconsistent_geometry(
    pose_id: str, changes: dict[str, object], error: str
) -> None:
    payload = POSES[pose_id].model_dump(mode="json")
    payload.update(changes)
    with pytest.raises(ValidationError, match=error):
        NeutralPose.model_validate(payload)


def test_support_contact_ownership_and_loading() -> None:
    with pytest.raises(ValidationError, match="support surface"):
        SupportContact(body_part="left_knee", surface="table")
    pose = POSES["standing_parallel_relaxed"]
    payload = pose.model_dump(mode="json")
    payload["supports"] = [*payload["supports"], payload["supports"][0]]
    with pytest.raises(ValidationError, match="one surface"):
        NeutralPose.model_validate(payload)
    payload["supports"] = [
        contact.model_dump(mode="json") | {"load_bearing": False}
        for contact in pose.supports
    ]
    with pytest.raises(ValidationError, match="load-bearing"):
        NeutralPose.model_validate(payload)
    payload["supports"] = [
        *(contact.model_dump(mode="json") for contact in pose.supports),
        {"body_part": "left_knee", "surface": "mat", "load_bearing": True},
    ]
    with pytest.raises(ValidationError, match="support body part contradicts"):
        NeutralPose.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "error"),
    [
        ("pose_id", "pose IDs must be unique"),
        ("structure", "poses must differ structurally"),
        ("camera_id", "camera IDs must be unique"),
        ("camera_recipe", "camera recipes must differ"),
        ("camera_reference", "unknown camera"),
    ],
)
def test_library_rejects_ambiguous_entries(field: str, error: str) -> None:
    payload = LIBRARY.model_dump(mode="json")
    if field == "pose_id":
        payload["poses"][1]["pose_id"] = payload["poses"][0]["pose_id"]
    elif field == "structure":
        payload["poses"][1] = payload["poses"][0] | {
            "pose_id": "renamed_pose",
            "family": "new_family",
            "gaze": "downward",
        }
    elif field == "camera_id":
        payload["cameras"][1]["camera_id"] = payload["cameras"][0]["camera_id"]
    elif field == "camera_recipe":
        payload["cameras"][1] = payload["cameras"][0] | {
            "camera_id": payload["cameras"][1]["camera_id"]
        }
    elif field == "camera_reference":
        payload["poses"][0]["compatible_camera_ids"] = ["unknown_camera"]
    with pytest.raises(ValidationError, match=error):
        NeutralPoseLibrary.model_validate(payload)


def test_structural_distance_measures_fields_not_labels_or_gaze() -> None:
    pose = POSES["standing_parallel_relaxed"]
    left_turn = POSES["standing_parallel_turn_left"]
    assert structural_distance(pose, pose) == 0
    assert structural_distance(pose, left_turn) == 3 / 8
    assert structural_distance(left_turn, pose) == 3 / 8
    renamed = NeutralPose.model_validate(
        pose.model_dump(mode="json")
        | {
            "pose_id": "renamed_pose",
            "family": "renamed_family",
            "gaze": "downward",
            "compatible_camera_ids": ["left_eye"],
            "supports": [
                contact.model_dump(mode="json") for contact in reversed(pose.supports)
            ],
        }
    )
    assert structural_distance(pose, renamed) == 0


@pytest.mark.parametrize("seed", [0, 1, 42, 123456])
def test_sampling_is_reproducible_balanced_and_unique(seed: int) -> None:
    random_state = random.getstate()
    full = sample_pose_references(LIBRARY, seed=seed, count=48)
    assert random.getstate() == random_state
    assert full == sample_pose_references(LIBRARY, seed=seed, count=48)
    assert full == PoseReferenceBatch.model_validate_json(full.model_dump_json())
    assert len({scene.pose.pose_id for scene in full.scenes}) == 48
    assert full.report == describe_reference_scenes(full.scenes, full.history_before)
    for count in (1, 6, 16, 20, 32, 48):
        batch = sample_pose_references(LIBRARY, seed=seed, count=count)
        assert len(batch.scenes) == count
        assert [s.pose for s in batch.scenes] == [s.pose for s in full.scenes[:count]]
        counts = Counter(scene.pose.family for scene in batch.scenes)
        assert len(counts) == min(count, 16)
        assert max(counts.values()) - min(counts.values()) <= 1
        if count >= 16:
            assert len(batch.report.body_level_counts) == 5
        assert all(
            scene.camera.camera_id in scene.pose.compatible_camera_ids
            for scene in batch.scenes
        )


def test_sampling_is_independent_of_catalog_order() -> None:
    reordered = NeutralPoseLibrary(
        cameras=tuple(reversed(LIBRARY.cameras)),
        poses=tuple(reversed(LIBRARY.poses)),
        subjects=tuple(reversed(LIBRARY.subjects)),
        presentations=tuple(reversed(LIBRARY.presentations)),
    )
    for count in (1, 16, 48):
        assert sample_pose_references(reordered, seed=42, count=count) == (
            sample_pose_references(LIBRARY, seed=42, count=count)
        )


def test_sampler_follows_family_first_maximin_rule() -> None:
    batch = sample_pose_references(LIBRARY, seed=7, count=32)
    selected: list[NeutralPose] = []
    family_counts: Counter[str] = Counter()
    remaining = list(LIBRARY.poses)
    for scene in batch.scenes:
        minimum_family_count = min(family_counts[pose.family] for pose in remaining)
        eligible = [
            pose
            for pose in remaining
            if family_counts[pose.family] == minimum_family_count
        ]
        assert scene.pose in eligible
        if selected:
            nearest_distances = [
                min(structural_distance(pose, previous) for previous in selected)
                for pose in eligible
            ]
            actual = min(
                structural_distance(scene.pose, previous) for previous in selected
            )
            assert actual == max(nearest_distances)
        selected.append(scene.pose)
        family_counts[scene.pose.family] += 1
        remaining.remove(scene.pose)


def test_seed_changes_selection_and_family_filter_is_respected() -> None:
    first = sample_pose_references(LIBRARY, seed=1, count=16)
    second = sample_pose_references(LIBRARY, seed=2, count=16)
    assert [scene.pose.pose_id for scene in first.scenes] != [
        scene.pose.pose_id for scene in second.scenes
    ]
    filtered = sample_pose_references(LIBRARY, seed=42, count=3, family="half_kneeling")
    assert filtered.report.family_counts == {"half_kneeling": 3}
    assert len({scene.pose.pose_id for scene in filtered.scenes}) == 3


@pytest.mark.parametrize("count", [0, -1, 49])
def test_sampling_rejects_unavailable_count(count: int) -> None:
    with pytest.raises(ValueError, match="count must be between 1 and 48"):
        sample_pose_references(LIBRARY, seed=0, count=count)


def test_unknown_family_and_oversized_filtered_sample_fail() -> None:
    with pytest.raises(ValueError, match="unknown reference pose family"):
        sample_pose_references(LIBRARY, seed=0, count=1, family="missing")
    with pytest.raises(ValueError, match="between 1 and 3"):
        sample_pose_references(LIBRARY, seed=0, count=4, family="half_kneeling")


def test_report_counts_exact_pairs_and_single_pose_has_no_distance() -> None:
    poses = LIBRARY.poses[:3]
    report = describe_reference_poses(poses)
    distances = [structural_distance(a, b) for a, b in combinations(poses, 2)]
    assert report.pair_count == 3
    assert report.minimum_structural_distance == min(distances)
    assert report.mean_structural_distance == sum(distances) / 3
    for counts in (
        report.family_counts,
        report.body_level_counts,
        report.spine_counts,
        report.balance_bias_counts,
    ):
        assert sum(counts.values()) == 3
    single = describe_reference_poses(poses[:1])
    assert single.pair_count == 0
    assert single.minimum_structural_distance is None
    assert single.mean_structural_distance is None
    with pytest.raises(ValueError, match="at least one pose"):
        describe_reference_poses(())


def test_scene_and_batch_reject_stale_derived_data() -> None:
    batch = sample_pose_references(LIBRARY, seed=0, count=2)
    payload = batch.model_dump(mode="json")
    payload["report"]["pose_count"] = 100
    with pytest.raises(ValidationError, match="report differs"):
        PoseReferenceBatch.model_validate(payload)
    payload = batch.model_dump(mode="json")
    payload["scenes"][1] = payload["scenes"][0]
    with pytest.raises(ValidationError, match="distinct poses"):
        PoseReferenceBatch.model_validate(payload)
    scene = batch.scenes[0].model_dump(mode="json")
    scene["prompt"] = "Different geometry."
    with pytest.raises(ValidationError, match="prompt differs"):
        PoseReferenceScene.model_validate(scene)
    with pytest.raises(ValueError, match="incompatible"):
        render_pose_reference(
            POSES["side_lying_rest_left"],
            LIBRARY.cameras[0],
            LIBRARY.subjects[0],
            LIBRARY.presentations[0],
        )


def test_cli_list_audit_and_sample_are_wired() -> None:
    runner = CliRunner()
    listing = runner.invoke(app, ["poses", "list"])
    assert listing.exit_code == 0, listing.output
    assert NeutralPoseLibrary.model_validate_json(listing.stdout) == LIBRARY
    audit = runner.invoke(app, ["poses", "audit"])
    assert audit.exit_code == 0, audit.output
    report = ReferenceLibraryAudit.model_validate_json(audit.stdout)
    assert report == audit_reference_library(LIBRARY)
    assert report.evidence == "static_proxy_geometry_and_symbolic_structure"
    assert report.pose_report.evidence == "symbolic_structure_only"
    assert report.geometry_checked_scenes == (
        report.compatible_pose_camera_presentation_count * report.subject_count
    )
    assert not report.geometry_rejections
    sample = runner.invoke(app, ["poses", "sample", "--seed", "42", "--count", "16"])
    assert sample.exit_code == 0, sample.output
    assert PoseReferenceBatch.model_validate_json(sample.stdout) == (
        sample_pose_references(LIBRARY, seed=42, count=16)
    )
    filtered = runner.invoke(app, ["poses", "list", "--family", "wall_supported"])
    assert filtered.exit_code == 0, filtered.output
    library = NeutralPoseLibrary.model_validate_json(filtered.stdout)
    assert len(library.poses) == 3
    assert {pose.family for pose in library.poses} == {"wall_supported"}


def test_cli_exports_exact_text_and_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "references" / "poses.txt"
    arguments = [
        "poses",
        "sample",
        "--seed",
        "42",
        "--count",
        "3",
        "--family",
        "half_kneeling",
        "--format",
        "text",
        "--output",
        str(path),
    ]
    runner = CliRunner()
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    expected = sample_pose_references(LIBRARY, seed=42, count=3, family="half_kneeling")
    assert path.read_text(encoding="utf-8").splitlines() == [
        scene.prompt for scene in expected.scenes
    ]
    original = path.read_bytes()
    duplicate = runner.invoke(app, arguments)
    assert duplicate.exit_code == 1
    assert path.read_bytes() == original
    assert "File exists" in duplicate.output


@pytest.mark.parametrize("command", ["list", "audit", "sample"])
def test_cli_json_exports_are_parseable(command: str, tmp_path: Path) -> None:
    path = tmp_path / f"{command}.json"
    result = CliRunner().invoke(app, ["poses", command, "--output", str(path)])
    assert result.exit_code == 0, result.output
    assert json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "arguments",
    [
        ["poses", "list", "--family", "missing"],
        ["poses", "sample", "--family", "missing"],
        ["poses", "sample", "--count", "49"],
        ["poses", "sample", "--family", "half_kneeling", "--count", "4"],
        ["poses", "sample", "--count", "0"],
        ["poses", "sample", "--format", "unsupported"],
    ],
)
def test_cli_invalid_input_does_not_publish(
    arguments: list[str], tmp_path: Path
) -> None:
    path = tmp_path / "must-not-exist.json"
    result = CliRunner().invoke(app, [*arguments, "--output", str(path)])
    assert result.exit_code != 0
    assert not path.exists()


def test_export_failure_removes_only_its_partial_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    existing = tmp_path / "existing.txt"
    existing.write_text("preserve", encoding="utf-8")
    path = tmp_path / "partial.txt"

    def fail_sync(_descriptor: int) -> None:
        raise OSError("simulated storage failure")

    monkeypatch.setattr(reference_cli.os, "fsync", fail_sync)
    result = CliRunner().invoke(
        app, ["poses", "sample", "--count", "1", "--output", str(path)]
    )
    assert result.exit_code == 1
    assert "simulated storage failure" in result.output
    assert not path.exists()
    assert existing.read_text(encoding="utf-8") == "preserve"


def test_reference_modules_have_no_pipeline_or_activity_dependencies() -> None:
    package = Path(reference_cli.__file__).parent
    for name in (
        "pose_reference.py",
        "pose_reference_catalog.py",
        "pose_reference_cli.py",
        "pose_reference_types.py",
        "pose_reference_history.py",
        "pose_reference_presentation.py",
        "pose_reference_geometry.py",
    ):
        tree = ast.parse((package / name).read_text(encoding="utf-8"))
        relative_imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level
        }
        assert relative_imports <= {
            "pose_reference",
            "pose_reference_catalog",
            "pose_reference_types",
            "pose_reference_history",
            "pose_reference_presentation",
            "pose_reference_geometry",
        }
        absolute_imports = {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and not node.level and node.module
        }
        absolute_imports.update(
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert absolute_imports <= {
            "__future__",
            "random",
            "collections",
            "itertools",
            "typing",
            "pydantic",
            "os",
            "enum",
            "pathlib",
            "typer",
            "hashlib",
            "json",
            "t2i_pose_geometry",
            "numpy",
            "scipy",
            "math",
            "functools",
            "importlib",
        }


_ISOLATED_REFERENCE_SCRIPT = """
import hashlib
import importlib.abc
import json
import socket
import sys

blocked = {"t2i_story_pipeline", "t2i_prompt_pipeline", "t2i_film_style_pipeline"}

class RejectOtherPipelines(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise AssertionError("unexpected dependency: " + fullname)
        return None

def reject_external_access(*args, **kwargs):
    raise AssertionError("pose references must not use a provider or activity catalog")

sys.meta_path.insert(0, RejectOtherPipelines())
socket.socket.connect = reject_external_access
socket.create_connection = reject_external_access

from t2i_spatial_pipeline import blueprint, catalog, config, service
from t2i_spatial_pipeline.pose_reference import sample_pose_references
from t2i_spatial_pipeline.pose_reference_catalog import build_neutral_pose_library
from t2i_spatial_pipeline.cli import app
from typer.testing import CliRunner

for module in (blueprint, config, service):
    module.load_spatial_provider_settings = reject_external_access
catalog.build_catalog = reject_external_access
service.build_scene_requests = reject_external_access

library = build_neutral_pose_library()
result = [
    sample_pose_references(library, seed=seed, count=count).model_dump(mode="json")
    for seed in (0, 42)
    for count in (1, 16, 48)
]
for command in ("list", "audit", "sample"):
    invocation = CliRunner().invoke(app, ["poses", command])
    assert invocation.exit_code == 0, invocation.output
    json.loads(invocation.stdout)
assert not any(name.split(".")[0] in blocked for name in sys.modules)
print(hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest())
"""


def test_offline_cli_and_sampling_survive_python_hash_randomization() -> None:
    digests = []
    for hash_seed in ("1", "99991"):
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OPENAI_", "COPILOT_"))
        }
        environment["PYTHONHASHSEED"] = hash_seed
        result = subprocess.run(
            [sys.executable, "-c", _ISOLATED_REFERENCE_SCRIPT],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        digests.append(result.stdout.strip())
    assert len(digests[0]) == 64
    assert digests[0] == digests[1]
