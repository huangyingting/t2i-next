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
    ContentLevelRefinement,
    StoryAuthoring,
    StoryStage,
)
from t2i_story_pipeline.prompts import theme_messages


def authored_rules() -> StoryAuthoring:
    return StoryAuthoring.model_validate(
        {
            "level_refinements": {
                level.value: {
                    "shared": [f"Shared palette for {level.value}."],
                    **{
                        stage.value: [f"Only {stage.value} at {level.value}."]
                        for stage in StoryStage
                    },
                }
                for level in ContentLevel
            },
            **{
                stage.value: {
                    "common": [f"Common {stage.value} instruction."],
                }
                for stage in StoryStage
            },
        }
    )


@pytest.mark.parametrize("level", list(ContentLevel))
def test_selected_refinements_have_one_ordered_owner(level: ContentLevel) -> None:
    authoring = authored_rules()
    assert isinstance(authoring.level_refinements[level], ContentLevelRefinement)
    assert "content_levels" not in authoring.model_dump_json()
    for stage in StoryStage:
        assert authoring.selected(stage, level) == (
            f"Common {stage.value} instruction.",
            f"Shared palette for {level.value}.",
            f"Only {stage.value} at {level.value}.",
        )


def test_selected_refinements_preserve_order_within_each_owner() -> None:
    authoring = StoryAuthoring.model_validate(
        {
            **{
                stage: {"common": [f"{stage} common zeta.", f"{stage} common alpha."]}
                for stage in ("themes", "frames")
            },
            "level_refinements": {
                "aesthetic": {
                    "shared": ["Shared zeta.", "Shared alpha."],
                    **{
                        stage: [f"{stage} specific zeta.", f"{stage} specific alpha."]
                        for stage in ("themes", "frames")
                    },
                }
            },
        }
    )
    for stage in StoryStage:
        assert authoring.selected(stage, ContentLevel.AESTHETIC) == (
            f"{stage.value} common zeta.",
            f"{stage.value} common alpha.",
            "Shared zeta.",
            "Shared alpha.",
            f"{stage.value} specific zeta.",
            f"{stage.value} specific alpha.",
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
        assert rules.count(getattr(core, stage.value)[-1]) == 1
        assert rules.index(getattr(core, stage.value)[-1]) > max(
            rules.index(rule) for rule in selected
        )
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
                    "level_refinements": {
                        level.value: {
                            "shared": ["Use a coordinated palette for both views."]
                        }
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
    content["authoring"]["level_refinements"][level.value]["shared"] = [
        "Changed palette."
    ]
    source["content"] = json.dumps(content)
    with pytest.raises(ValidationError, match="metadata differs"):
        ResolvedStoryInput.model_validate(data)


@pytest.mark.parametrize(
    ("authoring", "error"),
    [
        (
            {"level_refinements": {"aesthetic": {"shared": ["Repeated."] * 2}}},
            "shared refinements must not repeat",
        ),
        (
            {"level_refinements": {"unknown": {"shared": ["Unknown grade."]}}},
            "aesthetic.*erotic.*hardcore",
        ),
        (
            {"level_refinements": {"aesthetic": {"shared": ["First\nSecond"]}}},
            "不能包含换行",
        ),
        ({"level_refinements": ["Not a mapping."]}, "dictionary"),
        (
            {"level_refinements": {"aesthetic": {}}, "replace_system": True},
            "Extra inputs",
        ),
        (
            {
                "level_refinements": {
                    "aesthetic": {"themes": ["Repeated."], "frames": ["Repeated."]}
                }
            },
            "duplicate Theme/Frame",
        ),
        (
            {
                "level_refinements": {
                    "aesthetic": {"shared": ["Repeated."], "themes": ["Repeated."]}
                }
            },
            "shared refinements repeat themes",
        ),
        (
            {
                "level_refinements": {"aesthetic": {"shared": ["Repeated."]}},
                "frames": {"common": ["Repeated."]},
            },
            "refinements repeat frames common",
        ),
        (
            {
                "level_refinements": {"aesthetic": {"frames": ["Repeated."]}},
                "frames": {"common": ["Repeated."]},
            },
            "refinements repeat frames common",
        ),
        (
            {"level_refinements": {"aesthetic": {"frames": ["Repeated."] * 2}}},
            "frames refinements must not repeat",
        ),
        (
            {"level_refinements": {"aesthetic": {"themes": ["Repeated."] * 2}}},
            "themes refinements must not repeat",
        ),
        ({"level_refinements": {"aesthetic": []}}, "dictionary"),
        (
            {"level_refinements": {"aesthetic": {"common": ["Wrong owner."]}}},
            "Extra inputs",
        ),
    ],
)
def test_refinements_reject_ambiguous_ownership_and_invalid_shapes(
    authoring: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValidationError, match=error):
        StoryAuthoring.model_validate(authoring)


@pytest.mark.parametrize("owner", ("shared", "themes", "frames"))
@pytest.mark.parametrize("rules", ({}, {"aesthetic": ["Obsolete rule."]}))
@pytest.mark.parametrize("include_current", (False, True))
def test_former_maps_are_rejected_even_empty_or_alongside_current_shape(
    owner: str, rules: dict[str, list[str]], include_current: bool
) -> None:
    old = {"content_levels": rules}
    value: dict[str, object] = old if owner == "shared" else {owner: old}
    if include_current:
        value["level_refinements"] = {"aesthetic": {"shared": ["Current rule."]}}
    with pytest.raises(ValidationError) as caught:
        StoryAuthoring.model_validate(value)
    location = ("content_levels",) if owner == "shared" else (owner, "content_levels")
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == location
        for error in caught.value.errors()
    )


def test_cross_stage_common_rules_keep_their_stage_ownership() -> None:
    authoring = StoryAuthoring.model_validate(
        {
            "themes": {"common": ["Common palette."]},
            "frames": {"common": ["Common palette."]},
            "level_refinements": {
                "aesthetic": {
                    "shared": ["Shared layout."],
                    "themes": ["Plan composition."],
                    "frames": ["Render composition."],
                }
            },
        }
    )
    for stage, specific in (
        (StoryStage.THEMES, "Plan composition."),
        (StoryStage.FRAMES, "Render composition."),
    ):
        assert authoring.selected(stage, ContentLevel.AESTHETIC) == (
            "Common palette.",
            "Shared layout.",
            specific,
        )


def test_rule_shared_across_levels_has_no_cross_stage_copies() -> None:
    authoring = StoryAuthoring.model_validate(
        {
            "level_refinements": {
                "aesthetic": {"shared": ["Keep the wardrobe palette."]},
                "erotic": {"shared": ["Keep the wardrobe palette."]},
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


@pytest.mark.parametrize(
    "invalid", (None, "duplicate", "old_shared", "old_themes", "old_frames")
)
def test_offline_explain_selects_shared_rules_and_rejects_duplicate_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str | None
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
    }
    if invalid == "duplicate":
        source["authoring"]["level_refinements"]["erotic"]["frames"].append(
            "Shared palette for erotic."
        )
    elif invalid == "old_shared":
        source["authoring"]["content_levels"] = {}
    elif invalid in ("old_themes", "old_frames"):
        source["authoring"][invalid.removeprefix("old_")]["content_levels"] = {}
    path = tmp_path / "neutral.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "explain",
            "--input",
            str(path),
            "--content-level",
            "erotic",
            "--theme-quality-mode",
            "off",
            "--frame-quality-mode",
            "off",
        ],
    )
    payload = json.loads(result.stdout)
    assert result.exit_code == (2 if invalid else 0), result.stdout
    assert payload["status"] == ("invalid" if invalid else "valid")
    if invalid == "duplicate":
        assert "shared refinements repeat frames instructions" in payload["error"]
    elif invalid:
        assert "Extra inputs are not permitted" in payload["error"]
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
