from __future__ import annotations

import pytest
from pydantic import ValidationError

from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeFrame,
    NarrativeTheme,
    StoryRequest,
    exact_frame_sequence_model,
    exact_theme_batch_model,
)
from tests.story_factories import make_frame_sequence, make_theme_batch


def test_exact_theme_batch_schema_requires_requested_count() -> None:
    response_model = exact_theme_batch_model(2)

    with pytest.raises(ValidationError):
        response_model.model_validate(make_theme_batch(count=1).model_dump())


def test_exact_frame_schema_requires_requested_count() -> None:
    response_model = exact_frame_sequence_model(6)

    with pytest.raises(ValidationError):
        response_model.model_validate(
            make_frame_sequence(frame_count=5).model_dump()
        )


def test_narrative_frame_is_one_final_prose_paragraph() -> None:
    with pytest.raises(ValidationError, match="换行"):
        NarrativeFrame(frame_id="F01", prose="第一段。\n第二段。")


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


def test_story_request_accepts_all_content_levels() -> None:
    assert {
        StoryRequest(story="成年人物。", content_level=level).content_level
        for level in ContentLevel
    } == set(ContentLevel)


def test_story_request_rejects_unknown_content_level() -> None:
    with pytest.raises(ValidationError):
        StoryRequest(story="成年人物。", content_level="graphic")
