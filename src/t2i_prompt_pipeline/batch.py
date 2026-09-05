"""One durable, bounded executor for declarative generation batches."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, NoReturn

from pydantic import AwareDatetime, Field, ValidationError, model_validator

from t2i_prompt_pipeline.errors import (
    BatchPausedError,
    ConfigurationError,
    RunIncompleteError,
)
from t2i_prompt_pipeline.models import (
    AppConfig,
    GenerationSpec,
    Model,
    RunSettings,
    Text,
    ThemeSimilarityState,
)
from t2i_prompt_pipeline.persistence import exclusive_file_lock, write_json
from t2i_prompt_pipeline.pipeline import PromptStudio
from t2i_prompt_pipeline.providers.openai_compatible import OpenAICompatibleProvider
from t2i_prompt_pipeline.store import LocalRunStore
from t2i_prompt_pipeline.theme_similarity import ThemeSimilarityAnalyzer


@dataclass(frozen=True, slots=True)
class BatchTask:
    task_id: str
    spec: GenerationSpec
    label: str


class BatchRecovery(StrEnum):
    STOP = "stop"
    RETRY = "retry"


class BatchLimits(Model):
    max_task_attempts: int = Field(default=10, ge=1, le=1000)
    max_replacement_runs: int = Field(default=2, ge=0, le=100)
    max_duration_seconds: float = Field(
        default=86400, gt=0, le=31536000, allow_inf_nan=False
    )


class BatchTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"


class BatchTaskProgress(Model):
    status: BatchTaskStatus = BatchTaskStatus.PENDING
    run_ids: list[Text] = Field(default_factory=list)
    attempts: int = Field(default=0, ge=0)
    prompt_file: Text | None = None
    last_error: str | None = None

    @property
    def run_id(self) -> str | None:
        return self.run_ids[-1] if self.run_ids else None

    @model_validator(mode="after")
    def fields_match_status(self) -> BatchTaskProgress:
        if len(self.run_ids) != len(set(self.run_ids)):
            raise ValueError("任务 run ID 不能重复")
        if self.status == BatchTaskStatus.PENDING:
            if self.run_ids or self.attempts or self.prompt_file is not None:
                raise ValueError("pending 任务不能记录执行结果")
        elif not self.run_ids:
            raise ValueError("已开始任务必须记录 run ID")
        if (self.status == BatchTaskStatus.COMPLETED) != (
            self.prompt_file is not None
        ):
            raise ValueError("只有 completed 任务必须记录提示词文件")
        return self


class BatchState(Model):
    format: Literal["bounded-batch-v1"]
    batch_id: Text
    created_at: AwareDatetime
    runs_directory: Text
    prompts_directory: Text
    settings: RunSettings
    recovery: BatchRecovery
    limits: BatchLimits
    tasks: dict[str, BatchTaskProgress] = Field(min_length=1)
    pause_reason: str | None = None


@dataclass(frozen=True, slots=True)
class BatchResult:
    completed_tasks: int
    generated_frames: int
    prompt_files: tuple[str, ...]
    state_file: Path


def batch_fingerprint(
    tasks: tuple[BatchTask, ...], rules_fingerprint: str
) -> str:
    payload = {
        "format": "bounded-batch-v1",
        "rules_fingerprint": rules_fingerprint,
        "tasks": [
            {"task_id": task.task_id, "spec": task.spec.model_dump(mode="json")}
            for task in tasks
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


async def run_batch(
    config: AppConfig,
    tasks: tuple[BatchTask, ...],
    state_file: Path,
    *,
    recovery: BatchRecovery = BatchRecovery.STOP,
    limits: BatchLimits | None = None,
    retry_delay_seconds: float = 5,
    on_progress: Callable[[str], None] | None = None,
) -> BatchResult:
    """Execute tasks; omitted limits retain the persisted budget on resume."""
    ids = [task.task_id for task in tasks]
    if not ids or any(not item.strip() for item in ids) or len(ids) != len(set(ids)):
        raise ConfigurationError("批次任务 ID 必须非空且唯一")
    rule_selectors = ("content_level", "frame_mode", "output_language")
    if any(
        getattr(task.spec, field) != getattr(config.spec, field)
        for task in tasks
        for field in rule_selectors
    ):
        raise ConfigurationError("批次任务必须共用内容尺度、Frame 模式和输出语言")
    if not math.isfinite(retry_delay_seconds) or retry_delay_seconds < 0:
        raise ConfigurationError("重试等待秒数必须是非负有限数")
    path = state_file.resolve()
    with exclusive_file_lock(path.with_name(f"{path.name}.lock")):
        state = _load_state(path, config, tasks, recovery, limits)
        store = LocalRunStore(
            Path(state.runs_directory), Path(state.prompts_directory)
        )
        _reconcile(store, state, tasks, config, path)
        if all(
            progress.status == BatchTaskStatus.COMPLETED
            for progress in state.tasks.values()
        ):
            return _result(tasks, state, path)

        next_task = next(
            task for task in tasks
            if state.tasks[task.task_id].status != BatchTaskStatus.COMPLETED
        )
        progress = state.tasks[next_task.task_id]
        _check_attempts(state, progress, path, next_task.task_id)
        _replacement_needed(store, state, progress, path, next_task.task_id)
        # A wall-clock start is persisted, so restarts cannot replenish time.
        deadline = asyncio.timeout(_remaining_seconds(state))
        try:
            async with deadline:
                async with OpenAICompatibleProvider(config.provider) as author:
                    similarity = (
                        ThemeSimilarityAnalyzer(author, state.settings.theme_similarity)
                        if state.settings.theme_similarity is not None
                        else None
                    )
                    studio = PromptStudio(
                        author,
                        store,
                        state.settings,
                        theme_similarity=similarity,
                        on_progress=on_progress,
                    )
                    await _drive(
                        studio, store, config, tasks, state, path,
                        retry_delay_seconds, on_progress,
                    )
        except TimeoutError:
            if not deadline.expired():
                raise
            _pause(state, path, "批次总时限已耗尽")
        return _result(tasks, state, path)


def _load_state(
    path: Path,
    config: AppConfig,
    tasks: tuple[BatchTask, ...],
    recovery: BatchRecovery,
    limits: BatchLimits | None,
) -> BatchState:
    fingerprint = batch_fingerprint(tasks, config.rules.fingerprint())
    if not path.exists():
        state = BatchState(
            format="bounded-batch-v1",
            batch_id=fingerprint,
            created_at=_now(),
            runs_directory=str(config.runs_directory.resolve()),
            prompts_directory=str(config.prompts_directory.resolve()),
            settings=config.run_settings,
            recovery=recovery,
            limits=limits if limits is not None else BatchLimits(),
            tasks={task.task_id: BatchTaskProgress() for task in tasks},
        )
        _save(path, state)
        return state
    try:
        state = BatchState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as exc:
        raise ConfigurationError(f"批次状态文件无效：{path}：{exc}") from exc
    if state.batch_id != fingerprint or set(state.tasks) != {
        task.task_id for task in tasks
    }:
        raise ConfigurationError("批次状态与当前任务或规则不匹配")
    if (
        state.runs_directory != str(config.runs_directory.resolve())
        or state.prompts_directory != str(config.prompts_directory.resolve())
        or state.recovery != recovery
    ):
        raise ConfigurationError("批次目录或恢复策略与已保存状态不匹配")
    state.settings.ensure_resumable_with(config.run_settings)
    run_ids = [
        run_id for progress in state.tasks.values() for run_id in progress.run_ids
    ]
    if len(run_ids) != len(set(run_ids)):
        raise ConfigurationError("不同批次任务不能共享 run ID")
    if limits is not None:
        overrides = limits.model_dump(exclude_unset=True)
        updated = BatchLimits.model_validate({
            **state.limits.model_dump(), **overrides,
        })
        if any(
            value < getattr(state.limits, name)
            for name, value in updated.model_dump().items()
        ):
            raise ConfigurationError("恢复时只能提高批次预算，不能降低或重置")
        if updated != state.limits:
            state.limits = updated
            _save(path, state)
    return state


def _reconcile(
    store: LocalRunStore,
    state: BatchState,
    tasks: tuple[BatchTask, ...],
    config: AppConfig,
    path: Path,
) -> None:
    for task in tasks:
        progress = state.tasks[task.task_id]
        if progress.run_id is None:
            continue
        snapshot = store.inspect(progress.run_id)
        if (
            snapshot.spec != task.spec
            or snapshot.rules != config.rules
            or snapshot.settings != state.settings
        ):
            raise ConfigurationError(f"任务 {task.task_id} 的 run 请求或配置不匹配")
        if snapshot.completed is None:
            if progress.status == BatchTaskStatus.COMPLETED:
                raise ConfigurationError(f"任务 {task.task_id} 的 run 尚未完成")
            continue
        if (
            progress.prompt_file is not None
            and progress.prompt_file != snapshot.completed.prompt_file
        ):
            raise ConfigurationError(f"任务 {task.task_id} 的提示词文件记录不匹配")
        if progress.status != BatchTaskStatus.COMPLETED:
            progress.status = BatchTaskStatus.COMPLETED
            progress.prompt_file = snapshot.completed.prompt_file
            progress.last_error = None
            _save(path, state)


async def _drive(
    studio: PromptStudio,
    store: LocalRunStore,
    config: AppConfig,
    tasks: tuple[BatchTask, ...],
    state: BatchState,
    path: Path,
    retry_delay_seconds: float,
    on_progress: Callable[[str], None] | None,
) -> None:
    for index, task in enumerate(tasks, start=1):
        progress = state.tasks[task.task_id]
        prefix = f"[{index}/{len(tasks)}] {task.label}"
        if progress.status == BatchTaskStatus.COMPLETED:
            _emit(on_progress, f"{prefix}：已完成，跳过")
            continue
        while True:
            _check_attempts(state, progress, path, task.task_id)
            replace = _replacement_needed(
                store, state, progress, path, task.task_id
            )
            if progress.run_id is None or replace:
                snapshot = store.create(task.spec, state.settings, config.rules)
                progress.run_ids.append(snapshot.run_id)
                progress.status = BatchTaskStatus.RUNNING
                _save(path, state)
                if replace:
                    _emit(on_progress, f"{prefix}：改用新 run {snapshot.run_id}")
            run_id = progress.run_id
            assert run_id is not None
            # Reserve the attempt before any paid work, including after a crash.
            progress.attempts += 1
            progress.last_error = None
            state.pause_reason = None
            _save(path, state)
            _check_duration(state, path)
            _emit(
                on_progress,
                f"{prefix}：生成 run {run_id}，第 {progress.attempts} 次",
            )
            try:
                archived = await studio.resume(run_id)
            except RunIncompleteError as exc:
                progress.last_error = "; ".join((str(exc), *exc.causes[-3:]))
                _save(path, state)
                if state.recovery == BatchRecovery.STOP:
                    _pause(state, path, progress.last_error)
                _check_attempts(state, progress, path, task.task_id)
                _replacement_needed(store, state, progress, path, task.task_id)
                _emit(on_progress, f"{prefix}：尚未完成，等待后继续")
                await asyncio.sleep(retry_delay_seconds)
                continue
            progress.status = BatchTaskStatus.COMPLETED
            progress.prompt_file = archived.prompt_file
            _save(path, state)
            break


def _replacement_needed(
    store: LocalRunStore,
    state: BatchState,
    progress: BatchTaskProgress,
    path: Path,
    task_id: str,
) -> bool:
    if progress.run_id is None or state.recovery != BatchRecovery.RETRY:
        return False
    report = store.inspect(progress.run_id).theme_similarity_report
    if report is None or report.state != ThemeSimilarityState.EXHAUSTED:
        return False
    if len(progress.run_ids) - 1 >= state.limits.max_replacement_runs:
        _pause(state, path, f"{task_id} 替代 run 次数已耗尽")
    return True


def _check_attempts(
    state: BatchState,
    progress: BatchTaskProgress,
    path: Path,
    task_id: str,
) -> None:
    _check_duration(state, path)
    if progress.attempts >= state.limits.max_task_attempts:
        _pause(state, path, f"{task_id} 累计 run 尝试次数已耗尽")


def _check_duration(state: BatchState, path: Path) -> None:
    if _remaining_seconds(state) <= 0:
        _pause(state, path, "批次总时限已耗尽")


def _remaining_seconds(state: BatchState) -> float:
    return state.limits.max_duration_seconds - (
        _now() - state.created_at
    ).total_seconds()


def _now() -> datetime:
    return datetime.now(UTC)


def _pause(state: BatchState, path: Path, reason: str) -> NoReturn:
    state.pause_reason = reason
    _save(path, state)
    raise BatchPausedError(path, reason)


def _save(path: Path, state: BatchState) -> None:
    write_json(path, state.model_dump(mode="json"))


def _result(
    tasks: tuple[BatchTask, ...], state: BatchState, path: Path
) -> BatchResult:
    prompt_files = tuple(state.tasks[task.task_id].prompt_file for task in tasks)
    if any(prompt_file is None for prompt_file in prompt_files):
        raise ConfigurationError("批次结束时仍有任务缺少提示词文件")
    if state.pause_reason is not None:
        state.pause_reason = None
        _save(path, state)
    return BatchResult(
        completed_tasks=len(tasks),
        generated_frames=sum(
            task.spec.theme_count * task.spec.frames_per_theme for task in tasks
        ),
        prompt_files=tuple(item for item in prompt_files if item is not None),
        state_file=path,
    )


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)
