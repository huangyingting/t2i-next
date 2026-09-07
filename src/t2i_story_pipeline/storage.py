"""Publish completed story prompts without partial file contents."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from t2i_story_pipeline.errors import StoryStorageError
from t2i_story_pipeline.models import StoryResult


@dataclass(frozen=True, slots=True)
class PublishedStory:
    json_file: Path
    prose_file: Path
    prompt_file: Path


def publish_story(
    result: StoryResult,
    output_directory: Path,
) -> PublishedStory:
    output_directory = output_directory.resolve()
    json_file = output_directory / f"story-{result.run_id}.json"
    prose_file = output_directory / f"story-{result.run_id}.prose.txt"
    prompt_file = output_directory / f"story-{result.run_id}.prompt.txt"
    prose_text = (
        "\n".join(
            narrative.prose for theme in result.themes for narrative in theme.narratives
        )
        + "\n"
    )
    prompt_text = (
        "\n".join(
            narrative.prompt
            for theme in result.themes
            for narrative in theme.narratives
        )
        + "\n"
    )
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            json_file,
            json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        _atomic_write(prose_file, prose_text)
        _atomic_write(prompt_file, prompt_text)
    except OSError as exc:
        raise StoryStorageError(f"无法发布故事提示词：{exc}") from exc
    return PublishedStory(
        json_file=json_file,
        prose_file=prose_file,
        prompt_file=prompt_file,
    )


def _atomic_write(path: Path, text: str) -> None:
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
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
