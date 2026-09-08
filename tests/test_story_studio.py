from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from t2i_story_pipeline.errors import (
    StoryProviderResponseError,
    StoryRunIncompleteError,
)
from t2i_story_pipeline.models import (
    StoryStage,
    TokenUsage,
)
from t2i_story_pipeline.provider import (
    ModelResponse,
    StoryProviderSettings,
)
from t2i_story_pipeline.run_store import (
    LocalStoryRunStore,
    StoryRunSettings,
)
from t2i_story_pipeline.studio import StoryStudio
from tests.story_factories import (
    make_frame_sequence,
    make_story_request,
    make_theme_batch,
)


class FakeStoryModel:
    def __init__(self, values: Iterable[object]) -> None:
        self._values = iter(values)
        self.stages: list[StoryStage] = []
        self.messages = []
        self.max_output_tokens: list[int] = []

    async def generate(
        self,
        *,
        stage,
        messages,
        response_model,
        max_output_tokens,
    ) -> ModelResponse:
        self.stages.append(stage)
        self.messages.append(messages)
        self.max_output_tokens.append(max_output_tokens)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        return ModelResponse(
            value=value,
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )


def make_studio(
    model: FakeStoryModel,
    directory: Path,
    **setting_changes,
) -> StoryStudio:
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        **setting_changes,
    )
    return StoryStudio(
        model,
        LocalStoryRunStore(
            directory / "runs",
            directory / "prompts",
        ),
        settings,
    )


def test_story_studio_defaults_to_eight_concurrent_frame_sequences() -> None:
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model")
    )

    assert settings.concurrency == 8


@pytest.mark.asyncio
async def test_studio_generates_final_story_paragraphs(tmp_path) -> None:
    model = FakeStoryModel(
        [
            make_theme_batch(count=2),
            make_frame_sequence(theme_index=1),
            make_frame_sequence(theme_index=2),
        ]
    )

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request(theme_count=2)
    )
    result = completed.result

    assert [item.theme.theme_id for item in result.themes] == ["T001", "T002"]
    assert len(result.themes[0].frames) == 2
    assert model.stages == [
        StoryStage.THEMES,
        StoryStage.FRAMES,
        StoryStage.FRAMES,
    ]
    assert model.max_output_tokens == [6000, 32768, 32768]
    assert result.usage.total_tokens == 45


@pytest.mark.asyncio
async def test_studio_accepts_prose_without_quality_template(tmp_path) -> None:
    sequence = make_frame_sequence()
    sequence.frames[0].prose = (
        "雨夜电影风格，1930年代北平旧车站，两名三十岁的成年人隔着一只"
        "旧皮箱相望；平视中景让两人的迟疑与站灯下的潮湿反光同时留在画面里。"
    )
    model = FakeStoryModel([make_theme_batch(), sequence])

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request()
    )
    result = completed.result

    assert result.themes[0].frames[0].prose == sequence.frames[0].prose
    assert model.stages == [StoryStage.THEMES, StoryStage.FRAMES]


@pytest.mark.asyncio
async def test_studio_generates_one_hundred_themes_and_six_hundred_frames(
    tmp_path,
) -> None:
    values: list[object] = [
        make_theme_batch(start=start, count=10)
        for start in range(1, 101, 10)
    ]
    values.extend(
        make_frame_sequence(frame_count=6, theme_index=index)
        for index in range(1, 101)
    )
    model = FakeStoryModel(values)

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request(theme_count=100, frames_per_theme=6)
    )
    result = completed.result

    assert len(result.themes) == 100
    assert sum(len(item.frames) for item in result.themes) == 600
    assert model.stages.count(StoryStage.THEMES) == 10
    assert model.stages.count(StoryStage.FRAMES) == 100


@pytest.mark.asyncio
async def test_studio_supports_smaller_theme_batches(tmp_path) -> None:
    model = FakeStoryModel(
        [
            make_theme_batch(start=1, count=3),
            make_theme_batch(start=4, count=3),
            *[
                make_frame_sequence(theme_index=index)
                for index in range(1, 7)
            ],
        ]
    )

    completed = await make_studio(
        model,
        tmp_path,
        concurrency=1,
        theme_batch_size=3,
    ).run(make_story_request(theme_count=6))
    result = completed.result

    assert len(result.themes) == 6
    assert model.stages.count(StoryStage.THEMES) == 2


