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
    model_serializer,
    model_validator,
)

from t2i_story_pipeline.theme_memory import (
    ThemeDiversity,
    duplicate_themes,
    normalized_text,
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


class StageAuthoring(Model):
    common: tuple[RuleText, ...] = ()


class ContentLevelRefinement(Model):
    shared: tuple[RuleText, ...] = ()
    themes: tuple[RuleText, ...] = ()
    frames: tuple[RuleText, ...] = ()

    @model_validator(mode="after")
    def rules_have_one_owner(self) -> ContentLevelRefinement:
        for name, rules in (
            ("shared", self.shared),
            ("themes", self.themes),
            ("frames", self.frames),
        ):
            if len(rules) != len(set(rules)):
                raise ValueError(f"{name} refinements must not repeat rules")
        if set(self.themes) & set(self.frames):
            raise ValueError("duplicate Theme/Frame refinements belong in shared")
        for stage, rules in (("themes", self.themes), ("frames", self.frames)):
            if set(self.shared) & set(rules):
                raise ValueError(f"shared refinements repeat {stage} instructions")
        return self


class StoryAuthoring(Model):
    themes: StageAuthoring = Field(default_factory=StageAuthoring)
    frames: StageAuthoring = Field(default_factory=StageAuthoring)
    level_refinements: dict[ContentLevel, ContentLevelRefinement] = Field(
        default_factory=dict,
        description="Topic-specific refinements, not system-level replacements.",
    )

    @model_validator(mode="after")
    def refinements_do_not_repeat_common(self) -> StoryAuthoring:
        for level, refinement in self.level_refinements.items():
            for stage, common, specific in (
                ("themes", self.themes.common, refinement.themes),
                ("frames", self.frames.common, refinement.frames),
            ):
                if set(common) & set((*refinement.shared, *specific)):
                    raise ValueError(f"{level} refinements repeat {stage} common rules")
        return self

    def selected(
        self, stage: StoryStage, content_level: ContentLevel
    ) -> tuple[str, ...]:
        stage = StoryStage(stage)
        common = (
            self.themes.common if stage == StoryStage.THEMES else self.frames.common
        )
        refinement = self.level_refinements.get(ContentLevel(content_level))
        if refinement is None:
            return common
        specific = (
            refinement.themes if stage == StoryStage.THEMES else refinement.frames
        )
        return common + refinement.shared + specific


class StoryRuntime(Model):
    concurrency: int = Field(default=8, ge=1, le=32, strict=True)
    generation_retries: int = Field(default=2, ge=0, le=5, strict=True)
    theme_batch_size: int = Field(default=10, ge=1, le=10, strict=True)
    theme_output_tokens: int = Field(default=12000, ge=512, le=65536, strict=True)
    frame_output_tokens: int = Field(default=32768, ge=512, le=65536, strict=True)


class QualityMode(StrEnum):
    OFF = "off"
    REPORT = "report"
    ENFORCE = "enforce"


class FrozenQualityModel(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CameraEvidenceCheck(FrozenQualityModel):
    type: Literal["camera_evidence"]


class TextLengthBounds(FrozenQualityModel):
    min_chars: int = Field(default=1, ge=1, le=32768, strict=True)
    max_chars: int = Field(default=32768, ge=1, le=32768, strict=True)
    extra_person_chars: int = Field(default=0, ge=0, le=32768, strict=True)

    @model_validator(mode="after")
    def ordered_bounds(self) -> TextLengthBounds:
        if self.min_chars > self.max_chars:
            raise ValueError("min_chars 不能大于 max_chars")
        return self


class ProseLengthCheck(TextLengthBounds):
    type: Literal["prose_length"]


class AsciiCheck(FrozenQualityModel):
    type: Literal["ascii"]
    when_language: OutputLanguage | None = None


class WordCountCheck(FrozenQualityModel):
    type: Literal["word_count"]
    when_language: OutputLanguage | None = None
    min_words: int = Field(default=1, ge=1, le=32768, strict=True)
    max_words: int | None = Field(default=None, ge=1, le=32768, strict=True)

    @model_validator(mode="after")
    def ordered_bounds(self) -> WordCountCheck:
        if self.max_words is not None and self.min_words > self.max_words:
            raise ValueError("min_words 不能大于 max_words")
        return self


class RequiredTextCheck(FrozenQualityModel):
    type: Literal["required_text"]
    values: tuple[RuleText, ...] = Field(min_length=1)


class ForbiddenTextCheck(FrozenQualityModel):
    type: Literal["forbidden_text"]
    values: tuple[RuleText, ...] = Field(min_length=1)


QualityCheck = Annotated[
    CameraEvidenceCheck
    | ProseLengthCheck
    | RequiredTextCheck
    | ForbiddenTextCheck
    | AsciiCheck
    | WordCountCheck,
    Field(discriminator="type"),
]


class StageQualityPolicy(FrozenQualityModel):
    @model_serializer(mode="wrap")
    def serialize_configured_fields(self, handler):
        # Omitted fields inherit run defaults; explicit empty checks replace them.
        return {
            name: value
            for name, value in handler(self).items()
            if name in self.model_fields_set
        }


class FrameQualityPolicy(StageQualityPolicy):
    mode: QualityMode = QualityMode.REPORT
    checks: tuple[QualityCheck, ...] = ()

    @model_validator(mode="after")
    def unique_checks(self) -> FrameQualityPolicy:
        names = [check.type for check in self.checks]
        if len(names) != len(set(names)):
            raise ValueError("同一种质量检查只能配置一次")
        return self


ThemeTextField = Literal["title", "premise", "style"]


class ThemeRequiredTextCheck(RequiredTextCheck):
    field: ThemeTextField


class ThemeForbiddenTextCheck(ForbiddenTextCheck):
    field: ThemeTextField


class ThemeTextLengthCheck(TextLengthBounds):
    type: Literal["text_length"]
    field: ThemeTextField


ThemeQualityCheck = Annotated[
    ThemeRequiredTextCheck | ThemeForbiddenTextCheck | ThemeTextLengthCheck,
    Field(discriminator="type"),
]


class ThemeQualityPolicy(StageQualityPolicy):
    mode: QualityMode = QualityMode.REPORT
    checks: tuple[ThemeQualityCheck, ...] = ()

    @model_validator(mode="after")
    def unique_checks(self) -> ThemeQualityPolicy:
        keys = [(check.type, check.field) for check in self.checks]
        if len(keys) != len(set(keys)):
            raise ValueError("同一 Theme 字段的同一种质量检查只能配置一次")
        return self


class StoryQualityPolicy(FrozenQualityModel):
    themes: ThemeQualityPolicy = Field(default_factory=ThemeQualityPolicy)
    frames: FrameQualityPolicy = Field(default_factory=FrameQualityPolicy)


class ThemeEffectiveQuality(FrozenQualityModel):
    theme_id: ThemeId
    policy: StoryQualityPolicy


class StoryQualityIssue(Model):
    stage: StoryStage
    theme_id: ThemeId
    frame_id: FrameId | None = None
    field: Literal["title", "premise", "style", "prose"]
    check: Literal[
        "camera_evidence",
        "prose_length",
        "text_length",
        "required_text",
        "forbidden_text",
        "ascii",
        "word_count",
    ]
    message: RuleText

    @model_validator(mode="after")
    def stage_matches_target(self) -> StoryQualityIssue:
        if self.stage == StoryStage.FRAMES:
            if self.frame_id is None or self.field != "prose":
                raise ValueError("Frame 质量问题必须指定 frame_id 和 prose 字段")
        elif self.frame_id is not None or self.field == "prose":
            raise ValueError("Theme 质量问题只能指向 Theme 字段")
        return self

    def feedback(self) -> str:
        target = (
            f"{self.theme_id}-{self.frame_id}"
            if self.frame_id is not None
            else f"{self.theme_id}.{self.field}"
        )
        return f"{target} [{self.check}] {self.message}"


class StageQualityReport(Model):
    mode: QualityMode
    status: Literal["skipped", "passed", "warnings"]
    issues: list[StoryQualityIssue]


class StoryQualityReport(Model):
    themes: StageQualityReport
    frames: StageQualityReport

    @property
    def status(self) -> Literal["skipped", "passed", "warnings"]:
        statuses = {self.themes.status, self.frames.status}
        if "warnings" in statuses:
            return "warnings"
        return "passed" if "passed" in statuses else "skipped"

    @property
    def issues(self) -> list[StoryQualityIssue]:
        return [*self.themes.issues, *self.frames.issues]


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
    diversity: ThemeDiversity = Field(
        description=(
            "Compact factual novelty signature: subject, setting, situation "
            "and visual design"
        )
    )
    title: Text = Field(description="简洁自然的主题标题")
    premise: PremiseText = Field(
        description=(
            "所有 Frame 共用的具体事件或视觉命题，以及稳定的人物、地点和时间范围；"
            "不是泛泛的题材标签、多个事件的列表或写作指令"
        )
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

    @model_validator(mode="after")
    def distinct_frames(self) -> NarrativeThemeResult:
        texts = [normalized_text(frame.prose) for frame in self.frames]
        if len(texts) != len(set(texts)):
            raise ValueError("同一 Theme 的 Frame 正文不能完全重复")
        return self


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

    @model_validator(mode="after")
    def distinct_themes(self) -> StoryResult:
        themes = [item.theme for item in self.themes]
        issues = duplicate_themes(themes, [theme.theme_id for theme in themes], ())
        if issues:
            raise ValueError("; ".join(issues))
        return self


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
