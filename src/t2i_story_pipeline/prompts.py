"""Compile immutable story rules with dynamic generation payloads."""

from __future__ import annotations

import json

from t2i_story_pipeline.models import (
    NarrativeTheme,
    StoryRequest,
    StoryRuleSet,
    StoryStage,
)
from t2i_story_pipeline.provider import ChatMessage


def _cast_constraints(request: StoryRequest) -> dict[str, int | None]:
    return {
        "female_count": request.female_count,
        "male_count": request.male_count,
    }


def theme_messages(
    request: StoryRequest,
    rules: StoryRuleSet,
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
            content=rules.text_for(StoryStage.THEMES),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story": request.story,
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
    request: StoryRequest,
    theme: NarrativeTheme,
    rules: StoryRuleSet,
    *,
    frame_id: str | None = None,
    existing_frames: list[str] | None = None,
) -> list[ChatMessage]:
    frame_ids = [f"F{index:02d}" for index in range(1, request.frames_per_theme + 1)]
    frame_payload = (
        {
            "current_frame_id": frame_id,
            "program_assigns_frame_id": True,
            "existing_frame_prose": existing_frames or [],
        }
        if frame_id is not None
        else {"frame_ids": frame_ids}
    )
    return [
        ChatMessage(
            role="system",
            content=rules.text_for(StoryStage.FRAMES),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story": request.story,
                    "cast_constraints": _cast_constraints(request),
                    "content_level": request.content_level.value,
                    "output_language": request.output_language.value,
                    "theme": theme.model_dump(mode="json"),
                    "frames_per_theme": request.frames_per_theme,
                    **frame_payload,
                },
                ensure_ascii=False,
            ),
        ),
    ]
