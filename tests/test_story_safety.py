from __future__ import annotations

import pytest

from t2i_story_pipeline.errors import UnsafeStoryError
from t2i_story_pipeline.safety import (
    validate_generated_story,
    validate_source_story,
)


@pytest.mark.parametrize(
    "story",
    (
        "一名少女在雨夜车站等车。",
        "A teenage traveler waits at a station.",
    ),
)
def test_story_rejects_minor_or_age_ambiguous_characters(story: str) -> None:
    with pytest.raises(UnsafeStoryError, match="必须明确成年"):
        validate_source_story(story)


def test_story_rejects_coercive_sexual_content() -> None:
    with pytest.raises(UnsafeStoryError, match="胁迫语境"):
        validate_source_story("两名成年人在胁迫下被迫拍摄裸体照片。")


@pytest.mark.parametrize(
    "story",
    (
        "一名成年人被迫裸体。",
        "一名成年人被拖入房间，内衣被强行扯开。",
        "一名成年人被压制在桌边，内衣遭到撕扯。",
    ),
)
def test_story_rejects_passive_coercion_in_sexualized_context(
    story: str,
) -> None:
    with pytest.raises(UnsafeStoryError, match="胁迫语境"):
        validate_source_story(story)


def test_story_allows_nonsexual_historical_violence() -> None:
    validate_source_story("两名成年巡警将持刀嫌疑人压制在地并夺下武器。")


def test_story_allows_nonsexual_coercion_near_exposed_environment() -> None:
    validate_generated_story("暴雨使列车被迫停下，积水沿裸露的铁轨向远处流动。")


def test_story_rejects_intimacy_without_consent_signal() -> None:
    with pytest.raises(UnsafeStoryError, match="必须在故事中明确"):
        validate_source_story("两名三十岁的成年人在露台亲吻。")


def test_story_accepts_consensual_adult_intimacy() -> None:
    validate_source_story(
        "两名三十岁的成年人双方自愿在露台亲吻，彼此回应且任何一方都可以停止。"
    )


def test_explicit_content_level_requires_consent_in_source_story() -> None:
    with pytest.raises(UnsafeStoryError, match="必须在故事中明确"):
        validate_source_story(
            "两名三十岁的成年人站在卧室内。",
            require_intimate_consent=True,
        )

    validate_source_story(
        "两名三十岁的成年人自愿互动、彼此回应且随时可以停止。",
        require_intimate_consent=True,
    )


def test_generated_story_allows_adult_memory_of_youth() -> None:
    validate_generated_story("两名三十多岁的成年人回忆少年时代的旧车站。")


def test_generated_story_still_rejects_current_minor_character() -> None:
    with pytest.raises(UnsafeStoryError, match="未成年或年龄模糊"):
        validate_generated_story("一名少年站在旧车站月台。")
