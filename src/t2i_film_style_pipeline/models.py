"""Typed contracts for work-specific film-style profiling."""

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
        raise ValueError("value must be a single line")
    return value.strip()


_IMAGE_GEOMETRY = re.compile(
    r"画幅|宽高比|宽银幕|横幅画面|竖幅画面|"
    r"(?:接近|近似)方形|方形(?:构图|画面|格式)|"
    r"\b(?:aspect ratio|widescreen|square (?:frame|framing|composition|format)|"
    r"portrait orientation|"
    r"landscape orientation)\b|"
    r"\b(?:1\.33|1\.37|1\.66|1\.85|2\.35|2\.39)\s*:\s*1\b",
    re.IGNORECASE,
)


def contains_image_geometry(value: str) -> bool:
    return _IMAGE_GEOMETRY.search(value) is not None


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


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
SceneDirectionText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=8000, strip_whitespace=True),
]
CompiledBriefText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100000, strip_whitespace=True),
]
FilmRuleText = Annotated[
    str,
    StringConstraints(min_length=1, strip_whitespace=True),
    AfterValidator(_single_line),
]


class FilmWorkReference(Model):
    title: ShortText
    year: int | None = Field(default=None, ge=1888, le=2100)


class FilmStyleRequest(Model):
    director: ShortText
    works: tuple[FilmWorkReference, ...] = Field(min_length=1, max_length=12)
    output_language: str = Field(default="chinese", pattern=r"^(chinese|english)$")

    @model_validator(mode="after")
    def works_are_unique(self) -> FilmStyleRequest:
        normalized = {
            (work.title.casefold(), work.year)
            for work in self.works
        }
        if len(normalized) != len(self.works):
            raise ValueError("works must be unique")
        return self


class CharacterGender(StrEnum):
    FEMALE = "female"
    MALE = "male"
    UNKNOWN = "unknown"


class FilmCharacterAnchor(Model):
    canonical_name: ShortText
    gender: CharacterGender
    identity_and_appearance: TraitText
    canonical_costume: TraitText
    costume_features: tuple[ShortText, ...] = Field(min_length=1, max_length=8)


class FilmSceneAnchor(Model):
    canonical_name: ShortText
    narrative_context: TraitText
    environment: TraitText
    environment_features: tuple[ShortText, ...] = Field(
        min_length=2,
        max_length=8,
    )
    canonical_props: tuple[ShortText, ...] = Field(min_length=1, max_length=8)


class FilmWorkAnchors(Model):
    adult_characters: tuple[FilmCharacterAnchor, ...] = Field(
        min_length=1,
        max_length=12,
    )
    scenes: tuple[FilmSceneAnchor, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_identities(self) -> FilmWorkAnchors:
        for items in (self.adult_characters, self.scenes):
            names = [item.canonical_name.casefold() for item in items]
            if len(names) != len(set(names)):
                raise ValueError("canonical identities must be unique within a film")
        return self


class FilmCastSource(Model):
    work: FilmWorkReference
    anchors: FilmWorkAnchors


class FilmStyleRuleSet(Model):
    profile: tuple[FilmRuleText, ...] = Field(min_length=1)
    themes: tuple[FilmRuleText, ...] = Field(min_length=1)
    frames: tuple[FilmRuleText, ...] = Field(min_length=1)


class FilmStyleProfile(Model):
    style_summary: StyleSummaryText
    work_style_summaries: tuple[StyleSummaryText, ...] = Field(
        min_length=1,
        max_length=12,
    )
    work_anchors: tuple[FilmWorkAnchors, ...] = Field(
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

    @model_validator(mode="after")
    def omits_image_geometry(self) -> FilmStyleProfile:
        strings = (
            self.style_summary,
            *self.work_style_summaries,
            *(
                value
                for anchors in self.work_anchors
                for value in (
                    *(
                        item.canonical_name
                        for item in anchors.adult_characters
                    ),
                    *(
                        item.identity_and_appearance
                        for item in anchors.adult_characters
                    ),
                    *(
                        item.canonical_costume
                        for item in anchors.adult_characters
                    ),
                    *(
                        feature
                        for item in anchors.adult_characters
                        for feature in item.costume_features
                    ),
                    *(item.canonical_name for item in anchors.scenes),
                    *(item.narrative_context for item in anchors.scenes),
                    *(item.environment for item in anchors.scenes),
                    *(
                        feature
                        for item in anchors.scenes
                        for feature in item.environment_features
                    ),
                    *(
                        prop
                        for item in anchors.scenes
                        for prop in item.canonical_props
                    ),
                )
            ),
            self.palette,
            self.composition,
            self.blocking,
            self.camera,
            self.lighting,
            self.movement,
            self.production_design,
            self.material_and_finish,
            *self.signature_devices,
            *self.refusal_rules,
        )
        if any(contains_image_geometry(value) for value in strings):
            raise ValueError(
                "profile must not contain aspect ratio, image orientation, or size"
            )
        return self


class TokenUsage(Model):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class FilmStyleResult(Model):
    run_id: ShortText
    request: FilmStyleRequest
    profile: FilmStyleProfile
    compiled_context: CompiledBriefText
    usage: TokenUsage

    @model_validator(mode="after")
    def profile_matches_source_works(self) -> FilmStyleResult:
        if (
            len(self.profile.work_anchors) != len(self.request.works)
            or len(self.profile.work_style_summaries) != len(self.request.works)
        ):
            raise ValueError("profile anchors and summaries must match source works")
        return self


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
        work_anchors=(
            Annotated[
                tuple[FilmWorkAnchors, ...],
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
