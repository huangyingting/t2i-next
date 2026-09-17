"""Compile immutable story rules with dynamic generation payloads."""

from __future__ import annotations

import json

from t2i_story_pipeline.models import (
    NarrativeFrame,
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
    count: int,
    existing_themes: list[NarrativeTheme],
    semantic_name: str | None = None,
) -> list[ChatMessage]:
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
                    "theme_count": count,
                    "program_assigns_theme_ids": True,
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
    requested_frame_ids: list[str],
    accepted_frames: list[NarrativeFrame],
) -> list[ChatMessage]:
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
                    "requested_frame_slots": requested_frame_ids,
                    "program_assigns_frame_ids": True,
                    "accepted_frames": [
                        frame.model_dump(mode="json") for frame in accepted_frames
                    ],
                    "frame_batch_format": (
                        "Return exactly one <FRAME>...</FRAME> block per requested "
                        "slot, in order. Tags delimit prose; do not output IDs or JSON."
                    ),
                },
                ensure_ascii=False,
            ),
        ),
    ]
