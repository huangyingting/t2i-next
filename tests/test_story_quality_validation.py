from __future__ import annotations

import pytest

from t2i_story_pipeline.models import (
    NarrativeFrame,
    NarrativeThemeResult,
    OutputLanguage,
    StoryQualityPolicy,
)
from t2i_story_pipeline.quality_validation import (
    StoryQualityError,
    check_frame_quality,
    quality_report,
)
from tests.story_factories import make_theme


@pytest.mark.parametrize(
    ("language", "prose"),
    [
        (OutputLanguage.CHINESE, "平视中景，焦点落在车站标牌。"),
        (OutputLanguage.ENGLISH, "An eye-level medium shot with deep focus."),
    ],
)
def test_camera_evidence_is_language_aware(language, prose):
    policy = StoryQualityPolicy(checks=[{"type": "camera_evidence"}])
    assert (
        check_frame_quality(
            policy, language, "T001", NarrativeFrame(frame_id="F01", prose=prose)
        )
        == ()
    )


def test_camera_check_reports_missing_categories_not_semantic_guarantees():
    issues = check_frame_quality(
        StoryQualityPolicy(checks=[{"type": "camera_evidence"}]),
        OutputLanguage.CHINESE,
        "T001",
        NarrativeFrame(frame_id="F01", prose="中景。"),
    )
    assert len(issues) == 1
    assert "视角" in issues[0].message
    assert "焦点或景深" in issues[0].message
    assert issues[0].feedback().startswith("T001-F01 [camera_evidence]")


@pytest.mark.parametrize(
    ("prose", "fails"),
    [("一", True), ("一二", False), ("一二三", False), ("一二三四", True)],
)
def test_length_uses_inclusive_unicode_character_bounds(prose, fails):
    issues = check_frame_quality(
        StoryQualityPolicy(
            checks=[{"type": "prose_length", "min_chars": 2, "max_chars": 3}]
        ),
        OutputLanguage.CHINESE,
        "T001",
        NarrativeFrame(frame_id="F01", prose=prose),
    )
    assert bool(issues) is fails


def test_literal_checks_are_case_sensitive_and_report_each_value():
    issues = check_frame_quality(
        StoryQualityPolicy(
            checks=[
                {"type": "required_text", "values": ["Station", "rain"]},
                {"type": "forbidden_text", "values": ["station", "snow"]},
            ]
        ),
        OutputLanguage.ENGLISH,
        "T001",
        NarrativeFrame(frame_id="F01", prose="The station in snow."),
    )
    assert [issue.check for issue in issues] == [
        "required_text",
        "required_text",
        "forbidden_text",
        "forbidden_text",
    ]


@pytest.mark.parametrize(
    ("mode", "status", "count"),
    [("off", "skipped", 0), ("report", "warnings", 1)],
)
def test_reports_distinguish_skipped_and_warnings(mode, status, count):
    result = quality_report(
        StoryQualityPolicy(mode=mode, checks=[{"type": "camera_evidence"}]),
        OutputLanguage.CHINESE,
        [
            NarrativeThemeResult(
                theme=make_theme(),
                frames=[NarrativeFrame(frame_id="F01", prose="雨夜车站。")],
            )
        ],
    )
    assert result.status == status
    assert len(result.issues) == count


def test_enforcement_cannot_publish_failed_report():
    with pytest.raises(StoryQualityError, match="T001-F01"):
        quality_report(
            StoryQualityPolicy(mode="enforce", checks=[{"type": "camera_evidence"}]),
            OutputLanguage.CHINESE,
            [
                NarrativeThemeResult(
                    theme=make_theme(),
                    frames=[NarrativeFrame(frame_id="F01", prose="雨夜车站。")],
                )
            ],
        )
