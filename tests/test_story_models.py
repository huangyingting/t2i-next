from __future__ import annotations

import pytest
from pydantic import ValidationError

from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeFrame,
    NarrativeTheme,
    NarrativeThemeBatch,
    StoryRequest,
    exact_frame_sequence_model,
    exact_theme_batch_model,
)
from tests.story_factories import make_frame_sequence, make_theme_batch


def test_exact_theme_batch_schema_requires_requested_count() -> None:
    response_model = exact_theme_batch_model(2)

    with pytest.raises(ValidationError):
        response_model.model_validate(make_theme_batch(count=1).model_dump())


def test_theme_batch_requires_lowercase_snake_case_semantic_name() -> None:
    with pytest.raises(ValidationError):
        NarrativeThemeBatch(
            semantic_name="Lost Luggage",
            themes=make_theme_batch().themes,
        )


def test_exact_frame_schema_requires_requested_count() -> None:
    response_model = exact_frame_sequence_model(6)

    with pytest.raises(ValidationError):
        response_model.model_validate(
            make_frame_sequence(frame_count=5).model_dump()
        )


def test_narrative_frame_is_one_final_prose_paragraph() -> None:
    with pytest.raises(ValidationError, match="换行"):
        NarrativeFrame(frame_id="F01", prose="第一段。\n第二段。")


def test_narrative_frame_allows_up_to_32768_characters() -> None:
    frame = NarrativeFrame(frame_id="F01", prose="a" * 32768)

    assert len(frame.prose) == 32768
    with pytest.raises(ValidationError):
        NarrativeFrame(frame_id="F01", prose="a" * 32769)


def test_narrative_theme_requires_one_style_anchor() -> None:
    with pytest.raises(ValidationError):
        NarrativeTheme(
            theme_id="T001",
            title="遗失的行李",
            premise="两名成年人共同寻找行李。",
        )


def test_narrative_theme_does_not_truncate_long_style_description() -> None:
    style = "清代内廷暗调电影风格" * 10

    theme = NarrativeTheme(
        theme_id="T001",
        title="遗失的行李",
        premise="两名成年人共同寻找行李。",
        style=style,
    )

    assert theme.style == style


def test_narrative_theme_does_not_truncate_long_premise() -> None:
    premise = "人物寻找遗失行李。" * 40

    theme = NarrativeTheme(
        theme_id="T001",
        title="遗失的行李",
        premise=premise,
        style="旧城雨夜电影风格",
    )

    assert theme.premise == premise


def test_story_request_defaults_to_aesthetic_content() -> None:
    request = StoryRequest(story="两名三十岁的成年人站在旧车站。")

    assert request.content_level is ContentLevel.AESTHETIC


def test_story_request_accepts_long_form_briefs_with_a_bounded_limit() -> None:
    assert len(StoryRequest(story="a" * 30_000).story) == 30_000

    with pytest.raises(ValidationError):
        StoryRequest(story="a" * 50_001)


def test_story_request_rejects_source_prompt_path_instead_of_stem() -> None:
    with pytest.raises(ValidationError):
        StoryRequest(
            story="测试故事。",
            source_prompt_stem="../story",
        )

    with pytest.raises(ValidationError, match="必须包含字母或数字"):
        StoryRequest(
            story="测试故事。",
            source_prompt_stem="---",
        )


def test_story_request_supports_optional_and_male_only_cast_constraints() -> None:
    unconstrained = StoryRequest(story="测试故事。")
    request = StoryRequest(
        story="测试故事。",
        female_count=0,
        male_count=2,
    )

    assert unconstrained.female_count is None
    assert unconstrained.male_count is None
    assert request.female_count == 0
    assert request.male_count == 2


def test_story_request_rejects_invalid_cast_constraints() -> None:
    with pytest.raises(ValidationError, match="人物约束不能同时为零"):
        StoryRequest(story="测试故事。", female_count=0, male_count=0)

    with pytest.raises(ValidationError, match="每个主题最多包含八名角色"):
        StoryRequest(story="测试故事。", female_count=5, male_count=4)


def test_story_request_accepts_all_content_levels() -> None:
    assert {
        StoryRequest(story="成年人物。", content_level=level).content_level
        for level in ContentLevel
    } == set(ContentLevel)


def test_story_request_rejects_unknown_content_level() -> None:
    with pytest.raises(ValidationError):
        StoryRequest(story="成年人物。", content_level="graphic")
