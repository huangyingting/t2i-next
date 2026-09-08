"""Durable local filesystem primitives for story runs and outputs."""

from __future__ import annotations

import os
from pathlib import Path

from t2i_story_pipeline.errors import StoryStorageError


def durable_mkdir(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    if current.exists() and not current.is_dir():
        raise StoryStorageError(f"目录路径被文件占用：{current}")
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError:
            if not directory.is_dir():
                raise StoryStorageError(
                    f"目录路径被文件占用：{directory}"
                ) from None
        except OSError as exc:
            raise StoryStorageError(f"无法创建目录 {directory}：{exc}") from exc
        fsync_directory(directory.parent)


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise StoryStorageError(f"无法同步目录 {path}：{exc}") from exc
