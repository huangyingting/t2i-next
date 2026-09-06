from __future__ import annotations

import pytest

from t2i_prompt_pipeline.contracts import (
    frame_ids,
    normalize_foundation,
    normalize_frame,
    normalize_theme,
    theme_ids,
)
from t2i_prompt_pipeline.errors import GenerationContractError
from t2i_prompt_pipeline.models import CharacterFraming, OutputLanguage
from tests.factories import (
    make_foundation,
    make_frame_batch,
    make_spec,
    make_themes,
)


def normalize_test_theme(spec, theme):
    foundation = make_foundation(spec)
    return normalize_theme(
        spec,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )


def test_foundation_rejects_style_constraint_not_copied_from_brief() -> None:
    spec = make_spec(brief="韦斯安德森风格的有故事性的互动")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = ["一九六零年代"]

    with pytest.raises(GenerationContractError, match="不是 brief 原文"):
        normalize_foundation(spec, foundation)


def test_foundation_rejects_omitted_explicit_director_style() -> None:
    phrase = "贝纳尔多·贝托鲁奇（Bernardo Bertolucci）导演风格"
    spec = make_spec(brief=f"{phrase}的富有故事性的互动")

    with pytest.raises(GenerationContractError, match="遗漏 brief 明示风格"):
        normalize_foundation(spec, make_foundation(spec))


def test_theme_accepts_complete_explicit_brief_route() -> None:
    spec = make_spec(brief="两名成年人从电梯、走廊到房间展开重逢故事")
    theme = make_themes(spec)[0]
    theme.setting.location = "雨夜旧酒店的电梯经走廊连接房间"

    assert normalize_test_theme(spec, theme).setting == theme.setting


def test_theme_requires_every_explicit_brief_route_point() -> None:
    spec = make_spec(brief="两名成年人从电梯、走廊到房间展开重逢故事")
    theme = make_themes(spec)[0]
    theme.setting.location = "雨夜旧酒店房间"

    with pytest.raises(
        GenerationContractError,
        match=r"Theme\.setting 缺少 brief 路线地点.*电梯.*走廊",
    ):
        normalize_test_theme(spec, theme)


def test_theme_rejects_internal_schema_term_leakage() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    theme.setting.location = "required_route_points: 摄影棚中央"

    with pytest.raises(GenerationContractError, match="泄漏内部字段名"):
        normalize_test_theme(spec, theme)


def test_theme_reorders_characters_by_id() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    theme.characters.reverse()

    normalized = normalize_test_theme(spec, theme)

    assert [item.character_id for item in normalized.characters] == [
        "T01-C01",
        "T01-C02",
    ]


def test_theme_rejects_missing_character() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    theme.characters.pop()

    with pytest.raises(GenerationContractError, match="人物 ID 不完整或重复"):
        normalize_test_theme(spec, theme)


def test_frame_requires_every_theme_character() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters = [frame.characters[1]]

    with pytest.raises(
        GenerationContractError,
        match="每个 Frame 必须包含 Theme 全部人物",
    ):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


@pytest.mark.parametrize(
    ("facing", "message"),
    (
        ("toward pair", "必须直接写人物 ID 或镜头"),
        ("toward T99-C01", "引用未知人物 ID"),
    ),
)
def test_frame_requires_explicit_facing_target(
    facing: str,
    message: str,
) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].facing = facing

    with pytest.raises(GenerationContractError, match=message):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_english_rejects_chinese_text() -> None:
    spec = make_spec(output_language=OutputLanguage.ENGLISH)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.depth_of_field.focus_target = "camera朝向东北"

    with pytest.raises(GenerationContractError, match="混入输出语言之外的文字"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_rejects_invisible_action() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].action = "面部出画，右手从身侧抬起"

    with pytest.raises(GenerationContractError, match="action 包含不可见描述"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_rejects_explicit_cross_frame_reference() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].action = "右手沿用上一帧的位置握住铁栅"

    with pytest.raises(GenerationContractError, match="引用了其他 Frame"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_accepts_null_expression_for_head_crop() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].framing = CharacterFraming.HEAD_CROPPED_TORSO
    frame.characters[0].visible_appearance = "肩部以下躯干和双臂清晰入画"
    frame.characters[0].expression = None

    normalized = normalize_frame(
        spec,
        theme,
        frame,
        frame_ids(spec, theme.theme_id),
    )

    assert normalized.characters[0].expression is None


def test_frame_rejects_visible_head_crop_expression() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].framing = CharacterFraming.HEAD_CROPPED_TORSO

    with pytest.raises(GenerationContractError, match="expression 必须为 null"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))
