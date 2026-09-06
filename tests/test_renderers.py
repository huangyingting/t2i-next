from __future__ import annotations

import re

import pytest

from t2i_prompt_pipeline.models import (
    CastMember,
    CastPlan,
    CharacterFraming,
    Frame,
    OutputLanguage,
    PromptBook,
    Theme,
    ThemeBook,
)
from t2i_prompt_pipeline.renderers import render_book
from tests.factories import (
    make_foundation,
    make_frame_batch,
    make_spec,
    make_themes,
)


def render_prompt(
    theme: Theme,
    frame: Frame,
    output_language: OutputLanguage,
) -> str:
    book = PromptBook(
        semantic_name="renderer_test",
        cast_plan=CastPlan(
            members=[
                CastMember(gender=character.gender)
                for character in theme.characters
            ]
        ),
        themes=[ThemeBook(theme=theme, frames=[frame])],
    )
    return render_book(book, output_language)[0].text


def test_renderer_uses_each_fact_from_its_single_owner() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert prompt.count(theme.style) == 1
    assert prompt.count(theme.scene) == 1
    for character in theme.characters:
        assert prompt.count(character.appearance) == 1
        assert prompt.count(character.outfit) == 1
    assert "当前人物：" not in prompt


@pytest.mark.parametrize(
    ("female_count", "male_count"),
    (
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 0),
        (1, 1),
        (2, 1),
    ),
    ids=("one", "two", "three", "four", "one-man-one-woman", "one-man-two-women"),
)
def test_renderer_merges_each_visible_characters_stable_and_moment_facts(
    female_count: int,
    male_count: int,
) -> None:
    spec = make_spec(female_count=female_count, male_count=male_count)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]

    for index, (character, moment) in enumerate(
        zip(theme.characters, frame.characters, strict=True),
        start=1,
    ):
        character.appearance = f"外貌标记{index}"
        character.outfit = f"服饰标记{index}"
        moment.visible_appearance = (
            f"外貌标记{index}；服饰标记{index}"
        )
        moment.lighting_effect = f"左侧明亮，右侧阴影标记{index}"
        moment.expression = f"表情标记{index}"
        moment.action = f"动作标记{index}"

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE)

    assert prompt.count("人物：") == 1
    assert "当前人物：" not in prompt
    label_positions = [
        prompt.index(character.label) for character in theme.characters
    ]
    for index, character in enumerate(theme.characters, start=1):
        assert prompt.count(character.label) == 2
        markers = (
            f"外貌标记{index}",
            f"服饰标记{index}",
            f"阴影标记{index}",
            f"表情标记{index}",
            f"动作标记{index}",
        )
        assert all(prompt.count(marker) == 1 for marker in markers)
        marker_positions = [prompt.index(marker) for marker in markers]
        assert marker_positions == sorted(marker_positions)
        segment_end = (
            label_positions[index]
            if index < len(label_positions)
            else len(prompt)
        )
        assert all(
            label_positions[index - 1] < position < segment_end
            for position in marker_positions
        )


def test_renderer_uses_camera_visible_identity_description() -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    foundation.cast_plan.members[0].role = "植物学家"
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].visible_appearance = (
        f"{theme.characters[0].age}岁植物学家，人物1的稳定外貌，"
        "人物1的基础服饰"
    )
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[ThemeBook(theme=theme, frames=[frame])],
    )

    prompt = render_book(book, OutputLanguage.CHINESE)[0].text

    assert (
        f"女1：{theme.characters[0].age}岁植物学家，"
        "人物1的稳定外貌，人物1的基础服饰"
    ) in prompt


def test_renderer_derives_head_cropped_staging_from_enum() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    moment = frame.characters[0]
    moment.framing = CharacterFraming.HEAD_CROPPED_TORSO
    moment.placement = "右前景"
    moment.facing = "朝向镜头"
    moment.visible_appearance = "灰上衣包裹的肩胸和双臂"
    moment.expression = None

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE)

    assert (
        "人物：女1：灰上衣包裹的肩胸和双臂；"
        "受光：左脸明亮，右侧留有阴影1；动作1"
    ) in prompt
    assert "构图：女1：右前景，头部被裁切、躯干入画，朝向镜头" in prompt
    assert "表情1" not in prompt


