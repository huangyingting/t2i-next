"""Single-owner level refinements preserve the selected system contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.cli import app
from t2i_story_pipeline.inputs import (
    InputOverrides,
    ResolvedStoryInput,
    StoryDocument,
    resolve_story_input,
)
from t2i_story_pipeline.models import (
    ContentLevel,
    StoryAuthoring,
    StoryStage,
)
from t2i_story_pipeline.prompts import theme_messages


def authored_rules() -> StoryAuthoring:
    return StoryAuthoring.model_validate(
        {
            "content_levels": {
                level.value: [f"Shared palette for {level.value}."]
                for level in ContentLevel
            },
            **{
                stage.value: {
                    "common": [f"Common {stage.value} instruction."],
                    "content_levels": {
                        level.value: [f"Only {stage.value} at {level.value}."]
                        for level in ContentLevel
                    },
                }
                for stage in StoryStage
            },
        }
    )


@pytest.mark.parametrize("level", list(ContentLevel))
def test_selected_refinements_have_one_ordered_owner(level: ContentLevel) -> None:
    authoring = authored_rules()
    for stage in StoryStage:
        assert authoring.selected(stage, level) == (
            f"Common {stage.value} instruction.",
            f"Shared palette for {level.value}.",
            f"Only {stage.value} at {level.value}.",
        )


@pytest.mark.parametrize("level", list(ContentLevel))
def test_shared_refinements_never_replace_the_system_level(
    level: ContentLevel,
) -> None:
    document = StoryDocument(
        description="A neutral portrait.", authoring=authored_rules()
    )
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    core = resolve_story_rules(resolved.request)
    source = next(source for source in resolved.sources if source.kind == "document")
    for stage in StoryStage:
        selected = document.authoring.selected(stage, level)
        rules = getattr(resolved.rules, stage.value)
        assert (
            rules[: len(getattr(core, stage.value)) - 1]
            == getattr(core, stage.value)[:-1]
        )
        assert rules[-1] == getattr(core, stage.value)[-1]
        assert getattr(source, stage.value) == selected
        for rule in selected:
            assert rules.count(rule) == 1
        other_stage = (
            StoryStage.FRAMES if stage == StoryStage.THEMES else StoryStage.THEMES
        )
        for candidate in ContentLevel:
            assert f"Only {other_stage.value} at {candidate.value}." not in rules
            if candidate != level:
                assert f"Shared palette for {candidate.value}." not in rules
                assert f"Only {stage.value} at {candidate.value}." not in rules
        assert any("cannot replace, redefine, or weaken" in rule for rule in rules)
    messages = theme_messages(resolved, count=1, existing_themes=[])
    assert "authoring" not in json.loads(messages[1].content)
    for candidate in ContentLevel:
        assert (f"Shared palette for {candidate.value}." in messages[0].content) == (
            candidate == level
        )


@pytest.mark.parametrize("level", list(ContentLevel))
def test_module_shared_refinement_controls_stage_projection_and_frozen_replay(
    tmp_path: Path, level: ContentLevel
) -> None:
    directory = tmp_path / "_modules"
    directory.mkdir()
    path = directory / "neutral-layout.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": "neutral-layout",
                "kind": "layout_multiview",
                "authoring": {
                    "content_levels": {
                        level.value: ["Use a coordinated palette for both views."]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    document = StoryDocument.model_validate(
        {
            "description": "A neutral portrait.",
            "modules": [
                {
                    "id": "neutral-layout",
                    "parameters": {"layout": "grid", "rows": 1, "columns": 2},
                }
            ],
        }
    )
    resolved = resolve_story_input(
        document, InputOverrides(content_level=level), asset_root=tmp_path
    )
    for other_level in ContentLevel:
        inactive = resolve_story_input(
            document, InputOverrides(content_level=other_level), asset_root=tmp_path
        )
        for stage in StoryStage:
            context = inactive.context_for(stage, ["T001"])
            assert bool(context["modules"]) == (other_level == level)
    frozen = resolved.model_dump_json()
    path.unlink()
    restored = ResolvedStoryInput.model_validate_json(frozen)
    assert restored.fingerprint() == resolved.fingerprint()
    for stage in StoryStage:
        assert restored.context_for(stage, ["T001"]) == resolved.context_for(
            stage, ["T001"]
        )
        assert (
            getattr(restored.rules, stage.value).count(
                "Use a coordinated palette for both views."
            )
            == 1
        )
    data = json.loads(frozen)
    source = next(item for item in data["sources"] if item["kind"] == "module")
    content = json.loads(source["content"])
    content["authoring"]["content_levels"][level.value] = ["Changed palette."]
    source["content"] = json.dumps(content)
    with pytest.raises(ValidationError, match="metadata differs"):
        ResolvedStoryInput.model_validate(data)


@pytest.mark.parametrize(
    "authoring",
    [
        {"content_levels": {"aesthetic": ["Repeated.", "Repeated."]}},
        {"content_levels": {"unknown": ["Unknown grade."]}},
        {"content_levels": {"aesthetic": ["First\nSecond"]}},
        {"content_levels": ["Not a mapping."]},
        {"content_levels": {"aesthetic": []}, "replace_system": True},
        {
            "themes": {"content_levels": {"aesthetic": ["Repeated."]}},
            "frames": {"content_levels": {"aesthetic": ["Repeated."]}},
        },
        {
            "content_levels": {"aesthetic": ["Repeated."]},
            "themes": {"content_levels": {"aesthetic": ["Repeated."]}},
        },
        {
            "content_levels": {"aesthetic": ["Repeated."]},
            "frames": {"common": ["Repeated."]},
        },
        {
            "frames": {
                "common": ["Repeated."],
                "content_levels": {"aesthetic": ["Repeated."]},
            }
        },
        {"frames": {"content_levels": {"aesthetic": ["Repeated.", "Repeated."]}}},
    ],
)
def test_refinements_reject_ambiguous_ownership_and_invalid_shapes(
    authoring: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        StoryAuthoring.model_validate(authoring)


def test_rule_shared_across_levels_has_no_cross_stage_copies() -> None:
    authoring = StoryAuthoring.model_validate(
        {
            "content_levels": {
                "aesthetic": ["Keep the wardrobe palette."],
                "erotic": ["Keep the wardrobe palette."],
            }
        }
    )
    for stage in StoryStage:
        assert authoring.selected(stage, ContentLevel.AESTHETIC) == (
            "Keep the wardrobe palette.",
        )
        assert authoring.selected(stage, ContentLevel.EROTIC) == (
            "Keep the wardrobe palette.",
        )
        assert authoring.selected(stage, ContentLevel.HARDCORE) == ()


@pytest.mark.parametrize("duplicate", [False, True])
def test_offline_explain_selects_shared_rules_and_rejects_duplicate_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, duplicate: bool
) -> None:
    def unexpected_provider_load() -> None:
        pytest.fail("Offline explanation must not load provider settings.")

    monkeypatch.setattr(
        "t2i_story_pipeline.cli.load_story_provider_settings",
        unexpected_provider_load,
    )
    monkeypatch.chdir(tmp_path)
    source = {
        "id": "neutral",
        "description": "A neutral studio portrait.",
        "authoring": authored_rules().model_dump(mode="json"),
        "validation": {"themes": {"mode": "off"}, "frames": {"mode": "off"}},
    }
    if duplicate:
        source["authoring"]["frames"]["content_levels"]["erotic"].append(
            "Shared palette for erotic."
        )
    path = tmp_path / "neutral.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")
    result = CliRunner().invoke(
        app, ["explain", "--input", str(path), "--content-level", "erotic"]
    )
    payload = json.loads(result.stdout)
    assert result.exit_code == (2 if duplicate else 0), result.stdout
    assert payload["status"] == ("invalid" if duplicate else "valid")
    if duplicate:
        assert (
            "shared erotic refinements repeat frames instructions" in payload["error"]
        )
    else:
        assert payload["input"]["request"]["content_level"] == "erotic"
        for stage in StoryStage:
            rules = payload["input"]["rules"][stage.value]
            assert rules.count("Shared palette for erotic.") == 1
            assert "Shared palette for aesthetic." not in rules
            assert "Shared palette for hardcore." not in rules
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "prompts").exists()


@pytest.mark.parametrize(
    ("stage", "level"),
    [("unknown", ContentLevel.AESTHETIC), (StoryStage.THEMES, "unknown")],
)
def test_unknown_selection_does_not_silently_fall_back(
    stage: StoryStage, level: ContentLevel
) -> None:
    with pytest.raises(ValueError):
        authored_rules().selected(stage, level)
