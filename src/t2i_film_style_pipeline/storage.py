"""Atomic persistence for film-style runs and compiled Story Descriptions."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from t2i_film_style_pipeline.errors import FilmStyleStorageError
from t2i_film_style_pipeline.models import FilmStyleResult


@dataclass(frozen=True, slots=True)
class PublishedFilmStyle:
    run_directory: Path
    profile_file: Path
    prompt_file: Path


def publish_film_style(
    result: FilmStyleResult,
    *,
    runs_directory: Path,
    prompt_file: Path,
) -> PublishedFilmStyle:
    run_directory = (runs_directory / result.run_id).resolve()
    profile_file = run_directory / "profile.json"
    prompt_file = prompt_file.resolve()
    staging_directory: Path | None = None
    prompt_published = False
    try:
        runs_directory = runs_directory.resolve()
        runs_directory.mkdir(parents=True, exist_ok=True)
        if run_directory.exists():
            raise FileExistsError(f"run directory already exists: {run_directory}")
        staging_directory = Path(
            tempfile.mkdtemp(
                prefix=f".{result.run_id}-",
                suffix=".tmp",
                dir=runs_directory,
            )
        )
        _write_file(
            staging_directory / "request.json",
            result.request.model_dump_json(indent=2) + "\n",
        )
        _write_file(
            staging_directory / "profile.json",
            result.profile.model_dump_json(indent=2) + "\n",
        )
        _write_file(
            staging_directory / "result.json",
            result.model_dump_json(indent=2) + "\n",
        )
        _fsync_directory(staging_directory)
        _atomic_write(prompt_file, result.compiled_story.rstrip() + "\n")
        prompt_published = True
        _commit_run_directory(staging_directory, run_directory)
        staging_directory = None
    except OSError as exc:
        if prompt_published:
            prompt_file.unlink(missing_ok=True)
            _fsync_directory(prompt_file.parent)
        if staging_directory is not None:
            shutil.rmtree(staging_directory, ignore_errors=True)
        raise FilmStyleStorageError(
            f"failed to publish film-style run: {exc}"
        ) from exc
    return PublishedFilmStyle(
        run_directory=run_directory,
        profile_file=profile_file,
        prompt_file=prompt_file,
    )


def _write_file(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _commit_run_directory(staging: Path, destination: Path) -> None:
    os.replace(staging, destination)
    _fsync_directory(destination.parent)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
