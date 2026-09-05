from __future__ import annotations

from pathlib import Path

import pytest

from t2i_prompt_pipeline import cast_matrix_batch
from t2i_prompt_pipeline.batch import BatchLimits, BatchRecovery, BatchResult
from t2i_prompt_pipeline.cast_matrix_batch import (
    CAST_MATRIX_CASTS,
    CAST_MATRIX_FRAMES_PER_THEME,
    CAST_MATRIX_THEME_COUNT,
    build_cast_matrix_tasks,
    default_cast_matrix_state_file,
    run_cast_matrix_batch,
)
from t2i_prompt_pipeline.errors import ConfigurationError
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    FrameMode,
    ProviderSettings,
)
from tests.factories import make_rules, make_settings


def test_cast_matrix_tasks_have_requested_shape_and_casts() -> None:
    tasks = build_cast_matrix_tasks("共享视觉 brief", ContentLevel.EROTIC)

    assert len(tasks) == 5
    assert len(CAST_MATRIX_CASTS) == 5
    assert {(task.spec.female_count, task.spec.male_count) for task in tasks} == {
        (1, 0), (2, 0), (3, 0), (1, 1), (2, 1),
    }
    for task in tasks:
        assert task.spec.theme_count == CAST_MATRIX_THEME_COUNT == 100
        assert task.spec.frames_per_theme == CAST_MATRIX_FRAMES_PER_THEME == 6
        assert task.spec.frame_mode == FrameMode.SEQUENTIAL
        assert task.spec.content_level == ContentLevel.EROTIC
        assert task.cast.description in task.spec.brief
        assert "年满二十一岁" in task.spec.brief


def test_cast_matrix_rejects_an_empty_brief() -> None:
    with pytest.raises(ConfigurationError, match="brief 不能为空"):
        build_cast_matrix_tasks("  ", ContentLevel.AESTHETIC)


def test_default_state_file_is_stable_and_rules_specific(tmp_path: Path) -> None:
    tasks = build_cast_matrix_tasks("共享视觉 brief", ContentLevel.AESTHETIC)
    first = default_cast_matrix_state_file(tmp_path, tasks, "rules-a")
    repeated = default_cast_matrix_state_file(tmp_path, tasks, "rules-a")
    changed = default_cast_matrix_state_file(tmp_path, tasks, "rules-b")

    assert first == repeated
    assert first != changed
    assert first.parent == tmp_path
    assert first.name.startswith("cast-matrix-")


async def test_cast_matrix_uses_shared_retry_executor(monkeypatch, tmp_path):
    tasks = build_cast_matrix_tasks("共享视觉 brief", ContentLevel.AESTHETIC)
    config = AppConfig(
        spec=tasks[0].spec,
        provider=ProviderSettings(model="test"),
        runs_directory=tmp_path / "runs",
        prompts_directory=tmp_path / "prompts",
        run_settings=make_settings(),
        rules=make_rules(tasks[0].spec),
    )
    limits = BatchLimits(max_replacement_runs=1)
    path = tmp_path / "batch.json"
    expected = BatchResult(5, 3000, (), path)

    async def execute(received_config, received_tasks, state_file, **kwargs):
        assert received_config == config
        assert [(item.task_id, item.spec) for item in received_tasks] == [
            (item.task_id, item.spec) for item in tasks
        ]
        assert state_file == path
        assert kwargs["recovery"] == BatchRecovery.RETRY
        assert kwargs["limits"] == limits
        assert kwargs["retry_delay_seconds"] == 0
        return expected

    monkeypatch.setattr(cast_matrix_batch, "run_batch", execute)
    assert await run_cast_matrix_batch(
        config, tasks, path, limits=limits, retry_delay_seconds=0
    ) == expected
