"""Deterministic per-Theme allocations and finite cast applicability checks."""

from __future__ import annotations

import string
from typing import Self

from pydantic import Field, model_validator

from t2i_story_pipeline.inputs.schema import (
    BackgroundCountBand,
    CatalogCast,
    CatalogDocument,
    CatalogEntry,
    Count,
    FixedRole,
    InputAllocation,
    InputRequirements,
    Slug,
    StoryCast,
)
from t2i_story_pipeline.models import Model, RuleText, StoryRequest, ThemeId


class PlannedCast(Model):
    scope: RuleText = "all_people"
    female_count: Count | None = None
    male_count: Count | None = None
    fixed_roles: tuple[FixedRole, ...] = ()
    background_counts: tuple[BackgroundCountBand, ...] = ()
    principal_total: int | None = Field(default=None, ge=1, le=8, strict=True)
    total: int | None = Field(default=None, ge=1, le=38, strict=True)
    total_min: int = Field(ge=1, le=38, strict=True)
    total_max: int = Field(ge=1, le=38, strict=True)
    min_female: Count = 0
    min_male: Count = 0

    @model_validator(mode="after")
    def possible(self) -> Self:
        source = StoryCast(
            scope=self.scope,
            female_count=self.female_count,
            male_count=self.male_count,
            fixed_roles=self.fixed_roles,
            background_counts=self.background_counts,
        )
        candidates = _possible_casts(
            source, self.principal_total, self.min_female, self.min_male
        )
        if not candidates:
            raise ValueError("input plan has impossible cast facts or exceeds 8 people")
        principal_total, total_min, total_max = _cast_totals(source, candidates)
        if (
            self.principal_total != principal_total
            or self.total_min != total_min
            or self.total_max != total_max
            or self.total != (total_min if total_min == total_max else None)
        ):
            raise ValueError("input plan totals contradict principal/background facts")
        return self


class ThemeInputPlan(Model):
    theme_id: ThemeId
    catalog_id: Slug | None = None
    entry: CatalogEntry | None = None
    cast: PlannedCast

    @model_validator(mode="after")
    def catalog_matches(self) -> Self:
        if (self.catalog_id is None) != (self.entry is None):
            raise ValueError("plan entry and catalog_id must be supplied together")
        if self.entry is not None and self.entry.cast is not None:
            facts = self.entry.cast
            if self.cast.background_counts:
                raise ValueError(
                    "catalog cast totals cannot be combined with background count bands"
                )
            if (
                self.cast.total != facts.total
                or self.cast.min_female != facts.min_female
                or self.cast.min_male != facts.min_male
            ):
                raise ValueError("plan cast must preserve catalog cast facts")
        return self


def possible_casts(cast: PlannedCast) -> set[tuple[int, int]]:
    """Enumerate the bounded participant group, preserving unspecified counts."""
    source = StoryCast(
        scope=cast.scope,
        female_count=cast.female_count,
        male_count=cast.male_count,
        fixed_roles=cast.fixed_roles,
        background_counts=cast.background_counts,
    )
    return _possible_casts(source, cast.principal_total, cast.min_female, cast.min_male)


def _possible_casts(
    cast: StoryCast,
    principal_total: int | None,
    min_female: int,
    min_male: int,
) -> set[tuple[int, int]]:
    female_roles = sum(role.sex == "female" for role in cast.fixed_roles)
    male_roles = sum(role.sex == "male" for role in cast.fixed_roles)
    choices = sum(role.sex == "theme_choice" for role in cast.fixed_roles)
    possibilities: set[tuple[int, int]] = set()
    for female in range(9):
        for male in range(9):
            if cast.female_count is not None and female != cast.female_count:
                continue
            if cast.male_count is not None and male != cast.male_count:
                continue
            total = female + male + len(cast.fixed_roles)
            if not 1 <= total <= 8 or (
                principal_total is not None and total != principal_total
            ):
                continue
            if any(
                female + female_roles + chosen >= min_female
                and male + male_roles + choices - chosen >= min_male
                for chosen in range(choices + 1)
            ):
                possibilities.add((female, male))
    return possibilities


def _cast_totals(
    cast: StoryCast, candidates: set[tuple[int, int]]
) -> tuple[int | None, int, int]:
    principal_totals = {
        female + male + len(cast.fixed_roles) for female, male in candidates
    }
    low = min(principal_totals)
    high = max(principal_totals)
    background_min = min((band.min for band in cast.background_counts), default=0)
    background_max = max((band.max for band in cast.background_counts), default=0)
    return low if low == high else None, low + background_min, high + background_max


