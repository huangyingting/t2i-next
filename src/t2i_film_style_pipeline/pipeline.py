"""Resumable orchestration from film references to final image prompts."""

from __future__ import annotations

import fcntl
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from t2i_film_style_pipeline.content_validation import FilmStyleContentValidator
from t2i_film_style_pipeline.errors import (
    FilmStylePipelineError,
    FilmStyleRunIncompleteError,
    FilmStyleStorageError,
)
from t2i_film_style_pipeline.models import (
    FilmStyleRequest,
    FilmStyleResult,
    FilmStyleRuleSet,
    SceneDirectionText,
)
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    FilmPromptRuleSet,
    OutputLanguage,
)
from t2i_film_style_pipeline.prompt_provider import FilmPromptModel
from t2i_film_style_pipeline.prompt_run_store import (
    FilmPromptRunSettings,
    LocalFilmPromptRunStore,
)
from t2i_film_style_pipeline.prompt_studio import FilmPromptStudio
from t2i_film_style_pipeline.provider import (
    FilmStyleModel,
    FilmStyleProviderSettings,
)
from t2i_film_style_pipeline.service import FilmStyleStudio

ProgressCallback = Callable[[str], None]
_RUN_ID = re.compile(r"\d{8}T\d{6}Z-[a-f0-9]{8}")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FilmStyleRunStatus(StrEnum):
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class FilmStylePromptRequest(_Model):
    film_style: FilmStyleRequest
    scene_direction: SceneDirectionText | None = None
    output_filename_stem: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    )
    theme_count: int = Field(default=1, ge=1, le=100)
    frames_per_theme: int = Field(default=6, ge=1, le=6)
    female_count: int | None = Field(default=None, ge=0, le=8)
    male_count: int | None = Field(default=None, ge=0, le=8)
    content_level: ContentLevel = ContentLevel.AESTHETIC
    output_language: OutputLanguage = OutputLanguage.CHINESE

    def prompt_request(
        self,
        context: str,
    ) -> FilmPromptRequest:
        return FilmPromptRequest(
            context=context,
            prompt_filename_stem=(
                self.output_filename_stem
                or _short_filename_stem(self.film_style.director)
            ),
            theme_count=self.theme_count,
            frames_per_theme=self.frames_per_theme,
            female_count=self.female_count,
            male_count=self.male_count,
            content_level=self.content_level,
            output_language=self.output_language,
        )


def _short_filename_stem(value: str) -> str:
    normalized = re.sub(r"[^\w-]+", "_", value).strip("_-")
    return normalized[:80] or "导演风格"


class FilmStylePipelineSettings(_Model):
    film_provider: FilmStyleProviderSettings
    prompt: FilmPromptRunSettings
    validate_themes: bool
    validate_frames: bool


class FilmStyleRunManifest(_Model):
    run_id: str
    status: FilmStyleRunStatus
    created_at: str
    updated_at: str
    prompts_directory: str
    profile_run_id: str | None = None
    prompt_run_id: str | None = None
    profile_file: str | None = None
    compiled_context_file: str | None = None
    prompt_file: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CompletedFilmStylePromptRun:
    run_id: str
    profile_run_id: str
    prompt_run_id: str
    profile_file: Path
    compiled_context_file: Path
    prompt_file: Path


@dataclass(frozen=True, slots=True)
class FilmStyleRunSnapshot:
    request: FilmStylePromptRequest
    settings: FilmStylePipelineSettings
    rules: FilmStyleRuleSet
    manifest: FilmStyleRunManifest
    completed: CompletedFilmStylePromptRun | None = None


