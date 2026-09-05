"""Five-cast task definitions for the shared batch executor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from t2i_prompt_pipeline.batch import (
    BatchLimits,
    BatchRecovery,
    BatchResult,
    BatchTask,
    batch_fingerprint,
    run_batch,
)
from t2i_prompt_pipeline.errors import ConfigurationError
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    FrameMode,
    GenerationSpec,
    OutputLanguage,
)

CAST_MATRIX_THEME_COUNT = 100
CAST_MATRIX_FRAMES_PER_THEME = 6


@dataclass(frozen=True, slots=True)
class CastMatrixCast:
    slug: str
    description: str
    female_count: int
    male_count: int


@dataclass(frozen=True, slots=True)
class CastMatrixTask:
    task_id: str
    cast: CastMatrixCast
    spec: GenerationSpec


CAST_MATRIX_CASTS = (
    CastMatrixCast("one_woman", "一名年满二十一岁的成年女性", 1, 0),
    CastMatrixCast("two_women", "两名年满二十一岁的成年女性", 2, 0),
    CastMatrixCast("three_women", "三名年满二十一岁的成年女性", 3, 0),
    CastMatrixCast(
        "one_woman_one_man",
        "一名年满二十一岁的成年女性和一名年满二十一岁的成年男性",
        1,
        1,
    ),
    CastMatrixCast(
        "two_women_one_man",
        "两名年满二十一岁的成年女性和一名年满二十一岁的成年男性",
        2,
        1,
    ),
)


def build_cast_matrix_tasks(
    brief: str,
    content_level: ContentLevel,
) -> tuple[CastMatrixTask, ...]:
    shared_brief = brief.strip()
    if not shared_brief:
        raise ConfigurationError("brief 不能为空")
    return tuple(
        CastMatrixTask(
            task_id=cast.slug,
            cast=cast,
            spec=GenerationSpec(
                brief=_build_cast_brief(shared_brief, cast),
                theme_count=CAST_MATRIX_THEME_COUNT,
                frames_per_theme=CAST_MATRIX_FRAMES_PER_THEME,
                female_count=cast.female_count,
                male_count=cast.male_count,
                content_level=content_level,
                frame_mode=FrameMode.SEQUENTIAL,
                output_language=OutputLanguage.CHINESE,
            ),
        )
        for cast in CAST_MATRIX_CASTS
    )


def default_cast_matrix_state_file(
    runs_directory: Path,
    tasks: tuple[CastMatrixTask, ...],
    rules_fingerprint: str,
) -> Path:
    batch_id = batch_fingerprint(_batch_tasks(tasks), rules_fingerprint)
    return runs_directory / f"cast-matrix-{batch_id[-12:]}.json"


async def run_cast_matrix_batch(
    config: AppConfig,
    tasks: tuple[CastMatrixTask, ...],
    state_file: Path,
    *,
    limits: BatchLimits | None = None,
    retry_delay_seconds: float = 5,
    on_progress: Callable[[str], None] | None = None,
) -> BatchResult:
    return await run_batch(
        config,
        _batch_tasks(tasks),
        state_file,
        recovery=BatchRecovery.RETRY,
        limits=limits,
        retry_delay_seconds=retry_delay_seconds,
        on_progress=on_progress,
    )


def _batch_tasks(tasks: tuple[CastMatrixTask, ...]) -> tuple[BatchTask, ...]:
    return tuple(
        BatchTask(task.task_id, task.spec, task.cast.description) for task in tasks
    )


def _build_cast_brief(brief: str, cast: CastMatrixCast) -> str:
    separator = "" if brief.endswith(("。", "！", "？", ".", "!", "?")) else "。"
    return (
        f"{brief}{separator}"
        f"本组只出现{cast.description}，所有人物均为清醒、自愿参与的成年人。"
        "人物外貌、服饰与互动关系在同一主题的六个连续画面中保持一致。"
    )
