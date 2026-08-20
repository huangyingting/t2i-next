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
from t2i_prompt_pipeline.models import OutputLanguage
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
                "电影摄影以暖琥珀与灰蓝配色形成柔和侧光和中等反差，"
                "哑光木材与拉丝金属呈现细腻质感"
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
                "soft side light, "
                "moderate contrast, matte wood, and brushed brass textures"
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


def test_theme_style_preserves_long_complete_text() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0].model_copy(
        update={
            "style": (
                "电影摄影中青绿霓虹从窗外港务灯透入，与室内昏黄钨丝灯交织成冷暖分界线；"
                "雨幕将远景吞噬为柔焦光斑，近处金属栏杆与漆面座椅带海盐侵蚀的"
                "哑光氧化质感；慢快门使雨滴拖成银色丝线，窗上雾气和玻璃叠化出"
                "双重人影。"
            )
        }
    )

    normalized = normalize_test_theme(spec, theme)

    assert normalized.style == theme.style
    assert len(normalized.style) > 60


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


def test_theme_rejects_unrequested_latin_text_in_chinese_output() -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(
        update={"scene": "歪斜的 singleton 竹篮搁在柱脚"}
    )

    with pytest.raises(GenerationContractError, match="singleton"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


@pytest.mark.parametrize(
    "camera_term",
    [
        "相机位于人物左侧",
        "轨道横移长镜头",
        "斯坦尼康环绕近景",
        "固定机位中景",
        "焦距偏移",
    ],
)
def test_theme_style_rejects_frame_owned_camera_terms(
    camera_term: str,
) -> None:
    phrase = "韦斯安德森风格"
    spec = make_spec(brief=f"{phrase}的有故事性的互动")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = [phrase]
    theme = make_themes(spec)[0].model_copy(
        update={
            "style": f"{phrase}，电影摄影采用{camera_term}与暖色木纹。"
        }
    )

    with pytest.raises(GenerationContractError, match="Frame 专属具体摄影参数"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_theme_rejects_explicit_era_inferred_from_style_reference() -> None:
    phrase = "王家卫风格"
    spec = make_spec(brief=f"{phrase}的香港旧酒店重逢故事")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = [phrase]
    theme = make_themes(spec)[0].model_copy(
        update={
            "scene": "一九六零年代香港旧酒店，雨夜走廊连接电梯与客房",
            "style": f"{phrase}，电影摄影以潮湿霓虹塑造粗颗粒质感。",
        }
    )

    with pytest.raises(GenerationContractError, match="brief 未指定的时代"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_theme_style_allows_stable_slow_shutter_treatment() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0].model_copy(
        update={"style": "电影摄影采用慢速快门拖影与粗颗粒质感。"}
    )

    normalized = normalize_test_theme(spec, theme)

    assert "慢速快门拖影" in normalized.style


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


@pytest.mark.parametrize(
    ("field", "text", "message"),
    [
        ("outfit", "旗袍侧襟已解三粒盘扣", "稳定事实包含瞬时状态.*已"),
        ("scene", "铁皮斜顶承接雨声", "稳定事实包含非视觉信息.*雨声"),
    ],
)
def test_theme_rejects_transient_or_nonvisual_stable_facts(
    field: str,
    text: str,
    message: str,
) -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]
    if field == "outfit":
        theme.characters[0].outfit = text
    else:
        theme.scene = text

    with pytest.raises(GenerationContractError, match=message):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_theme_reports_all_deterministic_issues_together() -> None:
    spec = make_spec(
        brief="王家卫风格，两名成年人从电梯、走廊到房间重逢"
    )
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = ["王家卫风格"]
    theme = make_themes(spec)[0].model_copy(
        update={
            "scene": "一九六零年代旧酒店房间，铁架床靠窗",
            "style": "王家卫风格，电影摄影采用固定机位中景与粗颗粒。",
        }
    )

    with pytest.raises(GenerationContractError) as caught:
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )

    message = str(caught.value)
    assert "固定机位" in message
    assert "一九六零年代" in message
    assert "电梯" in message
    assert "走廊" in message


