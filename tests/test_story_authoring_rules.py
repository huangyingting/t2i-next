from __future__ import annotations

from pathlib import Path

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.inputs import load_story_document, resolve_story_input
from t2i_story_pipeline.models import ContentLevel, StoryAuthoring, StoryStage
from tests.story_factories import make_story_input, make_story_request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_story_rules_compile_only_the_selected_content_level() -> None:
    request = make_story_request(content_level=ContentLevel.EROTIC)

    rules = resolve_story_rules(request)

    for stage in StoryStage:
        text = rules.text_for(stage)
        assert "本次使用 极致情色级（erotic）" in text
        assert "本次使用 美学级（aesthetic）" not in text
        assert "本次使用 赤裸裸的性描写（hardcore）" not in text


def test_story_content_level_rules_match_prompt_pipeline() -> None:
    prompt_rules = (
        REPOSITORY_ROOT
        / "src"
        / "t2i_prompt_pipeline"
        / "rule_packs"
        / "system"
        / "content_levels"
    )
    story_rules = (
        REPOSITORY_ROOT
        / "src"
        / "t2i_story_pipeline"
        / "rule_packs"
        / "system"
        / "content_levels"
    )

    for filename in ("aesthetic.rules", "erotic.rules", "hardcore.rules"):
        assert (story_rules / filename).read_text(encoding="utf-8") == (
            prompt_rules / filename
        ).read_text(encoding="utf-8")


def test_story_rules_append_selected_authoring_in_stage_order() -> None:
    authoring = StoryAuthoring.model_validate(
        {
            stage: {
                "common": ["Shared authored rule.", f"User {stage} rule."],
                "content_levels": {
                    "aesthetic": ["User aesthetic rule."],
                    "erotic": ["Unselected erotic rule."],
                },
            }
            for stage in ("themes", "frames")
        }
    )
    request = make_story_request(content_level=ContentLevel.AESTHETIC)

    rules = resolve_story_rules(request, authoring=authoring)

    assert rules.themes[-4:-1] == (
        "Shared authored rule.",
        "User themes rule.",
        "User aesthetic rule.",
    )
    assert rules.frames[-4:-1] == (
        "Shared authored rule.",
        "User frames rule.",
        "User aesthetic rule.",
    )
    assert "Write every natural-language output field" in rules.themes[-1]
    assert "Write every natural-language output field" in rules.frames[-1]
    assert "Unselected erotic rule." not in rules.themes + rules.frames


def test_core_is_universal_and_named_policy_owns_nationality_defaults() -> None:
    request = make_story_request()
    core = resolve_story_rules(request)
    resolved = make_story_input(request)
    policy = next(source for source in resolved.sources if source.kind == "policy")
    assert policy.id == "standard-story"
    for stage in StoryStage:
        assert "默认为中国籍" not in core.text_for(stage)
        assert "场景国家默认为中国" not in core.text_for(stage)
        assert "默认为中国籍" in resolved.rules.text_for(stage)
        assert "场景国家默认为中国" in resolved.rules.text_for(stage)


def test_story_rules_fingerprint_changes_with_authored_rules() -> None:
    request = make_story_request()
    builtin = resolve_story_rules(request)
    authoring = StoryAuthoring.model_validate(
        {"themes": {"common": ["Project-specific story rule."]}}
    )

    customized = resolve_story_rules(request, authoring=authoring)

    assert customized.fingerprint() != builtin.fingerprint()


def test_specialized_story_inputs_own_their_presentation_contracts() -> None:
    required_contracts = {
        "creative.yaml": (
            "微缩成年人物",
            "缩略图",
            "明亮",
            "六区域广告概念板",
        ),
        "multi-view.yaml": (
            "A full-bleed [two/three/four]-view hard-cut tiled composition",
        ),
        "dress.yaml": (
            "恰好包含六个互不重叠的视图区",
        ),
        "edo-warai-e.yaml": (
            "平坦、分隔的色块",
            "中性外部词语",
            "实体搭建和真人表演",
        ),
        "ming-gongbi-mixi-tu.yaml": (
            "游丝般细腻的线条",
            "三矾九染",
            "茶褐色氧化",
        ),
    }

    for filename, phrases in required_contracts.items():
        document = load_story_document(
            REPOSITORY_ROOT / "story-inputs" / "recipes" / filename
        )
        resolved = resolve_story_input(document)
        story = "\n".join(
            (document.description, *resolved.rules.themes, *resolved.rules.frames)
        )
        assert all(phrase in story for phrase in phrases), (
            filename, [phrase for phrase in phrases if phrase not in story]
        )
        if filename == "creative.yaml":
            layout = next(
                module for module in resolved.modules
                if module.kind == "layout_multiview"
            )
            assert layout.parameters.layout == "grid"
            assert (layout.parameters.rows, layout.parameters.columns) == (3, 2)
