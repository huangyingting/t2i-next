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
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )


def test_theme_style_normalizes_language_specific_ending() -> None:
    chinese_spec = make_spec()
    chinese_theme = make_themes(chinese_spec)[0].model_copy(
        update={
            "style": (
                "电影摄影以暖琥珀与灰蓝配色形成中等反差"
            )
        }
    )
    english_spec = make_spec(output_language=OutputLanguage.ENGLISH)
    english_theme = make_themes(english_spec)[0].model_copy(
        update={
            "title": "Theme 1",
            "scene": "A quiet room with a wooden table by the window",
            "style": (
                "Cinematic photography balances warm amber and slate blue, "
                "with moderate contrast"
            ),
            "characters": [
                character.model_copy(
                    update={
                        "label": "Woman 1",
                        "appearance": "Shoulder-length dark hair and an oval face",
                        "outfit": "A white cotton shirt and charcoal trousers",
                    }
                )
                for character in make_themes(english_spec)[0].characters
            ],
        }
    )

    assert normalize_test_theme(
        chinese_spec,
        chinese_theme,
    ).style.endswith("。")
    assert normalize_test_theme(
        english_spec,
        english_theme,
    ).style.endswith(".")


def test_theme_style_rejects_probable_mid_phrase_truncation() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0].model_copy(
        update={"style": "电影摄影，" + "色" * 59 + "："}
    )

    with pytest.raises(GenerationContractError, match="疑似在句中截断"):
        normalize_test_theme(spec, theme)


