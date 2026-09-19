from __future__ import annotations

import pytest

from t2i_story_pipeline.inputs import (
    InputOverrides,
    StoryDocument,
    resolve_story_input,
)
from t2i_story_pipeline.models import (
    NarrativeFrame,
    OutputLanguage,
    StoryQualityPolicy,
    StoryStage,
)
from t2i_story_pipeline.quality_validation import (
    check_frame_quality,
    writing_constraints,
)


@pytest.mark.parametrize("language", list(OutputLanguage))
@pytest.mark.parametrize(
    ("stage", "field", "minimum", "maximum", "target"),
    [
        (StoryStage.FRAMES, None, 550, 1050, 800),
        (StoryStage.FRAMES, None, 900, 1900, 1400),
        (StoryStage.THEMES, "premise", 220, 580, 400),
        (StoryStage.THEMES, "style", 130, 390, 260),
        (StoryStage.FRAMES, None, 5, 8, 6),
    ],
)
def test_long_form_character_targets_use_the_effective_midpoint(
    language, stage, field, minimum, maximum, target
):
    check = {"min_chars": minimum, "max_chars": maximum}
    if stage == StoryStage.THEMES:
        check.update(type="text_length", field=field)
    else:
        check["type"] = "prose_length"
    policy = StoryQualityPolicy.model_validate(
        {stage.value: {"mode": "enforce", "checks": [check]}}
    )
    before = policy.model_dump_json()
    instructions = writing_constraints(policy, stage, language)
    assert len(instructions) == 1
    assert f"using {minimum} to {maximum} characters" in instructions[0]
    assert f"Aim for about {target} characters" in instructions[0]
    assert "not an additional acceptance condition" in instructions[0]
    assert "pad with repetition and decoration" in instructions[0]
    assert policy.model_dump_json() == before


@pytest.mark.parametrize("mode", ["off", "report", "enforce"])
def test_midpoint_is_not_a_new_acceptance_threshold(mode):
    policy = StoryQualityPolicy(
        frames={
            "mode": mode,
            "checks": [{"type": "prose_length", "min_chars": 5, "max_chars": 9}],
        }
    )
    assert (
        "Aim for about 7 characters"
        in writing_constraints(policy, StoryStage.FRAMES, OutputLanguage.CHINESE)[0]
    )
    for count in (5, 9):
        assert not check_frame_quality(
            policy.frames,
            OutputLanguage.CHINESE,
            "T001",
            NarrativeFrame(frame_id="F01", prose="x" * count),
        )
    for count in (4, 10):
        issues = check_frame_quality(
            policy.frames,
            OutputLanguage.CHINESE,
            "T001",
            NarrativeFrame(frame_id="F01", prose="x" * count),
        )
        assert bool(issues) is (mode != "off")


def test_titles_exact_lengths_and_word_counts_do_not_receive_midpoint_targets():
    policy = StoryQualityPolicy(
        themes={
            "checks": [
                {
                    "type": "text_length",
                    "field": "title",
                    "min_chars": 4,
                    "max_chars": 48,
                }
            ]
        },
        frames={
            "checks": [
                {"type": "prose_length", "min_chars": 100, "max_chars": 100},
                {"type": "word_count", "min_words": 10, "max_words": 20},
            ]
        },
    )
    for stage in StoryStage:
        assert all(
            "Aim for" not in instruction
            for instruction in writing_constraints(
                policy, stage, OutputLanguage.ENGLISH
            )
        )


@pytest.mark.parametrize(
    ("overrides", "bounds", "target"),
    [
        (
            InputOverrides(female_count=3, male_count=0),
            (550, 1050),
            800,
        ),
        (
            InputOverrides(
                female_count=2,
                male_count=2,
                output_language="english",
                frame_min_chars=900,
                frame_max_chars=1900,
            ),
            (900, 1900),
            1400,
        ),
    ],
)
def test_prompt_targets_follow_frozen_scaled_or_explicit_bounds(
    overrides, bounds, target
):
    resolved = resolve_story_input(
        StoryDocument(description="Adult volunteers arrange library books."), overrides
    )
    policy = resolved.quality_for("T001").frames
    assert (policy.checks[0].min_chars, policy.checks[0].max_chars) == bounds
    prompt = resolved.writing_rules_for(StoryStage.FRAMES, ["T001"])
    assert f"Aim for about {target} characters" in prompt
    restored = type(resolved).model_validate_json(resolved.model_dump_json())
    assert restored.writing_rules_for(StoryStage.FRAMES, ["T001"]) == prompt
