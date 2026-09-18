from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from t2i_spatial_pipeline.cli import app
from t2i_spatial_pipeline.pose_reference import (
    NeutralPoseLibrary,
    PoseReferenceBatch,
    PoseReferenceScene,
    audit_reference_library,
    render_pose_reference,
    sample_pose_references,
)
from t2i_spatial_pipeline.pose_reference_catalog import build_neutral_pose_library
from t2i_spatial_pipeline.pose_reference_history import (
    ReferenceChoice,
    ReferenceUsage,
    advance_reference_usage,
)
from t2i_spatial_pipeline.pose_reference_presentation import (
    presentation_accepts_camera,
    presentation_supports,
)

LIBRARY = build_neutral_pose_library()


def test_usage_updates_are_immutable_and_count_complete_choices() -> None:
    before = ReferenceUsage(catalog_fingerprint=LIBRARY.fingerprint())
    batch = sample_pose_references(LIBRARY, seed=42, count=3)
    choices = tuple(
        ReferenceChoice(
            pose_id=scene.pose.pose_id,
            camera_id=scene.camera.camera_id,
            presentation_id=scene.presentation.presentation_id,
        )
        for scene in batch.scenes
    )
    after = advance_reference_usage(before, choices)
    assert before.selected_scenes == 0
    assert before.pose_counts == {}
    assert after == batch.history_after
    assert after.completed_batches == 1
    assert after.selected_scenes == 3
    replay = advance_reference_usage(after, choices)
    assert replay.completed_batches == 2
    assert replay.selected_scenes == 6
    assert all(value == 2 for value in replay.pose_counts.values())
    assert all(value == 2 for value in replay.combination_counts.values())
    assert after.selected_scenes == 3
    assert ReferenceUsage.model_validate_json(replay.model_dump_json()) == replay
    with pytest.raises(ValueError, match="at least one"):
        advance_reference_usage(before, ())


@pytest.mark.parametrize(
    "changes",
    [
        {"selected_scenes": 2},
        {"completed_batches": 1},
        {"pose_counts": {"made_up": -1}},
        {"pose_counts": {"made_up": 0}},
        {"catalog_fingerprint": "wrong"},
    ],
)
def test_usage_rejects_inconsistent_snapshot(changes: dict[str, object]) -> None:
    payload = ReferenceUsage(
        catalog_fingerprint=LIBRARY.fingerprint()
    ).model_dump(mode="json")
    with pytest.raises(ValidationError):
        ReferenceUsage.model_validate(payload | changes)


def test_three_history_batches_exhaust_poses_before_reusing() -> None:
    history = ReferenceUsage(catalog_fingerprint=LIBRARY.fingerprint())
    seen: set[str] = set()
    for index in range(3):
        batch = sample_pose_references(LIBRARY, seed=42, count=16, history=history)
        selected = {scene.pose.pose_id for scene in batch.scenes}
        assert selected.isdisjoint(seen)
        assert len(selected) == len(batch.report.family_counts) == 16
        assert batch.report.previously_used_pose_scenes == 0
        assert batch.report.previously_used_combination_scenes == 0
        assert batch.history_before == history
        assert batch.history_after.selected_scenes == 16 * (index + 1)
        assert batch.history_after.completed_batches == index + 1
        assert all(scene.subject == batch.subject for scene in batch.scenes)
        seen.update(selected)
        history = batch.history_after
    assert len(seen) == 48
    fourth = sample_pose_references(LIBRARY, seed=42, count=16, history=history)
    assert fourth.report.previously_used_pose_scenes == 16
    assert fourth.history_after.selected_scenes == 64


def test_same_seed_snapshot_and_filters_replay_exactly() -> None:
    first = sample_pose_references(LIBRARY, seed=5, count=16)
    batch = sample_pose_references(
        LIBRARY, seed=5, count=3, family="half_kneeling",
        subject_id=first.subject.subject_id, history=first.history_after,
    )
    restored = PoseReferenceBatch.model_validate_json(batch.model_dump_json())
    assert restored == sample_pose_references(
        LIBRARY,
        seed=restored.seed,
        count=len(restored.scenes),
        family=restored.family_filter,
        presentation_id=restored.presentation_filter,
        subject_id=restored.subject.subject_id,
        history=restored.history_before,
    )
    assert restored.history_before == first.history_after
    assert len(restored.report.subject_counts) == 1
    assert sum(restored.report.camera_counts.values()) == 3
    assert sum(restored.report.presentation_counts.values()) == 3


