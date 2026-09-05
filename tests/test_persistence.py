from __future__ import annotations

import errno
import fcntl
import json
import os
import stat
from pathlib import Path

import pytest

from t2i_prompt_pipeline import persistence
from t2i_prompt_pipeline.errors import RunStoreError
from t2i_prompt_pipeline.persistence import (
    exclusive_file_lock,
    fsync_directory,
    write_json,
    write_text,
)


def test_write_text_replaces_atomically_and_syncs_file_then_directory(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "state.txt"
    path.write_text("old", encoding="utf-8")
    events = []
    original_fsync = os.fsync
    original_replace = os.replace

    def record_fsync(descriptor):
        directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        events.append("directory-fsync" if directory else "file-fsync")
        original_fsync(descriptor)

    def record_replace(source, destination):
        assert source.parent == path.parent
        assert source != path
        assert source.read_text(encoding="utf-8") == "新内容\n"
        assert path.read_text(encoding="utf-8") == "old"
        assert destination == path
        events.append("replace")
        original_replace(source, destination)

    monkeypatch.setattr(persistence.os, "fsync", record_fsync)
    monkeypatch.setattr(persistence.os, "replace", record_replace)

    write_text(path, "新内容\n")

    assert path.read_text(encoding="utf-8") == "新内容\n"
    assert events == ["file-fsync", "replace", "directory-fsync"]
    assert list(tmp_path.iterdir()) == [path]


def test_write_json_creates_parents_and_preserves_unicode(tmp_path) -> None:
    path = tmp_path / "nested" / "state.json"
    value = {"说明": "已完成", "count": 2, "items": [True, None]}

    write_json(path, value)

    text = path.read_text(encoding="utf-8")
    assert text == json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    assert json.loads(text) == value
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("stage", ["file-fsync", "replace", "directory-fsync"])
def test_write_failure_only_cleans_its_own_temporary_file(
    tmp_path, monkeypatch, stage
) -> None:
    path = tmp_path / "state.txt"
    path.write_text("old", encoding="utf-8")
    unrelated = tmp_path / ".state.txt-other.tmp"
    unrelated.write_text("another writer", encoding="utf-8")
    failure = OSError(errno.EIO, "injected write failure")
    original_fsync = os.fsync
    injected = False

    def fail_fsync(descriptor):
        nonlocal injected
        directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        operation = "directory-fsync" if directory else "file-fsync"
        if stage == operation and not injected:
            injected = True
            raise failure
        original_fsync(descriptor)

    def fail_replace(_source, _destination):
        raise failure

    monkeypatch.setattr(persistence.os, "fsync", fail_fsync)
    if stage == "replace":
        monkeypatch.setattr(persistence.os, "replace", fail_replace)

    with pytest.raises(RunStoreError, match="无法原子写入") as caught:
        write_text(path, "new")

    assert caught.value.__cause__ is failure
    assert path.read_text() == ("new" if stage == "directory-fsync" else "old")
    assert unrelated.read_text() == "another writer"
    assert set(tmp_path.iterdir()) == {path, unrelated}


def test_write_failure_reports_cleanup_error(tmp_path, monkeypatch) -> None:
    path = tmp_path / "state.txt"
    failure = OSError(errno.EIO, "replace failed")
    original_unlink = Path.unlink

    def fail_replace(_source, _destination):
        raise failure

    def fail_unlink(self, *args, **kwargs):
        if self.name.startswith(".state.txt-"):
            raise OSError(errno.EACCES, "unlink failed")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(persistence.os, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(
        RunStoreError, match="replace failed.*同时无法清理临时文件.*unlink failed"
    ) as caught:
        write_text(path, "new")

    assert caught.value.__cause__ is failure
    assert not path.exists()


def test_write_parent_error_uses_application_error_boundary(tmp_path) -> None:
    parent = tmp_path / "not-a-directory"
    parent.write_text("occupied")

    with pytest.raises(RunStoreError, match="无法原子写入"):
        write_text(parent / "state.txt", "new")

    assert parent.read_text() == "occupied"
    assert list(tmp_path.iterdir()) == [parent]


@pytest.mark.parametrize("fail", [False, True])
def test_fsync_directory_closes_descriptor_even_on_failure(
    tmp_path, monkeypatch, fail
) -> None:
    descriptors = []
    original_fsync = os.fsync

    def record_fsync(descriptor):
        descriptors.append(descriptor)
        assert stat.S_ISDIR(os.fstat(descriptor).st_mode)
        if fail:
            raise OSError(errno.EIO, "fsync failed")
        original_fsync(descriptor)

    monkeypatch.setattr(persistence.os, "fsync", record_fsync)

    if fail:
        with pytest.raises(OSError, match="fsync failed"):
            fsync_directory(tmp_path)
    else:
        fsync_directory(tmp_path)

    assert len(descriptors) == 1
    with pytest.raises(OSError) as caught:
        os.fstat(descriptors[0])
    assert caught.value.errno == errno.EBADF


def test_lock_excludes_competing_open_and_retains_file_on_release(tmp_path) -> None:
    path = tmp_path / "batch.lock"
    path.write_text("retained contents")
    inode = path.stat().st_ino

    with exclusive_file_lock(path):
        for _ in range(2):
            with pytest.raises(RunStoreError, match="文件锁已被占用"):
                with exclusive_file_lock(path):
                    pytest.fail("a competing lock was acquired")
            assert path.stat().st_ino == inode
        with exclusive_file_lock(tmp_path / "other.lock"):
            pass

    assert path.stat().st_ino == inode
    assert path.read_text() == "retained contents"
    with exclusive_file_lock(path):
        assert path.stat().st_ino == inode


@pytest.mark.parametrize("exception_type", [ValueError, OSError, KeyboardInterrupt])
def test_lock_releases_when_body_raises(tmp_path, exception_type) -> None:
    path = tmp_path / "nested" / "batch.lock"
    failure = exception_type("body failed")

    with pytest.raises(exception_type) as caught:
        with exclusive_file_lock(path):
            raise failure

    assert caught.value is failure
    assert path.is_file()
    with exclusive_file_lock(path):
        pass


def test_lock_open_error_uses_application_error_boundary(tmp_path) -> None:
    with pytest.raises(RunStoreError, match="无法打开文件锁"):
        with exclusive_file_lock(tmp_path):
            pytest.fail("a directory was opened as a lock file")


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (fcntl.LOCK_EX | fcntl.LOCK_NB, "无法获取文件锁"),
        (fcntl.LOCK_UN, "无法释放文件锁"),
    ],
)
def test_lock_io_errors_close_descriptor_and_allow_reacquiring(
    tmp_path, monkeypatch, operation, message
) -> None:
    path = tmp_path / "batch.lock"
    original_flock = fcntl.flock
    descriptors = []
    failure = OSError(errno.EIO, "flock failed")

    def fail_flock(descriptor, requested):
        if requested == operation:
            descriptors.append(descriptor)
            raise failure
        original_flock(descriptor, requested)

    with monkeypatch.context() as patch:
        patch.setattr(persistence.fcntl, "flock", fail_flock)
        with pytest.raises(RunStoreError, match=message) as caught:
            with exclusive_file_lock(path):
                pass

    assert caught.value.__cause__ is failure
    assert len(descriptors) == 1
    with pytest.raises(OSError) as closed:
        os.fstat(descriptors[0])
    assert closed.value.errno == errno.EBADF
    assert path.is_file()
    with exclusive_file_lock(path):
        pass


def test_lock_close_error_uses_application_error_boundary(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "batch.lock"
    original_close = os.close
    failure = OSError(errno.EIO, "close failed")

    def fail_close(descriptor):
        original_close(descriptor)
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(persistence.os, "close", fail_close)
        with pytest.raises(RunStoreError, match="无法关闭文件锁") as caught:
            with exclusive_file_lock(path):
                pass

    assert caught.value.__cause__ is failure
    with exclusive_file_lock(path):
        pass
