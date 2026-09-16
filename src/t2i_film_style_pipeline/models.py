"""Typed contracts for work-specific film-style profiling."""

from __future__ import annotations

import re
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
        raise ValueError("value must be a single line")
    return value.strip()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


ShortText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=160, strip_whitespace=True),
    AfterValidator(_single_line),
]
TraitText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=600, strip_whitespace=True),
    AfterValidator(_single_line),
]
StyleSummaryText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=600, strip_whitespace=True),
    AfterValidator(_single_line),
]
BriefText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=55000, strip_whitespace=True),
]
CompiledBriefText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100000, strip_whitespace=True),
]


class FilmWorkReference(Model):
    title: ShortText
    year: int | None = Field(default=None, ge=1888, le=2100)


class FilmStyleRequest(Model):
    director: ShortText
    works: tuple[FilmWorkReference, ...] = Field(min_length=1, max_length=12)
    base_brief: BriefText
    output_language: str = Field(default="chinese", pattern=r"^(chinese|english)$")

    @model_validator(mode="after")
    def base_brief_uses_current_contract(self) -> FilmStyleRequest:
        if not self.base_brief.startswith("BRIEF\n\n"):
            raise ValueError("base brief must start with 'BRIEF\\n\\n'")
        normalized = {
            (work.title.casefold(), work.year)
            for work in self.works
        }
        if len(normalized) != len(self.works):
            raise ValueError("works must be unique")
        return self


class FilmStyleProfile(Model):
    profile_name: ShortText
    style_summary: StyleSummaryText
    work_style_summaries: tuple[StyleSummaryText, ...] = Field(
        min_length=1,
        max_length=12,
    )
    palette: TraitText
    composition: TraitText
    blocking: TraitText
    camera: TraitText
    lighting: TraitText
    movement: TraitText
    production_design: TraitText
    material_and_finish: TraitText
    signature_devices: tuple[TraitText, ...] = Field(min_length=3, max_length=8)
    refusal_rules: tuple[TraitText, ...] = Field(min_length=3, max_length=8)


class TokenUsage(Model):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class FilmStyleResult(Model):
    run_id: ShortText
    request: FilmStyleRequest
    profile: FilmStyleProfile
    compiled_story: CompiledBriefText
    usage: TokenUsage


@lru_cache(maxsize=12)
def exact_film_style_profile_model(count: int) -> type[FilmStyleProfile]:
    if not 1 <= count <= 12:
        raise ValueError("work count must be between 1 and 12")
    return create_model(
        f"FilmStyleProfile{count}",
        __base__=FilmStyleProfile,
        work_style_summaries=(
            Annotated[
                tuple[StyleSummaryText, ...],
                Field(min_length=count, max_length=count),
            ],
            ...,
        ),
    )


_WORK_WITH_YEAR = re.compile(r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)\s*$")


def parse_work_reference(value: str) -> FilmWorkReference:
    normalized = value.strip()
    match = _WORK_WITH_YEAR.fullmatch(normalized)
    if match is None:
        return FilmWorkReference(title=normalized)
    return FilmWorkReference(
        title=match.group("title").strip(),
        year=int(match.group("year")),
    )