def test_theme_style_allows_abstract_composition_and_perspective() -> None:
    phrase = "斯坦利·库布里克风格"
    spec = make_spec(brief=f"{phrase}的两名成年人互动")
    foundation = make_foundation(spec)
    foundation.style_constraints.required_phrases = [phrase]
    theme = make_themes(spec)[0].model_copy(
        update={
            "style": (
                f"{phrase}，轴线构图与单点透视形成深景深倾向，"
                "电影摄影以冷白光刻画抛光石材。"
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
        update={"style": f"{phrase}，粗粒黑白电影摄影与硬质侧光。"}
    )

    normalized = normalize_theme(
        spec,
        foundation.style_constraints,
        foundation.cast_plan,
        theme,
        theme_ids(spec),
    )

    assert phrase in normalized.style


@pytest.mark.parametrize(
    "style",
    [
        "水彩纸本以暖黄色晕染乡村厨房。",
        "Graphite pencil drawing with dense cross-hatching.",
    ],
)
def test_theme_style_requires_camera_captured_medium(style: str) -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(update={"style": style})

    with pytest.raises(GenerationContractError, match="必须使用摄影或摄像"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


def test_theme_style_rejects_unrequested_illustration_medium() -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0].model_copy(
        update={"style": "电影摄影捕捉水彩纸本的晕染边界。"}
    )

    with pytest.raises(GenerationContractError, match="使用非相机实拍媒介：水彩"):
        normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            theme_ids(spec),
        )


@pytest.mark.parametrize(
    ("style", "output_language"),
    [
        (
            "湿版火棉胶摄影呈现潮湿木材与银盐颗粒。",
            OutputLanguage.CHINESE,
        ),
        (
            "纪录片摄像以手持数字影像记录潮湿街道。",
            OutputLanguage.CHINESE,
        ),
        (
            "Cinematic photography with restrained natural light.",
            OutputLanguage.ENGLISH,
        ),
        (
            "Observational videography with available practical light.",
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


def test_frame_accepts_visible_character_subset_in_theme_order() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters = [frame.characters[1]]

    normalized = normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))

    assert [moment.character_id for moment in normalized.characters] == [
        theme.characters[1].character_id
    ]


def test_frame_rejects_mixed_language_camera_text() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.view = ".camera朝向东北"

    with pytest.raises(
        GenerationContractError,
        match="混入输出语言之外的文字.*camera",
    ):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_rejects_reference_to_omitted_ordinal_character() -> None:
    spec = make_spec(female_count=2, male_count=0)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters = [frame.characters[0]]
    frame.characters[0].action = "女1注视画面中的女2"

    with pytest.raises(
        GenerationContractError,
        match="引用了未列入 characters 的可见人物.*女2",
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

    with pytest.raises(GenerationContractError, match="重复或不属于 Theme"):
        normalize_frame(spec, theme, duplicate, frame_ids(spec, theme.theme_id))
    with pytest.raises(GenerationContractError, match="重复或不属于 Theme"):
        normalize_frame(spec, theme, unknown, frame_ids(spec, theme.theme_id))


def test_frame_rejects_completely_invisible_character_placeholder() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    invisible = frame.characters[0].model_copy(
        update={"expression": "不可见，出画。", "action": "不可见，出画。"}
    )
    frame.characters = [invisible]

    with pytest.raises(GenerationContractError, match="必须从 characters 省略"):
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

    with pytest.raises(GenerationContractError, match="action 包含不可见描述"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


@pytest.mark.parametrize(
    ("field", "text"),
    [
        ("action", "右手仍握住铁栅"),
        ("details", "粗呢外套已抛落床沿"),
        ("action", "双手保持在肩膀两侧"),
        ("details", "皮革束带继续垂落在床沿"),
    ],
)
def test_frame_accepts_standalone_state_shorthand(
    field: str,
    text: str,
) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    if field == "action":
        frame.characters[0].action = text
    else:
        frame.details = text

    normalized = normalize_frame(
        spec,
        theme,
        frame,
        frame_ids(spec, theme.theme_id),
    )

    if field == "action":
        assert normalized.characters[0].action == text
    else:
        assert normalized.details == text


@pytest.mark.parametrize(
    ("field", "text"),
    [
        ("action", "右手沿用上一帧的位置握住铁栅"),
        ("details", "粗呢外套如前放在床沿"),
    ],
)
def test_frame_rejects_explicit_cross_frame_reference(
    field: str,
    text: str,
) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    if field == "action":
        frame.characters[0].action = text
    else:
        frame.details = text

    with pytest.raises(GenerationContractError, match="引用了其他 Frame"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


@pytest.mark.parametrize(
    "details",
    [
        "雨声从走廊尽头传来",
        "防火门方向传来积水滴落铁管的空洞回响",
        "升降机铁栅碰撞声不可见但栅影微晃",
        "两人呼吸不可见但交握指节泛白",
    ],
)
def test_frame_rejects_nonvisual_sound_details(details: str) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.details = details

    with pytest.raises(GenerationContractError, match="非视觉信息"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_reports_all_text_issues_together() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].action = "右手沿用上一帧的位置握住铁栅"
    frame.details = "雨声从走廊尽头传来"

    with pytest.raises(GenerationContractError) as caught:
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))

    message = str(caught.value)
    assert "上一帧" in message
    assert "雨声" in message


def test_frame_rejects_compound_english_invisible_placeholder() -> None:
    spec = make_spec(output_language=OutputLanguage.ENGLISH)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].expression = "face not visible, out of frame."
    frame.characters[0].action = "not visible, out of frame."

    with pytest.raises(GenerationContractError, match="必须从 characters 省略"):
        normalize_frame(spec, theme, frame, frame_ids(spec, theme.theme_id))


def test_frame_omits_invisible_expression_when_action_is_visible() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].expression = "面部不可见。"

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
def test_frame_treats_literal_empty_placeholder_as_missing_expression(
    literal: str,
) -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].expression = literal

    normalized = normalize_frame(
        spec,
        theme,
        frame,
        frame_ids(spec, theme.theme_id),
    )

    assert normalized.characters[0].expression is None


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