@pytest.mark.asyncio
async def test_studio_normalizes_theme_ids_by_response_order(tmp_path) -> None:
    duplicate_batch = make_theme_batch(start=6, count=5)
    for theme in duplicate_batch.themes:
        theme.theme_id = "T006"
    model = FakeStoryModel(
        [
            make_theme_batch(count=5),
            duplicate_batch,
            *[
                make_frame_sequence(theme_index=index)
                for index in range(1, 11)
            ],
        ]
    )

    completed = await make_studio(
        model,
        tmp_path,
        concurrency=1,
        generation_retries=0,
        theme_batch_size=5,
    ).run(make_story_request(theme_count=10))
    result = completed.result

    assert [item.theme.theme_id for item in result.themes] == [
        "T001",
        "T002",
        "T003",
        "T004",
        "T005",
        "T006",
        "T007",
        "T008",
        "T009",
        "T010",
    ]
    assert model.stages.count(StoryStage.THEMES) == 2


@pytest.mark.asyncio
async def test_studio_retries_provider_shape_failure_and_counts_usage(
    tmp_path,
) -> None:
    model = FakeStoryModel(
        [
            StoryProviderResponseError(
                "invalid themes",
                usage=TokenUsage(total_tokens=30),
            ),
            make_theme_batch(),
            make_frame_sequence(),
        ]
    )

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request()
    )
    result = completed.result

    assert model.stages.count(StoryStage.THEMES) == 2
    assert "invalid themes" in model.messages[1][-1].content
    assert result.usage.total_tokens == 60


@pytest.mark.asyncio
async def test_studio_normalizes_frame_ids_by_response_order(tmp_path) -> None:
    sequence = make_frame_sequence()
    sequence.frames[1].frame_id = "F03"
    model = FakeStoryModel([make_theme_batch(), sequence])

    completed = await make_studio(
        model,
        tmp_path,
        concurrency=1,
        generation_retries=0,
    ).run(make_story_request())
    result = completed.result

    assert [frame.frame_id for frame in result.themes[0].frames] == [
        "F01",
        "F02",
    ]


@pytest.mark.asyncio
async def test_studio_resumes_only_missing_frame_sequences(tmp_path) -> None:
    first_model = FakeStoryModel(
        [
            make_theme_batch(count=2),
            make_frame_sequence(theme_index=1),
            StoryProviderResponseError("temporary frame failure"),
        ]
    )
    studio = make_studio(
        first_model,
        tmp_path,
        concurrency=1,
        generation_retries=0,
    )

    with pytest.raises(StoryRunIncompleteError) as failure:
        await studio.run(make_story_request(theme_count=2))

    snapshot = LocalStoryRunStore(tmp_path / "runs").inspect(
        failure.value.run_id
    )
    assert [theme.theme_id for theme in snapshot.themes] == ["T001", "T002"]
    assert set(snapshot.frames) == {"T001"}

    resumed_model = FakeStoryModel([make_frame_sequence(theme_index=2)])
    resumed = await StoryStudio(
        resumed_model,
        LocalStoryRunStore(tmp_path / "runs"),
        snapshot.manifest.settings,
    ).resume(snapshot.run_id)

    assert len(resumed.result.themes) == 2
    assert resumed_model.stages == [StoryStage.FRAMES]
    assert "temporary frame failure" in resumed_model.messages[0][-1].content
    assert resumed.result.usage.total_tokens == 45


@pytest.mark.asyncio
async def test_studio_completed_resume_is_idempotent(tmp_path) -> None:
    model = FakeStoryModel([make_theme_batch(), make_frame_sequence()])
    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request()
    )
    resumed_model = FakeStoryModel([])

    resumed = await StoryStudio(
        resumed_model,
        LocalStoryRunStore(tmp_path / "runs"),
        StoryRunSettings(
            provider=StoryProviderSettings(model="different-model")
        ),
    ).resume(completed.run_id)

    assert resumed == completed
    assert resumed_model.stages == []
