from __future__ import annotations

import json

from t2i_story_pipeline.prompts import (
    interpretation_messages,
    narrative_messages,
    theme_messages,
)
from tests.story_factories import (
    make_narrative_theme,
    make_story_blueprint,
    make_story_request,
)


def test_interpretation_request_is_story_focused() -> None:
    request = make_story_request(theme_count=3, frames_per_theme=6)
    messages = interpretation_messages(request)
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert (
        "他们确认彼此身份后一起寻找遗失的行李"
        in payload["source_evidence_options"]
    )
    assert payload["theme_count"] == 3
    assert payload["frames_per_theme"] == 6
    assert "时间、地点" in messages[0].content
    assert "正在发生的动作" in messages[0].content
    assert "二十一岁以上成年人" in messages[0].content


def test_narrative_request_contains_complete_blueprint() -> None:
    request = make_story_request()
    blueprint = make_story_blueprint()
    theme = make_narrative_theme()
    messages = narrative_messages(request, blueprint, theme)
    payload = json.loads(messages[1].content)

    assert payload["story_blueprint"] == blueprint.model_dump(mode="json")
    assert (
        "他们确认彼此身份后一起寻找遗失的行李"
        in payload["source_evidence_options"]
    )
    assert payload["narrative_theme"] == theme.model_dump(mode="json")
    assert payload["frames_per_theme"] == 2
    assert "时空开场、环境证据、人物进入" in messages[0].content
    assert "感官的可见证据" in messages[0].content
    assert "材质物理反馈" in messages[0].content
    assert "不得为了填字段虚构前因或人物关系" in messages[0].content
    assert "decisive_moment" in messages[0].content
    assert "不得添加可替换的装饰" in messages[0].content


def test_theme_request_requires_distinct_creative_intents() -> None:
    request = make_story_request(theme_count=12, frames_per_theme=6)
    blueprint = make_story_blueprint()
    existing = [make_narrative_theme()]
    messages = theme_messages(
        request,
        blueprint,
        start_index=2,
        count=10,
        existing_themes=existing,
    )
    payload = json.loads(messages[1].content)

    assert payload["batch_start"] == 2
    assert payload["batch_count"] == 10
    assert payload["frames_per_theme"] == 6
    assert payload["existing_theme_ledger"][0]["theme_id"] == "T001"
    assert "决定性瞬间" in messages[0].content
    assert "不得只替换形容词" in messages[0].content
    assert "不得在同一字段内重复" in messages[0].content


def test_narrative_request_requires_creative_intent_to_be_visualized() -> None:
    request = make_story_request()
    messages = narrative_messages(
        request,
        make_story_blueprint(),
        make_narrative_theme(),
    )

    assert "不得把 emotional_core" in messages[0].content
    assert "一张静态画面中的一个决定性瞬间" in messages[0].content
    assert "不得写切镜、推镜、镜头运动或连续时间推进" in (messages[0].content)
    assert "具体人物动作、物件位置、环境变化和光影关系" in (messages[0].content)
