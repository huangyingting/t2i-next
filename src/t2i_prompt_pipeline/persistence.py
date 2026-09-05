"""Atomic filesystem writes and process-exclusive state access."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from t2i_prompt_pipeline.errors import RunStoreError


def write_text(path: Path, text: str) -> None:
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
                fsync_directory(temporary.parent)
            except OSError as cleanup_error:
                raise RunStoreError(
                    f"无法原子写入 {path}：{exc}；"
                    f"同时无法清理临时文件：{cleanup_error}"
                ) from exc
        raise RunStoreError(f"无法原子写入 {path}：{exc}") from exc


def write_json(path: Path, value: object) -> None:
    write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Hold a nonblocking advisory lock, retaining its inode after release."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        raise RunStoreError(f"无法打开文件锁 {path}：{exc}") from exc
    acquired = False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RunStoreError(f"文件锁已被占用：{path}") from exc
        except OSError as exc:
            raise RunStoreError(f"无法获取文件锁 {path}：{exc}") from exc
        acquired = True
        yield
    finally:
        try:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError as exc:
            raise RunStoreError(f"无法释放文件锁 {path}：{exc}") from exc
        finally:
            try:
                os.close(descriptor)
            except OSError as exc:
                raise RunStoreError(f"无法关闭文件锁 {path}：{exc}") from exc
