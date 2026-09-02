"""Resumable five-cast prompt batch for one shared brief."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import Field, ValidationError, model_validator

from t2i_prompt_pipeline.errors import (
    ConfigurationError,
    RunIncompleteError,
    RunStoreError,
)
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    FrameMode,
    GenerationSpec,
    Model,
    OutputLanguage,
    ThemeSimilarityState,
)
from t2i_prompt_pipeline.pipeline import PromptStudio
from t2i_prompt_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from t2i_prompt_pipeline.store import LocalRunStore, RunSnapshot
from t2i_prompt_pipeline.theme_similarity import ThemeSimilarityAnalyzer

CAST_MATRIX_THEME_COUNT = 100
CAST_MATRIX_FRAMES_PER_THEME = 6
CAST_MATRIX_BATCH_VERSION = "cast-matrix-100x6-v1"


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


class CastMatrixTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"


class CastMatrixTaskProgress(Model):
    status: CastMatrixTaskStatus = CastMatrixTaskStatus.PENDING
    run_id: str | None = None
    prompt_file: str | None = None

    @model_validator(mode="after")
    def fields_match_status(self) -> CastMatrixTaskProgress:
        if self.status == CastMatrixTaskStatus.PENDING:
            if self.run_id is not None or self.prompt_file is not None:
                raise ValueError("pending 任务不能记录 run 或提示词文件")
        elif self.status == CastMatrixTaskStatus.RUNNING:
            if self.run_id is None or self.prompt_file is not None:
                raise ValueError("running 任务必须只记录 run_id")
        elif self.run_id is None or self.prompt_file is None:
            raise ValueError("completed 任务必须记录 run_id 和提示词文件")
        return self


class CastMatrixBatchState(Model):
    batch_id: str
    tasks: dict[str, CastMatrixTaskProgress] = Field(
        min_length=len(CAST_MATRIX_CASTS),
        max_length=len(CAST_MATRIX_CASTS),
    )


@dataclass(frozen=True, slots=True)
class CastMatrixBatchResult:
    completed_tasks: int
    generated_frames: int
    prompt_files: tuple[str, ...]
    state_file: Path


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
    batch_id = _batch_id(tasks, rules_fingerprint)
    return runs_directory / f"cast-matrix-{batch_id[-12:]}.json"


async def run_cast_matrix_batch(
    config: AppConfig,
    tasks: tuple[CastMatrixTask, ...],
    state_file: Path,
    *,
    retry_delay_seconds: float = 5,
    on_progress: Callable[[str], None] | None = None,
) -> CastMatrixBatchResult:
    if retry_delay_seconds < 0:
        raise ConfigurationError("重试等待秒数不能为负数")
    resolved_state_file = state_file.resolve()
    batch_id = _batch_id(tasks, config.rules.fingerprint())
    state = _load_or_create_state(resolved_state_file, tasks, batch_id)
    store = LocalRunStore(
        config.runs_directory,
        config.prompts_directory,
    )
    if all(
        progress.status == CastMatrixTaskStatus.COMPLETED
        for progress in state.tasks.values()
    ):
        for task in tasks:
            _verify_existing_run(store, task, state.tasks[task.task_id])
        return _build_result(tasks, state, resolved_state_file)

    async with OpenAICompatibleProvider(config.provider) as author:
        similarity = (
            ThemeSimilarityAnalyzer(author, config.run_settings.theme_similarity)
            if config.run_settings.theme_similarity is not None
            else None
        )
        studio = PromptStudio(
            author,
            store,
            config.run_settings,
            theme_similarity=similarity,
            on_progress=on_progress,
        )
        await _drive_tasks(
            tasks,
            state,
            resolved_state_file,
            store,
            studio,
            config,
            retry_delay_seconds,
            on_progress,
        )

    return _build_result(tasks, state, resolved_state_file)


def _build_result(
    tasks: tuple[CastMatrixTask, ...],
    state: CastMatrixBatchState,
    state_file: Path,
) -> CastMatrixBatchResult:
    prompt_files = tuple(state.tasks[task.task_id].prompt_file for task in tasks)
    if any(prompt_file is None for prompt_file in prompt_files):
        raise ConfigurationError("人物矩阵结束时仍有任务缺少提示词文件")
    completed_prompt_files = tuple(
        prompt_file for prompt_file in prompt_files if prompt_file is not None
    )
    return CastMatrixBatchResult(
        completed_tasks=len(completed_prompt_files),
        generated_frames=(
            len(completed_prompt_files)
            * CAST_MATRIX_THEME_COUNT
            * CAST_MATRIX_FRAMES_PER_THEME
        ),
        prompt_files=completed_prompt_files,
        state_file=state_file,
    )


async def _drive_tasks(
    tasks: tuple[CastMatrixTask, ...],
    state: CastMatrixBatchState,
    state_file: Path,
    store: LocalRunStore,
    studio: PromptStudio,
    config: AppConfig,
    retry_delay_seconds: float,
    on_progress: Callable[[str], None] | None,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    total = len(tasks)
    for index, task in enumerate(tasks, start=1):
        progress = state.tasks[task.task_id]
        if progress.status == CastMatrixTaskStatus.COMPLETED:
            _verify_existing_run(store, task, progress)
            _emit(
                on_progress,
                f"[{index}/{total}] 已完成，跳过：{task.cast.description}",
            )
            continue

        if progress.run_id is None:
            progress = _create_task_run(store, task, config)
            state.tasks[task.task_id] = progress
            _write_state(state_file, state)
        else:
            _verify_existing_run(store, task, progress)

        while True:
            _emit(
                on_progress,
                f"[{index}/{total}] 生成：{task.cast.description} / "
                f"run {progress.run_id}",
            )
            try:
                archived = await studio.resume(progress.run_id)
            except RunIncompleteError as exc:
                snapshot = store.inspect(exc.run_id)
                if _similarity_exhausted(snapshot):
                    progress = _create_task_run(store, task, config)
                    state.tasks[task.task_id] = progress
                    _write_state(state_file, state)
                    _emit(
                        on_progress,
                        f"[{index}/{total}] 原 run 相似度重生成已耗尽，"
                        f"改用新 run {progress.run_id}",
                    )
                else:
                    _emit(
                        on_progress,
                        f"[{index}/{total}] 尚缺 {exc.missing_themes} 个 Theme、"
                        f"{exc.missing_frames} 个 Frame，等待后继续同一 run",
                    )
                if retry_delay_seconds:
                    await sleep(retry_delay_seconds)
                continue

            progress = CastMatrixTaskProgress(
                status=CastMatrixTaskStatus.COMPLETED,
                run_id=archived.run_id,
                prompt_file=archived.prompt_file,
            )
            state.tasks[task.task_id] = progress
            _write_state(state_file, state)
            break


def _create_task_run(
    store: LocalRunStore,
    task: CastMatrixTask,
    config: AppConfig,
) -> CastMatrixTaskProgress:
    snapshot = store.create(
        task.spec,
        config.run_settings,
        config.rules,
    )
    return CastMatrixTaskProgress(
        status=CastMatrixTaskStatus.RUNNING,
        run_id=snapshot.run_id,
    )


def _similarity_exhausted(snapshot: RunSnapshot) -> bool:
    report = snapshot.theme_similarity_report
    return report is not None and report.state == ThemeSimilarityState.EXHAUSTED


def _build_cast_brief(brief: str, cast: CastMatrixCast) -> str:
    separator = "" if brief.endswith(("。", "！", "？", ".", "!", "?")) else "。"
    return (
        f"{brief}{separator}"
        f"本组只出现{cast.description}，所有人物均为清醒、自愿参与的成年人。"
        "人物外貌、服饰与互动关系在同一主题的六个连续画面中保持一致。"
    )


def _batch_id(
    tasks: tuple[CastMatrixTask, ...],
    rules_fingerprint: str,
) -> str:
    encoded = json.dumps(
        {
            "version": CAST_MATRIX_BATCH_VERSION,
            "rules_fingerprint": rules_fingerprint,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "spec": task.spec.model_dump(mode="json"),
                }
                for task in tasks
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"{CAST_MATRIX_BATCH_VERSION}-{hashlib.sha256(encoded).hexdigest()}"


def _load_or_create_state(
    path: Path,
    tasks: tuple[CastMatrixTask, ...],
    batch_id: str,
) -> CastMatrixBatchState:
    expected_ids = {task.task_id for task in tasks}
    if not path.exists():
        state = CastMatrixBatchState(
            batch_id=batch_id,
            tasks={task.task_id: CastMatrixTaskProgress() for task in tasks},
        )
        _write_state(path, state)
        return state
    if not path.is_file():
        raise ConfigurationError(f"批次状态路径不是文件：{path}")
    try:
        state = CastMatrixBatchState.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError) as exc:
        raise ConfigurationError(f"批次状态文件无效：{path}：{exc}") from exc
    if state.batch_id != batch_id or set(state.tasks) != expected_ids:
        raise ConfigurationError("批次状态与当前 brief、content level 或规则不匹配")
    return state


def _verify_existing_run(
    store: LocalRunStore,
    task: CastMatrixTask,
    progress: CastMatrixTaskProgress,
) -> None:
    if progress.run_id is None:
        raise ConfigurationError(f"任务 {task.task_id} 缺少 run_id")
    snapshot = store.inspect(progress.run_id)
    if snapshot.spec != task.spec:
        raise ConfigurationError(
            f"任务 {task.task_id} 的 run {progress.run_id} 请求不匹配"
        )
    if progress.status == CastMatrixTaskStatus.COMPLETED and snapshot.completed is None:
        raise ConfigurationError(
            f"任务 {task.task_id} 被标记完成，但 run {progress.run_id} 尚未完成"
        )
    if (
        snapshot.completed is not None
        and progress.prompt_file is not None
        and snapshot.completed.prompt_file != progress.prompt_file
    ):
        raise ConfigurationError(f"任务 {task.task_id} 的提示词文件记录不匹配")


def _write_state(path: Path, state: CastMatrixBatchState) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}-",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                state.model_dump(mode="json"),
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        raise RunStoreError(f"无法保存批次状态：{path}：{exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)
