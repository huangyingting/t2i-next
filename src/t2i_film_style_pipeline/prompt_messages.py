"""Compile immutable film prompt rules with dynamic generation payloads."""

from __future__ import annotations

import json

from t2i_film_style_pipeline.prompt_models import (
    FilmPromptRequest,
    FilmPromptRuleSet,
    FilmPromptStage,
    NarrativeFrame,
    NarrativeTheme,
)
from t2i_film_style_pipeline.prompt_provider import ChatMessage


def _cast_constraints(request: FilmPromptRequest) -> dict[str, int | None]:
    return {
        "female_count": request.female_count,
        "male_count": request.male_count,
    }


def theme_messages(
    request: FilmPromptRequest,
    rules: FilmPromptRuleSet,
    *,
    start_index: int,
    count: int,
    existing_themes: list[NarrativeTheme],
    semantic_name: str | None = None,
    program_assigns_ids: bool = False,
) -> list[ChatMessage]:
    theme_ids = [f"T{index:03d}" for index in range(start_index, start_index + count)]
    identity_payload = (
        {"theme_count": count, "program_assigns_theme_ids": True}
        if program_assigns_ids
        else {"theme_ids": theme_ids}
    )
    return [
        ChatMessage(
            role="system",
            content=rules.text_for(FilmPromptStage.THEMES),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "film_context": request.context,
                    "cast_constraints": _cast_constraints(request),
                    "content_level": request.content_level.value,
                    "output_language": request.output_language.value,
                    "semantic_name": semantic_name,
                    **identity_payload,
                    "frames_per_theme": request.frames_per_theme,
                    "existing_themes": [
                        theme.model_dump(mode="json") for theme in existing_themes
                    ],
                },
                ensure_ascii=False,
            ),
        ),
    ]


def frame_messages(
    request: FilmPromptRequest,
    theme: NarrativeTheme,
    rules: FilmPromptRuleSet,
    *,
    requested_frame_ids: list[str],
    accepted_frames: list[NarrativeFrame],
) -> list[ChatMessage]:
    return [
        ChatMessage(
            role="system",
            content=rules.text_for(FilmPromptStage.FRAMES),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "film_context": request.context,
                    "cast_constraints": _cast_constraints(request),
                    "content_level": request.content_level.value,
                    "output_language": request.output_language.value,
                    "theme": theme.model_dump(mode="json"),
                    "frames_per_theme": request.frames_per_theme,
                    "requested_frame_slots": requested_frame_ids,
                    "program_assigns_frame_ids": True,
                    "accepted_frame_prose": [
                        frame.prose for frame in accepted_frames
                    ],
                    "frame_batch_format": (
                        "Return exactly one <FRAME>...</FRAME> block for each "
                        "requested_frame_slots item, in the listed order."
                    ),
                },
                ensure_ascii=False,
            ),
        ),
    ]
