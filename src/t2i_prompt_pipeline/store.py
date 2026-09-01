"""Crash-safe incremental run checkpoints."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from t2i_prompt_pipeline.contracts import (
    normalize_checkpoint_graph,
)
from t2i_prompt_pipeline.errors import (
    GenerationContractError,
    RunNotFoundError,
    RunStoreError,
)
from t2i_prompt_pipeline.models import (
    ArchivedRun,
    Foundation,
    Frame,
    GenerationAttempt,
    GenerationResult,
    GenerationSpec,
    PromptBook,
    ResolvedRuleSet,
    RunManifest,
    RunSettings,
    RunStatus,
    RunSummary,
    Theme,
    ThemeSimilarityReport,
    ThemeSimilarityState,
    safe_run_id,
)
from t2i_prompt_pipeline.renderers import render_book

type CheckpointArtifact = Foundation | Theme | Frame


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    run_id: str
    spec: GenerationSpec
    settings: RunSettings
    rules: ResolvedRuleSet
    foundation: Foundation | None
    themes: dict[str, Theme]
    frames: dict[str, Frame]
    manifest: RunManifest
    theme_similarity_report: ThemeSimilarityReport | None = None
    completed: ArchivedRun | None = None


@dataclass(frozen=True, slots=True)
class RunListing:
    runs: tuple[RunSummary, ...]
    unreadable: tuple[str, ...]


class RunStore(Protocol):
    def create(
        self,
        spec: GenerationSpec,
        settings: RunSettings,
        rules: ResolvedRuleSet,
    ) -> RunSnapshot: ...

    def inspect(self, run_id: str) -> RunSnapshot: ...

    def start(self, run_id: str) -> RunSnapshot: ...

    def checkpoint(
        self,
        run_id: str,
        artifact: CheckpointArtifact,
    ) -> None: ...

    def record_attempt(
        self,
        run_id: str,
        attempt: GenerationAttempt,
    ) -> None: ...

    def attempts(self, run_id: str) -> tuple[GenerationAttempt, ...]: ...

    def record_theme_similarity(
        self,
        run_id: str,
        report: ThemeSimilarityReport,
    ) -> None: ...

    def apply_theme_rejections(
        self,
        run_id: str,
        report: ThemeSimilarityReport,
    ) -> None: ...

    def clear_theme_similarity(
        self,
        run_id: str,
    ) -> None: ...

    def fail(self, run_id: str, error: str) -> None: ...

    def complete(
        self,
        run_id: str,
        result: GenerationResult,
    ) -> ArchivedRun: ...


class LocalRunStore:
    """Filesystem adapter with per-artifact atomic commits.

    Only ``create`` records a prompts directory; every later stage republishes
    to the directory frozen in the run manifest. Callers that just resume or
    list existing runs therefore leave ``prompts_root`` unset.
    """

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
        spec: GenerationSpec,
        settings: RunSettings,
        rules: ResolvedRuleSet,
    ) -> RunSnapshot:
        if self._prompts_root is None:
            raise RunStoreError("创建 run 需要提示词目录")
        run_id = self._new_run_id()
        final_directory = self._runs_root / run_id
        staging: Path | None = None
        now = self._now()
        manifest = RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            created_at=now,
            updated_at=now,
            settings=settings,
            prompts_directory=str(self._prompts_root),
            rules_fingerprint=rules.fingerprint(),
        )
        try:
            self._runs_root.mkdir(parents=True, exist_ok=True)
            self._fsync_directory(self._runs_root.parent)
            staging = Path(
                tempfile.mkdtemp(
                    prefix=f".{run_id}-",
                    dir=self._runs_root,
                )
            )
            (staging / "themes").mkdir()
            (staging / "frames").mkdir()
            self._write_json(
                staging / "request.json",
                spec.model_dump(mode="json"),
            )
            self._write_json(
                staging / "manifest.json",
                manifest.model_dump(mode="json"),
            )
            self._write_json(
                staging / "rules.json",
                rules.model_dump(mode="json"),
            )
            self._write_text(staging / "attempts.jsonl", "")
            os.replace(staging, final_directory)
            self._fsync_directory(self._runs_root)
        except (OSError, RunStoreError) as exc:
            if staging is not None:
                try:
                    self._remove_tree(staging)
                except OSError as cleanup_error:
                    raise RunStoreError(
                        f"无法创建 run：{exc}；同时无法清理 staging："
                        f"{cleanup_error}"
                    ) from exc
            raise RunStoreError(f"无法创建 run：{exc}") from exc
        return RunSnapshot(
            run_id=run_id,
            spec=spec,
            settings=settings,
            rules=rules,
            foundation=None,
            themes={},
            frames={},
            manifest=manifest,
            theme_similarity_report=None,
        )

    def inspect(self, run_id: str) -> RunSnapshot:
        directory = self._run_directory(run_id)
        try:
            spec = GenerationSpec.model_validate_json(
                (directory / "request.json").read_text(encoding="utf-8")
            )
            manifest = RunManifest.model_validate_json(
                (directory / "manifest.json").read_text(encoding="utf-8")
            )
            rules = ResolvedRuleSet.model_validate_json(
                (directory / "rules.json").read_text(encoding="utf-8")
            )
            if manifest.run_id != run_id:
                raise RunStoreError(
                    f"Run {run_id} 的 manifest run_id 不匹配"
                )
            if rules.fingerprint() != manifest.rules_fingerprint:
                raise RunStoreError(
                    f"Run {run_id} 的 rules.json 指纹不匹配"
                )
            foundation_path = directory / "foundation.json"
            foundation = (
                Foundation.model_validate_json(
                    foundation_path.read_text(encoding="utf-8")
                )
                if foundation_path.exists()
                else None
            )
            similarity_path = directory / "theme-similarity.json"
            theme_similarity_report = (
                ThemeSimilarityReport.model_validate_json(
                    similarity_path.read_text(encoding="utf-8")
                )
                if similarity_path.exists()
                else None
            )
            completed: ArchivedRun | None = None
            if manifest.status == RunStatus.COMPLETED:
                completed = self._load_completed(
                    directory,
                    manifest,
                    spec,
                )
                themes = {
                    item.theme.theme_id: item.theme
                    for item in completed.result.book.themes
                }
                frames = {
                    frame.frame_id: frame
                    for item in completed.result.book.themes
                    for frame in item.frames
                }
            else:
                themes = {}
                for path in sorted((directory / "themes").glob("T*.json")):
                    theme = Theme.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                    if path.stem != theme.theme_id:
                        raise RunStoreError(
                            "Theme checkpoint 文件名与内容不匹配："
                            f"{path.name}"
                        )
                    themes[theme.theme_id] = theme
                frames = {}
                for path in sorted(
                    (directory / "frames").glob("T*-F*.json")
                ):
                    frame = Frame.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                    if path.stem != frame.frame_id:
                        raise RunStoreError(
                            "Frame checkpoint 文件名与内容不匹配："
                            f"{path.name}"
                        )
                    frames[frame.frame_id] = frame
                themes, frames = normalize_checkpoint_graph(
                    spec,
                    foundation,
                    themes,
                    frames,
                )
        except (OSError, ValidationError, GenerationContractError) as exc:
            raise RunStoreError(
                f"Run {run_id} 的 checkpoint 损坏：{exc}"
            ) from exc

        return RunSnapshot(
            run_id=run_id,
            spec=spec,
            settings=manifest.settings,
            rules=rules,
            foundation=foundation,
            themes=themes,
            frames=frames,
            manifest=manifest,
            theme_similarity_report=theme_similarity_report,
            completed=completed,
        )

    def list_runs(self) -> RunListing:
        """Summarise runs newest first, reading manifests but no checkpoints.

        A run whose manifest or request is unreadable is reported separately
        rather than dropped, so a corrupted run stays discoverable.
        """
        if not self._runs_root.is_dir():
            return RunListing(runs=(), unreadable=())
        summaries: list[RunSummary] = []
        unreadable: list[str] = []
        for directory in sorted(self._runs_root.iterdir(), reverse=True):
            if not directory.is_dir() or not safe_run_id(directory.name):
                continue
            try:
                manifest = self._read_manifest(directory)
                spec = GenerationSpec.model_validate_json(
                    (directory / "request.json").read_text(encoding="utf-8")
                )
            except (RunStoreError, OSError, ValidationError):
                unreadable.append(directory.name)
                continue
            summaries.append(
                RunSummary(
                    run_id=manifest.run_id,
                    status=manifest.status,
                    created_at=manifest.created_at,
                    updated_at=manifest.updated_at,
                    brief=spec.brief,
                    theme_count=spec.theme_count,
                    frames_per_theme=spec.frames_per_theme,
                    prompt_file=manifest.prompt_file,
                    error=manifest.error,
                )
            )
        summaries.sort(key=lambda summary: summary.created_at, reverse=True)
        return RunListing(runs=tuple(summaries), unreadable=tuple(unreadable))

    def start(self, run_id: str) -> RunSnapshot:
        snapshot = self.inspect(run_id)
        if snapshot.completed is not None:
            return snapshot
        manifest = snapshot.manifest.model_copy(
            update={
                "status": RunStatus.RUNNING,
                "updated_at": self._now(),
                "error": None,
            }
        )
        self._write_manifest(self._run_directory(run_id), manifest)
        return RunSnapshot(
            run_id=snapshot.run_id,
            spec=snapshot.spec,
            settings=snapshot.settings,
            rules=snapshot.rules,
            foundation=snapshot.foundation,
            themes=snapshot.themes,
            frames=snapshot.frames,
            manifest=manifest,
            theme_similarity_report=snapshot.theme_similarity_report,
        )

    def checkpoint(
        self,
        run_id: str,
        artifact: CheckpointArtifact,
    ) -> None:
        directory = self._run_directory(run_id)
        if isinstance(artifact, Foundation):
            path = directory / "foundation.json"
        elif isinstance(artifact, Theme):
            path = directory / "themes" / f"{artifact.theme_id}.json"
        elif isinstance(artifact, Frame):
            path = directory / "frames" / f"{artifact.frame_id}.json"
        else:
            raise TypeError(f"不支持的 checkpoint：{type(artifact).__name__}")
        self._write_json(path, artifact.model_dump(mode="json"))

    def record_attempt(
        self,
        run_id: str,
        attempt: GenerationAttempt,
    ) -> None:
        if attempt.operation_id is not None and any(
            recorded.operation_id == attempt.operation_id
            for recorded in self.attempts(run_id)
        ):
            return
        path = self._run_directory(run_id) / "attempts.jsonl"
        self._append_line(path, attempt.model_dump_json() + "\n")

    def attempts(self, run_id: str) -> tuple[GenerationAttempt, ...]:
        path = self._run_directory(run_id) / "attempts.jsonl"
        try:
            text = path.read_text(encoding="utf-8")
            if text and not text.endswith("\n"):
                last_complete_line = text.rfind("\n")
                text = (
                    text[: last_complete_line + 1]
                    if last_complete_line >= 0
                    else ""
                )
                self._write_text(path, text)
            lines = text.splitlines()
            return tuple(
                GenerationAttempt.model_validate_json(line)
                for line in lines
                if line
            )
        except (OSError, ValidationError) as exc:
            raise RunStoreError(
                f"Run {run_id} 的 attempts.jsonl 损坏：{exc}"
            ) from exc

    def record_theme_similarity(
        self,
        run_id: str,
        report: ThemeSimilarityReport,
    ) -> None:
        path = self._run_directory(run_id) / "theme-similarity.json"
        self._write_json(path, report.model_dump(mode="json"))

    def apply_theme_rejections(
        self,
        run_id: str,
        report: ThemeSimilarityReport,
    ) -> None:
        directory = self._run_directory(run_id)
        if report.state != ThemeSimilarityState.REJECTION_PENDING:
            raise RunStoreError(
                "只能应用 pending 状态的 Theme similarity rejection"
            )
        try:
            persisted = ThemeSimilarityReport.model_validate_json(
                (directory / "theme-similarity.json").read_text(
                    encoding="utf-8"
                )
            )
            if persisted.audit_id != report.audit_id:
                raise RunStoreError(
                    "Theme similarity rejection 与当前 report 不一致"
                )
            rejected_ids = tuple(
                rejection.rejected_theme_id
                for rejection in report.rejections
            )
            frames_directory = directory / "frames"
            themes_directory = directory / "themes"
            for theme_id in rejected_ids:
                for path in frames_directory.glob(
                    f"{theme_id}-F*.json"
                ):
                    path.unlink()
            self._fsync_directory(frames_directory)
            for theme_id in rejected_ids:
                (themes_directory / f"{theme_id}.json").unlink(
                    missing_ok=True
                )
            self._fsync_directory(themes_directory)
            self._write_json(
                directory / "theme-similarity.json",
                report.model_copy(
                    update={"state": ThemeSimilarityState.REGENERATING}
                ).model_dump(mode="json"),
            )
        except (OSError, ValidationError) as exc:
            raise RunStoreError(
                f"Run {run_id} 无法拒绝重复 Theme：{exc}"
            ) from exc

    def clear_theme_similarity(self, run_id: str) -> None:
        directory = self._run_directory(run_id)
        try:
            (directory / "theme-similarity.json").unlink(missing_ok=True)
            self._fsync_directory(directory)
        except OSError as exc:
            raise RunStoreError(
                f"Run {run_id} 无法清除 Theme similarity report：{exc}"
            ) from exc

    def fail(self, run_id: str, error: str) -> None:
        directory = self._run_directory(run_id)
        manifest = self._read_manifest(directory)
        self._write_manifest(
            directory,
            manifest.model_copy(
                update={
                    "status": RunStatus.FAILED,
                    "updated_at": self._now(),
                    "error": error,
                }
            ),
        )

    def complete(
        self,
        run_id: str,
        result: GenerationResult,
    ) -> ArchivedRun:
        directory = self._run_directory(run_id)
        manifest = self._read_manifest(directory)
        prompt_path = (
            Path(manifest.prompt_file)
            if manifest.prompt_file is not None
            else self._allocate_prompt_path(
                result.book.semantic_name,
                (
                    Path(manifest.prompts_directory)
                    / result.spec.content_level.value
                ),
            )
        )
        if manifest.prompt_file is None:
            manifest = manifest.model_copy(
                update={
                    "prompt_file": str(prompt_path),
                    "updated_at": self._now(),
                }
            )
            try:
                self._write_manifest(directory, manifest)
            except RunStoreError as exc:
                reservation = (
                    prompt_path.parent
                    / f".{prompt_path.name}.reserve"
                )
                try:
                    self._remove_reservation(reservation)
                except RunStoreError as cleanup_error:
                    raise RunStoreError(
                        f"{exc}；同时无法清理 reservation："
                        f"{cleanup_error}"
                    ) from exc
                raise

        self._write_json(
            directory / "book.json",
            result.book.model_dump(mode="json"),
        )
        self._write_text(prompt_path, self._prompt_text(result))
        reservation = prompt_path.parent / f".{prompt_path.name}.reserve"
        self._remove_reservation(reservation)
        manifest = manifest.model_copy(
            update={
                "status": RunStatus.COMPLETED,
                "updated_at": self._now(),
                "error": None,
            }
        )
        self._write_manifest(directory, manifest)
        return ArchivedRun(
            run_id=run_id,
            request_file=str(directory / "request.json"),
            book_file=str(directory / "book.json"),
            prompt_file=str(prompt_path),
            result=result,
        )

    def _load_completed(
        self,
        directory: Path,
        manifest: RunManifest,
        spec: GenerationSpec,
    ) -> ArchivedRun:
        if manifest.prompt_file is None:
            raise RunStoreError("已完成 run 缺少 prompt_file")
        try:
            book = PromptBook.model_validate_json(
                (directory / "book.json").read_text(encoding="utf-8")
            )
            result = GenerationResult(
                spec=spec,
                book=book,
                prompts=render_book(book, spec.output_language),
            )
        except (OSError, ValidationError) as exc:
            raise RunStoreError(f"已完成 run 无法读取：{exc}") from exc
        prompt_path = Path(manifest.prompt_file)
        if not prompt_path.is_file():
            raise RunStoreError(f"已完成 run 的提示词不存在：{prompt_path}")
        return ArchivedRun(
            run_id=manifest.run_id,
            request_file=str(directory / "request.json"),
            book_file=str(directory / "book.json"),
            prompt_file=str(prompt_path),
            result=result,
        )

    def _allocate_prompt_path(
        self,
        semantic_name: str,
        prompts_root: Path,
    ) -> Path:
        try:
            prompts_root.mkdir(parents=True, exist_ok=True)
            self._fsync_directory(prompts_root.parent)
        except OSError as exc:
            raise RunStoreError(
                f"无法创建提示词目录：{exc}"
            ) from exc
        for sequence in count(1):
            filename = f"{semantic_name}_{sequence:04d}.txt"
            final_path = prompts_root / filename
            reservation = prompts_root / f".{filename}.reserve"
            try:
                descriptor = os.open(
                    reservation,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                continue
            except OSError as exc:
                raise RunStoreError(
                    f"无法分配提示词文件序号：{exc}"
                ) from exc
            try:
                os.close(descriptor)
                self._fsync_directory(prompts_root)
                if final_path.exists():
                    self._remove_reservation(reservation)
                    continue
                return final_path
            except OSError as exc:
                try:
                    self._remove_reservation(reservation)
                except RunStoreError as cleanup_error:
                    raise RunStoreError(
                        f"无法提交提示词文件 reservation：{exc}；"
                        f"同时无法清理 reservation：{cleanup_error}"
                    ) from exc
                raise RunStoreError(
                    f"无法提交提示词文件 reservation：{exc}"
                ) from exc
        raise RunStoreError("无法分配提示词文件序号")

    def _run_directory(self, run_id: str) -> Path:
        if not safe_run_id(run_id):
            raise RunNotFoundError(f"无效的 run ID：{run_id}")
        directory = self._runs_root / run_id
        if not directory.is_dir():
            raise RunNotFoundError(f"Run 不存在：{run_id}")
        return directory

    def _read_manifest(self, directory: Path) -> RunManifest:
        try:
            return RunManifest.model_validate_json(
                (directory / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise RunStoreError(f"manifest 无法读取：{exc}") from exc

    def _write_manifest(
        self,
        directory: Path,
        manifest: RunManifest,
    ) -> None:
        self._write_json(
            directory / "manifest.json",
            manifest.model_dump(mode="json"),
        )

    @classmethod
    def _write_json(cls, path: Path, value: object) -> None:
        cls._write_text(
            path,
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        )

    @classmethod
    def _write_text(cls, path: Path, text: str) -> None:
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{path.name}-",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, path)
            cls._fsync_directory(path.parent)
        except OSError as exc:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                    cls._fsync_directory(temporary.parent)
                except OSError as cleanup_error:
                    raise RunStoreError(
                        f"无法原子写入 {path}：{exc}；"
                        f"同时无法清理临时文件：{cleanup_error}"
                    ) from exc
            raise RunStoreError(f"无法原子写入 {path}：{exc}") from exc

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        descriptor: int | None = None
        try:
            descriptor = os.open(path, os.O_APPEND | os.O_WRONLY)
            remaining = memoryview(line.encode("utf-8"))
            while remaining:
                written = os.write(descriptor, remaining)
                remaining = remaining[written:]
            os.fsync(descriptor)
        except OSError as exc:
            raise RunStoreError(f"无法追加写入 {path}：{exc}") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @classmethod
    def _remove_reservation(cls, reservation: Path) -> None:
        try:
            reservation.unlink(missing_ok=True)
            cls._fsync_directory(reservation.parent)
        except OSError as exc:
            raise RunStoreError(
                f"无法清理提示词文件 reservation：{exc}"
            ) from exc

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _remove_tree(path: Path) -> None:
        if not path.exists():
            return
        for child in path.iterdir():
            if child.is_dir():
                LocalRunStore._remove_tree(child)
            else:
                child.unlink(missing_ok=True)
        path.rmdir()

    @staticmethod
    def _prompt_text(result: GenerationResult) -> str:
        return "\n".join(prompt.text for prompt in result.prompts) + "\n"

    @staticmethod
    def _new_run_id() -> str:
        return (
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-"
            f"{uuid4().hex[:8]}"
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class _MemoryRun:
    spec: GenerationSpec
    rules: ResolvedRuleSet
    manifest: RunManifest
    foundation: Foundation | None
    themes: dict[str, Theme]
    frames: dict[str, Frame]
    attempts: list[GenerationAttempt] = field(default_factory=list)
    theme_similarity_report: ThemeSimilarityReport | None = None
    completed: ArchivedRun | None = None


class InMemoryRunStore:
    """Test adapter with the same checkpoint semantics."""

    def __init__(self) -> None:
        self.runs: dict[str, _MemoryRun] = {}
        self._name_counts: dict[tuple[str, str], int] = {}

    def create(
        self,
        spec: GenerationSpec,
        settings: RunSettings,
        rules: ResolvedRuleSet,
    ) -> RunSnapshot:
        run_id = f"20000101T000000Z-{len(self.runs) + 1:08x}"
        now = LocalRunStore._now()
        manifest = RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            created_at=now,
            updated_at=now,
            settings=settings,
            prompts_directory="memory://prompts",
            rules_fingerprint=rules.fingerprint(),
        )
        self.runs[run_id] = _MemoryRun(
            spec=spec,
            rules=rules,
            manifest=manifest,
            foundation=None,
            themes={},
            frames={},
        )
        return self.inspect(run_id)

    def inspect(self, run_id: str) -> RunSnapshot:
        try:
            run = self.runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError(f"Run 不存在：{run_id}") from exc
        if run.completed is not None:
            themes = {
                item.theme.theme_id: item.theme
                for item in run.completed.result.book.themes
            }
            frames = {
                frame.frame_id: frame
                for item in run.completed.result.book.themes
                for frame in item.frames
            }
        else:
            try:
                themes, frames = normalize_checkpoint_graph(
                    run.spec,
                    run.foundation,
                    dict(run.themes),
                    dict(run.frames),
                )
            except GenerationContractError as exc:
                raise RunStoreError(
                    f"Run {run_id} 的 checkpoint 损坏：{exc}"
                ) from exc
        return RunSnapshot(
            run_id=run_id,
            spec=run.spec,
            settings=run.manifest.settings,
            rules=run.rules,
            foundation=run.foundation,
            themes=themes,
            frames=frames,
            manifest=run.manifest,
            theme_similarity_report=run.theme_similarity_report,
            completed=run.completed,
        )

    def start(self, run_id: str) -> RunSnapshot:
        self.inspect(run_id)
        run = self.runs[run_id]
        if run.completed is None:
            run.manifest = run.manifest.model_copy(
                update={
                    "status": RunStatus.RUNNING,
                    "error": None,
                    "updated_at": LocalRunStore._now(),
                }
            )
        return self.inspect(run_id)

    def checkpoint(
        self,
        run_id: str,
        artifact: CheckpointArtifact,
    ) -> None:
        run = self.runs[run_id]
        if isinstance(artifact, Foundation):
            run.foundation = artifact
        elif isinstance(artifact, Theme):
            run.themes[artifact.theme_id] = artifact
        elif isinstance(artifact, Frame):
            run.frames[artifact.frame_id] = artifact
        else:
            raise TypeError(type(artifact).__name__)

    def record_attempt(
        self,
        run_id: str,
        attempt: GenerationAttempt,
    ) -> None:
        if attempt.operation_id is not None and any(
            recorded.operation_id == attempt.operation_id
            for recorded in self.runs[run_id].attempts
        ):
            return
        self.runs[run_id].attempts.append(attempt)

    def attempts(self, run_id: str) -> tuple[GenerationAttempt, ...]:
        return tuple(self.runs[run_id].attempts)

    def record_theme_similarity(
        self,
        run_id: str,
        report: ThemeSimilarityReport,
    ) -> None:
        self.runs[run_id].theme_similarity_report = report

    def apply_theme_rejections(
        self,
        run_id: str,
        report: ThemeSimilarityReport,
    ) -> None:
        if report.state != ThemeSimilarityState.REJECTION_PENDING:
            raise RunStoreError(
                "只能应用 pending 状态的 Theme similarity rejection"
            )
        run = self.runs[run_id]
        rejected = {
            rejection.rejected_theme_id
            for rejection in report.rejections
        }
        for theme_id in rejected:
            run.themes.pop(theme_id, None)
        run.frames = {
            frame_id: frame
            for frame_id, frame in run.frames.items()
            if frame_id.split("-F", 1)[0] not in rejected
        }
        run.theme_similarity_report = report.model_copy(
            update={"state": ThemeSimilarityState.REGENERATING}
        )

    def clear_theme_similarity(self, run_id: str) -> None:
        self.runs[run_id].theme_similarity_report = None

    def fail(self, run_id: str, error: str) -> None:
        run = self.runs[run_id]
        run.manifest = run.manifest.model_copy(
            update={
                "status": RunStatus.FAILED,
                "error": error,
                "updated_at": LocalRunStore._now(),
            }
        )

    def complete(
        self,
        run_id: str,
        result: GenerationResult,
    ) -> ArchivedRun:
        run = self.runs[run_id]
        semantic_name = result.book.semantic_name
        if run.manifest.prompt_file is None:
            content_level = result.spec.content_level.value
            name_key = (content_level, semantic_name)
            sequence = self._name_counts.get(name_key, 0) + 1
            self._name_counts[name_key] = sequence
            prompt_file = (
                f"memory://prompts/{content_level}/"
                f"{semantic_name}_{sequence:04d}.txt"
            )
        else:
            prompt_file = run.manifest.prompt_file
        archived = ArchivedRun(
            run_id=run_id,
            request_file=f"memory://{run_id}/request.json",
            book_file=f"memory://{run_id}/book.json",
            prompt_file=prompt_file,
            result=result,
        )
        run.manifest = run.manifest.model_copy(
            update={
                "status": RunStatus.COMPLETED,
                "prompt_file": prompt_file,
                "error": None,
                "updated_at": LocalRunStore._now(),
            }
        )
        run.completed = archived
        return archived
