"""Bounded catalog cycles and retry-stable per-Frame assignments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.inputs import (
    CatalogDocument,
    InputOverrides,
    ResolvedStoryInput,
    StoryDocument,
    resolve_story_input,
)
from t2i_story_pipeline.inputs.schema import FrameAssignment
from t2i_story_pipeline.models import NarrativeFrame, NarrativeTheme, StoryStage
from t2i_story_pipeline.prompts import frame_messages


def write_catalog(root: Path, period: int) -> Path:
    directory = root / "_catalogs"
    directory.mkdir()
    path = directory / "neutral-cycle.yaml"
    entries = [
        {
            "id": f"slot-{index}",
            "themes": [f"Theme-only fact {index}."],
            "frames": [f"Frame-only fact {index}."],
            "frame_assignment": {
                "frames_per_theme": 2,
                "slots": [
                    {"frame_id": "F01", "rules": [f"Front view {index}."]},
                    {"frame_id": "F02", "rules": [f"Rear view {index}."]},
                ],
            },
        }
        for index in range(period)
    ]
    path.write_text(
        yaml.safe_dump(
            {
                "id": "neutral-cycle",
                "entries": entries,
                "slots": [entry["id"] for entry in entries],
            }
        ),
        encoding="utf-8",
    )
    return path


def cycle_document(count: int, frames: int = 2) -> StoryDocument:
    return StoryDocument.model_validate(
        {
            "description": "A neutral studio portrait.",
            "generation": {"theme_count": count, "frames_per_theme": frames},
            "allocation": {"type": "cyclic_slots", "catalog": "neutral-cycle"},
        }
    )


@pytest.mark.parametrize("period", [3, 4, 12, 30])
@pytest.mark.parametrize("count", [1, 3, 10, 31, 100])
def test_cycles_use_global_indices_without_catalog_exhaustion(
    tmp_path: Path, period: int, count: int
) -> None:
    write_catalog(tmp_path, period)
    document = cycle_document(count)
    resolved = resolve_story_input(document, asset_root=tmp_path)
    assert [plan.entry.id for plan in resolved.plans] == [
        f"slot-{index % period}" for index in range(count)
    ]
    rebatched = resolve_story_input(
        document, InputOverrides(theme_batch_size=1), asset_root=tmp_path
    )
    assert rebatched.plans == resolved.plans


def test_cycle_context_and_frame_retry_survive_asset_removal(tmp_path: Path) -> None:
    path = write_catalog(tmp_path, 30)
    resolved = resolve_story_input(cycle_document(100), asset_root=tmp_path)
    frozen = resolved.model_dump_json()
    path.unlink()
    restored = ResolvedStoryInput.model_validate_json(frozen)
    assert restored.fingerprint() == resolved.fingerprint()
    theme_context = restored.context_for(StoryStage.THEMES, ["T031", "T030"])
    assert [plan["entry"]["id"] for plan in theme_context["plans"]] == [
        "slot-0",
        "slot-29",
    ]
    assert "Frame-only" not in json.dumps(theme_context)
    assert "Front view" not in json.dumps(theme_context)
    assert "Rear view" not in json.dumps(theme_context)
    full = restored.context_for(StoryStage.FRAMES, ["T031"])
    retry = restored.context_for(StoryStage.FRAMES, ["T031"], frame_ids=["F02"])
    assert full["plans"][0]["frame_slots"] == [
        {"frame_id": "F01", "rules": ["Front view 0."]},
        {"frame_id": "F02", "rules": ["Rear view 0."]},
    ]
    assert retry["plans"][0]["frame_slots"] == [
        {"frame_id": "F02", "rules": ["Rear view 0."]}
    ]
    assert "Front view" not in json.dumps(retry)
    assert "Theme-only" not in json.dumps(retry)
    data = restored.model_dump(mode="json")
    data["plans"][30]["entry"]["frame_assignment"]["slots"][1]["rules"] = [
        "An altered camera."
    ]
    with pytest.raises(ValidationError, match="frozen allocation"):
        ResolvedStoryInput.model_validate(data)


@pytest.mark.parametrize("frames", [1, 3, 4, 5, 6])
def test_frame_assignment_applies_only_to_declared_frame_count(
    tmp_path: Path, frames: int
) -> None:
    write_catalog(tmp_path, 12)
    resolved = resolve_story_input(cycle_document(1, frames), asset_root=tmp_path)
    context = resolved.context_for(StoryStage.FRAMES, ["T001"])
    assert context["plans"][0]["frame_slots"] == []
    assert "Front view" not in json.dumps(context)
    assert "Rear view" not in json.dumps(context)
    assert context["plans"][0]["entry"]["rules"] == ["Frame-only fact 0."]


def test_frame_prompt_keeps_retry_slot_identity(tmp_path: Path) -> None:
    write_catalog(tmp_path, 3)
    resolved = resolve_story_input(cycle_document(1), asset_root=tmp_path)
    theme = NarrativeTheme(
        theme_id="T001",
        title="Studio portrait",
        premise="An adult stands in a studio.",
        style="Soft studio lighting.",
    )
    accepted = NarrativeFrame(frame_id="F01", prose="The completed front view.")
    payload = json.loads(
        frame_messages(
            resolved,
            theme,
            requested_frame_ids=["F02"],
            accepted_frames=[accepted],
        )[1].content
    )
    assert payload["requested_frame_slots"] == ["F02"]
    assert payload["input_context"]["plans"][0]["frame_slots"] == [
        {"frame_id": "F02", "rules": ["Rear view 0."]}
    ]
    assert payload["accepted_frames"] == [accepted.model_dump(mode="json")]
    assert "Front view 0." not in json.dumps(payload["input_context"])


@pytest.mark.parametrize(
    ("stage", "frame_ids"),
    [
        (StoryStage.THEMES, ["F01"]),
        (StoryStage.FRAMES, []),
        (StoryStage.FRAMES, ["F01", "F01"]),
        (StoryStage.FRAMES, ["F03"]),
        (StoryStage.FRAMES, ["F00"]),
        (StoryStage.FRAMES, ["not-a-frame"]),
    ],
)
def test_invalid_frame_selections_fail_explicitly(
    tmp_path: Path, stage: StoryStage, frame_ids: list[str]
) -> None:
    write_catalog(tmp_path, 3)
    resolved = resolve_story_input(cycle_document(1), asset_root=tmp_path)
    with pytest.raises(StoryConfigurationError):
        resolved.context_for(stage, ["T001"], frame_ids=frame_ids)


@pytest.mark.parametrize(
    "assignment",
    [
        {"frames_per_theme": 0, "slots": []},
        {"frames_per_theme": 7, "slots": []},
        {"frames_per_theme": True, "slots": []},
        {"frames_per_theme": 1, "slots": []},
        {
            "frames_per_theme": 2,
            "slots": [{"frame_id": "F01", "rules": ["One view."]}],
        },
        {
            "frames_per_theme": 2,
            "slots": [{"frame_id": "F01", "rules": ["One view."]}] * 2,
        },
        {
            "frames_per_theme": 1,
            "slots": [{"frame_id": "F02", "rules": ["Wrong slot."]}],
        },
        {
            "frames_per_theme": 1,
            "slots": [{"frame_id": "F01", "rules": []}],
        },
    ],
)
def test_frame_assignments_are_bounded_complete_and_nonempty(
    assignment: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        FrameAssignment.model_validate(assignment)


def test_cycle_requires_explicit_slot_order(tmp_path: Path) -> None:
    path = write_catalog(tmp_path, 3)
    data = yaml.safe_load(path.read_text())
    del data["slots"]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(StoryConfigurationError, match="explicit slot order"):
        resolve_story_input(cycle_document(1), asset_root=tmp_path)


def test_superseded_axes_and_expressions_are_not_an_alternative_schema() -> None:
    with pytest.raises(ValidationError):
        StoryDocument.model_validate(
            {
                "description": "A neutral portrait.",
                "allocation": {"type": "catalog_axes", "catalog": "neutral"},
            }
        )
    with pytest.raises(ValidationError):
        CatalogDocument.model_validate(
            {"id": "neutral", "entries": [{"id": "one"}], "axes": []}
        )
