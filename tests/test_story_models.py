from __future__ import annotations

import pytest
from pydantic import ValidationError

from t2i_story_pipeline.models import (
    NarrativeThemeResult,
    ReviewDimension,
    ReviewIssue,
    StoryBlueprint,
    StoryResult,
    TokenUsage,
)
from t2i_story_pipeline.render import render_narratives
from tests.story_factories import (
    make_narrative_review,
    make_narrative_sequence,
    make_narrative_theme,
    make_story_blueprint,
    make_story_request,
)


def test_blueprint_requires_contiguous_character_ids() -> None:
    payload = make_story_blueprint().model_dump(mode="json")
    payload["characters"][1]["character_id"] = "C03"

    with pytest.raises(ValidationError, match="人物 ID 必须"):
        StoryBlueprint.model_validate(payload)


def test_blueprint_rejects_unknown_character_references() -> None:
    payload = make_story_blueprint().model_dump(mode="json")
    payload["beats"][0]["participant_ids"] = ["C01", "C99"]

    with pytest.raises(ValidationError, match="引用未知人物"):
        StoryBlueprint.model_validate(payload)


def test_blueprint_requires_ordered_story_beats() -> None:
    payload = make_story_blueprint().model_dump(mode="json")
    payload["beats"][1]["beat_id"] = "B03"

    with pytest.raises(ValidationError, match="故事节拍 ID 必须"):
        StoryBlueprint.model_validate(payload)


def test_story_result_requires_a_passing_final_review() -> None:
    blueprint = make_story_blueprint()
    sequence = make_narrative_sequence()

    with pytest.raises(ValidationError, match="最终叙事评审未达到发布标准"):
        StoryResult(
            run_id="abcdef123456",
            request=make_story_request(),
            blueprint=blueprint,
            themes=[
                NarrativeThemeResult(
                    theme=make_narrative_theme(),
                    sequence=sequence,
                    narratives=render_narratives(
                        blueprint,
                        make_narrative_theme(),
                        sequence,
                    ),
                    reviews=[make_narrative_review(passing=False)],
                    revision_count=0,
                )
            ],
            usage=TokenUsage(total_tokens=30),
        )


def test_review_issue_rejects_unbounded_critic_prose() -> None:
    with pytest.raises(ValidationError):
        ReviewIssue(
            scene_id="S01",
            dimension=ReviewDimension.CREATIVE_UNITY,
            problem="问" * 241,
            required_change="修正",
        )


def test_narrative_scene_allows_only_one_decisive_action() -> None:
    payload = make_narrative_sequence(frame_count=1).scenes[0].model_dump(
        mode="json"
    )
    payload["present_actions"].append(payload["present_actions"][0])

    with pytest.raises(ValidationError):
        type(make_narrative_sequence(frame_count=1).scenes[0]).model_validate(
            payload
        )


def test_narrative_scene_rejects_explicitly_invisible_content() -> None:
    payload = make_narrative_sequence(frame_count=1).scenes[0].model_dump(
        mode="json"
    )
    payload["material_and_physical_feedback"] = [
        "指尖气流扰动不可见却可感。"
    ]

    with pytest.raises(ValidationError, match="必须能够直接成像"):
        type(make_narrative_sequence(frame_count=1).scenes[0]).model_validate(
            payload
        )


def test_narrative_scene_schema_exposes_invisible_content_constraint() -> None:
    schema = type(
        make_narrative_sequence(frame_count=1).scenes[0]
    ).model_json_schema()

    evidence_items = schema["properties"]["sensory_evidence"]["items"]
    assert evidence_items["not"]["pattern"] == "不可见"


def test_narrative_scene_rejects_time_progression_inside_one_frame() -> None:
    payload = make_narrative_sequence(frame_count=1).scenes[0].model_dump(
        mode="json"
    )
    payload["present_actions"][0]["resulting_state"] = "两人随后走向出口。"

    with pytest.raises(ValidationError, match="不得包含连续时间推进"):
        type(make_narrative_sequence(frame_count=1).scenes[0]).model_validate(
            payload
        )


def test_narrative_scene_rejects_shot_scale_transition() -> None:
    payload = make_narrative_sequence(frame_count=1).scenes[0].model_dump(
        mode="json"
    )
    payload["camera_composition"] = "平视中景转为远景固定。"

    with pytest.raises(ValidationError, match="不得包含镜头运动或景别转换"):
        type(make_narrative_sequence(frame_count=1).scenes[0]).model_validate(
            payload
        )


def test_narrative_scene_rejects_time_progression_in_character_entry() -> None:
    payload = make_narrative_sequence(frame_count=1).scenes[0].model_dump(
        mode="json"
    )
    payload["character_entry"] = "人物一入画，人物二随后跟进。"

    with pytest.raises(ValidationError, match="人物入画不得包含连续时间推进"):
        type(make_narrative_sequence(frame_count=1).scenes[0]).model_validate(
            payload
        )
