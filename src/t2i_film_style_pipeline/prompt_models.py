"""Film-owned domain models for Theme and Frame prompt generation."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    create_model,
)


def _single_line(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("画面正文不能包含换行")
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
FilmContextText = Annotated[
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


class FilmPromptStage(StrEnum):
    THEMES = "themes"
    FRAMES = "frames"


class FilmPromptRuleSet(Model):
    themes: tuple[RuleText, ...] = Field(min_length=1)
    frames: tuple[RuleText, ...] = Field(min_length=1)

    def for_stage(self, stage: FilmPromptStage) -> tuple[str, ...]:
        if stage == FilmPromptStage.THEMES:
            return self.themes
        return self.frames

    def text_for(self, stage: FilmPromptStage) -> str:
        return "\n".join(self.for_stage(stage))

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class FilmPromptRequest(Model):
    context: FilmContextText
    source_prompt_stem: SourcePromptStem | None = None
    prompt_filename_stem: SourcePromptStem | None = None
    theme_count: int = Field(default=1, ge=1, le=100)
    frames_per_theme: int = Field(default=6, ge=1, le=6)
    content_level: ContentLevel = ContentLevel.AESTHETIC
    output_language: OutputLanguage = OutputLanguage.CHINESE


class NarrativeTheme(Model):
    theme_id: ThemeId
    title: Text = Field(description="简洁自然的主题标题")
    premise: PremiseText = Field(
        description="完整的人物、地点与当前情境前提，不包含写作指令"
    )
    style: StyleText = Field(
        description="完整、具体、可执行的视觉方案，不包含写作指令或内部字段"
    )


class NarrativeThemeDraft(Model):
    title: Text = Field(description="简洁自然的主题标题")
    premise: PremiseText = Field(
        description="完整的人物、地点与当前情境前提，不包含写作指令"
    )
    style: StyleText = Field(
        description="完整、具体、可执行的视觉方案，不包含写作指令或内部字段"
    )


class NarrativeThemeBatch(Model):
    semantic_name: SemanticName
    themes: list[NarrativeTheme] = Field(min_length=1, max_length=10)


class NarrativeThemeDraftBatch(Model):
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


class FilmPromptResult(Model):
    run_id: Text
    semantic_name: SemanticName
    request: FilmPromptRequest
    themes: list[NarrativeThemeResult] = Field(min_length=1, max_length=100)
    usage: TokenUsage


@lru_cache(maxsize=10)
def exact_theme_batch_model(count: int) -> type[NarrativeThemeBatch]:
    if not 1 <= count <= 10:
        raise ValueError("主题批次大小必须介于 1 和 10")
    return create_model(
        f"NarrativeThemeBatch{count}",
        __base__=NarrativeThemeBatch,
        themes=(
            Annotated[
                list[NarrativeTheme],
                Field(min_length=count, max_length=count),
            ],
            ...,
        ),
    )


@lru_cache(maxsize=10)
def exact_theme_draft_batch_model(
    count: int,
) -> type[NarrativeThemeDraftBatch]:
    if not 1 <= count <= 10:
        raise ValueError("主题批次大小必须介于 1 和 10")
    return create_model(
        f"NarrativeThemeDraftBatch{count}",
        __base__=NarrativeThemeDraftBatch,
        themes=(
            Annotated[
                list[NarrativeThemeDraft],
                Field(min_length=count, max_length=count),
            ],
            ...,
        ),
    )


@lru_cache(maxsize=6)
def exact_frame_sequence_model(count: int) -> type[NarrativeFrameSequence]:
    if not 1 <= count <= 6:
        raise ValueError("画面数量必须介于 1 和 6")
    return create_model(
        f"NarrativeFrameSequence{count}",
        __base__=NarrativeFrameSequence,
        frames=(
            Annotated[
                list[NarrativeFrame],
                Field(min_length=count, max_length=count),
            ],
            ...,
        ),
    )


def schema_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return normalized[:64] or "film_prompt_response"
