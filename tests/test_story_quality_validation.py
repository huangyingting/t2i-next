from __future__ import annotations

import pytest
from pydantic import ValidationError

from t2i_story_pipeline.models import (
    FrameQualityPolicy,
    NarrativeFrame,
    NarrativeThemeResult,
    OutputLanguage,
    StoryQualityPolicy,
    ThemeQualityPolicy,
)
from t2i_story_pipeline.quality_validation import (
    StoryQualityError,
    check_frame_quality,
    check_theme_quality,
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
    policy = FrameQualityPolicy(checks=[{"type": "camera_evidence"}])
    assert (
        check_frame_quality(
            policy, language, "T001", NarrativeFrame(frame_id="F01", prose=prose)
        )
        == ()
    )


def test_camera_check_reports_missing_categories_not_semantic_guarantees():
    issues = check_frame_quality(
        FrameQualityPolicy(checks=[{"type": "camera_evidence"}]),
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
        FrameQualityPolicy(
            checks=[{"type": "prose_length", "min_chars": 2, "max_chars": 3}]
        ),
        OutputLanguage.CHINESE,
        "T001",
        NarrativeFrame(frame_id="F01", prose=prose),
    )
    assert bool(issues) is fails


def test_literal_checks_are_case_sensitive_and_report_each_value():
    issues = check_frame_quality(
        FrameQualityPolicy(
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
        StoryQualityPolicy(
            frames=FrameQualityPolicy(mode=mode, checks=[{"type": "camera_evidence"}])
        ),
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
            StoryQualityPolicy(
                frames=FrameQualityPolicy(
                    mode="enforce", checks=[{"type": "camera_evidence"}]
                )
            ),
            OutputLanguage.CHINESE,
            [
                NarrativeThemeResult(
                    theme=make_theme(),
                    frames=[NarrativeFrame(frame_id="F01", prose="雨夜车站。")],
                )
            ],
        )


def test_theme_checks_target_individual_fields_and_report_locations():
    theme = make_theme().model_copy(
        update={
            "title": "Station",
            "premise": "rainy platform",
            "style": "soft light",
        }
    )
    policy = ThemeQualityPolicy(
        checks=[
            {"type": "required_text", "field": "premise", "values": ["Station"]},
            {"type": "forbidden_text", "field": "style", "values": ["light"]},
            {"type": "text_length", "field": "title", "min_chars": 8},
        ]
    )
    issues = check_theme_quality(policy, theme.theme_id, theme)
    assert [issue.field for issue in issues] == ["premise", "style", "title"]
    assert all(issue.stage == "themes" and issue.frame_id is None for issue in issues)
    assert issues[0].feedback().startswith("T001.premise [required_text]")
    assert "Station" in issues[0].message


@pytest.mark.parametrize(
    ("title", "fails"),
    [("一", True), ("一二", False), ("一二三", False), ("一二三四", True)],
)
def test_theme_length_has_inclusive_unicode_bounds(title, fails):
    policy = ThemeQualityPolicy(
        checks=[
            {"type": "text_length", "field": "title", "min_chars": 2, "max_chars": 3}
        ]
    )
    theme = make_theme().model_copy(update={"title": title})
    assert bool(check_theme_quality(policy, theme.theme_id, theme)) is fails


def test_theme_check_uniqueness_is_per_field():
    checks = [
        {"type": "required_text", "field": field, "values": ["rain"]}
        for field in ("title", "premise", "style")
    ]
    assert len(ThemeQualityPolicy(checks=checks).checks) == 3
    with pytest.raises(ValidationError, match="只能配置一次"):
        ThemeQualityPolicy(checks=[*checks, checks[0]])


def test_final_report_keeps_stage_modes_and_issues_separate():
    policy = StoryQualityPolicy(
        themes=ThemeQualityPolicy(
            mode="report",
            checks=[{"type": "required_text", "field": "style", "values": ["absent"]}],
        ),
        frames=FrameQualityPolicy(
            mode="off",
            checks=[{"type": "required_text", "values": ["absent"]}],
        ),
    )
    report = quality_report(
        policy,
        OutputLanguage.CHINESE,
        [
            NarrativeThemeResult(
                theme=make_theme(),
                frames=[NarrativeFrame(frame_id="F01", prose="rain")],
            )
        ],
    )
    assert report.themes.status == "warnings"
    assert report.themes.mode == "report"
    assert report.frames.status == "skipped"
    assert report.frames.mode == "off"
    assert report.status == "warnings"
    assert len(report.issues) == 1
    assert set(report.model_dump()) == {"themes", "frames"}


def test_enforced_theme_policy_is_rechecked_before_publication():
    policy = StoryQualityPolicy(
        themes=ThemeQualityPolicy(
            mode="enforce",
            checks=[
                {"type": "required_text", "field": "premise", "values": ["absent"]}
            ],
        )
    )
    with pytest.raises(StoryQualityError, match="T001.premise"):
        quality_report(
            policy,
            OutputLanguage.CHINESE,
            [
                NarrativeThemeResult(
                    theme=make_theme(),
                    frames=[NarrativeFrame(frame_id="F01", prose="rain")],
                )
            ],
        )
