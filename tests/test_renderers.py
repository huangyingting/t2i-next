from __future__ import annotations

import pytest

from t2i_prompt_pipeline.models import (
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


def make_book(theme: Theme, frame: Frame, spec=None) -> PromptBook:
    foundation = make_foundation(spec or make_spec())
    return PromptBook(
        semantic_name="renderer_test",
        style_constraints=foundation.style_constraints,
        cast_plan=foundation.cast_plan,
        themes=[ThemeBook(theme=theme, frames=[frame])],
    )


def render_prompt(
    theme: Theme,
    frame: Frame,
    output_language: OutputLanguage,
    spec=None,
) -> str:
    return render_book(make_book(theme, frame, spec), output_language)[0].text


def test_renderer_only_projects_frame_visible_character_facts() -> None:
    spec = make_spec(female_count=1, male_count=1)
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE, spec)

    assert prompt.startswith("实拍摄影")
    for phrase in foundation.style_constraints.required_phrases:
        assert prompt.count(phrase) == 1
    assert prompt.count(theme.setting.location) == 1
    for value in (
        *theme.setting.fixed_elements,
        theme.setting.background_population,
        theme.setting.atmosphere,
    ):
        assert prompt.count(value) == 1
    for value in theme.setting.available_light_sources:
        assert value in prompt
    for character, moment in zip(
        theme.characters,
        frame.characters,
        strict=True,
    ):
        assert prompt.count(character.appearance) == 1
        assert prompt.count(character.outfit) == 1
        assert prompt.count(moment.visible_appearance) == 1
    assert "当前人物：" not in prompt


@pytest.mark.parametrize(
    ("female_count", "male_count", "labels"),
    (
        (1, 0, ("女1",)),
        (2, 0, ("女1", "女2")),
        (1, 1, ("女1", "男1")),
        (2, 1, ("女1", "女2", "男1")),
    ),
)
def test_renderer_derives_labels_from_cast_plan(
    female_count: int,
    male_count: int,
    labels: tuple[str, ...],
) -> None:
    spec = make_spec(female_count=female_count, male_count=male_count)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE, spec)

    for label in labels:
        assert f"{label}：" in prompt
    assert "T01-C" not in prompt


def test_renderer_uses_frame_projection_without_repeating_stable_facts() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    character = theme.characters[0]
    moment = frame.characters[0]
    character.appearance = "齐肩黑发与椭圆脸"
    character.outfit = "白衬衫、灰长裤和黑靴"
    moment.visible_appearance = "齐肩黑发、完整面部和白衬衫上身"
    moment.lighting_effect = "左脸明亮，右颊留有阴影"
    moment.expression = "目光落在木桌上"
    moment.action = "右手扶住木桌边缘"

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE, spec)

    assert character.appearance not in prompt
    assert character.outfit not in prompt
    for value in (
        moment.visible_appearance,
        moment.lighting_effect,
        moment.expression,
        moment.action,
    ):
        assert prompt.count(value) == 1


def test_renderer_omits_unused_theme_light_sources() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    theme.setting.available_light_sources = ["左窗日光", "顶部轨道灯"]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.lighting.source = "左窗日光"

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE, spec)

    assert "左窗日光" in prompt
    assert "顶部轨道灯" not in prompt
    assert "可用光源：" not in prompt


def test_renderer_includes_concise_visual_atmosphere() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    theme.setting.atmosphere = "暖黄低照度下安静而亲密"
    frame = make_frame_batch(spec, theme).frames[0]

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE, spec)

    assert "氛围：暖黄低照度下安静而亲密" in prompt


def test_renderer_outputs_structured_depth_and_lighting() -> None:
    spec = make_spec(female_count=2, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    frame.camera.depth_of_field.focus_target = "三人面部与中央绳结"
    frame.camera.depth_of_field.background_effect = "后墙与围观人群逐层虚化"
    frame.camera.lighting.source = "顶部冷白荧光灯"
    frame.camera.lighting.position = "人物正上方"
    frame.camera.lighting.color = "冷白色"
    frame.camera.lighting.scene_effect = "地面明亮，车库深处落入暗部"

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE, spec)

    assert "景深：moderate" in prompt
    assert "焦点：三人面部与中央绳结" in prompt
    assert "背景成像：后墙与围观人群逐层虚化" in prompt
    assert "光源：顶部冷白荧光灯" in prompt
    assert "光位：人物正上方" in prompt
    assert "光色：冷白色" in prompt
    assert "场景明暗：地面明亮，车库深处落入暗部" in prompt


def test_renderer_derives_head_cropped_staging() -> None:
    spec = make_spec()
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    moment = frame.characters[0]
    moment.framing = CharacterFraming.HEAD_CROPPED_TORSO
    moment.placement = "右前景"
    moment.facing = "朝向镜头"
    moment.visible_appearance = "灰上衣包裹的肩胸和双臂"
    moment.expression = None

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE, spec)

    assert "头部被裁切、躯干入画" in prompt
    assert "表情1" not in prompt


def test_renderer_sanitizes_internal_ids_in_natural_text() -> None:
    spec = make_spec(female_count=1, male_count=1)
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]
    theme.setting.location = "T01-C01与T01-C02所在的大厅"
    frame.characters[0].facing = "朝向T01-C02"

    prompt = render_prompt(theme, frame, OutputLanguage.CHINESE, spec)

    assert "T01-C" not in prompt
    assert "女1与男1所在的大厅" in prompt
    assert "朝向男1" in prompt


def test_renderer_produces_english_prompt() -> None:
    spec = make_spec(
        output_language=OutputLanguage.ENGLISH,
        female_count=1,
        male_count=1,
    )
    theme = make_themes(spec)[0]
    frame = make_frame_batch(spec, theme).frames[0]

    prompt = render_prompt(theme, frame, OutputLanguage.ENGLISH, spec)

    assert prompt.startswith("Live-action photography")
    assert "Location:" in prompt
    assert "Depth of field:" in prompt
    assert "Woman 1:" in prompt
    assert "Man 1:" in prompt
