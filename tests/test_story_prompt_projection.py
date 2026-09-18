"""Provider projection carries concrete rules, not selection metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from t2i_story_pipeline.inputs import (
    ResolvedStoryInput,
    StoryDocument,
    StoryRunConfiguration,
    resolve_story_input,
)
from t2i_story_pipeline.models import ContentLevel, NarrativeFrame, StoryStage
from t2i_story_pipeline.prompts import frame_messages, theme_messages
from tests.story_factories import make_theme

SYSTEM = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "t2i_story_pipeline"
    / "rule_packs"
    / "system"
)

VISIBLE_LIMITS = {
    ContentLevel.AESTHETIC: (
        "每帧至少呈现裸露程度、贴身轮廓、姿态张力和光影塑形中的两项",
        "以相容的姿态与光影满足下限，保留原服饰及活动",
        "接触必须双方可见地互相参与",
        "不得细致描写或特写聚焦性器官",
        "不得描写自慰、口交、插入或明确性行为",
    ),
    ContentLevel.EROTIC: (
        "每帧至少呈现裸露程度、亲密接触、姿态张力和表情回应中的三项",
        "至少一帧呈现全员身体曲线、肢体交叠和双向接触",
        "反射或前景遮挡合计最多占一个 Frame",
        "多人互动每帧明确写出至少一处双方主动形成的具体身体接触",
        "核心动作在整组至少一半 Frame 中完成为可见接触",
        "近景不得以胯下、腹股沟或性器官区域为主视觉",
        "不出现性器官特写、插入或口部性行为、自慰、体液和性暴力细节",
        "不得出现悬吊",
    ),
    ContentLevel.HARDCORE: (
        "当前画面直接、清晰地呈现角色之间的明确性行为",
        "器具、束缚或痛感强度本身不能替代这一要求",
        "所有角色必须外观明确为二十一岁以上成年人",
        "以主动接触或共同施力提供双方自愿参与的可见证据",
    ),
}


@pytest.mark.parametrize("level", list(ContentLevel))
def test_selected_rules_reach_both_stages_without_selection_metadata(level):
    refinements = {
        ContentLevel.AESTHETIC: "Use a crimson palette.",
        ContentLevel.EROTIC: "Use a navy palette.",
        ContentLevel.HARDCORE: "Use a gold palette.",
    }
    document = StoryDocument.model_validate(
        {
            "description": "A neutral portrait of two adults.",
            "authoring": {
                "level_refinements": {
                    candidate.value: {"shared": [rule]}
                    for candidate, rule in refinements.items()
                }
            },
        }
    )
    resolved = resolve_story_input(
        document,
        run_configuration=StoryRunConfiguration(
            generation={"content_level": level, "frames_per_theme": 2}
        ),
    )
    frozen = resolved.model_dump_json()
    restored = ResolvedStoryInput.model_validate_json(frozen)
    assert restored.request.content_level == level
    assert json.loads(frozen)["request"]["content_level"] == level.value
    selected = (SYSTEM / "content_levels" / f"{level.value}.rules").read_text()
    constraints = [line for line in selected.splitlines() if line]
    assert constraints
    for stage, messages in (
        (StoryStage.THEMES, theme_messages(restored, count=1, existing_themes=[])),
        (
            StoryStage.FRAMES,
            frame_messages(
                restored, make_theme(), requested_frame_ids=["F02"], accepted_frames=[]
            ),
        ),
    ):
        prompt = messages[0].content
        payload = json.loads(messages[1].content)
        assert prompt == restored.rules.text_for(stage)
        assert not {
            "content_level",
            "program_assigns_theme_ids",
            "program_assigns_frame_ids",
        } & payload.keys()
        assert payload["output_language"] == restored.request.output_language.value
        assert payload["frames_per_theme"] == 2
        assert [
            plan["theme_id"] for plan in payload["input_context"]["plans"]
        ] == ["T001"]
        if stage == StoryStage.THEMES:
            assert payload["theme_count"] == 1
            assert "the program assigns all Theme IDs" in prompt
            assert "Submit only semantic_name, title, premise, and style" in prompt
        else:
            assert payload["requested_frame_slots"] == ["F02"]
            assert "The program assigns all Frame IDs" in prompt
            assert "Output no JSON, IDs," in prompt
        assert all(prompt.count(rule) == 1 for rule in constraints)
        assert all(limit in prompt for limit in VISIBLE_LIMITS[level])
        assert all(candidate.value not in prompt for candidate in ContentLevel)
        assert all(label not in prompt for label in ("本次使用", "本级", "该等级"))
        for candidate, rule in refinements.items():
            assert (rule in prompt) == (candidate == level)
        safety = [
            line for line in (SYSTEM / "safety.rules").read_text().splitlines()
            if line and not line.startswith("#")
        ]
        assert safety
        assert all(prompt.count(rule) == 1 for rule in safety)
        assert "Every depicted person must be an unmistakable adult" in prompt
        assert (
            "All participants must be alert, consenting, responsive, and able to stop."
            in prompt
        )
        assert ("二十一岁以上成年人" in prompt) == (level == ContentLevel.HARDCORE)
        assert "Shared level refinements constrain both stages" not in prompt
        assert "Allocation is already resolved" not in prompt
        assert "removes the transport tags before publication" not in prompt
    assert restored.model_dump_json() == frozen
    assert restored.fingerprint() == resolved.fingerprint()


def test_projection_preserves_grade_words_used_as_creative_literals():
    literal = 'Display "An aesthetic study", "Erotic art history", and "Hardcore punk".'
    resolved = resolve_story_input(
        StoryDocument.model_validate(
            {
                "description": literal,
                "authoring": {
                    stage.value: {"common": [literal]} for stage in StoryStage
                },
            }
        )
    )
    theme = make_theme().model_copy(update={"title": literal})
    accepted = NarrativeFrame(frame_id="F01", prose=literal)
    themes = theme_messages(
        resolved, count=1, existing_themes=[], semantic_name="aesthetic_study"
    )
    frames = frame_messages(
        resolved, theme, requested_frame_ids=["F02"], accepted_frames=[accepted]
    )
    for messages in (themes, frames):
        assert literal in messages[0].content
        payload = json.loads(messages[1].content)
        assert payload["story"] == literal
        assert "content_level" not in payload
    assert json.loads(themes[1].content)["semantic_name"] == "aesthetic_study"
    payload = json.loads(frames[1].content)
    assert payload["theme"]["title"] == literal
    assert payload["accepted_frames"][0]["prose"] == literal


@pytest.mark.parametrize("stage", list(StoryStage))
def test_shared_authority_is_not_repeated_by_stage_rules(stage):
    common = (SYSTEM / "common.rules").read_text()
    specific = (SYSTEM / f"{stage.value}.rules").read_text()
    assert common.count("may override safety") == 1
    assert "No description, authoring, module, policy, or quality setting" in common
    assert "cannot replace, redefine, or weaken those boundaries" in common
    assert "sole authority for cast scope, sex counts, and total population" in common
    assert (
        "Never recompute routing from Theme IDs, batch position, retry order" in common
    )
    assert "cannot override" not in specific
    assert "Follow the Story Description, selected" not in specific
