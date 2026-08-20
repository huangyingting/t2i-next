from __future__ import annotations

from typing import Any

from t2i_prompt_pipeline.authoring_rules import resolve_rules
from t2i_prompt_pipeline.models import (
    Camera,
    CastMember,
    CastPlan,
    Character,
    CharacterMoment,
    Foundation,
    Frame,
    FrameBatch,
    Gender,
    GenerationSpec,
    OutputLanguage,
    ResolvedRuleSet,
    RunSettings,
    StyleConstraints,
    Theme,
    format_character_id,
    format_frame_id,
    format_theme_id,
)


def make_spec(
    *,
    brief: str = "两名成年人在室内交谈",
    theme_count: int = 1,
    frames_per_theme: int = 1,
    female_count: int | None = 1,
    male_count: int | None = 0,
    output_language: OutputLanguage = OutputLanguage.CHINESE,
) -> GenerationSpec:
    return GenerationSpec(
        brief=brief,
        theme_count=theme_count,
        frames_per_theme=frames_per_theme,
        female_count=female_count,
        male_count=male_count,
        output_language=output_language,
    )


def make_rules(spec: GenerationSpec) -> ResolvedRuleSet:
    return resolve_rules(spec)


def make_settings(**changes: Any) -> RunSettings:
    values = {
        "provider_signature": "test-provider",
        "output_token_limit": 16384,
        "theme_batch_size": 5,
        "generation_retries": 2,
        "max_concurrency": 4,
        **changes,
    }
    return RunSettings.model_validate(values)


def make_theme(spec: GenerationSpec, theme_index: int) -> Theme:
    theme_id = format_theme_id(theme_index, spec.theme_count)
    is_english = spec.output_language == OutputLanguage.ENGLISH
    female_count = (
        spec.female_count if spec.female_count is not None else 1
    )
    male_count = spec.male_count if spec.male_count is not None else 0
    genders = [
        *([Gender.FEMALE] * female_count),
        *([Gender.MALE] * male_count),
    ]
    return Theme(
        theme_id=theme_id,
        title=f"Theme {theme_index}" if is_english else f"主题{theme_index}",
        scene=(
            f"A quiet room {theme_index} with a wooden table by the window"
            if is_english
            else f"安静的室内{theme_index}，木桌靠窗"
        ),
        style=(
            "Cinematic photography balances warm amber and slate blue, "
            "soft side light, "
            "moderate contrast, matte wood, and brushed brass textures."
            if is_english
            else (
                "电影摄影以暖琥珀为主色、灰蓝为辅助色，柔和侧光形成中等反差，"
                "哑光木材与拉丝黄铜呈现细腻质感。"
            )
        ),
        characters=[
            Character(
                character_id=format_character_id(theme_id, index),
                label=(
                    (
                        f"Woman {index}"
                        if is_english
                        else f"女{index}"
                    )
                    if gender == Gender.FEMALE
                    else (
                        f"Man {index - female_count}"
                        if is_english
                        else f"男{index - female_count}"
                    )
                ),
                gender=gender,
                age=25 + index,
                appearance=(
                    f"Character {index} stable appearance"
                    if is_english
                    else f"人物{index}的稳定外貌"
                ),
                outfit=(
                    f"Character {index} base outfit"
                    if is_english
                    else f"人物{index}的基础服饰"
                ),
            )
            for index, gender in enumerate(genders, start=1)
        ],
    )


def make_foundation(spec: GenerationSpec | None = None) -> Foundation:
    is_english = (
        spec is not None
        and spec.output_language == OutputLanguage.ENGLISH
    )
    female_count = (
        spec.female_count
        if spec is not None and spec.female_count is not None
        else 1
    )
    male_count = (
        spec.male_count
        if spec is not None and spec.male_count is not None
        else 0
    )
    return Foundation(
        semantic_name="quiet_cafe_conversation",
        style_constraints=StyleConstraints(required_phrases=[]),
        cast_plan=CastPlan(
            members=[
                *[
                    CastMember(
                        role=("Conversation participant" if is_english else "交谈者"),
                        gender=Gender.FEMALE,
                    )
                    for _ in range(female_count)
                ],
                *[
                    CastMember(
                        role=("Conversation participant" if is_english else "交谈者"),
                        gender=Gender.MALE,
                    )
                    for _ in range(male_count)
                ],
            ]
        ),
    )


def make_themes(spec: GenerationSpec) -> list[Theme]:
    return [
        make_theme(spec, index)
        for index in range(1, spec.theme_count + 1)
    ]


def make_frame_batch(
    spec: GenerationSpec,
    theme: Theme,
) -> FrameBatch:
    is_english = spec.output_language == OutputLanguage.ENGLISH
    return FrameBatch(
        theme_id=theme.theme_id,
        frames=[
            Frame(
                frame_id=format_frame_id(
                    theme.theme_id,
                    index,
                    spec.frames_per_theme,
                ),
                camera=Camera(
                    shot="Medium shot" if is_english else "中景",
                    view="Eye-level view" if is_english else "平视",
                    composition=(
                        f"Composition {index}"
                        if is_english
                        else f"构图{index}"
                    ),
                ),
                characters=[
                    CharacterMoment(
                        character_id=character.character_id,
                        expression=(
                            f"Expression {index}"
                            if is_english
                            else f"表情{index}"
                        ),
                        action=(
                            f"Action {index}"
                            if is_english
                            else f"动作{index}"
                        ),
                    )
                    for character in theme.characters
                ],
                details=(
                    f"Current detail {index}"
                    if is_english
                    else f"当前细节{index}"
                ),
            )
            for index in range(1, spec.frames_per_theme + 1)
        ],
    )