def test_theme_style_normalizes_trailing_list_separator_without_retry() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0].model_copy(
        update={"style": "电影摄影，" + "色" * 59 + "，"}
    )

    assert normalize_test_theme(spec, theme).style == (
        "电影摄影，" + "色" * 59 + "。"
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
    foundation = make_foundation(spec)

    with pytest.raises(
        GenerationContractError,
        match="遗漏 brief 明示风格.*贝纳尔多",
    ):
        normalize_foundation(spec, foundation)


@pytest.mark.parametrize(
    "brief",
    [
        "两种风格的对比：城市与乡村",
        "描述一种建筑风格的演变过程",
    ],
)
def test_foundation_does_not_treat_generic_style_as_creator_anchor(
    brief: str,
) -> None:
    spec = make_spec(brief=brief)

    assert normalize_foundation(spec, make_foundation(spec))


def test_theme_style_must_preserve_verbatim_brief_constraints() -> None:
    spec = make_spec(brief="韦斯安德森风格的有故事性的互动")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = ["韦斯安德森风格"]
    theme = make_themes(spec)[0]

    with pytest.raises(GenerationContractError, match="缺少 brief 原文约束"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_theme_style_must_use_brief_constraints_exactly_once() -> None:
    phrase = "韦斯安德森风格"
    spec = make_spec(brief=f"{phrase}的有故事性的互动")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = [phrase]
    theme = make_themes(spec)[0].model_copy(
        update={
            "style": f"电影摄影采用{phrase}的构图，结合{phrase}的配色。"
        }
    )

    with pytest.raises(GenerationContractError, match="重复 brief 原文约束"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_theme_chinese_allows_unrequested_latin_text() -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(
        update={"scene": "歪斜的 singleton 竹篮搁在柱脚"}
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert "singleton" in normalized.scene


@pytest.mark.parametrize(
    ("field", "text"),
    (
        ("style", "摄影实拍，保留 required_phrases：柔和光线。"),
        ("scene", "私人摄影棚，required_route_points: 摄影棚中央。"),
    ),
)
def test_theme_rejects_internal_schema_term_leakage(
    field: str,
    text: str,
) -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]
    setattr(theme, field, text)

    with pytest.raises(GenerationContractError, match="泄漏内部字段名"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_theme_accepts_explicit_era_from_brief() -> None:
    era = "一九六零年代"
    spec = make_spec(brief=f"{era}香港旧酒店重逢故事")
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(
        update={"scene": f"{era}香港旧酒店，雨夜走廊连接电梯与客房"}
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert era in normalized.scene


def test_theme_requires_every_explicit_brief_route_point() -> None:
    spec = make_spec(
        brief="两名成年人从电梯、走廊到房间展开重逢故事"
    )
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(
        update={"scene": "雨夜旧酒店房间，铁架床靠近木格窗"}
    )

    with pytest.raises(
        GenerationContractError,
        match=r"Theme.scene 缺少 brief 路线地点.*电梯.*走廊",
    ):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_theme_accepts_complete_explicit_brief_route() -> None:
    spec = make_spec(
        brief="两名成年人从电梯、走廊到房间展开重逢故事"
    )
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(
        update={"scene": "雨夜旧酒店的电梯经走廊连接房间"}
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert normalized.scene == theme.scene


def test_theme_accepts_equivalent_hotel_route_terms() -> None:
    spec = make_spec(
        brief="两名成年人从电梯、走廊到房间展开重逢故事"
    )
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(
        update={"scene": "雨夜旧酒店的升降机经长廊连接客房"}
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert normalized.scene == theme.scene


def test_theme_style_allows_abstract_composition_and_perspective() -> None:
    phrase = "斯坦利·库布里克风格"
    spec = make_spec(brief=f"{phrase}的两名成年人互动")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = [phrase]
    theme = make_themes(spec)[0].model_copy(
        update={
            "style": (
                f"{phrase}，轴线构图与单点透视形成深景深倾向，"
                "电影摄影以冷白色调刻画抛光石材。"
            )
        }
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert "单点透视" in normalized.style


def test_theme_style_allows_camera_constraint_copied_from_brief() -> None:
    phrase = "低机位构图"
    spec = make_spec(brief=f"{phrase}的两名成年人互动")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = [phrase]
    theme = make_themes(spec)[0].model_copy(
        update={"style": f"{phrase}，粗粒黑白电影摄影与硬反差。"}
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert phrase in normalized.style


def test_theme_scene_allows_background_population_fact() -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(
        update={"scene": "私人摄影棚，背景没有其他人。"}
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert normalized.scene == theme.scene


@pytest.mark.parametrize(
    ("style", "output_language"),
    [
        (
            "湿版火棉胶摄影，低饱和银盐色调。",
            OutputLanguage.CHINESE,
        ),
        (
            "纪录片摄像，低饱和冷灰色调。",
            OutputLanguage.CHINESE,
        ),
        (
            "Cinematic photography with restrained colors.",
            OutputLanguage.ENGLISH,
        ),
        (
            "Observational videography in low saturation.",
            OutputLanguage.ENGLISH,
        ),
    ],
)
def test_theme_style_accepts_camera_captured_medium(
    style: str,
    output_language: OutputLanguage,
) -> None:
    spec = make_spec(output_language=output_language)
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(update={"style": style})

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert normalized.style == style


def test_explicit_illustration_phrase_remains_inside_photographic_style() -> None:
    phrase = "水彩风格"
    spec = make_spec(brief=f"{phrase}的两名成年人互动")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = [phrase]
    theme = make_themes(spec)[0].model_copy(
        update={
            "style": (
                f"{phrase}，电影摄影拍摄带晕染表面处理的实体布景。"
            )
        }
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert normalized.style.count(phrase) == 1


def test_foundation_accepts_unconstrained_brief_cast() -> None:
    spec = make_spec(female_count=None, male_count=None)
    foundation = make_foundation(
        make_spec(female_count=2, male_count=1)
    )

    assert normalize_foundation(spec, foundation) is foundation


def test_foundation_rejects_explicit_cast_constraint_conflict() -> None:
    spec = make_spec(female_count=1, male_count=0)
    foundation = make_foundation(
        make_spec(female_count=2, male_count=1)
    )

    with pytest.raises(
        GenerationContractError,
        match=r"brief 解析为女性 2 名.*--female-count 要求 1 名",
    ):
        normalize_foundation(spec, foundation)


def test_theme_character_order_must_match_cast_plan_gender() -> None:
    spec = make_spec(female_count=1, male_count=1)
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]
    theme.characters[0].gender, theme.characters[1].gender = (
        theme.characters[1].gender,
        theme.characters[0].gender,
    )

    with pytest.raises(GenerationContractError, match="不符合 Cast Plan"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_frame_requires_every_theme_character() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters = [frame.characters[1]]

    with pytest.raises(
        GenerationContractError,
        match="每个 Frame 必须包含 Theme 全部人物",
    ):
        normalize_frame(
            spec,
            theme,
            frame,
            frame_ids(spec, theme.theme_id),
        )


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
        normalize_frame(
            spec,
            theme,
            frame,
            frame_ids(spec, theme.theme_id),
        )


def test_frame_chinese_allows_english_camera_term() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.view = ".camera朝向东北"

    normalized = normalize_frame(
        spec,
        theme,
        frame,
        frame_ids(spec, theme.theme_id),
    )

    assert normalized.camera.view == ".camera朝向东北"


def test_frame_english_still_rejects_chinese_text() -> None:
    spec = make_spec(output_language=OutputLanguage.ENGLISH)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.view = "camera朝向东北"

    with pytest.raises(
        GenerationContractError,
        match="混入输出语言之外的文字.*朝向东北",
    ):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


@pytest.mark.parametrize(
    ("style", "shot"),
    [
        ("胶片质感，景深偏浅。", "中景，自然透视，深景深"),
        ("Film texture with deep focus.", "Medium shot, shallow focus"),
    ],
)
def test_frame_rejects_depth_opposed_to_theme_style(
    style: str,
    shot: str,
) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0].model_copy(update={"style": style})
    frame = make_frame_batch(spec, theme).frames[0].model_copy(
        update={
            "camera": make_frame_batch(spec, theme).frames[0].camera.model_copy(
                update={"shot": shot}
            )
        }
    )

    with pytest.raises(
        GenerationContractError,
        match=r"camera\.shot 必须继承 Theme\.style",
    ):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


@pytest.mark.parametrize(
    ("style", "shot"),
    [
        ("胶片质感，景深偏浅。", "中景，自然透视，浅景深"),
        ("胶片质感。", "中景，自然透视，深景深"),
    ],
)
def test_frame_accepts_matching_or_unspecified_theme_depth(
    style: str,
    shot: str,
) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0].model_copy(update={"style": style})
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.shot = shot

    normalized = normalize_frame(
        spec,
        theme,
        frame,
        frame_ids(spec, theme.theme_id),
    )

    assert normalized.camera.shot == shot


def test_frame_rejects_unknown_or_duplicate_visible_characters() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    duplicate = frame.model_copy(
        update={"characters": [frame.characters[0], frame.characters[0]]}
    )
    unknown_moment = frame.characters[0].model_copy(
        update={"character_id": "T02-C01"}
    )
    unknown = frame.model_copy(update={"characters": [unknown_moment]})

    with pytest.raises(GenerationContractError, match="缺失、重复或来自其他 Theme"):
        normalize_frame(spec, theme, duplicate, frame_ids(spec, theme.theme_id))
    with pytest.raises(GenerationContractError, match="缺失、重复或来自其他 Theme"):
        normalize_frame(spec, theme, unknown, frame_ids(spec, theme.theme_id))


def test_frame_rejects_completely_invisible_character_placeholder() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    invisible = frame.characters[0].model_copy(
        update={"expression": "不可见，出画。", "action": "不可见，出画。"}
    )
    frame.characters = [invisible]

    with pytest.raises(
        GenerationContractError,
        match="所有人物必须入画",
    ):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


@pytest.mark.parametrize(
    "action",
    [
        "背对镜头，全身出画不可见",
        "面部出画，右手从身侧抬起",
    ],
)
def test_frame_rejects_visibility_words_inside_action(action: str) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].action = action

    with pytest.raises(
        GenerationContractError,
        match="action 包含不可见描述",
    ):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


@pytest.mark.parametrize(
    "text",
    ("右手仍握住铁栅", "双手保持在肩膀两侧"),
)
def test_frame_accepts_standalone_state_shorthand(text: str) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].action = text

    normalized = normalize_frame(
        spec,
        theme,
        frame,
        frame_ids(spec, theme.theme_id),
    )

    assert normalized.characters[0].action == text


def test_frame_rejects_explicit_cross_frame_reference() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].action = "右手沿用上一帧的位置握住铁栅"

    with pytest.raises(GenerationContractError, match="引用了其他 Frame"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_rejects_compound_english_invisible_placeholder() -> None:
    spec = make_spec(output_language=OutputLanguage.ENGLISH)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].expression = "face not visible, out of frame."
    frame.characters[0].action = "not visible, out of frame."

    with pytest.raises(
        GenerationContractError,
        match="action 不能声明人物不可见",
    ):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_accepts_null_expression_for_head_crop() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].expression = None
    frame.characters[0].framing = CharacterFraming.HEAD_CROPPED_TORSO
    frame.characters[0].visible_appearance = (
        "肩部以下躯干与基础服饰入画，头部不入画"
    )
    normalized = normalize_frame(
        spec,
        theme,
        frame,
        frame_ids(spec, theme.theme_id),
    )

    assert normalized.characters[0].expression is None

@pytest.mark.parametrize(
    "literal",
    ["null", "NULL", "None", "nil", "undefined", "N/A", "无", "空"],
)
def test_frame_rejects_literal_empty_expression_when_head_is_visible(
    literal: str,
) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].expression = literal

    with pytest.raises(
        GenerationContractError,
        match="expression 与 framing 不一致",
    ):
        normalize_frame(
            spec,
            theme,
            frame,
            frame_ids(spec, theme.theme_id),
        )


def test_frame_rejects_empty_placeholder_action() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].action = "null"

    with pytest.raises(GenerationContractError):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_keeps_expression_that_merely_contains_a_placeholder_word() -> (
    None
):
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].expression = "空洞的眼神越过对方肩膀"

    normalized = normalize_frame(
        spec,
        theme,
        frame,
        frame_ids(spec, theme.theme_id),
    )

    assert normalized.characters[0].expression == "空洞的眼神越过对方肩膀"
