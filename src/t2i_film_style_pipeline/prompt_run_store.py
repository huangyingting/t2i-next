"""Crash-safe run records and incremental film prompt checkpoints."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from itertools import count
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from t2i_film_style_pipeline.errors import (
    FilmPromptRunNotFoundError,
    FilmStyleStorageError,
)
from t2i_film_style_pipeline.prompt_models import (
    FilmPromptRequest,
    FilmPromptResult,
    FilmPromptRuleSet,
    FilmPromptStage,
    NarrativeFrame,
    NarrativeFrameSequence,
    NarrativeTheme,
    SemanticName,
    TokenUsage,
)
from t2i_film_style_pipeline.prompt_persistence import durable_mkdir, fsync_directory
from t2i_film_style_pipeline.prompt_provider import FilmPromptProviderSettings
from t2i_film_style_pipeline.prompt_storage import (
    PublishedFilmPrompt,
    publish_film_prompt,
)

_RUN_ID = re.compile(r"\d{8}T\d{6}Z-[a-f0-9]{8}")
_COUNT_NAMES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
)


def _cast_slug(request: FilmPromptRequest) -> str:
    female_count = request.female_count
    male_count = request.male_count
    if female_count is None and male_count is None:
        return "unspecified_cast"
    if female_count is not None and male_count is not None:
        parts = []
        if female_count:
            parts.append(
                f"{_COUNT_NAMES[female_count]}_"
                f"{'woman' if female_count == 1 else 'women'}"
            )
        if male_count:
            parts.append(
                f"{_COUNT_NAMES[male_count]}_{'man' if male_count == 1 else 'men'}"
            )
        return "_".join(parts)

    parts = []
    if female_count is None:
        parts.append("unspecified_women")
    else:
        parts.append(
            f"{_COUNT_NAMES[female_count]}_{'woman' if female_count == 1 else 'women'}"
        )
    if male_count is None:
        parts.append("unspecified_men")
    else:
        parts.append(
            f"{_COUNT_NAMES[male_count]}_{'man' if male_count == 1 else 'men'}"
        )
    return "_".join(parts)


def _numeric_cast_slug(request: FilmPromptRequest) -> str:
    def count_slug(
        value: int | None,
        singular: str,
        plural: str,
    ) -> str:
        if value is None:
            return f"unspecified_{plural}"
        noun = singular if value == 1 else plural
        return f"{value}_{noun}"

    return "_".join(
        (
            count_slug(request.female_count, "woman", "women"),
            count_slug(request.male_count, "man", "men"),
        )
    )


def _normalize_source_prompt_stem(value: str) -> str:
    normalized = re.sub(r"[^\w-]+", "_", value.lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_-")
    if not normalized:
        raise FilmStyleStorageError(
            "提示词文件名必须至少包含一个可用于输出文件名的字符"
        )
    return normalized


def _prompt_filename_stem(
    request: FilmPromptRequest,
    semantic_name: str,
) -> str:
    if request.prompt_filename_stem is not None:
        return _normalize_source_prompt_stem(request.prompt_filename_stem)
    if request.source_prompt_stem is None:
        return f"{semantic_name}_{_cast_slug(request)}"
    return "_".join(
        (
            _normalize_source_prompt_stem(request.source_prompt_stem),
            request.content_level.value,
            _numeric_cast_slug(request),
        )
    )


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FilmPromptRunStatus(StrEnum):
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class FilmPromptAttemptOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PROVIDER_ERROR = "provider_error"
    TRUNCATED = "truncated"


class ThemeOutputMode(StrEnum):
    STRUCTURED_WITH_IDS = "structured_with_ids"
    STRUCTURED_WITHOUT_IDS = "structured_without_ids"


class FilmPromptRunSettings(_Model):
    provider: FilmPromptProviderSettings
    concurrency: int = Field(default=8, ge=1, le=32)
    generation_retries: int = Field(default=2, ge=0, le=5)
    theme_batch_size: int = Field(default=10, ge=1, le=10)
    theme_output_tokens: int = Field(default=6000, ge=512, le=65536)
    frame_output_tokens: int = Field(default=32768, ge=512, le=65536)
    theme_output_mode: ThemeOutputMode = ThemeOutputMode.STRUCTURED_WITH_IDS


class FilmPromptRunManifest(_Model):
    run_id: str
    status: FilmPromptRunStatus
    created_at: str
    updated_at: str
    settings: FilmPromptRunSettings
    rules_fingerprint: str
    prompts_directory: str
    semantic_name: SemanticName | None = None
    prompt_file: str | None = None
    error: str | None = None


class FilmPromptAttempt(_Model):
    occurred_at: str
    stage: FilmPromptStage
    operation_id: str
    requested_ids: list[str] = Field(max_length=100)
    attempt: int = Field(ge=1)
    max_output_tokens: int = Field(ge=512, le=65536)
    outcome: FilmPromptAttemptOutcome
    accepted_ids: list[str] = Field(max_length=100)
    issues: list[str]
    duration_ms: int = Field(ge=0)
    error: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)


@dataclass(frozen=True, slots=True)
class CompletedFilmPromptRun:
    run_id: str
    request_file: Path
    result_file: Path
    published: PublishedFilmPrompt
    result: FilmPromptResult


@dataclass(frozen=True, slots=True)
class FilmPromptRunSnapshot:
    run_id: str
    request: FilmPromptRequest
    rules: FilmPromptRuleSet
    manifest: FilmPromptRunManifest
    themes: tuple[NarrativeTheme, ...]
    frames: dict[str, NarrativeFrameSequence]
    completed: CompletedFilmPromptRun | None = None


@dataclass(frozen=True, slots=True)
class FilmPromptRunSummary:
    run_id: str
    status: FilmPromptRunStatus
    created_at: str
    updated_at: str
    context: str
    theme_count: int
    frames_per_theme: int
    prompt_file: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class FilmPromptRunListing:
    runs: tuple[FilmPromptRunSummary, ...]
    unreadable: tuple[str, ...]


class LocalFilmPromptRunStore:
    """Filesystem-backed film prompt runs with atomic per-artifact checkpoints."""

    def __init__(
        self,
        runs_root: Path,
        prompts_root: Path | None = None,
    ) -> None:
        self._runs_root = runs_root.resolve()
        self._prompts_root = (
            prompts_root.resolve() if prompts_root is not None else None
        )

    def create(
        self,
        request: FilmPromptRequest,
        settings: FilmPromptRunSettings,
        rules: FilmPromptRuleSet,
    ) -> FilmPromptRunSnapshot:
        if self._prompts_root is None:
            raise FilmStyleStorageError("创建 film prompt run 需要 prompts 目录")
        run_id = self._new_run_id()
        final_directory = self._runs_root / run_id
        staging: Path | None = None
        now = self._now()
        manifest = FilmPromptRunManifest(
            run_id=run_id,
            status=FilmPromptRunStatus.RUNNING,
            created_at=now,
            updated_at=now,
            settings=settings,
            rules_fingerprint=rules.fingerprint(),
            prompts_directory=str(self._prompts_root),
        )
        try:
            durable_mkdir(self._runs_root)
            staging = Path(tempfile.mkdtemp(prefix=f".{run_id}-", dir=self._runs_root))
            durable_mkdir(staging / "themes")
            durable_mkdir(staging / "frames")
            durable_mkdir(staging / "attempts")
            _write_json(staging / "request.json", request.model_dump(mode="json"))
            _write_json(staging / "rules.json", rules.model_dump(mode="json"))
            _write_json(
                staging / "manifest.json",
                manifest.model_dump(mode="json"),
            )
            os.replace(staging, final_directory)
            fsync_directory(self._runs_root)
        except (OSError, FilmStyleStorageError) as exc:
            if staging is not None and staging.exists():
                try:
                    shutil.rmtree(staging)
                except OSError as cleanup_error:
                    raise FilmStyleStorageError(
                        f"无法创建 film prompt run：{exc}；同时无法清理 staging："
                        f"{cleanup_error}"
                    ) from exc
            raise FilmStyleStorageError(f"无法创建 film prompt run：{exc}") from exc
        return FilmPromptRunSnapshot(
            run_id=run_id,
            request=request,
            rules=rules,
            manifest=manifest,
            themes=(),
            frames={},
        )

    def inspect(self, run_id: str) -> FilmPromptRunSnapshot:
        directory = self._run_directory(run_id)
        try:
            request = FilmPromptRequest.model_validate_json(
                (directory / "request.json").read_text(encoding="utf-8")
            )
            rules = FilmPromptRuleSet.model_validate_json(
                (directory / "rules.json").read_text(encoding="utf-8")
            )
            manifest = FilmPromptRunManifest.model_validate_json(
                (directory / "manifest.json").read_text(encoding="utf-8")
            )
            if manifest.run_id != run_id:
                raise FilmStyleStorageError(f"Run {run_id} 的 manifest run_id 不匹配")
            if rules.fingerprint() != manifest.rules_fingerprint:
                raise FilmStyleStorageError(f"Run {run_id} 的 rules.json 指纹不匹配")
            themes = self._load_themes(directory, request)
            frames = self._load_frames(directory, request, themes)
            if manifest.status == FilmPromptRunStatus.COMPLETED:
                completed = self._load_completed(
                    directory,
                    manifest,
                    request,
                    themes,
                    frames,
                )
                return FilmPromptRunSnapshot(
                    run_id=run_id,
                    request=request,
                    rules=rules,
                    manifest=manifest,
                    themes=themes,
                    frames=frames,
                    completed=completed,
                )
        except FilmStyleStorageError:
            raise
        except (OSError, ValidationError, ValueError) as exc:
            raise FilmStyleStorageError(
                f"Run {run_id} 的 checkpoint 损坏：{exc}"
            ) from exc
        return FilmPromptRunSnapshot(
            run_id=run_id,
            request=request,
            rules=rules,
            manifest=manifest,
            themes=themes,
            frames=frames,
        )

    def list_runs(self) -> FilmPromptRunListing:
        if not self._runs_root.is_dir():
            return FilmPromptRunListing(runs=(), unreadable=())
        summaries: list[FilmPromptRunSummary] = []
        unreadable: list[str] = []
        for directory in sorted(self._runs_root.iterdir(), reverse=True):
            if not directory.is_dir() or _RUN_ID.fullmatch(directory.name) is None:
                continue
            try:
                request_text = (directory / "request.json").read_text(encoding="utf-8")
                json.loads(request_text)
            except (OSError, json.JSONDecodeError):
                unreadable.append(directory.name)
                continue
            try:
                manifest = self._read_manifest(directory)
                if manifest.run_id != directory.name:
                    raise FilmStyleStorageError("manifest run_id 与目录名称不匹配")
                request = FilmPromptRequest.model_validate_json(request_text)
            except (OSError, ValidationError, FilmStyleStorageError):
                unreadable.append(directory.name)
                continue
            summaries.append(
                FilmPromptRunSummary(
                    run_id=manifest.run_id,
                    status=manifest.status,
                    created_at=manifest.created_at,
                    updated_at=manifest.updated_at,
                    context=request.context,
                    theme_count=request.theme_count,
                    frames_per_theme=request.frames_per_theme,
                    prompt_file=manifest.prompt_file,
                    error=manifest.error,
                )
            )
        summaries.sort(key=lambda item: item.created_at, reverse=True)
        return FilmPromptRunListing(
            runs=tuple(summaries),
            unreadable=tuple(unreadable),
        )

    def start(self, run_id: str) -> FilmPromptRunSnapshot:
        snapshot = self.inspect(run_id)
        if snapshot.completed is not None:
            return snapshot
        self._write_manifest(
            self._run_directory(run_id),
            snapshot.manifest.model_copy(
                update={
                    "status": FilmPromptRunStatus.RUNNING,
                    "updated_at": self._now(),
                    "error": None,
                }
            ),
        )
        return self.inspect(run_id)

    def checkpoint_themes(
        self,
        run_id: str,
        themes: list[NarrativeTheme],
        semantic_name: str,
    ) -> None:
        snapshot = self.inspect(run_id)
        if snapshot.completed is not None:
            raise FilmStyleStorageError(f"Run {run_id} 已完成，不能写入 checkpoint")
        expected_start = len(snapshot.themes) + 1
        expected_ids = [
            f"T{index:03d}"
            for index in range(expected_start, expected_start + len(themes))
        ]
        actual_ids = [theme.theme_id for theme in themes]
        if actual_ids != expected_ids:
            raise FilmStyleStorageError(
                f"Theme checkpoint 不连续：expected={expected_ids}, actual={actual_ids}"
            )
        directory = self._run_directory(run_id)
        if (
            snapshot.manifest.semantic_name is not None
            and snapshot.manifest.semantic_name != semantic_name
        ):
            raise FilmStyleStorageError("Theme checkpoint semantic_name 与 run 不一致")
        if snapshot.manifest.semantic_name is None:
            self._write_manifest(
                directory,
                snapshot.manifest.model_copy(
                    update={
                        "semantic_name": semantic_name,
                        "updated_at": self._now(),
                    }
                ),
            )
        for theme in themes:
            _write_json(
                directory / "themes" / f"{theme.theme_id}.json",
                theme.model_dump(mode="json"),
            )
        self._touch_manifest(directory)

    def checkpoint_frame(
        self,
        run_id: str,
        theme_id: str,
        frame: NarrativeFrame,
    ) -> None:
        try:
            directory = self._run_directory(run_id)
            request = FilmPromptRequest.model_validate_json(
                (directory / "request.json").read_text(encoding="utf-8")
            )
            if not (directory / "themes" / f"{theme_id}.json").is_file():
                raise FilmStyleStorageError(
                    f"Frame checkpoint 缺少 Theme checkpoint：{theme_id}"
                )
            expected_ids = {
                f"F{index:02d}" for index in range(1, request.frames_per_theme + 1)
            }
            if frame.frame_id not in expected_ids:
                raise FilmStyleStorageError(
                    f"{theme_id} Frame checkpoint ID 不匹配：{frame.frame_id}"
                )
            frame_directory = directory / "frames" / theme_id
            durable_mkdir(frame_directory)
            checkpoint = frame_directory / f"{frame.frame_id}.json"
            if checkpoint.exists():
                persisted = NarrativeFrame.model_validate_json(
                    checkpoint.read_text(encoding="utf-8")
                )
                if persisted != frame:
                    raise FilmStyleStorageError(
                        f"{theme_id}-{frame.frame_id} checkpoint 已存在且内容不同"
                    )
                return
            _write_json(checkpoint, frame.model_dump(mode="json"))
            self._touch_manifest(directory)
        except FilmStyleStorageError:
            raise
        except (OSError, ValidationError) as exc:
            raise FilmStyleStorageError(
                f"Run {run_id} 无法写入 Frame checkpoint：{exc}"
            ) from exc

    def record_attempt(self, run_id: str, attempt: FilmPromptAttempt) -> None:
        directory = self._run_directory(run_id) / "attempts"
        operation = re.sub(r"[^A-Za-z0-9_-]+", "_", attempt.operation_id)
        path = directory / f"{operation}-{attempt.attempt:04d}.json"
        if path.exists():
            raise FilmStyleStorageError(
                f"Run {run_id} 的 generation attempt 已存在：{path.name}"
            )
        _write_json(path, attempt.model_dump(mode="json"))

    def attempts(self, run_id: str) -> tuple[FilmPromptAttempt, ...]:
        directory = self._run_directory(run_id) / "attempts"
        try:
            attempts = [
                FilmPromptAttempt.model_validate_json(path.read_text(encoding="utf-8"))
                for path in directory.glob("*.json")
            ]
        except (OSError, ValidationError) as exc:
            raise FilmStyleStorageError(
                f"Run {run_id} 的 generation attempt 损坏：{exc}"
            ) from exc
        attempts.sort(
            key=lambda item: (
                item.occurred_at,
                item.operation_id,
                item.attempt,
            )
        )
        return tuple(attempts)

    def total_usage(self, run_id: str) -> TokenUsage:
        usage = TokenUsage()
        for attempt in self.attempts(run_id):
            usage += attempt.usage
        return usage

    def now(self) -> str:
        return self._now()

    def fail(self, run_id: str, error: str) -> None:
        directory = self._run_directory(run_id)
        manifest = self._read_manifest(directory)
        if manifest.status == FilmPromptRunStatus.COMPLETED:
            return
        self._write_manifest(
            directory,
            manifest.model_copy(
                update={
                    "status": FilmPromptRunStatus.FAILED,
                    "updated_at": self._now(),
                    "error": error,
                }
            ),
        )

    def complete(
        self,
        run_id: str,
        result: FilmPromptResult,
    ) -> CompletedFilmPromptRun:
        snapshot = self.inspect(run_id)
        if snapshot.completed is not None:
            return snapshot.completed
        if result.run_id != run_id or result.request != snapshot.request:
            raise FilmStyleStorageError("完成结果与 film prompt run 不匹配")
        if (
            snapshot.manifest.semantic_name is None
            or result.semantic_name != snapshot.manifest.semantic_name
        ):
            raise FilmStyleStorageError(
                "完成结果的 semantic_name 与 film prompt run 不匹配"
            )
        if len(snapshot.themes) != snapshot.request.theme_count:
            raise FilmStyleStorageError("Theme checkpoint 尚未完整")
        if len(snapshot.frames) != snapshot.request.theme_count:
            raise FilmStyleStorageError("Frame checkpoint 尚未完整")
        expected_themes = [
            (
                theme,
                snapshot.frames[theme.theme_id].frames,
            )
            for theme in snapshot.themes
        ]
        actual_themes = [(item.theme, item.frames) for item in result.themes]
        if actual_themes != expected_themes:
            raise FilmStyleStorageError("完成结果与已保存 checkpoint 不匹配")
        if result.usage != self.total_usage(run_id):
            raise FilmStyleStorageError("完成结果的 token usage 与运行记录不匹配")
        directory = self._run_directory(run_id)
        result_file = directory / "result.json"
        completion_manifest = snapshot.manifest
        prompt_path = (
            Path(completion_manifest.prompt_file)
            if completion_manifest.prompt_file is not None
            else self._allocate_prompt_path(
                _prompt_filename_stem(
                    result.request,
                    result.semantic_name,
                ),
                (
                    Path(completion_manifest.prompts_directory)
                    / completion_manifest.created_at[:10]
                    / result.request.content_level.value
                ),
            )
        )
        if completion_manifest.prompt_file is None:
            completion_manifest = completion_manifest.model_copy(
                update={
                    "prompt_file": str(prompt_path),
                    "updated_at": self._now(),
                }
            )
            try:
                self._write_manifest(directory, completion_manifest)
            except FilmStyleStorageError:
                self._remove_reservation(
                    prompt_path.parent / f".{prompt_path.name}.reserve"
                )
                raise
        _write_json(result_file, result.model_dump(mode="json"))
        published = publish_film_prompt(result, prompt_path)
        self._remove_reservation(prompt_path.parent / f".{prompt_path.name}.reserve")
        manifest = completion_manifest.model_copy(
            update={
                "status": FilmPromptRunStatus.COMPLETED,
                "updated_at": self._now(),
                "prompt_file": str(published.prompt_file),
                "error": None,
            }
        )
        self._write_manifest(directory, manifest)
        return CompletedFilmPromptRun(
            run_id=run_id,
            request_file=directory / "request.json",
            result_file=result_file,
            published=published,
            result=result,
        )

    @contextmanager
    def lock(self, run_id: str) -> Iterator[None]:
        path = self._run_directory(run_id) / ".lock"
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise FilmStyleStorageError(f"无法打开 run 锁 {path}：{exc}") from exc
        acquired = False
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise FilmStyleStorageError(
                    f"Run {run_id} 正在被另一个进程使用"
                ) from exc
            acquired = True
            yield
        finally:
            try:
                if acquired:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _load_themes(
        self,
        directory: Path,
        request: FilmPromptRequest,
    ) -> tuple[NarrativeTheme, ...]:
        themes: list[NarrativeTheme] = []
        for path in sorted((directory / "themes").glob("T*.json")):
            theme = NarrativeTheme.model_validate_json(path.read_text(encoding="utf-8"))
            if path.stem != theme.theme_id:
                raise FilmStyleStorageError(
                    f"Theme checkpoint 文件名与内容不匹配：{path.name}"
                )
            themes.append(theme)
        expected_ids = [f"T{index:03d}" for index in range(1, len(themes) + 1)]
        actual_ids = [theme.theme_id for theme in themes]
        if actual_ids != expected_ids or len(themes) > request.theme_count:
            raise FilmStyleStorageError(f"Theme checkpoint 序列损坏：{actual_ids}")
        return tuple(themes)

    def _load_frames(
        self,
        directory: Path,
        request: FilmPromptRequest,
        themes: tuple[NarrativeTheme, ...],
    ) -> dict[str, NarrativeFrameSequence]:
        theme_ids = {theme.theme_id for theme in themes}
        expected_frame_ids = {
            f"F{index:02d}" for index in range(1, request.frames_per_theme + 1)
        }
        frames: dict[str, NarrativeFrameSequence] = {}
        for theme_directory in sorted((directory / "frames").glob("T*")):
            if not theme_directory.is_dir():
                raise FilmStyleStorageError(
                    f"Frame checkpoint 使用了已废弃的文件格式：{theme_directory.name}"
                )
            if theme_directory.name not in theme_ids:
                raise FilmStyleStorageError(
                    f"Frame checkpoint 缺少 Theme checkpoint：{theme_directory.name}"
                )
            sequence_frames: list[NarrativeFrame] = []
            for path in sorted(theme_directory.glob("F*.json")):
                frame = NarrativeFrame.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                if path.stem != frame.frame_id:
                    raise FilmStyleStorageError(
                        f"Frame checkpoint 文件名与内容不匹配：{path.name}"
                    )
                sequence_frames.append(frame)
            actual_ids = [frame.frame_id for frame in sequence_frames]
            if (
                len(actual_ids) != len(set(actual_ids))
                or not set(actual_ids).issubset(expected_frame_ids)
                or actual_ids != sorted(actual_ids)
            ):
                raise FilmStyleStorageError(
                    f"{theme_directory.name} Frame checkpoint ID 损坏：{actual_ids}"
                )
            if sequence_frames:
                frames[theme_directory.name] = NarrativeFrameSequence(
                    frames=sequence_frames
                )
        return frames

    def _load_completed(
        self,
        directory: Path,
        manifest: FilmPromptRunManifest,
        request: FilmPromptRequest,
        themes: tuple[NarrativeTheme, ...],
        frames: dict[str, NarrativeFrameSequence],
    ) -> CompletedFilmPromptRun:
        if manifest.prompt_file is None:
            raise FilmStyleStorageError("已完成 run 缺少发布文件路径")
        result_file = directory / "result.json"
        try:
            result = FilmPromptResult.model_validate_json(
                result_file.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise FilmStyleStorageError(
                f"已完成 run 无法读取 result.json：{exc}"
            ) from exc
        if result.run_id != manifest.run_id or result.request != request:
            raise FilmStyleStorageError("已完成 run 的 result 与 manifest 不匹配")
        if (
            manifest.semantic_name is None
            or result.semantic_name != manifest.semantic_name
        ):
            raise FilmStyleStorageError(
                "已完成 run 的 semantic_name 与 manifest 不匹配"
            )
        if (
            len(themes) != request.theme_count
            or len(frames) != request.theme_count
            or any(
                len(sequence.frames) != request.frames_per_theme
                for sequence in frames.values()
            )
        ):
            raise FilmStyleStorageError("已完成 run 的 checkpoint 不完整")
        expected_themes = [(theme, frames[theme.theme_id].frames) for theme in themes]
        actual_themes = [(item.theme, item.frames) for item in result.themes]
        if actual_themes != expected_themes:
            raise FilmStyleStorageError("已完成 run 的 result 与 checkpoint 不匹配")
        if result.usage != self.total_usage(manifest.run_id):
            raise FilmStyleStorageError(
                "已完成 run 的 result token usage 与 attempt 记录不匹配"
            )
        prompt_file = Path(manifest.prompt_file)
        if not prompt_file.is_file():
            raise FilmStyleStorageError("已完成 run 的发布文件不存在")
        return CompletedFilmPromptRun(
            run_id=manifest.run_id,
            request_file=directory / "request.json",
            result_file=result_file,
            published=PublishedFilmPrompt(
                prompt_file=prompt_file,
            ),
            result=result,
        )

    def _allocate_prompt_path(
        self,
        filename_stem: str,
        prompts_directory: Path,
    ) -> Path:
        try:
            durable_mkdir(prompts_directory)
        except OSError as exc:
            raise FilmStyleStorageError(f"无法创建提示词目录：{exc}") from exc
        for sequence in count(1):
            filename = f"{filename_stem}_{sequence:04d}.txt"
            final_path = prompts_directory / filename
            reservation = prompts_directory / f".{filename}.reserve"
            try:
                descriptor = os.open(
                    reservation,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                continue
            except OSError as exc:
                raise FilmStyleStorageError(f"无法分配提示词文件序号：{exc}") from exc
            try:
                os.close(descriptor)
                fsync_directory(prompts_directory)
                if final_path.exists():
                    self._remove_reservation(reservation)
                    continue
                return final_path
            except OSError as exc:
                raise FilmStyleStorageError(f"无法分配提示词文件序号：{exc}") from exc
        raise FilmStyleStorageError("无法分配提示词文件序号")

    @staticmethod
    def _remove_reservation(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
            fsync_directory(path.parent)
        except OSError as exc:
            raise FilmStyleStorageError(
                f"无法清理提示词文件 reservation：{exc}"
            ) from exc

    def _run_directory(self, run_id: str) -> Path:
        if _RUN_ID.fullmatch(run_id) is None:
            raise FilmPromptRunNotFoundError(f"无效的 film prompt run ID：{run_id}")
        directory = self._runs_root / run_id
        if not directory.is_dir():
            raise FilmPromptRunNotFoundError(f"Film prompt run 不存在：{run_id}")
        return directory

    def _read_manifest(self, directory: Path) -> FilmPromptRunManifest:
        try:
            return FilmPromptRunManifest.model_validate_json(
                (directory / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise FilmStyleStorageError(
                f"无法读取 {directory.name} manifest：{exc}"
            ) from exc

    def _write_manifest(
        self,
        directory: Path,
        manifest: FilmPromptRunManifest,
    ) -> None:
        _write_json(
            directory / "manifest.json",
            manifest.model_dump(mode="json"),
        )

    def _touch_manifest(self, directory: Path) -> None:
        manifest = self._read_manifest(directory)
        self._write_manifest(
            directory,
            manifest.model_copy(update={"updated_at": self._now()}),
        )

    def _new_run_id(self) -> str:
        for _ in range(100):
            run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
            if not (self._runs_root / run_id).exists():
                return run_id
        raise FilmStyleStorageError("无法分配唯一的 film prompt run ID")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def _write_text(path: Path, text: str) -> None:
    temporary: Path | None = None
    try:
        durable_mkdir(path.parent)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    except OSError as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_error:
                raise FilmStyleStorageError(
                    f"无法原子写入 {path}：{exc}；同时无法清理临时文件：{cleanup_error}"
                ) from exc
        raise FilmStyleStorageError(f"无法原子写入 {path}：{exc}") from exc
