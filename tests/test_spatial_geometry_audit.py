from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from t2i_pose_geometry import (
    ActorPose,
    BodyContact,
    Box,
    Contact,
    Scene,
    SceneSolveRequest,
    SceneSolveResult,
    Tolerances,
    validate_scene,
)
from t2i_spatial_pipeline.cli import app


@pytest.fixture
def request_path(tmp_path: Path) -> Path:
    actors = (
        ActorPose(actor_id="first", root_position=(0, 0, 0.92)),
        ActorPose(
            actor_id="second",
            root_position=(0.04, -0.28, 0.94),
            root_rotation=(0, 0, 180),
        ),
    )
    request = SceneSolveRequest(
        scene=Scene(
            actors=actors,
            objects=(Box(object_id="floor", center=(0, 0, -0.1), size=(4, 4, 0.2)),),
            contacts=tuple(
                Contact(
                    actor_id=actor.actor_id, anchor=f"{side}_sole", object_id="floor"
                )
                for actor in actors
                for side in ("left", "right")
            ),
            body_contacts=(
                BodyContact(
                    actor_id="first",
                    anchor="back",
                    target_actor_id="second",
                    target_anchor="back",
                ),
            ),
        ),
        variables_by_actor={"first": ("root_z",), "second": ("root_position",)},
    )
    path = tmp_path / "request.json"
    path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_geometry_cli_exports_actual_scene_and_independent_evidence(
    request_path: Path, tmp_path: Path
) -> None:
    report = tmp_path / "evidence" / "report.json"
    preview = tmp_path / "evidence" / "geometry.svg"
    invocation = CliRunner().invoke(
        app,
        [
            "audit-geometry",
            str(request_path),
            "--output",
            str(report),
            "--preview",
            str(preview),
        ],
    )

    assert invocation.exit_code == 0, invocation.output
    evidence = json.loads(report.read_text(encoding="utf-8"))
    assert evidence == json.loads(invocation.stdout)
    assert evidence["accepted"] is True
    assert evidence["physical_validation"] is False
    assert evidence["catalog_certification"] is False
    result = SceneSolveResult.model_validate(evidence["result"])
    assert result.accepted
    assert result.report == validate_scene(result.scene, tolerances=result.tolerances)
    assert len(result.scene.actors) == 2
    assert preview.read_text(encoding="utf-8").startswith("<svg")


def test_geometry_cli_retains_failed_candidate_with_matching_preview_tolerances(
    request_path: Path, tmp_path: Path
) -> None:
    request = SceneSolveRequest.model_validate_json(request_path.read_text())
    actors = (
        request.scene.actors[0].model_copy(update={"root_position": (0, 0, 0.895)}),
        request.scene.actors[1].model_copy(
            update={"root_position": (0, -0.2115, 0.895)}
        ),
    )
    scene = request.scene.model_copy(update={"actors": actors})
    assert validate_scene(scene).passed
    request = SceneSolveRequest(
        scene=scene,
        variables_by_actor={"first": (), "second": ()},
        tolerances=Tolerances(contact_m=0.001),
    )
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    report, preview = tmp_path / "failed.json", tmp_path / "failed.svg"
    invocation = CliRunner().invoke(
        app,
        [
            "audit-geometry",
            str(request_path),
            "--output",
            str(report),
            "--preview",
            str(preview),
        ],
    )

    assert invocation.exit_code == 1
    evidence = json.loads(report.read_text(encoding="utf-8"))
    assert evidence["accepted"] is False
    assert evidence["result"]["report"]["passed"] is False
    assert any(
        issue["code"] == "body_contact_distance"
        for issue in evidence["result"]["report"]["issues"]
    )
    assert "body_contact_distance" in preview.read_text(encoding="utf-8")


def test_geometry_cli_does_not_drop_unknown_contact_endpoints(
    request_path: Path, tmp_path: Path
) -> None:
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    payload["scene"]["body_contacts"][0]["anchor"] = "unmodeled_surface"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    report = tmp_path / "report.json"
    invocation = CliRunner().invoke(
        app, ["audit-geometry", str(request_path), "--output", str(report)]
    )

    assert invocation.exit_code == 1
    assert "Unknown contact anchor" in invocation.output
    assert not report.exists()


@pytest.mark.parametrize("option", ("--output", "--preview"))
def test_geometry_cli_cannot_overwrite_its_input(
    request_path: Path, option: str
) -> None:
    original = request_path.read_bytes()
    invocation = CliRunner().invoke(
        app, ["audit-geometry", str(request_path), option, str(request_path)]
    )

    assert invocation.exit_code == 1
    assert "paths must be distinct" in invocation.output
    assert request_path.read_bytes() == original