def test_history_binds_presentation_and_subject_definitions() -> None:
    first = sample_pose_references(LIBRARY, seed=0, count=1)
    payload = LIBRARY.model_dump(mode="json")
    payload["subjects"][0]["appearance"] += " A small freckle on the left cheek."
    changed = NeutralPoseLibrary.model_validate(payload)
    assert changed.fingerprint() != LIBRARY.fingerprint()
    with pytest.raises(ValueError, match="different catalog definition"):
        sample_pose_references(changed, seed=0, count=1, history=first.history_after)
    payload = LIBRARY.model_dump(mode="json")
    payload["presentations"][0]["palette"] += " A muted green accent."
    changed = NeutralPoseLibrary.model_validate(payload)
    with pytest.raises(ValueError, match="different catalog definition"):
        sample_pose_references(changed, seed=0, count=1, history=first.history_after)


def test_unknown_history_ids_fail_even_with_matching_fingerprint() -> None:
    batch = sample_pose_references(LIBRARY, seed=0, count=1)
    payload = batch.history_after.model_dump()
    payload["pose_counts"] = {"unknown_pose": 1}
    history = ReferenceUsage.model_validate(payload)
    with pytest.raises(ValueError, match="unknown catalog IDs"):
        sample_pose_references(LIBRARY, seed=0, count=1, history=history)


def test_batch_rejects_stale_history_and_inconsistent_subject() -> None:
    batch = sample_pose_references(LIBRARY, seed=0, count=2)
    payload = batch.model_dump(mode="json")
    payload["history_after"] = payload["history_before"]
    with pytest.raises(ValidationError, match="history differs"):
        PoseReferenceBatch.model_validate(payload)
    payload = batch.model_dump(mode="json")
    scene = batch.scenes[0]
    another = next(s for s in LIBRARY.subjects if s != batch.subject)
    replacement = PoseReferenceScene(
        pose=scene.pose, camera=scene.camera,
        subject=another, presentation=scene.presentation,
        prompt=render_pose_reference(
            scene.pose, scene.camera, another, scene.presentation
        ),
    )
    payload["scenes"][0] = replacement.model_dump(mode="json")
    with pytest.raises(ValidationError, match="preserve the batch subject"):
        PoseReferenceBatch.model_validate(payload)
    payload = batch.model_dump(mode="json")
    payload["family_filter"] = "not_the_selected_family"
    with pytest.raises(ValidationError, match="family filter"):
        PoseReferenceBatch.model_validate(payload)


def test_every_selected_environment_realizes_the_exact_supports() -> None:
    batch = sample_pose_references(LIBRARY, seed=3, count=48)
    assert len(batch.report.presentation_counts) > 1
    assert len(batch.report.camera_counts) > 1
    for scene in batch.scenes:
        required = tuple(contact.surface for contact in scene.pose.supports)
        assert presentation_supports(scene.presentation, required)
        assert presentation_accepts_camera(scene.presentation, scene.camera)
        assert scene.subject == batch.subject
        assert scene.camera.framing == "full_body"
        assert "rather than twisting the head toward the lens" in scene.prompt
        realizations = {r.surface: r for r in scene.presentation.supports}
        for surface in required:
            assert realizations[surface].description in scene.prompt
    report = audit_reference_library(LIBRARY)
    expected = sum(
        camera.camera_id in pose.compatible_camera_ids
        and presentation_accepts_camera(presentation, camera)
        and presentation_supports(
            presentation, tuple(contact.surface for contact in pose.supports)
        )
        for pose in LIBRARY.poses
        for camera in LIBRARY.cameras
        for presentation in LIBRARY.presentations
    )
    assert report.compatible_pose_camera_presentation_count == expected
    assert report.subject_count == len(LIBRARY.subjects)
    assert report.visual_validation is False


def test_environment_filter_excludes_unsupported_poses_without_duplicates() -> None:
    presentation = next(
        p for p in LIBRARY.presentations if not presentation_supports(p, ("step",))
    )
    eligible = [
        pose for pose in LIBRARY.poses
        if presentation_supports(
            presentation, tuple(contact.surface for contact in pose.supports)
        ) and any(
            camera.camera_id in pose.compatible_camera_ids
            and presentation_accepts_camera(presentation, camera)
            for camera in LIBRARY.cameras
        )
    ]
    assert 0 < len(eligible) < 48
    batch = sample_pose_references(
        LIBRARY, seed=0, count=len(eligible),
        presentation_id=presentation.presentation_id,
    )
    assert {scene.pose for scene in batch.scenes} == set(eligible)
    assert batch.report.presentation_counts == {
        presentation.presentation_id: len(eligible)
    }
    with pytest.raises(ValueError, match="count must be between"):
        sample_pose_references(
            LIBRARY, seed=0, count=len(eligible) + 1,
            presentation_id=presentation.presentation_id,
        )
    with pytest.raises(ValueError, match="no reference poses fit"):
        sample_pose_references(
            LIBRARY, seed=0, count=1,
            family="step_supported", presentation_id=presentation.presentation_id,
        )


