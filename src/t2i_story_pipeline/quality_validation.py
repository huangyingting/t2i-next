"""Optional local evidence checks, not a semantic or safety evaluator."""

from __future__ import annotations

import re
from collections.abc import Sequence

from t2i_story_pipeline.errors import StoryContractError
from t2i_story_pipeline.models import (
    AsciiCheck,
    CameraEvidenceCheck,
    ForbiddenTextCheck,
    FrameQualityPolicy,
    NarrativeFrame,
    NarrativeThemeDraft,
    NarrativeThemeResult,
    OutputLanguage,
    QualityCheck,
    QualityMode,
    RequiredTextCheck,
    StageQualityReport,
    StoryQualityIssue,
    StoryQualityPolicy,
    StoryQualityReport,
    StoryStage,
    TextLengthBounds,
    ThemeQualityPolicy,
    WordCountCheck,
)

_CAMERA_EVIDENCE = {
    OutputLanguage.CHINESE: (
        ("景别", re.compile(r"特写|近景|中景|中近景|中远景|全景|远景")),
        ("视角", re.compile(r"平视|俯视|仰视|俯拍|仰拍|顶视|鸟瞰|机位")),
        ("焦点或景深", re.compile(r"焦点|对焦|聚焦|景深|深焦|浅焦")),
    ),
    OutputLanguage.ENGLISH: (
        (
            "shot scale",
            re.compile(
                r"\b(?:close[- ]up|medium shot|wide shot|long shot|full shot)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "viewpoint",
            re.compile(
                r"\b(?:eye[- ]level|high[- ]angle|low[- ]angle|overhead|"
                r"bird.s[- ]eye|camera position)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "focus or depth of field",
            re.compile(r"\b(?:focus|depth of field)\b", re.IGNORECASE),
        ),
    ),
}


class StoryQualityError(StoryContractError):
    def __init__(self, issues: Sequence[StoryQualityIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("；".join(issue.feedback() for issue in issues))


def _frame_check_applies(check: QualityCheck, language: OutputLanguage) -> bool:
    return (
        not isinstance(check, AsciiCheck | WordCountCheck)
        or check.when_language is None
        or check.when_language == language
    )


def _text_check_messages(
    check: TextLengthBounds | RequiredTextCheck | ForbiddenTextCheck,
    text: str,
) -> list[str]:
    if isinstance(check, TextLengthBounds):
        length = len(text)
        return (
            [
                f"正文长度为 {length} 字符，要求 "
                f"{check.min_chars} 至 {check.max_chars} 字符"
            ]
            if not check.min_chars <= length <= check.max_chars
            else []
        )
    if isinstance(check, RequiredTextCheck):
        return [f"缺少指定原文：{value}" for value in check.values if value not in text]
    return [f"出现禁止原文：{value}" for value in check.values if value in text]


def check_theme_quality(
    policy: ThemeQualityPolicy,
    theme_id: str,
    theme: NarrativeThemeDraft,
) -> tuple[StoryQualityIssue, ...]:
    if policy.mode == QualityMode.OFF:
        return ()
    return tuple(
        StoryQualityIssue(
            stage=StoryStage.THEMES,
            theme_id=theme_id,
            field=check.field,
            check=check.type,
            message=message,
        )
        for check in policy.checks
        for message in _text_check_messages(check, getattr(theme, check.field))
    )


def check_frame_quality(
    policy: FrameQualityPolicy,
    language: OutputLanguage,
    theme_id: str,
    frame: NarrativeFrame,
) -> tuple[StoryQualityIssue, ...]:
    if policy.mode == QualityMode.OFF:
        return ()
    issues: list[StoryQualityIssue] = []
    for check in policy.checks:
        if not _frame_check_applies(check, language):
            continue
        messages: list[str] = []
        if isinstance(check, CameraEvidenceCheck):
            missing = [
                name
                for name, pattern in _CAMERA_EVIDENCE[language]
                if pattern.search(frame.prose) is None
            ]
            if missing:
                messages.append("缺少摄影文字证据：" + "、".join(missing))
        elif isinstance(check, AsciiCheck):
            if not frame.prose.isascii():
                messages.append("正文包含非 ASCII 字符")
        elif isinstance(check, WordCountCheck):
            count = len(frame.prose.split())
            if count < check.min_words:
                messages.append(
                    f"正文包含 {count} 个空白分隔词，至少需要 {check.min_words} 个"
                )
            if check.max_words is not None and count > check.max_words:
                messages.append(
                    f"正文包含 {count} 个空白分隔词，最多允许 {check.max_words} 个"
                )
        else:
            messages = _text_check_messages(check, frame.prose)
        issues.extend(
            StoryQualityIssue(
                stage=StoryStage.FRAMES,
                theme_id=theme_id,
                frame_id=frame.frame_id,
                field="prose",
                check=check.type,
                message=message,
            )
            for message in messages
        )
    return tuple(issues)


def quality_report(
    policy: StoryQualityPolicy,
    language: OutputLanguage,
    themes: Sequence[NarrativeThemeResult],
) -> StoryQualityReport:
    theme_issues = [
        issue
        for item in themes
        for issue in check_theme_quality(policy.themes, item.theme.theme_id, item.theme)
    ]
    frame_issues = [
        issue
        for item in themes
        for frame in item.frames
        for issue in check_frame_quality(
            policy.frames, language, item.theme.theme_id, frame
        )
    ]
    return StoryQualityReport(
        themes=_stage_report(
            policy.themes, theme_issues, active_checks=bool(policy.themes.checks)
        ),
        frames=_stage_report(
            policy.frames,
            frame_issues,
            active_checks=any(
                _frame_check_applies(check, language) for check in policy.frames.checks
            ),
        ),
    )


def _stage_report(
    policy: ThemeQualityPolicy | FrameQualityPolicy,
    issues: list[StoryQualityIssue],
    *,
    active_checks: bool,
) -> StageQualityReport:
    if issues and policy.mode == QualityMode.ENFORCE:
        raise StoryQualityError(issues)
    return StageQualityReport(
        mode=policy.mode,
        status=(
            "skipped"
            if policy.mode == QualityMode.OFF or not active_checks
            else "warnings"
            if issues
            else "passed"
        ),
        issues=issues,
    )