def test_renderer_exposes_actionable_scene_and_per_character_lighting() -> None:
    spec = make_spec(female_count=2, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.lighting.source = "顶部冷白荧光灯与右后方琥珀色街灯"
    frame.camera.lighting.position = "人物上方及画面右后方"
    frame.camera.lighting.color = "冷白与暖琥珀色"
    frame.camera.lighting.scene_effect = (
        "立柱正面明亮，车库深处和卷帘门落入暗部"
    )
    effects = (
        "左脸和肩部明亮，右侧躯干落入阴影",
        "背部形成暖色轮廓高光，胸前保持暗部",
        "额头受顶光照亮，眼窝和下颌形成硬阴影",
    )
    for moment, effect in zip(frame.characters, effects, strict=True):
        moment.lighting_effect = effect

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE)

    assert "光源：顶部冷白荧光灯与右后方琥珀色街灯" in prompt
    assert "光位：人物上方及画面右后方" in prompt
    assert "光色：冷白与暖琥珀色" in prompt
    assert "场景明暗：立柱正面明亮，车库深处和卷帘门落入暗部" in prompt
    for character, effect in zip(theme.characters, effects, strict=True):
        assert f"{character.label}：" in prompt
        assert f"受光：{effect}" in prompt


def test_renderer_uses_each_themes_complete_style() -> None:
    spec = make_spec(theme_count=2)
    foundation = make_foundation()
    themes = make_themes(spec)
    themes[0].style = (
        "韦斯安德森式实景电影摄影，平面舞台调度结合暖琥珀与灰蓝配色，"
        "柔和侧光刻画哑光木材与拉丝黄铜"
    )
    themes[1].style = (
        "韦斯安德森式微缩模型摄影，轴向陈列结合深青与暗红配色，"
        "冷硬顶光刻画湿润石材与氧化金属"
    )
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[
            ThemeBook(
                theme=theme,
                frames=make_frame_batch(spec, theme).frames,
            )
            for theme in themes
        ],
    )

    prompts = render_book(book, OutputLanguage.CHINESE)

    assert themes[0].style in prompts[0].text
    assert themes[1].style not in prompts[0].text
    assert themes[1].style in prompts[1].text
    assert themes[0].style not in prompts[1].text
    assert prompts[0].text.partition("主题：")[0] != prompts[1].text.partition(
        "主题："
    )[0]


def test_renderer_builds_staging_and_replaces_character_ids() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.shot += "。"
    frame.camera.view += "。"
    frame.characters[0].placement = "画面左侧。"
    frame.characters[0].facing = "朝向T01-C01。"

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert "。。" not in prompt
    assert "。；" not in prompt
    assert "T01-C01" not in prompt
    assert "构图：女1：画面左侧，头部与躯干入画，朝向女1" in prompt


def test_invalid_id_label_falls_back_without_leaking_ids() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    theme.characters[0].label = "T01-C02"
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].facing = "朝向T01-C02"
    frame.characters[1].facing = "朝向T01-C01"

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert "T01-C01" not in prompt
    assert "T01-C02" not in prompt
    assert "女1：位置1，头部与躯干入画，朝向男1" in prompt
    assert "男1：位置2，头部与躯干入画，朝向女1" in prompt


def test_renderer_uses_names_and_gender_ordinals() -> None:
    spec = make_spec(female_count=2, male_count=2)
    theme = make_themes(spec)[0]
    theme.characters[0].label = "林岚"
    theme.characters[1].label = "女性"
    theme.characters[2].label = "周明"
    theme.characters[3].label = "男性"
    frame = make_frame_batch(spec, theme).frames[0]

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert "林岚：" in prompt
    assert "女2：" in prompt
    assert "周明：" in prompt
    assert "男2：" in prompt


