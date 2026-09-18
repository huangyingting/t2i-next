"""Structural selection statistics, not rendered-image similarity estimates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from .catalog import PoseCatalog, PoseEntry, StrictModel, entry_signature

if TYPE_CHECKING:
    from .service import SceneRequest


class StructuralDiagnostics(StrictModel):
    evidence: Literal["symbolic_structure_only"] = "symbolic_structure_only"
    visual_validation: Literal[False] = False
    evaluated_batches: int = Field(default=0, ge=0)
    evaluated_scenes: int = Field(default=0, ge=0)
    within_batch_pairs: int = Field(default=0, ge=0)
    same_macro_structure_pairs: int = Field(default=0, ge=0)
    minimum_distinct_macro_structures: int | None = Field(default=None, ge=1)
    unique_pose_entries: int = Field(default=0, ge=0)
    unique_pose_structures: int = Field(default=0, ge=0)
    unique_macro_structures: int = Field(default=0, ge=0)
    exact_selection_repeats: int = Field(default=0, ge=0)
    coverage: dict[str, dict[str, int]] = Field(default_factory=dict)


def _structure_signatures(entry: PoseEntry) -> tuple[str, str]:
    pose = entry.central_pose
    macro_payload = {
        "body_level": pose.body_level,
        "torso_orientation": pose.torso_orientation,
        "pelvis_orientation": pose.pelvis_orientation,
        "primary_surface": pose.primary_surface,
        "support_points": sorted(pose.support_points),
        "actors": [
            {
                "role": plan.role,
                "pose_function": plan.pose_function,
                "composition_pattern": plan.composition_pattern,
                "screen_position": plan.screen_position,
                "depth_plane": plan.depth_plane,
                "support_points": sorted(plan.support_points),
            }
            for plan in sorted(entry.actor_plans, key=lambda item: item.role)
        ],
    }
    pose_payload = {
        **macro_payload,
        "leg_configuration": pose.leg_configuration,
        "arm_configuration": pose.arm_configuration,
        "limb_roles": {
            plan.role: sorted(plan.limb_roles) for plan in entry.actor_plans
        },
    }
    return entry_signature(macro_payload), entry_signature(pose_payload)


def accumulate_structural_diagnostics(
    previous: StructuralDiagnostics,
    catalog: PoseCatalog,
    requests: Sequence[SceneRequest],
) -> StructuralDiagnostics:
    if not requests:
        raise ValueError("structural diagnostics require at least one scene")
    entries = {
        (entry.central_pose.family, entry.central_pose.variant): entry
        for entry in catalog.entries
    }
    coverage = {
        dimension: Counter(counts)
        for dimension, counts in previous.coverage.items()
    }
    batch_macros: Counter[str] = Counter()
    for request in requests:
        if request.cast_key != catalog.cast_key:
            raise ValueError(
                f"{request.scene_id} cast differs from diagnostic catalog"
            )
        key = (request.family, request.variant)
        if key not in entries:
            raise ValueError(f"{request.scene_id} pose not found in diagnostic catalog")
        entry = entries[key]
        pose = entry.central_pose
        macro_signature, pose_signature = _structure_signatures(entry)
        selection_signature = entry_signature(
            {
                "cast_key": request.cast_key,
                "family": request.family,
                "variant": request.variant,
                "activity_id": request.activity_id,
                "viewpoint": request.viewpoint,
                "shot_scale": request.shot_scale,
            }
        )
        dimensions = {
            "pose_entry": entry.pose_id,
            "pose_structure": pose_signature,
            "macro_structure": macro_signature,
            "selection": selection_signature,
            "family": pose.family,
            "body_level": pose.body_level,
            "torso_orientation": pose.torso_orientation,
            "pelvis_orientation": pose.pelvis_orientation,
            "primary_surface": pose.primary_surface,
            "viewpoint": request.viewpoint,
            "shot_scale": request.shot_scale,
        }
        for dimension, value in dimensions.items():
            coverage.setdefault(dimension, Counter())[value] += 1
        batch_macros[macro_signature] += 1

    previous_minimum = previous.minimum_distinct_macro_structures
    scene_count = len(requests)
    return StructuralDiagnostics(
        evaluated_batches=previous.evaluated_batches + 1,
        evaluated_scenes=previous.evaluated_scenes + scene_count,
        within_batch_pairs=(
            previous.within_batch_pairs + scene_count * (scene_count - 1) // 2
        ),
        same_macro_structure_pairs=(
            previous.same_macro_structure_pairs
            + sum(count * (count - 1) // 2 for count in batch_macros.values())
        ),
        minimum_distinct_macro_structures=(
            len(batch_macros)
            if previous_minimum is None
            else min(previous_minimum, len(batch_macros))
        ),
        unique_pose_entries=len(coverage["pose_entry"]),
        unique_pose_structures=len(coverage["pose_structure"]),
        unique_macro_structures=len(coverage["macro_structure"]),
        exact_selection_repeats=sum(
            count - 1 for count in coverage["selection"].values()
        ),
        coverage={
            dimension: dict(sorted(counts.items()))
            for dimension, counts in sorted(coverage.items())
        },
    )