class LocalFilmStyleRunStore:
    """Persist the top-level run and locate its resumable child runs."""

    def __init__(self, runs_root: Path) -> None:
        self._runs_root = runs_root.resolve()

    def create(
        self,
        request: FilmStylePromptRequest,
        settings: FilmStylePipelineSettings,
        rules: FilmStyleRuleSet,
        *,
        prompts_directory: Path,
    ) -> FilmStyleRunSnapshot:
        run_id = _new_run_id()
        now = _now()
        manifest = FilmStyleRunManifest(
            run_id=run_id,
            status=FilmStyleRunStatus.RUNNING,
            created_at=now,
            updated_at=now,
            prompts_directory=str(prompts_directory.resolve()),
        )
        final_directory = self._runs_root / run_id
        staging: Path | None = None
        try:
            self._runs_root.mkdir(parents=True, exist_ok=True)
            staging = Path(
                tempfile.mkdtemp(prefix=f".{run_id}-", dir=self._runs_root)
            )
            (staging / "profile-runs").mkdir()
            (staging / "prompt-runs").mkdir()
            _write_json(staging / "request.json", request)
            _write_json(staging / "settings.json", settings)
            _write_json(staging / "rules.json", rules)
            _write_json(staging / "manifest.json", manifest)
            os.replace(staging, final_directory)
            _fsync_directory(self._runs_root)
        except OSError as exc:
            if staging is not None and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise FilmStyleStorageError(
                f"failed to create film-style run: {exc}"
            ) from exc
        return FilmStyleRunSnapshot(
            request=request,
            settings=settings,
            rules=rules,
            manifest=manifest,
        )

    def inspect(self, run_id: str) -> FilmStyleRunSnapshot:
        directory = self.run_directory(run_id)
        try:
            request = FilmStylePromptRequest.model_validate_json(
                (directory / "request.json").read_text(encoding="utf-8")
            )
            settings = FilmStylePipelineSettings.model_validate_json(
                (directory / "settings.json").read_text(encoding="utf-8")
            )
            rules = FilmStyleRuleSet.model_validate_json(
                (directory / "rules.json").read_text(encoding="utf-8")
            )
            manifest = FilmStyleRunManifest.model_validate_json(
                (directory / "manifest.json").read_text(encoding="utf-8")
            )
            if manifest.run_id != run_id:
                raise FilmStyleStorageError(
                    f"Run {run_id} manifest run_id does not match"
                )
            completed = (
                _completed_from_manifest(manifest)
                if manifest.status == FilmStyleRunStatus.COMPLETED
                else None
            )
        except FilmStyleStorageError:
            raise
        except (OSError, ValidationError) as exc:
            raise FilmStyleStorageError(
                f"Run {run_id} checkpoint is invalid: {exc}"
            ) from exc
        return FilmStyleRunSnapshot(
            request=request,
            settings=settings,
            rules=rules,
            manifest=manifest,
            completed=completed,
        )

    @contextmanager
    def lock(self, run_id: str) -> Iterator[None]:
        lock_path = self.run_directory(run_id) / ".lock"
        try:
            with lock_path.open("a", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise FilmStyleStorageError(
                f"failed to lock film-style run {run_id}: {exc}"
            ) from exc

    def start(self, run_id: str) -> FilmStyleRunSnapshot:
        snapshot = self.inspect(run_id)
        if snapshot.completed is not None:
            return snapshot
        self._update_manifest(
            snapshot.manifest.model_copy(
                update={
                    "status": FilmStyleRunStatus.RUNNING,
                    "updated_at": _now(),
                    "error": None,
                }
            )
        )
        return self.inspect(run_id)

    def checkpoint_profile(
        self,
        run_id: str,
        profile_run_id: str,
        *,
        profile_file: Path,
        compiled_context_file: Path,
    ) -> FilmStyleRunSnapshot:
        snapshot = self.inspect(run_id)
        self._update_manifest(
            snapshot.manifest.model_copy(
                update={
                    "profile_run_id": profile_run_id,
                    "profile_file": str(profile_file.resolve()),
                    "compiled_context_file": str(compiled_context_file.resolve()),
                    "updated_at": _now(),
                }
            )
        )
        return self.inspect(run_id)

    def checkpoint_prompt(
        self,
        run_id: str,
        prompt_run_id: str,
    ) -> FilmStyleRunSnapshot:
        snapshot = self.inspect(run_id)
        self._update_manifest(
            snapshot.manifest.model_copy(
                update={
                    "prompt_run_id": prompt_run_id,
                    "updated_at": _now(),
                }
            )
        )
        return self.inspect(run_id)

    def complete(
        self,
        run_id: str,
        *,
        prompt_file: Path,
    ) -> CompletedFilmStylePromptRun:
        snapshot = self.inspect(run_id)
        manifest = snapshot.manifest
        if (
            manifest.profile_run_id is None
            or manifest.prompt_run_id is None
            or manifest.profile_file is None
            or manifest.compiled_context_file is None
        ):
            raise FilmStyleStorageError(
                f"Run {run_id} cannot complete before both child runs"
            )
        completed_manifest = manifest.model_copy(
            update={
                "status": FilmStyleRunStatus.COMPLETED,
                "prompt_file": str(prompt_file.resolve()),
                "updated_at": _now(),
                "error": None,
            }
        )
        self._update_manifest(completed_manifest)
        return _completed_from_manifest(completed_manifest)

    def fail(self, run_id: str, error: str) -> None:
        snapshot = self.inspect(run_id)
        if snapshot.completed is not None:
            return
        self._update_manifest(
            snapshot.manifest.model_copy(
                update={
                    "status": FilmStyleRunStatus.FAILED,
                    "updated_at": _now(),
                    "error": error,
                }
            )
        )

    def discover_profile(
        self,
        run_id: str,
    ) -> tuple[FilmStyleResult, Path, Path] | None:
        snapshot = self.inspect(run_id)
        root = self.profile_runs_directory(run_id)
        candidates = sorted(root.glob("*/result.json"))
        if len(candidates) > 1:
            raise FilmStyleStorageError(
                f"Run {run_id} contains multiple profile child runs"
            )
        if not candidates:
            if snapshot.manifest.profile_run_id is not None:
                raise FilmStyleStorageError(
                    f"Run {run_id} is missing its recorded profile child run"
                )
            return None
        try:
            result = FilmStyleResult.model_validate_json(
                candidates[0].read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise FilmStyleStorageError(
                f"Run {run_id} profile checkpoint is invalid: {exc}"
            ) from exc
        if (
            snapshot.manifest.profile_run_id is not None
            and result.run_id != snapshot.manifest.profile_run_id
        ):
            raise FilmStyleStorageError(
                f"Run {run_id} profile child ID does not match its manifest"
            )
        compiled_context_file = candidates[0].parent / "compiled-context.txt"
        try:
            compiled_context = compiled_context_file.read_text(
                encoding="utf-8"
            ).rstrip()
        except (OSError, UnicodeError) as exc:
            raise FilmStyleStorageError(
                f"Run {run_id} cannot read its compiled film context"
            ) from exc
        if compiled_context != result.compiled_context.rstrip():
            raise FilmStyleStorageError(
                f"Run {run_id} compiled film context does not match its result"
            )
        return result, candidates[0].parent / "profile.json", compiled_context_file

    def discover_prompt_run_id(self, run_id: str) -> str | None:
        root = self.prompt_runs_directory(run_id)
        listing = LocalFilmPromptRunStore(root).list_runs()
        if listing.unreadable:
            raise FilmStyleStorageError(
                f"Run {run_id} contains unreadable prompt checkpoints"
            )
        if len(listing.runs) > 1:
            raise FilmStyleStorageError(
                f"Run {run_id} contains multiple prompt child runs"
            )
        return listing.runs[0].run_id if listing.runs else None

    def run_directory(self, run_id: str) -> Path:
        if _RUN_ID.fullmatch(run_id) is None:
            raise FilmStyleStorageError(f"invalid film-style run ID: {run_id}")
        directory = self._runs_root / run_id
        if not directory.is_dir():
            raise FilmStyleStorageError(f"film-style run does not exist: {run_id}")
        return directory

    def profile_runs_directory(self, run_id: str) -> Path:
        return self.run_directory(run_id) / "profile-runs"

    def prompt_runs_directory(self, run_id: str) -> Path:
        return self.run_directory(run_id) / "prompt-runs"

    def _update_manifest(self, manifest: FilmStyleRunManifest) -> None:
        _atomic_write_json(
            self.run_directory(manifest.run_id) / "manifest.json",
            manifest,
        )


class FilmStylePromptStudio:
    """Drive the profile and prompt stages behind one resumable run ID."""

    def __init__(
        self,
        film_model: FilmStyleModel,
        prompt_model: FilmPromptModel,
        store: LocalFilmStyleRunStore,
        settings: FilmStylePipelineSettings,
        rules: FilmStyleRuleSet,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._film_model = film_model
        self._prompt_model = prompt_model
        self._store = store
        self._settings = settings
        self._rules = rules
        self._on_progress = on_progress

    async def run(
        self,
        request: FilmStylePromptRequest,
        *,
        prompts_directory: Path,
    ) -> CompletedFilmStylePromptRun:
        snapshot = self._store.create(
            request,
            self._settings,
            self._rules,
            prompts_directory=prompts_directory,
        )
        self._emit(f"Run 已创建：{snapshot.manifest.run_id}")
        return await self._drive(snapshot.manifest.run_id)

    async def resume(self, run_id: str) -> CompletedFilmStylePromptRun:
        snapshot = self._store.inspect(run_id)
        if snapshot.completed is not None:
            self._emit(f"Run 已完成：{run_id}")
            return snapshot.completed
        if snapshot.settings != self._settings:
            raise FilmStyleStorageError(
                "current provider settings do not match the film-style run"
            )
        if snapshot.rules != self._rules:
            raise FilmStyleStorageError(
                "current film-style rules do not match the frozen run rules"
            )
        self._emit(f"继续 Run：{run_id}")
        return await self._drive(run_id)

    async def _drive(self, run_id: str) -> CompletedFilmStylePromptRun:
        with self._store.lock(run_id):
            snapshot = self._store.start(run_id)
            if snapshot.completed is not None:
                return snapshot.completed
            try:
                film_result, compiled_context_file = await self._profile(snapshot)
                snapshot = self._store.inspect(run_id)
                prompt_store = LocalFilmPromptRunStore(
                    self._store.prompt_runs_directory(run_id),
                    Path(snapshot.manifest.prompts_directory),
                )
                prompt_run_id = (
                    snapshot.manifest.prompt_run_id
                    or self._store.discover_prompt_run_id(run_id)
                )
                prompt_request = snapshot.request.prompt_request(
                    film_result.compiled_context
                )
                prompt_rules = FilmPromptRuleSet(
                    themes=snapshot.rules.themes,
                    frames=snapshot.rules.frames,
                )
                content_validator = (
                    FilmStyleContentValidator(
                        snapshot.request.film_style,
                        film_result.profile,
                    )
                    if (
                        snapshot.settings.validate_themes
                        or snapshot.settings.validate_frames
                    )
                    else None
                )
                if prompt_run_id is None:
                    prompt_snapshot = prompt_store.create(
                        prompt_request,
                        snapshot.settings.prompt,
                        prompt_rules,
                    )
                    prompt_run_id = prompt_snapshot.run_id
                    self._store.checkpoint_prompt(run_id, prompt_run_id)
                    self._emit(f"Prompt checkpoint 已创建：{prompt_run_id}")
                elif snapshot.manifest.prompt_run_id is None:
                    self._store.checkpoint_prompt(run_id, prompt_run_id)
                completed_prompt = await FilmPromptStudio(
                    self._prompt_model,
                    prompt_store,
                    snapshot.settings.prompt,
                    prompt_rules,
                    on_progress=self._on_progress,
                    theme_validator=(
                        content_validator.validate_theme
                        if (
                            content_validator is not None
                            and snapshot.settings.validate_themes
                        )
                        else None
                    ),
                    frame_validator=(
                        content_validator.validate_frame
                        if (
                            content_validator is not None
                            and snapshot.settings.validate_frames
                        )
                        else None
                    ),
                ).resume(prompt_run_id)
                return self._store.complete(
                    run_id,
                    prompt_file=completed_prompt.published.prompt_file,
                )
            except FilmStylePipelineError as exc:
                self._store.fail(run_id, str(exc))
                raise FilmStyleRunIncompleteError(run_id, str(exc)) from exc

    async def _profile(
        self,
        snapshot: FilmStyleRunSnapshot,
    ) -> tuple[FilmStyleResult, Path]:
        discovered = self._store.discover_profile(snapshot.manifest.run_id)
        if discovered is None:
            completed = await FilmStyleStudio(
                self._film_model,
                snapshot.rules.profile,
                runs_directory=self._store.profile_runs_directory(
                    snapshot.manifest.run_id
                ),
            ).run(
                snapshot.request.film_style,
                scene_direction=snapshot.request.scene_direction,
            )
            result = completed.result
            profile_file = completed.published.profile_file
            compiled_context_file = completed.published.compiled_context_file
            self._emit(f"视觉档案已保存：{profile_file}")
        else:
            result, profile_file, compiled_context_file = discovered
        if snapshot.manifest.profile_run_id is None:
            self._store.checkpoint_profile(
                snapshot.manifest.run_id,
                result.run_id,
                profile_file=profile_file,
                compiled_context_file=compiled_context_file,
            )
        return result, compiled_context_file

    def _emit(self, message: str) -> None:
        if self._on_progress is not None:
            self._on_progress(message)


def _completed_from_manifest(
    manifest: FilmStyleRunManifest,
) -> CompletedFilmStylePromptRun:
    if (
        manifest.profile_run_id is None
        or manifest.prompt_run_id is None
        or manifest.profile_file is None
        or manifest.compiled_context_file is None
        or manifest.prompt_file is None
    ):
        raise FilmStyleStorageError(
            f"completed Run {manifest.run_id} is missing output paths"
        )
    return CompletedFilmStylePromptRun(
        run_id=manifest.run_id,
        profile_run_id=manifest.profile_run_id,
        prompt_run_id=manifest.prompt_run_id,
        profile_file=Path(manifest.profile_file),
        compiled_context_file=Path(manifest.compiled_context_file),
        prompt_file=Path(manifest.prompt_file),
    )


def _new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, value: BaseModel) -> None:
    text = value.model_dump_json(indent=2) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_json(path: Path, value: BaseModel) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(value.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise FilmStyleStorageError(
            f"failed to persist film-style manifest: {exc}"
        ) from exc


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