def _planned_cast(cast: StoryCast, facts: CatalogCast | None) -> PlannedCast:
    if facts is not None and cast.background_counts:
        raise ValueError(
            "catalog cast totals cannot be combined with background count bands"
        )
    min_female = facts.min_female if facts is not None else 0
    min_male = facts.min_male if facts is not None else 0
    candidates = _possible_casts(
        cast, facts.total if facts is not None else None, min_female, min_male
    )
    if not candidates:
        raise ValueError("input plan has impossible cast facts or exceeds 8 principals")
    principal_total, total_min, total_max = _cast_totals(cast, candidates)
    return PlannedCast(
        **cast.model_dump(),
        principal_total=principal_total,
        total=total_min if total_min == total_max else None,
        total_min=total_min,
        total_max=total_max,
        min_female=min_female,
        min_male=min_male,
    )


def plan_themes(
    request: StoryRequest,
    cast: StoryCast,
    allocation: InputAllocation | None,
    catalog: CatalogDocument | None,
) -> tuple[ThemeInputPlan, ...]:
    """Freeze plans by global ordinal, independently of provider batch boundaries.

    Cyclic catalogs deliberately assign their first listed slot to T001.
    Explicit catalog order resolves ambiguous source offsets, not model arithmetic.
    """
    selected: list[CatalogEntry | None]
    if allocation is None:
        if catalog is not None:
            raise ValueError("catalog requires an allocation")
        selected = [None] * request.theme_count
    else:
        if catalog is None or catalog.id != allocation.catalog:
            raise ValueError("allocation catalog is missing or has a mismatched id")
        by_id = {entry.id: entry for entry in catalog.entries}
        if allocation.type == "fixed_slots":
            if catalog.slots is None or len(catalog.slots) != request.theme_count:
                raise ValueError(
                    f"catalog {catalog.id}: fixed_slots must exactly match theme_count "
                    f"({request.theme_count})"
                )
            ids = list(catalog.slots)
            selected = [by_id[item_id] for item_id in ids]
        elif allocation.type == "alphabet_coverage":
            alphabet = list(string.ascii_lowercase)
            if set(by_id) != set(alphabet):
                raise ValueError(
                    f"catalog {catalog.id}: "
                    "alphabet_coverage requires exactly entries a-z"
                )
            if catalog.diversity_order is None:
                raise ValueError(
                    f"catalog {catalog.id}: alphabet_coverage requires an explicit "
                    "diversity_order permutation"
                )
            ids = (
                list(catalog.diversity_order[: request.theme_count])
                if request.theme_count < 26
                else [alphabet[index % 26] for index in range(request.theme_count)]
            )
            selected = [by_id[item_id] for item_id in ids]
        else:
            if catalog.slots is None:
                raise ValueError(
                    f"catalog {catalog.id}: cyclic_slots requires "
                    "an explicit slot order"
                )
            selected = [
                by_id[catalog.slots[index % len(catalog.slots)]]
                for index in range(request.theme_count)
            ]
    plans = []
    for index, entry in enumerate(selected, start=1):
        facts = entry.cast if entry is not None else None
        plans.append(
            ThemeInputPlan(
                theme_id=f"T{index:03d}",
                catalog_id=catalog.id if catalog is not None else None,
                entry=entry,
                cast=_planned_cast(cast, facts),
            )
        )
    return tuple(plans)


def validate_requirements(
    request: StoryRequest,
    plans: tuple[ThemeInputPlan, ...],
    requirements: tuple[tuple[str, InputRequirements], ...],
) -> None:
    """Intersect visual applicability without rewriting caller choices."""
    for source, requirement in requirements:
        allowed = requirement.content_levels
        if allowed is not None and request.content_level not in allowed:
            raise ValueError(f"{source}: content_level must be one of {allowed}")
        if requirement.cast_constraints == "unspecified" and (
            request.female_count is not None or request.male_count is not None
        ):
            raise ValueError(f"{source}: cast_constraints must remain unspecified")

    for plan in plans:
        candidates = possible_casts(plan.cast)
        sources = ", ".join(source for source, _ in requirements)
        for source, requirement in requirements:
            if requirement.allowed_casts is not None:
                allowed = {
                    (cast.female_count, cast.male_count)
                    for cast in requirement.allowed_casts
                }
                if not candidates <= allowed:
                    raise ValueError(
                        f"{source}: {plan.theme_id} cast is unspecified or outside "
                        f"allowed_casts {sorted(allowed)}"
                    )
                candidates &= allowed
            for index, name in enumerate(("female_count", "male_count")):
                bounds = getattr(requirement, name)
                if bounds is None:
                    continue
                # The requirement must be established by request/plan, not silently
                # turned into an implicit cast assignment.
                if any(
                    bounds.min is not None
                    and pair[index] < bounds.min
                    or bounds.max is not None
                    and pair[index] > bounds.max
                    for pair in candidates
                ):
                    raise ValueError(
                        f"{source}: {plan.theme_id} {name} is unspecified or "
                        f"violates {bounds}"
                    )
                candidates = {
                    pair
                    for pair in candidates
                    if (bounds.min is None or pair[index] >= bounds.min)
                    and (bounds.max is None or pair[index] <= bounds.max)
                }
        if not candidates:
            raise ValueError(f"{sources}: {plan.theme_id} has incompatible cast limits")
