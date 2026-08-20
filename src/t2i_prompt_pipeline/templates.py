"""Language-aware authoring requests used by the generation module."""

from __future__ import annotations

import json

from t2i_prompt_pipeline.contracts import brief_route_points
from t2i_prompt_pipeline.models import (
    CastPlan,
    Foundation,
    Frame,
    FrameMode,
    GenerationSpec,
    GenerationStage,
    ResolvedRuleSet,
    Theme,
    format_character_id,
)
from t2i_prompt_pipeline.providers.base import ChatMessage
from t2i_prompt_pipeline.variation_plans import build_variation_plan


def foundation_messages(
    spec: GenerationSpec,
    rules: ResolvedRuleSet,
    validation_issues: tuple[str, ...] = (),
) -> list[ChatMessage]:
    request = {
        "brief": spec.brief,
        "cast_constraints": {
            "female_count": spec.female_count,
            "male_count": spec.male_count,
        },
        "cast_default": {
            "member_count": 1,
            "gender": "女性",
        },
        "content_level": spec.content_level.value,
        "output_language": spec.output_language.value,
    }
    if validation_issues:
        request["validation_issues"] = list(validation_issues)
    return [
        ChatMessage(
            role="system",
            content=rules.text_for(GenerationStage.FOUNDATION),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(request, ensure_ascii=False),
        ),
    ]


def theme_batch_messages(
    spec: GenerationSpec,
    foundation: Foundation,
    theme_ids: tuple[str, ...],
    rules: ResolvedRuleSet,
    validation_issues: tuple[str, ...] = (),
    existing_themes: tuple[Theme, ...] = (),
) -> list[ChatMessage]:
    character_count = foundation.cast_plan.member_count
    character_ids = {
        theme_id: [
            format_character_id(theme_id, index)
            for index in range(1, character_count + 1)
        ]
        for theme_id in theme_ids
    }
    request = {
        "brief": spec.brief,
        "content_level": spec.content_level.value,
        "output_language": spec.output_language.value,
        "style_constraints": foundation.style_constraints.model_dump(
            mode="json"
        ),
        "cast_plan": foundation.cast_plan.model_dump(mode="json"),
        "theme_ids": list(theme_ids),
        "character_ids": character_ids,
    }
    required_route_points = brief_route_points(spec.brief)
    if required_route_points:
        request["required_route_points"] = list(required_route_points)
    if validation_issues:
        request["validation_issues"] = list(validation_issues)
    if existing_themes:
        request["existing_themes"] = [
            theme.model_dump(mode="json") for theme in existing_themes
        ]
    return [
        ChatMessage(
            role="system",
            content=rules.text_for(GenerationStage.THEMES),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(request, ensure_ascii=False),
        ),
    ]


def frame_messages(
    spec: GenerationSpec,
    cast_plan: CastPlan,
    theme: Theme,
    frame_ids: tuple[str, ...],
    rules: ResolvedRuleSet,
    existing_frames: tuple[Frame, ...] = (),
    validation_issues: tuple[str, ...] = (),
) -> list[ChatMessage]:
    request = {
        "brief": spec.brief,
        "content_level": spec.content_level.value,
        "output_language": spec.output_language.value,
        "frame_mode": spec.frame_mode.value,
        "cast_plan": cast_plan.model_dump(mode="json"),
        "frame_ids": list(frame_ids),
        "available_character_ids": [
            character.character_id for character in theme.characters
        ],
        "theme": theme.model_dump(mode="json"),
        "existing_frames": [
            frame.model_dump(mode="json")
            for frame in existing_frames
        ],
    }
    if validation_issues:
        request["validation_issues"] = list(validation_issues)
    if spec.frame_mode == FrameMode.VARIATIONS:
        request["variation_plan"] = build_variation_plan(
            theme.theme_id,
            frame_ids,
        )
    return [
        ChatMessage(
            role="system",
            content=rules.text_for(GenerationStage.FRAMES),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(request, ensure_ascii=False),
        ),
    ]
