from __future__ import annotations

from t2i_prompt_pipeline import safe_avant_garde_batch
from t2i_prompt_pipeline.batch import BatchLimits, BatchRecovery, BatchResult
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    FrameMode,
    ProviderSettings,
)
from t2i_prompt_pipeline.safe_avant_garde_batch import (
    AVANT_GARDE_ARTISTS,
    SAFE_AVANT_GARDE_FRAMES_PER_THEME,
    SAFE_AVANT_GARDE_THEME_COUNT,
    SAFE_CAST_CONFIGURATIONS,
    build_safe_avant_garde_tasks,
    run_safe_avant_garde_batch,
)
from tests.factories import make_rules, make_settings


def test_safe_avant_garde_matrix_has_exact_requested_shape() -> None:
    tasks = build_safe_avant_garde_tasks()

    assert len(AVANT_GARDE_ARTISTS) == 24
    assert len({artist.slug for artist in AVANT_GARDE_ARTISTS}) == 24
    assert len(SAFE_CAST_CONFIGURATIONS) == 3
    assert len(tasks) == 72
    assert (
        len(tasks)
        * SAFE_AVANT_GARDE_THEME_COUNT
        * SAFE_AVANT_GARDE_FRAMES_PER_THEME
        == 43_200
    )
    assert len({task.task_id for task in tasks}) == 72


def test_safe_avant_garde_tasks_are_clothed_adult_variations() -> None:
    tasks = build_safe_avant_garde_tasks()

    assert {
        (task.spec.female_count, task.spec.male_count)
        for task in tasks
    } == {(1, 1), (2, 1), (3, 0)}
    for task in tasks:
        assert task.artist.name in task.spec.brief
        assert task.spec.theme_count == 100
        assert task.spec.frames_per_theme == 6
        assert task.spec.content_level == ContentLevel.AESTHETIC
        assert task.spec.frame_mode == FrameMode.VARIATIONS
        assert "25岁以上" in task.spec.brief
        assert "不透明且完整覆盖" in task.spec.brief
        assert "不出现裸露、性行为" in task.spec.brief


async def test_safe_batch_uses_shared_stop_executor(monkeypatch, tmp_path):
    tasks = build_safe_avant_garde_tasks()
    config = AppConfig(
        spec=tasks[0].spec,
        provider=ProviderSettings(model="test"),
        runs_directory=tmp_path / "runs",
        prompts_directory=tmp_path / "prompts",
        run_settings=make_settings(),
        rules=make_rules(tasks[0].spec),
    )
    limits = BatchLimits(max_task_attempts=12)
    path = tmp_path / "batch.json"
    expected = BatchResult(72, 43200, (), path)

    async def execute(received_config, received_tasks, state_file, **kwargs):
        assert received_config == config
        assert [(item.task_id, item.spec) for item in received_tasks] == [
            (item.task_id, item.spec) for item in tasks
        ]
        assert state_file == path
        assert kwargs.get("recovery", BatchRecovery.STOP) == BatchRecovery.STOP
        assert kwargs["limits"] == limits
        return expected

    monkeypatch.setattr(safe_avant_garde_batch, "run_batch", execute)
    assert await run_safe_avant_garde_batch(config, path, limits=limits) == expected
