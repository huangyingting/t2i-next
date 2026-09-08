from __future__ import annotations

from collections.abc import Iterable

import pytest

from t2i_story_pipeline.errors import (
    StoryContractError,
    StoryProviderResponseError,
    UnsafeStoryError,
)
from t2i_story_pipeline.models import (
    ContentLevel,
    StoryRequest,
    StoryStage,
    TokenUsage,
)
from t2i_story_pipeline.provider import ModelResponse
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


@pytest.mark.asyncio
async def test_studio_generates_final_story_paragraphs() -> None:
    model = FakeStoryModel(
        [
            make_theme_batch(count=2),
            make_frame_sequence(theme_index=1),
            make_frame_sequence(theme_index=2),
        ]
    )

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request(theme_count=2)
    )

    assert [item.theme.theme_id for item in result.themes] == ["T001", "T002"]
    assert len(result.themes[0].frames) == 2
    assert model.stages == [
        StoryStage.THEMES,
        StoryStage.FRAMES,
        StoryStage.FRAMES,
    ]
    assert result.usage.total_tokens == 45


@pytest.mark.asyncio
async def test_studio_accepts_prose_without_quality_template() -> None:
    sequence = make_frame_sequence()
    sequence.frames[0].prose = (
        "雨夜电影风格，1930年代北平旧车站，两名三十岁的成年人隔着一只"
        "旧皮箱相望；平视中景让两人的迟疑与站灯下的潮湿反光同时留在画面里。"
    )
    model = FakeStoryModel([make_theme_batch(), sequence])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert result.themes[0].frames[0].prose == sequence.frames[0].prose
    assert model.stages == [StoryStage.THEMES, StoryStage.FRAMES]


@pytest.mark.asyncio
async def test_studio_requires_source_consent_for_explicit_content_level() -> None:
    model = FakeStoryModel([])
    request = StoryRequest(
        story="两名三十岁的成年人在卧室内交谈。",
        content_level=ContentLevel.EROTIC,
    )

    with pytest.raises(UnsafeStoryError, match="必须在故事中明确"):
        await StoryStudio(model).generate(request)

    assert model.stages == []


@pytest.mark.asyncio
async def test_studio_generates_one_hundred_themes_and_six_hundred_frames() -> None:
    values: list[object] = [
        make_theme_batch(start=start, count=10)
        for start in range(1, 101, 10)
    ]
    values.extend(
        make_frame_sequence(frame_count=6, theme_index=index)
        for index in range(1, 101)
    )
    model = FakeStoryModel(values)

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request(theme_count=100, frames_per_theme=6)
    )

    assert len(result.themes) == 100
    assert sum(len(item.frames) for item in result.themes) == 600
    assert model.stages.count(StoryStage.THEMES) == 10
    assert model.stages.count(StoryStage.FRAMES) == 100


@pytest.mark.asyncio
async def test_studio_retries_provider_shape_failure_and_counts_usage() -> None:
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

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert model.stages.count(StoryStage.THEMES) == 2
    assert "invalid themes" in model.messages[1][-1].content
    assert result.usage.total_tokens == 60


@pytest.mark.asyncio
async def test_studio_rejects_wrong_frame_ids() -> None:
    sequence = make_frame_sequence()
    sequence.frames[1].frame_id = "F03"
    model = FakeStoryModel([make_theme_batch(), sequence])

    with pytest.raises(StoryContractError, match="画面数量或顺序"):
        await StoryStudio(
            model,
            concurrency=1,
            generation_retries=0,
        ).generate(make_story_request())


@pytest.mark.asyncio
async def test_studio_rejects_unsafe_source_before_provider_call() -> None:
    model = FakeStoryModel([])
    request = make_story_request()
    request.story = "一名少女在车站等待。"

    with pytest.raises(UnsafeStoryError):
        await StoryStudio(model).generate(request)

    assert model.stages == []


@pytest.mark.asyncio
async def test_studio_rejects_generated_sexual_violence() -> None:
    sequence = make_frame_sequence()
    sequence.frames[0].prose = "两名成年人正在实施明确的性暴力。"
    model = FakeStoryModel([make_theme_batch(), sequence])

    with pytest.raises(UnsafeStoryError):
        await StoryStudio(
            model,
            concurrency=1,
            generation_retries=0,
        ).generate(make_story_request())