def test_renderer_removes_character_ids_from_every_text_field() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    theme.style = "T01-C01的风格"
    theme.title = "T01-C02的主题"
    theme.scene = "T01-C01与T01-C02所在的场景"
    theme.characters[0].appearance = "T01-C01的外貌"
    frame.characters[1].placement = "T01-C02位于右侧"
    frame.characters[0].action = "靠近T01-C02"
    theme.scene = (
        "T99-C01与T99-C02所在场景，主题T01，T01-F01，与F01，角色C01"
    )

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert not re.search(r"T\d{2,4}-C\d{2}", prompt)
    assert "T01" not in prompt
    assert "F01" not in prompt
    assert "C01" not in prompt
    assert "女1的风格" in prompt
    assert "男1位于右侧" in prompt
    assert "当前主题，当前镜头" in prompt


def test_bare_id_cleanup_preserves_modifier_tokens() -> None:
    spec = make_spec(frames_per_theme=16)
    foundation = make_foundation()
    theme = make_themes(spec)[0]
    theme.style = (
        "canvas F16 aperture, Canon C70 camera, T90 railway platform, "
        "F16 shutter, T90 highway exit"
    )
    frames = make_frame_batch(spec, theme).frames
    known_t90 = theme.model_copy(
        update={
            "theme_id": "T90",
            "characters": [
                character.model_copy(
                    update={"character_id": "T90-C01"}
                )
                for character in theme.characters
            ],
        }
    )
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[
            ThemeBook(theme=theme, frames=frames),
            ThemeBook(theme=known_t90, frames=[]),
        ],
    )
    prompt = render_book(book, OutputLanguage.CHINESE)[0].text

    assert "canvas F16 aperture" in prompt
    assert "Canon C70 camera" in prompt
    assert "T90 railway platform" in prompt
    assert "F16 shutter" in prompt
    assert "T90 highway exit" in prompt


def test_bare_internal_label_and_explicit_relations_are_sanitized() -> None:
    spec = make_spec()
    make_foundation()
    theme = make_themes(spec)[0]
    theme.characters[0].label = "C01"
    frame = make_frame_batch(spec, theme).frames[0]
    theme.scene = "F01场景，T01色调"

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert "C01" not in prompt
    assert "F01" not in prompt
    assert "T01" not in prompt
    assert "女1" in prompt
    assert "当前镜头场景，当前主题色调" in prompt


def test_renderer_produces_english_prompt_and_localized_fallback_labels() -> None:
    spec = make_spec(
        female_count=1,
        male_count=1,
        output_language=OutputLanguage.ENGLISH,
    )
    make_foundation()
    theme = make_themes(spec)[0]
    theme.style = "Cinematic realism with restrained visual grammar"
    theme.title = "A quiet reunion"
    theme.scene = "A hotel lobby after midnight"
    theme.characters[0].label = "Female 1"
    theme.characters[0].appearance = "Short black hair and dark eyes"
    theme.characters[0].outfit = "A tailored navy coat"
    theme.characters[1].label = "Alex"
    theme.characters[1].appearance = "Silver hair and a square jaw"
    theme.characters[1].outfit = "A charcoal wool suit"
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.shot = "medium shot"
    frame.camera.view = "eye level"
    frame.characters[0].placement = "left foreground"
    frame.characters[0].facing = "facing T01-C02"
    frame.characters[0].expression = "a restrained smile"
    frame.characters[0].visible_appearance = (
        "a 26-year-old woman with short black hair and dark eyes, "
        "wearing a tailored navy coat"
    )
    frame.characters[0].action = "looks toward T01-C02"
    frame.characters[1].expression = "quiet surprise"
    frame.characters[1].placement = "right foreground"
    frame.characters[1].facing = "facing T01-C01"
    frame.characters[1].visible_appearance = (
        "a 27-year-old man with silver hair and a square jaw, "
        "wearing a charcoal wool suit"
    )
    frame.characters[1].action = "sets down a suitcase"
    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.ENGLISH,
    )

    assert "Theme: A quiet reunion" in prompt
    assert prompt.startswith(theme.style)
    assert "Scene: A hotel lobby after midnight" in prompt
    assert "Woman 1: a 26-year-old woman" in prompt
    assert "Alex: a 27-year-old man" in prompt
    assert "Shot: medium shot; View: eye level" in prompt
    assert (
        "Composition: Woman 1: left foreground, head and torso in frame, "
        "facing Alex"
    ) in prompt
    assert "Current characters:" not in prompt
    assert "主题：" not in prompt
    assert "T01" not in prompt
