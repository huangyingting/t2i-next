from __future__ import annotations

from collections.abc import Iterable

import pytest

from t2i_story_pipeline.errors import (
    StoryContractError,
    StoryProviderResponseError,
    UnsafeStoryError,
)
from t2i_story_pipeline.models import ContentLevel, StoryRequest, StoryStage, TokenUsage
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


def quality_feedback_text(result) -> str:
    return " | ".join(
        f"{item.item_id}: {';'.join(item.issues)}"
        for item in result.quality_feedback
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
    assert result.themes[0].frames[0].prose.startswith(
        "1930年代北平电影风格"
    )
    assert model.stages == [
        StoryStage.THEMES,
        StoryStage.FRAMES,
        StoryStage.FRAMES,
    ]
    assert result.usage.total_tokens == 45


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
@pytest.mark.parametrize(
    ("level", "expected_issue"),
    (
        (ContentLevel.EROTIC, "erotic 缺少直接可见的成人情色事实"),
        (ContentLevel.HARDCORE, "hardcore 缺少直接明确的成人性行为"),
    ),
)
async def test_studio_reports_content_level_underflow_without_retry(
    level: ContentLevel,
    expected_issue: str,
) -> None:
    model = FakeStoryModel([make_theme_batch(), make_frame_sequence()])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request(content_level=level)
    )

    assert expected_issue in quality_feedback_text(result)
    assert model.stages == [StoryStage.THEMES, StoryStage.FRAMES]


@pytest.mark.asyncio
async def test_studio_reports_historical_anachronism_without_retry() -> None:
    sequence = make_frame_sequence()
    sequence.frames[0].prose = sequence.frames[0].prose.replace(
        "同一只旧皮箱",
        "智能手机旁的同一只旧皮箱",
    )
    model = FakeStoryModel([make_theme_batch(), sequence])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert "时代或季节背景不符的事物：智能手机" in quality_feedback_text(result)
    assert model.stages == [StoryStage.THEMES, StoryStage.FRAMES]


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
async def test_studio_reports_chinese_theme_with_unexpected_english() -> None:
    invalid = make_theme_batch()
    invalid.themes[0].premise += " The clue is hidden in the case."
    model = FakeStoryModel(
        [
            invalid,
            make_frame_sequence(),
        ]
    )

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert model.stages.count(StoryStage.THEMES) == 1
    assert "原文之外的英文词" in quality_feedback_text(result)
    assert result.themes[0].theme.theme_id == "T001"


@pytest.mark.asyncio
async def test_studio_reports_theme_fact_not_present_in_story() -> None:
    invalid = make_theme_batch()
    invalid.themes[0].premise += "其中一人是低位妃嫔。"
    model = FakeStoryModel([invalid, make_frame_sequence()])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert "来源敏感事实" in quality_feedback_text(result)


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
async def test_studio_reports_frame_without_theme_style_prefix() -> None:
    invalid = make_frame_sequence()
    invalid.frames[0].prose = "1930年代秋夜，人物站在旧车站。"
    model = FakeStoryModel(
        [
            make_theme_batch(),
            invalid,
        ]
    )

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert model.stages.count(StoryStage.FRAMES) == 1
    assert "必须以主题风格开头" in quality_feedback_text(result)


@pytest.mark.asyncio
async def test_studio_reports_frame_with_continuous_action_shape() -> None:
    invalid = make_frame_sequence()
    invalid.frames[0].prose = (
        "1930年代北平电影风格，1930年代秋夜的旧车站。"
        "两名三十岁的成年人站在月台上。"
        "此刻，左侧人物正在握住皮箱提手。"
        "随后右侧人物起身走向站柱。"
        "镜头采用平视中景，浅景深聚焦提手。"
        "光线来自侧后方站灯，气氛警惕。"
    )
    model = FakeStoryModel(
        [
            make_theme_batch(),
            invalid,
        ]
    )

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert model.stages.count(StoryStage.FRAMES) == 1
    assert "推进词" in quality_feedback_text(result)
    assert len(result.themes[0].frames) == 2


