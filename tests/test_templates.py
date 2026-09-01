from __future__ import annotations

import json

from t2i_prompt_pipeline.models import ContentLevel, FrameMode, OutputLanguage
from t2i_prompt_pipeline.templates import (
    foundation_messages,
    frame_messages,
    theme_batch_messages,
)
from tests.factories import (
    make_foundation,
    make_frame_batch,
    make_rules,
    make_spec,
    make_themes,
)


def test_theme_request_contains_stable_facts_and_stage_rules() -> None:
    spec = make_spec(
        brief="两名成年人从电梯、走廊到房间重逢",
        theme_count=2,
        frames_per_theme=5,
        female_count=1,
        male_count=1,
    )
    foundation = make_foundation(spec)

    messages = theme_batch_messages(
        spec,
        foundation,
        ("T01", "T02"),
        make_rules(spec),
    )
    request = json.loads(messages[1].content)
    instructions = messages[0].content

    assert request["content_level"] == "aesthetic"
    assert request["output_language"] == "chinese"
    assert request["theme_ids"] == ["T01", "T02"]
    assert request["required_route_points"] == ["电梯", "走廊", "房间"]
    assert request["character_ids"]["T02"] == ["T02-C01", "T02-C02"]
    assert request["style_constraints"] == (
        foundation.style_constraints.model_dump(mode="json")
    )
    assert request["cast_plan"] == foundation.cast_plan.model_dump(mode="json")

    assert "Theme 只拥有 title、跨 Frame 稳定的 scene" in instructions
    assert "人物位置、表情、动作、接触、遮挡和具体镜头属于 Frame" in (
        instructions
    )
    assert "required_route_points" in instructions
    assert "摄影或摄像实拍方案" in instructions
    assert "不同的完整方案" in instructions
    assert "Character.label 是最终显示名" in instructions
    assert "本次使用 美学级（aesthetic）" in instructions


def test_frame_request_contains_theme_context_and_stage_rules() -> None:
    spec = make_spec(frames_per_theme=3)
    spec.content_level = ContentLevel.EROTIC
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]
    existing = make_frame_batch(spec, theme).frames[0]

    messages = frame_messages(
        spec,
        foundation.cast_plan,
        theme,
        ("T01-F02", "T01-F03"),
        make_rules(spec),
        (existing,),
    )
    request = json.loads(messages[1].content)
    instructions = messages[0].content

    assert request["brief"] == spec.brief
    assert request["theme"] == theme.model_dump(mode="json")
    assert request["cast_plan"] == foundation.cast_plan.model_dump(mode="json")
    assert request["content_level"] == "erotic"
    assert request["output_language"] == "chinese"
    assert request["frame_ids"] == ["T01-F02", "T01-F03"]
    assert request["existing_frames"][0]["frame_id"] == "T01-F01"
    assert request["available_character_ids"] == ["T01-C01"]
    assert "style_anchor" not in request
    assert "style_constraints" not in request
    assert "variation_range" not in request
    assert "character_ids_per_frame" not in request
    assert "variation_plan" not in request

    assert "Frame 只拥有 camera、当前可见人物" in instructions
    assert "同一三维空间" in instructions
    assert "完整可见因果链" in instructions
    assert "核心道具已有来源" in instructions
    assert "本次使用 极致情色级（erotic）" in instructions
    assert "当前画面直接呈现" in instructions


def test_variation_frame_request_contains_plan_and_exclusive_rules() -> None:
    spec = make_spec(frames_per_theme=5)
    spec.frame_mode = FrameMode.VARIATIONS
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]

    messages = frame_messages(
        spec,
        foundation.cast_plan,
        theme,
        tuple(f"T01-F{index:02d}" for index in range(1, 6)),
        make_rules(spec),
        (),
    )
    request = json.loads(messages[1].content)
    instructions = messages[0].content

    assert request["variation_plan"]["T01-F01"].startswith("空间关系")
    assert request["variation_plan"]["T01-F03"].startswith("锚点细节")
    assert "互不依赖的完整候选画面" in instructions
    assert "request.variation_plan" in instructions
    assert "任意两帧至少在三项上实质不同" in instructions
    assert "完整可见因果链" not in instructions
    assert "终帧" not in instructions


def test_foundation_request_contains_only_foundation_inputs() -> None:
    spec = make_spec(theme_count=100)
    messages = foundation_messages(spec, make_rules(spec))
    request = json.loads(messages[1].content)
    instructions = messages[0].content

    assert request == {
        "brief": "两名成年人在室内交谈",
        "cast_constraints": {"female_count": 1, "male_count": 0},
        "cast_default": {"member_count": 1, "gender": "女性"},
        "content_level": "aesthetic",
        "output_language": "chinese",
    }
    assert "CastPlan.members 按人物首次出现顺序展开" in instructions
    assert "CastPlan.members" in instructions
    assert "StyleConstraints.required_phrases" in instructions
    assert "brief 中连续、逐字一致的原文片段" in instructions
    assert "camera.shot" not in instructions


def test_foundation_never_requests_implicit_creator_mapping() -> None:
    content_spec = make_spec()
    style_spec = make_spec()
    style_spec.brief = "对称构图，低饱和配色，硬质侧光与大面积留白"

    content_request = json.loads(
        foundation_messages(content_spec, make_rules(content_spec))[1].content
    )
    style_request = json.loads(
        foundation_messages(style_spec, make_rules(style_spec))[1].content
    )

    assert "implicit_creator_mapping_allowed" not in content_request
    assert "implicit_creator_mapping_allowed" not in style_request


def test_validation_context_is_structured_in_retry_requests() -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]
    rules = make_rules(spec)

    theme_request = json.loads(
        theme_batch_messages(
            spec,
            foundation,
            ("T02",),
            rules,
            validation_issues=("T02：缺少路线点：走廊",),
            existing_themes=(theme,),
        )[1].content
    )
    frame_request = json.loads(
        frame_messages(
            spec,
            foundation.cast_plan,
            theme,
            ("T01-F01",),
            rules,
            (),
            validation_issues=("T01-F01：包含不可见声音",),
        )[1].content
    )

    assert theme_request["validation_issues"] == ["T02：缺少路线点：走廊"]
    assert theme_request["existing_themes"][0]["theme_id"] == "T01"
    assert frame_request["validation_issues"] == ["T01-F01：包含不可见声音"]


def test_english_language_requirement_is_sent_to_every_stage() -> None:
    spec = make_spec(
        female_count=1,
        male_count=1,
        output_language=OutputLanguage.ENGLISH,
    )
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    rules = make_rules(spec)
    stage_messages = (
        foundation_messages(spec, rules),
        theme_batch_messages(spec, foundation, ("T01",), rules),
        frame_messages(
            spec,
            foundation.cast_plan,
            theme,
            ("T01-F01",),
            rules,
            (frame,),
        ),
    )

    for messages in stage_messages:
        request = json.loads(messages[1].content)
        assert request["output_language"] == "english"
        assert "自然、流利、简练的英文" in messages[0].content
        assert "不得夹杂中文或其他语言" in messages[0].content
    assert "Woman 1、Woman 2" in stage_messages[1][0].content
    assert "Man 1、Man 2" in stage_messages[1][0].content