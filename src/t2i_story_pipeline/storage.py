"""Publish completed narrative prompts without partial file contents."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from t2i_story_pipeline.errors import StoryStorageError
from t2i_story_pipeline.models import StoryResult
from t2i_story_pipeline.persistence import durable_mkdir, fsync_directory


@dataclass(frozen=True, slots=True)
class PublishedStory:
    prompt_file: Path


def publish_story(
    result: StoryResult,
    prompt_file: Path,
) -> PublishedStory:
    prompt_file = prompt_file.resolve()
    prompt_text = (
        "\n".join(
            frame.prose
            for theme in result.themes
            for frame in theme.frames
        )
        + "\n"
    )
    try:
        _atomic_write(prompt_file, prompt_text)
    except OSError as exc:
        raise StoryStorageError(f"无法发布故事提示词：{exc}") from exc
    return PublishedStory(prompt_file=prompt_file)


def _atomic_write(path: Path, text: str) -> None:
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
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
