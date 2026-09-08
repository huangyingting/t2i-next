"""Minimal domain models for prose-first narrative image prompts."""

from __future__ import annotations

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
    model_validator,
)


def _single_line(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("叙事正文不能包含换行")
    return value.strip()


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
    StringConstraints(min_length=1, max_length=20000, strip_whitespace=True),
]
NarrativeProse = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32768, strip_whitespace=True),
    AfterValidator(_single_line),
]
ThemeId = Annotated[str, StringConstraints(pattern=r"^T\d{3}$")]
FrameId = Annotated[str, StringConstraints(pattern=r"^F\d{2}$")]


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


class StoryRequest(Model):
    story: StoryText
    theme_count: int = Field(default=1, ge=1, le=100)
    frames_per_theme: int = Field(default=6, ge=1, le=6)
    female_count: int | None = Field(default=None, ge=0, le=8)
    male_count: int | None = Field(default=None, ge=0, le=8)
    content_level: ContentLevel = ContentLevel.AESTHETIC
    output_language: OutputLanguage = OutputLanguage.CHINESE

    @model_validator(mode="after")
    def cast_constraints_fit(self) -> StoryRequest:
        counts = tuple(
            count
            for count in (self.female_count, self.male_count)
            if count is not None
        )
        if self.female_count == 0 and self.male_count == 0:
            raise ValueError("人物约束不能同时为零")
        if sum(counts) > 8:
            raise ValueError("每个主题最多包含八名角色")
        return self


class NarrativeTheme(Model):
    theme_id: ThemeId
    title: Text = Field(description="简洁自然的中文主题标题")
    premise: PremiseText = Field(
        description="至多两句的完整人物故事前提，不包含写作指令"
    )
    style: StyleText = Field(
        description="一句完整简洁的视觉风格描述，不包含写作指令或内部字段"
    )


class NarrativeThemeBatch(Model):
    themes: list[NarrativeTheme] = Field(min_length=1, max_length=10)


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
    request: StoryRequest
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
    return normalized[:64] or "story_response"
