"""Typed stage projections, distinct from complete frozen input snapshots."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from t2i_story_pipeline.inputs.planning import (
    PlannedCast,
    ThemeInputPlan,
)
from t2i_story_pipeline.inputs.schema import (
    CatalogCast,
    CatalogEntry,
    FrameSlotRules,
    ModuleContext,
    Slug,
)
from t2i_story_pipeline.models import FrameId, Model, RuleText, StoryStage, ThemeId


class ContextSelection(Model):
    stage: StoryStage
    theme_ids: tuple[ThemeId, ...] = Field(min_length=1)
    frame_ids: tuple[FrameId, ...] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def unique_themes(self) -> Self:
        if len(self.theme_ids) != len(set(self.theme_ids)):
            raise ValueError("context theme_ids must not contain duplicates")
        if self.frame_ids is not None:
            if self.stage != StoryStage.FRAMES:
                raise ValueError("frame_ids are only valid for Frame context")
            if len(self.frame_ids) != len(set(self.frame_ids)):
                raise ValueError("context frame_ids must not contain duplicates")
        return self


class StageCatalogEntry(Model):
    id: Slug
    rules: tuple[RuleText, ...]
    cast: CatalogCast | None = None

    @classmethod
    def from_entry(cls, entry: CatalogEntry, stage: StoryStage) -> Self:
        return cls(
            id=entry.id,
            rules=entry.themes if stage == StoryStage.THEMES else entry.frames,
            cast=entry.cast,
        )


class StageThemeInputPlan(Model):
    theme_id: ThemeId
    catalog_id: Slug | None = None
    entry: StageCatalogEntry | None = None
    frame_slots: tuple[FrameSlotRules, ...] = ()
    cast: PlannedCast

    @classmethod
    def from_plan(
        cls,
        plan: ThemeInputPlan,
        stage: StoryStage,
        frames_per_theme: int,
        frame_ids: tuple[str, ...],
    ) -> Self:
        entry = plan.entry
        assignment = entry.frame_assignment if entry is not None else None
        assigned_slots = (
            {slot.frame_id: slot for slot in assignment.slots}
            if assignment is not None
            else {}
        )
        frame_slots = (
            tuple(assigned_slots[frame_id] for frame_id in frame_ids)
            if stage == StoryStage.FRAMES
            and assignment is not None
            and assignment.slot_count == frames_per_theme
            else ()
        )
        return cls(
            theme_id=plan.theme_id,
            catalog_id=plan.catalog_id,
            entry=(
                StageCatalogEntry.from_entry(entry, stage)
                if entry is not None
                else None
            ),
            frame_slots=frame_slots,
            cast=plan.cast,
        )


class StageInputContext(Model):
    modules: tuple[ModuleContext, ...]
    plans: tuple[StageThemeInputPlan, ...]