@pytest.mark.asyncio
async def test_studio_reports_frame_without_camera_sentence() -> None:
    invalid = make_frame_sequence()
    invalid.frames[0].prose = invalid.frames[0].prose.replace(
        "镜头采用",
        "画面使用",
    )
    model = FakeStoryModel([make_theme_batch(), invalid])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert "镜头采用" in quality_feedback_text(result)


@pytest.mark.asyncio
async def test_studio_reports_pose_transition_in_character_paragraph() -> None:
    invalid = make_frame_sequence()
    invalid.frames[0].prose = invalid.frames[0].prose.replace(
        "紧绷的目光落在同一只旧皮箱上。",
        "紧绷的目光落在同一只旧皮箱上，右侧人物已从站姿蹲落。",
    )
    model = FakeStoryModel([make_theme_batch(), invalid])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert "姿态变化" in quality_feedback_text(result)


@pytest.mark.asyncio
async def test_studio_reports_secondary_action_in_character_paragraph() -> None:
    invalid = make_frame_sequence()
    invalid.frames[0].prose = invalid.frames[0].prose.replace(
        "紧绷的目光落在同一只旧皮箱上。",
        "紧绷的目光落在同一只旧皮箱上，右手伸向皮箱。",
    )
    model = FakeStoryModel([make_theme_batch(), invalid])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert "次动作" in quality_feedback_text(result)


@pytest.mark.asyncio
async def test_studio_reports_chained_actions_in_action_sentence() -> None:
    invalid = make_frame_sequence()
    invalid.frames[0].prose = invalid.frames[0].prose.replace(
        "右侧人物保持俯身姿态",
        "右侧人物随后起身又伸手",
    )
    model = FakeStoryModel([make_theme_batch(), invalid])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert "串联动作" in quality_feedback_text(result)


@pytest.mark.asyncio
async def test_studio_accepts_short_progressive_marker() -> None:
    sequence = make_frame_sequence()
    sequence.frames[0].prose = sequence.frames[0].prose.replace(
        "正在握紧",
        "正握紧",
    )
    model = FakeStoryModel([make_theme_batch(), sequence])

    result = await StoryStudio(
        model,
        concurrency=1,
        generation_retries=0,
    ).generate(make_story_request())

    assert "正握紧" in result.themes[0].frames[0].prose
    assert "T001/F01" not in quality_feedback_text(result)


@pytest.mark.asyncio
async def test_studio_reports_frame_fact_not_present_in_story() -> None:
    invalid = make_frame_sequence()
    invalid.frames[0].prose = invalid.frames[0].prose.replace(
        "两名三十岁的成年人",
        "一名低位妃嫔与一名三十岁的成年人",
    )
    model = FakeStoryModel([make_theme_batch(), invalid])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert "来源敏感事实" in quality_feedback_text(result)


@pytest.mark.asyncio
async def test_studio_reports_repeated_action_sentences() -> None:
    invalid = make_frame_sequence()
    invalid.frames[1].prose = invalid.frames[0].prose
    model = FakeStoryModel([make_theme_batch(), invalid])

    result = await StoryStudio(model, concurrency=1).generate(
        make_story_request()
    )

    assert "相似度" in quality_feedback_text(result)


@pytest.mark.asyncio
async def test_studio_rejects_unsafe_source_before_provider_call() -> None:
    model = FakeStoryModel([])
    request = make_story_request()
    request.story = "一名少女在车站等待。"

    with pytest.raises(UnsafeStoryError):
        await StoryStudio(model).generate(request)

    assert model.stages == []


@pytest.mark.asyncio
async def test_studio_rejects_generated_coercive_sexual_content() -> None:
    sequence = make_frame_sequence()
    sequence.frames[0].prose = (
        "1930年代北平电影风格，"
        "两名成年人在胁迫下被迫拍摄裸体照片。"
    )
    model = FakeStoryModel([make_theme_batch(), sequence])

    with pytest.raises(UnsafeStoryError):
        await StoryStudio(
            model,
            concurrency=1,
            generation_retries=0,
        ).generate(make_story_request())
