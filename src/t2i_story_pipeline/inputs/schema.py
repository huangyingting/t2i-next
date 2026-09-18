"""Closed, data-only schemas for story inputs and their explicit assets."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PrivateAttr, StringConstraints, model_validator

from t2i_story_pipeline.models import (
    ContentLevel,
    FrameId,
    Model,
    OutputLanguage,
    QualityMode,
    RuleText,
    StoryAuthoring,
    StoryQualityPolicy,
    StoryRequest,
    StoryRuntime,
    StoryText,
)

Slug = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$"
    ),
]
Count = Annotated[int, Field(ge=0, le=8, strict=True)]


class FixedRole(Model):
    id: Slug
    sex: Literal["female", "male", "theme_choice"]


class BackgroundCountBand(Model):
    min: int = Field(ge=0, le=30, strict=True)
    max: int = Field(ge=0, le=30, strict=True)

    @model_validator(mode="after")
    def ordered(self) -> BackgroundCountBand:
        if self.min > self.max:
            raise ValueError("background count minimum must not exceed maximum")
        return self


class StoryCast(Model):
    female_count: Count | None = None
    male_count: Count | None = None
    scope: RuleText = "all_people"
    fixed_roles: tuple[FixedRole, ...] = ()
    background_counts: tuple[BackgroundCountBand, ...] = ()

    @model_validator(mode="after")
    def valid_scope(self) -> StoryCast:
        ids = [role.id for role in self.fixed_roles]
        if len(ids) != len(set(ids)):
            raise ValueError("fixed_roles IDs must be unique")
        if self.scope == "all_people" and self.fixed_roles:
            raise ValueError("fixed_roles require an explicit participant scope")
        if self.scope == "all_people" and self.background_counts:
            raise ValueError("background_counts require an explicit principal scope")
        if self.scope != "all_people" and (
            self.female_count is None or self.male_count is None
        ):
            raise ValueError("scoped cast requires both female_count and male_count")
        if (
            sum(value or 0 for value in (self.female_count, self.male_count))
            + len(self.fixed_roles)
            > 8
        ):
            raise ValueError("principal cast including fixed_roles exceeds 8 people")
        ordered_bands = sorted(self.background_counts, key=lambda band: band.min)
        if any(left.max >= right.min for left, right in pairwise(ordered_bands)):
            raise ValueError("background count bands must not overlap or repeat")
        return self


class StoryRunGeneration(Model):
    """Execution choices; omitted gender counts inherit the visual cast."""

    theme_count: int = Field(default=1, ge=1, le=100, strict=True)
    frames_per_theme: int = Field(default=6, ge=1, le=6, strict=True)
    content_level: ContentLevel = ContentLevel.AESTHETIC
    output_language: OutputLanguage = OutputLanguage.CHINESE
    female_count: Count | None = None
    male_count: Count | None = None

    def request(self, document: StoryDocument) -> StoryRequest:
        cast = self.effective_cast(document.cast)
        return StoryRequest(
            story=document.description,
            source_prompt_stem=document.id,
            theme_count=self.theme_count,
            frames_per_theme=self.frames_per_theme,
            female_count=cast.female_count,
            male_count=cast.male_count,
            content_level=self.content_level,
            output_language=self.output_language,
        )

    def effective_cast(self, cast: StoryCast) -> StoryCast:
        values = cast.model_dump()
        for name in ("female_count", "male_count"):
            if (value := getattr(self, name)) is not None:
                values[name] = value
        return StoryCast.model_validate(values)


def default_validation(language: OutputLanguage) -> StoryQualityPolicy:
    # English character budgets are calibrated starting defaults, not quality claims.
    title, premise, style, frame = (
        ((4, 48, 0), (160, 520, 60), (100, 360, 30), (450, 950, 100))
        if language == OutputLanguage.CHINESE
        else ((4, 96, 0), (320, 1040, 120), (200, 720, 60), (900, 1900, 200))
    )
    return StoryQualityPolicy(
        themes={
            "mode": "enforce",
            "checks": [
                {
                    "type": "text_length",
                    "field": field,
                    "min_chars": bounds[0],
                    "max_chars": bounds[1],
                    "extra_person_chars": bounds[2],
                }
                for field, bounds in (
                    ("title", title), ("premise", premise), ("style", style)
                )
            ],
        },
        frames={
            "mode": "enforce",
            "checks": [
                {
                    "type": "prose_length",
                    "min_chars": frame[0],
                    "max_chars": frame[1],
                    "extra_person_chars": frame[2],
                }
            ],
        },
    )


class StoryRunConfiguration(Model):
    """External execution configuration, frozen with every resolved input."""

    generation: StoryRunGeneration = Field(default_factory=StoryRunGeneration)
    runtime: StoryRuntime = Field(default_factory=StoryRuntime)
    validation: StoryQualityPolicy = Field(default_factory=StoryQualityPolicy)


class Bounds(Model):
    min: int | None = Field(default=None, ge=0, le=100, strict=True)
    max: int | None = Field(default=None, ge=0, le=100, strict=True)

    @model_validator(mode="after")
    def ordered(self) -> Bounds:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("minimum must not exceed maximum")
        return self


class AllowedCast(Model):
    female_count: Count
    male_count: Count

    @model_validator(mode="after")
    def valid_total(self) -> AllowedCast:
        if not 1 <= self.female_count + self.male_count <= 8:
            raise ValueError("allowed cast total must be between 1 and 8")
        return self


class InputRequirements(Model):
    allowed_casts: tuple[AllowedCast, ...] | None = Field(default=None, min_length=1)
    female_count: Bounds | None = None
    male_count: Bounds | None = None
    content_levels: tuple[ContentLevel, ...] | None = Field(default=None, min_length=1)
    cast_constraints: Literal["unspecified"] | None = None


class ModuleReference(Model):
    id: Slug
    parameters: dict[str, object] = Field(default_factory=dict)


class InputAllocation(Model):
    type: Literal["fixed_slots", "alphabet_coverage", "cyclic_slots"]
    catalog: Slug


class StoryDocument(Model):
    """Direct prose can omit id; file-backed documents must declare one."""

    id: Slug | None = None
    description: StoryText
    cast: StoryCast = Field(default_factory=StoryCast)
    authoring: StoryAuthoring = Field(default_factory=StoryAuthoring)
    modules: tuple[ModuleReference, ...] = ()
    requirements: InputRequirements = Field(default_factory=InputRequirements)
    allocation: InputAllocation | None = None
    _source_path: Path | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def unique_modules(self) -> StoryDocument:
        ids = [module.id for module in self.modules]
        if len(ids) != len(set(ids)):
            raise ValueError("module IDs must be unique")
        return self


class InputOverrides(Model):
    """None means no override; explicit zero is never discarded."""

    theme_count: int | None = Field(default=None, ge=1, le=100, strict=True)
    frames_per_theme: int | None = Field(default=None, ge=1, le=6, strict=True)
    content_level: ContentLevel | None = None
    output_language: OutputLanguage | None = None
    female_count: Count | None = None
    male_count: Count | None = None
    concurrency: int | None = Field(default=None, ge=1, le=32, strict=True)
    generation_retries: int | None = Field(default=None, ge=0, le=5, strict=True)
    theme_batch_size: int | None = Field(default=None, ge=1, le=10, strict=True)
    theme_output_tokens: int | None = Field(default=None, ge=512, le=65536, strict=True)
    frame_output_tokens: int | None = Field(default=None, ge=512, le=65536, strict=True)
    theme_quality_mode: QualityMode | None = None
    frame_quality_mode: QualityMode | None = None
    frame_min_words: int | None = Field(default=None, ge=1, le=32768, strict=True)
    frame_max_words: int | None = Field(default=None, ge=1, le=32768, strict=True)
    frame_min_chars: int | None = Field(default=None, ge=1, le=32768, strict=True)
    frame_max_chars: int | None = Field(default=None, ge=1, le=32768, strict=True)


class LayoutParameters(Model):
    layout: Literal["grid", "collage"]
    rows: int | None = Field(default=None, ge=1, le=100, strict=True)
    columns: int | None = Field(default=None, ge=1, le=100, strict=True)
    min_views: int | None = Field(default=None, ge=1, le=100, strict=True)
    max_views: int | None = Field(default=None, ge=1, le=100, strict=True)

    @model_validator(mode="after")
    def coherent_dimensions(self) -> LayoutParameters:
        if (self.rows is None) != (self.columns is None):
            raise ValueError("grid rows and columns must be supplied together")
        if self.layout == "collage" and self.rows is not None:
            raise ValueError("collage cannot specify grid rows or columns")
        if (
            self.min_views is not None
            and self.max_views is not None
            and self.min_views > self.max_views
        ):
            raise ValueError("min_views must not exceed max_views")
        if self.rows is not None and self.columns is not None:
            views = self.rows * self.columns
            if (
                views > 100
                or (self.min_views is not None and views < self.min_views)
                or (self.max_views is not None and views > self.max_views)
            ):
                raise ValueError("grid dimensions contradict view bounds")
        return self


class VisibleCopyParameters(Model):
    product: Literal["poster", "magazine_cover", "sleeve", "graphic"]
    copy_language: Literal["english"] = "english"
    ascii: Literal["required"] = "required"


class SilkPaintingParameters(Model):
    pass


class ModuleDocument(Model):
    id: Slug
    kind: Literal["layout_multiview", "visible_copy", "silk_painting"]
    authoring: StoryAuthoring = Field(default_factory=StoryAuthoring)
    requirements: InputRequirements = Field(default_factory=InputRequirements)


class LayoutModuleContext(Model):
    id: Slug
    kind: Literal["layout_multiview"]
    parameters: LayoutParameters


class VisibleCopyModuleContext(Model):
    id: Slug
    kind: Literal["visible_copy"]
    parameters: VisibleCopyParameters


class SilkPaintingModuleContext(Model):
    id: Slug
    kind: Literal["silk_painting"]
    parameters: SilkPaintingParameters


ModuleContext = Annotated[
    LayoutModuleContext | VisibleCopyModuleContext | SilkPaintingModuleContext,
    Field(discriminator="kind"),
]


class CatalogCast(Model):
    total: int = Field(ge=1, le=8, strict=True)
    min_female: Count = 0
    min_male: Count = 0

    @model_validator(mode="after")
    def possible_cast(self) -> CatalogCast:
        if self.min_female + self.min_male > self.total:
            raise ValueError("catalog minimum sex counts exceed total")
        return self


class FrameSlotRules(Model):
    frame_id: FrameId
    rules: tuple[RuleText, ...] = Field(min_length=1)


class FrameAssignment(Model):
    slots: tuple[FrameSlotRules, ...] = Field(min_length=1, max_length=6)

    @property
    def slot_count(self) -> int:
        return len(self.slots)

    @model_validator(mode="after")
    def complete_slots(self) -> FrameAssignment:
        expected = [f"F{index:02d}" for index in range(1, self.slot_count + 1)]
        if [slot.frame_id for slot in self.slots] != expected:
            raise ValueError(
                "frame_assignment slots must have sequential IDs starting at F01"
            )
        return self


class CatalogEntry(Model):
    id: Slug
    themes: tuple[RuleText, ...] = ()
    frames: tuple[RuleText, ...] = ()
    cast: CatalogCast | None = None
    frame_assignment: FrameAssignment | None = None


class CatalogDocument(Model):
    id: Slug
    entries: tuple[CatalogEntry, ...] = Field(min_length=1, max_length=100)
    slots: tuple[Slug, ...] | None = Field(default=None, min_length=1, max_length=100)
    diversity_order: tuple[Slug, ...] | None = Field(
        default=None, min_length=1, max_length=100
    )

    @model_validator(mode="after")
    def valid_references(self) -> CatalogDocument:
        ids = [entry.id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("catalog entry IDs must be unique")
        for name in ("slots", "diversity_order"):
            references = getattr(self, name)
            if references is None:
                continue
            if len(references) != len(set(references)):
                raise ValueError(f"catalog {name} must not contain duplicate IDs")
            if not set(references) <= set(ids):
                raise ValueError(f"catalog {name} has dangling entry references")
        if self.diversity_order is not None and set(self.diversity_order) != set(ids):
            raise ValueError("catalog diversity_order must be a full permutation")
        return self


class PolicyDocument(Model):
    id: Literal["standard-story"]
    authoring: StoryAuthoring
