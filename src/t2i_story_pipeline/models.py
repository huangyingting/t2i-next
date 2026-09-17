"""Minimal domain models for prose-first narrative image prompts."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    create_model,
    model_validator,
)


def _single_line(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("叙事正文不能包含换行")
    return value.strip()


def _usable_source_prompt_stem(value: str) -> str:
    if not any(character.isalnum() for character in value):
        raise ValueError("提示词文件名必须包含字母或数字")
    return value


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


Text = Annotated[
    str,
    StringConstraints(min_length=1, max_length=500, strip_whitespace=True),
    AfterValidator(_single_line),
]
StyleText = Annotated[
    str,
    StringConstraints(min_length=1, strip_whitespace=True),
    AfterValidator(_single_line),
]
PremiseText = Annotated[
    str,
    StringConstraints(min_length=1, strip_whitespace=True),
    AfterValidator(_single_line),
]
StoryText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=55000, strip_whitespace=True),
]
RuleText = Annotated[
    str,
    StringConstraints(min_length=1, strip_whitespace=True),
    AfterValidator(_single_line),
]
NarrativeProse = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32768, strip_whitespace=True),
    AfterValidator(_single_line),
]
ThemeId = Annotated[str, StringConstraints(pattern=r"^T\d{3}$")]
FrameId = Annotated[str, StringConstraints(pattern=r"^F\d{2}$")]
SemanticName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]
SourcePromptStem = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=120,
        strip_whitespace=True,
        pattern=r"^[^/\\\r\n]+$",
    ),
    AfterValidator(_usable_source_prompt_stem),
]


class OutputLanguage(StrEnum):
    CHINESE = "chinese"
    ENGLISH = "english"


class ContentLevel(StrEnum):
    AESTHETIC = "aesthetic"
    EROTIC = "erotic"
    HARDCORE = "hardcore"


class StoryStage(StrEnum):
    THEMES = "themes"
    FRAMES = "frames"


class StoryAuthoring(Model):
    themes: tuple[RuleText, ...] = ()
    frames: tuple[RuleText, ...] = ()


class QualityMode(StrEnum):
    OFF = "off"
    REPORT = "report"
    ENFORCE = "enforce"


class CameraEvidenceCheck(Model):
    type: Literal["camera_evidence"]


class ProseLengthCheck(Model):
    type: Literal["prose_length"]
    min_chars: int = Field(default=1, ge=1, le=32768, strict=True)
    max_chars: int = Field(default=32768, ge=1, le=32768, strict=True)

    @model_validator(mode="after")
    def ordered_bounds(self) -> ProseLengthCheck:
        if self.min_chars > self.max_chars:
            raise ValueError("min_chars 不能大于 max_chars")
        return self


class RequiredTextCheck(Model):
    type: Literal["required_text"]
    values: tuple[RuleText, ...] = Field(min_length=1)


class ForbiddenTextCheck(Model):
    type: Literal["forbidden_text"]
    values: tuple[RuleText, ...] = Field(min_length=1)


QualityCheck = Annotated[
    CameraEvidenceCheck | ProseLengthCheck | RequiredTextCheck | ForbiddenTextCheck,
    Field(discriminator="type"),
]


class StoryQualityPolicy(Model):
    mode: QualityMode = QualityMode.REPORT
    checks: tuple[QualityCheck, ...] = ()

    @model_validator(mode="after")
    def unique_checks(self) -> StoryQualityPolicy:
        names = [check.type for check in self.checks]
        if len(names) != len(set(names)):
            raise ValueError("同一种质量检查只能配置一次")
        return self


class StoryQualityIssue(Model):
    theme_id: ThemeId
    frame_id: FrameId
    check: Literal[
        "camera_evidence", "prose_length", "required_text", "forbidden_text"
    ]
    message: RuleText

    def feedback(self) -> str:
        return f"{self.theme_id}-{self.frame_id} [{self.check}] {self.message}"


class StoryQualityReport(Model):
    mode: QualityMode
    status: Literal["skipped", "passed", "warnings"]
    issues: list[StoryQualityIssue]


class StoryRuleSet(Model):
    themes: tuple[RuleText, ...] = Field(min_length=1)
    frames: tuple[RuleText, ...] = Field(min_length=1)

    def for_stage(self, stage: StoryStage) -> tuple[str, ...]:
        if stage == StoryStage.THEMES:
            return self.themes
        return self.frames

    def text_for(self, stage: StoryStage) -> str:
        return "\n".join(self.for_stage(stage))

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class StoryRequest(Model):
    story: StoryText
    source_prompt_stem: SourcePromptStem | None = None
    prompt_filename_stem: SourcePromptStem | None = None
    theme_count: int = Field(default=1, ge=1, le=100)
    frames_per_theme: int = Field(default=6, ge=1, le=6)
    female_count: int | None = Field(default=None, ge=0, le=8)
    male_count: int | None = Field(default=None, ge=0, le=8)
    content_level: ContentLevel = ContentLevel.AESTHETIC
    output_language: OutputLanguage = OutputLanguage.CHINESE

    @model_validator(mode="after")
    def cast_constraints_fit(self) -> StoryRequest:
        counts = tuple(
            count for count in (self.female_count, self.male_count) if count is not None
        )
        if self.female_count == 0 and self.male_count == 0:
            raise ValueError("人物约束不能同时为零")
        if sum(counts) > 8:
            raise ValueError("每个主题最多包含八名角色")
        return self


class NarrativeThemeDraft(Model):
    title: Text = Field(description="简洁自然的主题标题")
    premise: PremiseText = Field(
        description="完整的人物、地点与当前情境前提，不包含写作指令"
    )
    style: StyleText = Field(
        description="完整、具体、可执行的视觉方案，不包含写作指令或内部字段"
    )


class NarrativeTheme(NarrativeThemeDraft):
    theme_id: ThemeId


class NarrativeThemeBatch(Model):
    semantic_name: SemanticName
    themes: list[NarrativeThemeDraft] = Field(min_length=1, max_length=10)


class NarrativeFrame(Model):
    frame_id: FrameId
    prose: NarrativeProse = Field(
        description="只含最终画面正文的单段自然语言，不包含内部编号或写作指令"
    )


class NarrativeFrameSequence(Model):
    frames: list[NarrativeFrame] = Field(min_length=1, max_length=6)


class NarrativeThemeResult(Model):
    theme: NarrativeTheme
    frames: list[NarrativeFrame] = Field(min_length=1, max_length=6)


class TokenUsage(Model):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class StoryResult(Model):
    run_id: Text
    semantic_name: SemanticName
    request: StoryRequest
    themes: list[NarrativeThemeResult] = Field(min_length=1, max_length=100)
    usage: TokenUsage
    quality: StoryQualityReport


@lru_cache(maxsize=10)
def exact_theme_batch_model(count: int) -> type[NarrativeThemeBatch]:
    if not 1 <= count <= 10:
        raise ValueError("主题批次大小必须介于 1 和 10")
    return create_model(
        f"NarrativeThemeBatch{count}",
        __base__=NarrativeThemeBatch,
        themes=(
            Annotated[
                list[NarrativeThemeDraft],
                Field(min_length=count, max_length=count),
            ],
            ...,
        ),
    )


def schema_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return normalized[:64] or "story_response"
