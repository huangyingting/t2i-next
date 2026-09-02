from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from t2i_prompt_pipeline.cast_matrix_batch import (
    CAST_MATRIX_CASTS,
    CAST_MATRIX_FRAMES_PER_THEME,
    CAST_MATRIX_THEME_COUNT,
    CastMatrixBatchState,
    CastMatrixTaskProgress,
    CastMatrixTaskStatus,
    _batch_id,
    _drive_tasks,
    build_cast_matrix_tasks,
    default_cast_matrix_state_file,
)
from t2i_prompt_pipeline.errors import ConfigurationError, RunIncompleteError
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    FrameMode,
    ProviderSettings,
    ThemeSimilarityState,
)
from tests.factories import make_rules, make_settings


def test_cast_matrix_tasks_have_requested_shape_and_casts() -> None:
    tasks = build_cast_matrix_tasks("共享视觉 brief", ContentLevel.EROTIC)

    assert len(tasks) == 5
    assert len(CAST_MATRIX_CASTS) == 5
    assert {(task.spec.female_count, task.spec.male_count) for task in tasks} == {
        (1, 0),
        (2, 0),
        (3, 0),
        (1, 1),
        (2, 1),
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


@pytest.mark.asyncio
async def test_drive_tasks_retries_and_replaces_similarity_exhaustion(
    tmp_path: Path,
) -> None:
    tasks = build_cast_matrix_tasks("共享视觉 brief", ContentLevel.EROTIC)
    rules = make_rules(tasks[0].spec)
    config = AppConfig(
        spec=tasks[0].spec,
        provider=ProviderSettings(model="test"),
        runs_directory=tmp_path / "runs",
        prompts_directory=tmp_path / "prompts",
        run_settings=make_settings(),
        rules=rules,
    )
    state = CastMatrixBatchState(
        batch_id=_batch_id(tasks, rules.fingerprint()),
        tasks={task.task_id: CastMatrixTaskProgress() for task in tasks},
    )

    class FakeStore:
        def __init__(self) -> None:
            self.created: list[SimpleNamespace] = []

        def create(self, spec, settings, resolved_rules):
            snapshot = SimpleNamespace(
                run_id=f"run-{len(self.created) + 1}",
                spec=spec,
                settings=settings,
                rules=resolved_rules,
                completed=None,
                theme_similarity_report=None,
            )
            self.created.append(snapshot)
            return snapshot

        def inspect(self, run_id):
            return next(item for item in self.created if item.run_id == run_id)

    store = FakeStore()

    class FakeStudio:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def resume(self, run_id):
            self.calls.append(run_id)
            if run_id == "run-1":
                store.inspect(run_id).theme_similarity_report = SimpleNamespace(
                    state=ThemeSimilarityState.EXHAUSTED
                )
                raise RunIncompleteError(
                    run_id,
                    missing_themes=1,
                    missing_frames=600,
                    causes=("similarity exhausted",),
                )
            return SimpleNamespace(
                run_id=run_id,
                prompt_file=f"/prompts/{run_id}.txt",
            )

    studio = FakeStudio()
    messages: list[str] = []
    state_file = tmp_path / "state.json"

    await _drive_tasks(
        tasks,
        state,
        state_file,
        store,
        studio,
        config,
        0,
        messages.append,
    )

    assert len(store.created) == 6
    assert studio.calls[:2] == ["run-1", "run-2"]
    assert all(
        progress.status == CastMatrixTaskStatus.COMPLETED
        for progress in state.tasks.values()
    )
    saved = json.loads(state_file.read_text())
    assert all(
        progress["status"] == "completed" for progress in saved["tasks"].values()
    )
    assert any("改用新 run run-2" in message for message in messages)
