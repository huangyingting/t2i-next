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

_THEME_NOVELTY_AXES = (
    "优先使用账本中较少出现的原作作品、场景或人物组合",
    "改变稳定的人物关系、权力方向或主动回应关系，但不固定 Frame 动作",
    "选择账本中较少出现的内容路径或互动范围",
    "改变场景内部的空间层次、人物距离和调度范围",
    "改变主要景别、机位方向、透视和焦点层级的组合",
    "改变主光来源、明暗关系、色彩重音和材质重点",
    "改变当前事件、环境状态或关键器物在画面中的作用",
    "改变前景框景、遮挡方式、空气状态和成片运动倾向",
)


def _cast_constraints(request: FilmPromptRequest) -> dict[str, int | None]:
    return {
        "female_count": request.female_count,
        "male_count": request.male_count,
    }


def _theme_excerpt(value: str, *, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[:limit].rstrip()


def _theme_diversity_ledger(
    existing_themes: list[NarrativeTheme],
) -> dict[str, object]:
    return {
        "used_titles": [theme.title for theme in existing_themes],
        "used_theme_signatures": [
            {
                "theme_id": theme.theme_id,
                "premise_excerpt": _theme_excerpt(theme.premise, limit=180),
                "style_excerpt": _theme_excerpt(theme.style, limit=140),
            }
            for theme in existing_themes
        ],
    }


def _current_theme_novelty_targets(
    *,
    start_index: int,
    count: int,
) -> list[dict[str, object]]:
    targets = []
    axis_count = len(_THEME_NOVELTY_AXES)
    for offset in range(count):
        absolute_index = start_index + offset
        first_axis = (absolute_index - 1) % axis_count
        second_axis = (absolute_index * 3 + 1) % axis_count
        if second_axis == first_axis:
            second_axis = (second_axis + 1) % axis_count
        targets.append(
            {
                "output_position": offset + 1,
                "novelty_priorities": [
                    _THEME_NOVELTY_AXES[first_axis],
                    _THEME_NOVELTY_AXES[second_axis],
                ],
            }
        )
    return targets


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
                    "diversity_ledger": _theme_diversity_ledger(
                        existing_themes
                    ),
                    "current_batch_novelty_targets": (
                        _current_theme_novelty_targets(
                            start_index=start_index,
                            count=count,
                        )
                    ),
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