@pytest.mark.parametrize("argument", ["subject_id", "presentation_id"])
def test_unknown_visual_recipe_fails(argument: str) -> None:
    with pytest.raises(ValueError, match="unknown reference"):
        sample_pose_references(LIBRARY, seed=0, count=1, **{argument: "missing"})


def test_reference_renderer_rejects_unsupported_environment_and_space() -> None:
    pose = next(p for p in LIBRARY.poses if p.family == "step_supported")
    camera = next(
        c for c in LIBRARY.cameras if c.camera_id in pose.compatible_camera_ids
    )
    unsupported = next(
        p for p in LIBRARY.presentations if not presentation_supports(p, ("step",))
    )
    with pytest.raises(ValueError, match="lacks a required support"):
        render_pose_reference(pose, camera, LIBRARY.subjects[0], unsupported)
    cramped = next(p for p in LIBRARY.presentations if p.space == "standard")
    long_camera = next(
        c for c in LIBRARY.cameras
        if c.subject_distance == "extended_full_body_clearance"
    )
    pose = next(
        p for p in LIBRARY.poses
        if long_camera.camera_id in p.compatible_camera_ids
        and presentation_supports(cramped, tuple(c.surface for c in p.supports))
    )
    with pytest.raises(ValueError, match="requires more space"):
        render_pose_reference(pose, long_camera, LIBRARY.subjects[0], cramped)


def test_cli_history_is_a_read_only_chain_and_preserves_subject(tmp_path: Path) -> None:
    runner = CliRunner()
    previous = tmp_path / "first.json"
    following = tmp_path / "second.json"
    first = runner.invoke(
        app, ["poses", "sample", "--count", "16", "--seed", "42",
              "--output", str(previous)]
    )
    assert first.exit_code == 0, first.output
    original = previous.read_bytes()
    result = runner.invoke(
        app, ["poses", "sample", "--count", "16", "--seed", "99",
              "--history", str(previous), "--output", str(following)]
    )
    assert result.exit_code == 0, result.output
    prior = PoseReferenceBatch.model_validate_json(original)
    current = PoseReferenceBatch.model_validate_json(following.read_bytes())
    assert current.subject == prior.subject
    assert current.history_before == prior.history_after
    assert current.history_after.selected_scenes == 32
    assert current.report.previously_used_pose_scenes == 0
    assert previous.read_bytes() == original
    repeated = runner.invoke(
        app, ["poses", "sample", "--count", "16", "--seed", "99",
              "--history", str(previous)]
    )
    assert repeated.exit_code == 0, repeated.output
    assert PoseReferenceBatch.model_validate_json(repeated.stdout) == current
    assert previous.read_bytes() == original


def test_cli_subject_and_presentation_filters_are_recorded() -> None:
    subject = LIBRARY.subjects[-1]
    presentation = next(p for p in LIBRARY.presentations if p.space == "extended")
    result = CliRunner().invoke(
        app, ["poses", "sample", "--count", "1", "--subject", subject.subject_id,
              "--presentation", presentation.presentation_id]
    )
    assert result.exit_code == 0, result.output
    batch = PoseReferenceBatch.model_validate_json(result.stdout)
    assert batch.subject == subject
    assert batch.presentation_filter == presentation.presentation_id
    assert batch.scenes[0].presentation == presentation


@pytest.mark.parametrize(
    "content", ['{"schema_version":"1.0"}', "not a JSON snapshot", "{}"]
)
def test_cli_invalid_history_does_not_publish(content: str, tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    output = tmp_path / "not-created.json"
    history.write_text(content, encoding="utf-8")
    result = CliRunner().invoke(
        app, ["poses", "sample", "--history", str(history), "--output", str(output)]
    )
    assert result.exit_code == 1
    assert "current-schema" in result.output
    assert history.read_text(encoding="utf-8") == content
    assert not output.exists()


def test_current_schema_only_for_catalog_and_batch() -> None:
    old_library = LIBRARY.model_dump(mode="json") | {"schema_version": "1.0"}
    with pytest.raises(ValidationError):
        NeutralPoseLibrary.model_validate(old_library)
    old_batch = sample_pose_references(LIBRARY, seed=0, count=1).model_dump()
    old_batch["schema_version"] = "1.0"
    with pytest.raises(ValidationError):
        PoseReferenceBatch.model_validate_json(json.dumps(old_batch))
