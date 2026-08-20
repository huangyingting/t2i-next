from __future__ import annotations

import re

from t2i_prompt_pipeline.models import (
    CastMember,
    CastPlan,
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
    assert prompt.count(frame.details) == 1


def test_renderer_combines_shared_role_with_theme_visual_identity() -> None:
    spec = make_spec()
    foundation = make_foundation(spec)
    foundation.cast_plan.members[0].role = "植物学家"
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[ThemeBook(theme=theme, frames=[frame])],
    )

    prompt = render_book(book, OutputLanguage.CHINESE)[0].text

    assert f"女1（植物学家，{theme.characters[0].age}岁）" in prompt


def test_renderer_includes_only_characters_visible_in_frame() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters = [frame.characters[0]]

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert theme.characters[0].appearance in prompt
    assert theme.characters[1].appearance not in prompt
    assert theme.characters[1].outfit not in prompt


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


def test_renderer_normalizes_boundaries_and_replaces_ids_in_details() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.shot += "。"
    frame.camera.view += "。"
    frame.camera.composition += "。"
    frame.details = "T01-C01的手靠近杯子。"

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert "。。" not in prompt
    assert "。；" not in prompt
    assert "T01-C01" not in prompt
    assert "女1的手靠近杯子" in prompt


def test_invalid_id_label_falls_back_without_leaking_ids() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    theme.characters[0].label = "T01-C02"
    frame = make_frame_batch(spec, theme).frames[0]
    frame.details = "T01-C01 / T01-C02"

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert "T01-C01" not in prompt
    assert "T01-C02" not in prompt
    assert "细节：女1 / 男1" in prompt


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

    assert "林岚（女性" in prompt
    assert "女2（" in prompt
    assert "周明（男性" in prompt
    assert "男2（" in prompt


def test_renderer_removes_character_ids_from_every_text_field() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    theme.style = "T01-C01的风格"
    theme.title = "T01-C02的主题"
    theme.scene = "T01-C01与T01-C02所在的场景"
    theme.characters[0].appearance = "T01-C01的外貌"
    frame.camera.composition = "T01-C02位于右侧"
    frame.characters[0].action = "靠近T01-C02"
    frame.details = (
        "T99-C01与T99-C02，主题T01，T01-F01，与F01，角色C01"
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
    frame.details = "F01居中，T01色调"

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert "C01" not in prompt
    assert "F01" not in prompt
    assert "T01" not in prompt
    assert "女1" in prompt
    assert "当前镜头居中，当前主题色调" in prompt


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
    frame.camera.composition = "balanced two-shot"
    frame.characters[0].expression = "a restrained smile"
    frame.characters[0].action = "looks toward T01-C02"
    frame.characters[1].expression = "quiet surprise"
    frame.characters[1].action = "sets down a suitcase"
    frame.details = "T01-F01 holds on T01-C01 and T01-C02"

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.ENGLISH,
    )

    assert "Theme: A quiet reunion" in prompt
    assert prompt.startswith(theme.style)
    assert "Scene: A hotel lobby after midnight" in prompt
    assert "Woman 1 (age 26)" in prompt
    assert "Alex (male, age 27)" in prompt
    assert "Shot: medium shot; View: eye level" in prompt
    assert "current shot holds on Woman 1 and Alex" in prompt
    assert "主题：" not in prompt
    assert "T01" not in prompt


def test_renderer_omits_expression_separator_when_face_is_not_visible() -> None:
    spec = make_spec()
    make_foundation()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.characters[0].expression = None
    frame.characters[0].action = "右手托住花盆底部"

    prompt = render_prompt(
        theme,
        frame,
        OutputLanguage.CHINESE,
    )

    assert "当前人物：女1：右手托住花盆底部" in prompt
    assert "女1：；右手托住花盆底部" not in prompt
