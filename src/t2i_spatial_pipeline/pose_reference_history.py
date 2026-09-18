"""Immutable usage snapshots for reproducible neutral reference sampling."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from .pose_reference_types import Identifier, ReferenceModel

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
PositiveCount = Annotated[int, Field(ge=1)]


def reference_digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ReferenceChoice(ReferenceModel):
    pose_id: Identifier
    camera_id: Identifier
    presentation_id: Identifier

    def fingerprint(self) -> str:
        return reference_digest(self.model_dump(mode="json"))


class ReferenceUsage(ReferenceModel):
    catalog_fingerprint: Digest
    completed_batches: int = Field(default=0, ge=0)
    selected_scenes: int = Field(default=0, ge=0)
    pose_counts: dict[Identifier, PositiveCount] = Field(default_factory=dict)
    camera_counts: dict[Identifier, PositiveCount] = Field(default_factory=dict)
    presentation_counts: dict[Identifier, PositiveCount] = Field(default_factory=dict)
    combination_counts: dict[Digest, PositiveCount] = Field(default_factory=dict)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> ReferenceUsage:
        for counts in (
            self.pose_counts, self.camera_counts,
            self.presentation_counts, self.combination_counts,
        ):
            if sum(counts.values()) != self.selected_scenes:
                raise ValueError("usage counts do not match selected scene total")
        if bool(self.completed_batches) != bool(self.selected_scenes):
            raise ValueError("usage batches and scenes must both be empty or nonempty")
        if self.completed_batches > self.selected_scenes:
            raise ValueError("usage cannot contain more batches than scenes")
        return self


def advance_reference_usage(
    previous: ReferenceUsage,
    choices: tuple[ReferenceChoice, ...],
) -> ReferenceUsage:
    if not choices:
        raise ValueError("usage update requires at least one reference choice")
    poses = Counter(previous.pose_counts)
    cameras = Counter(previous.camera_counts)
    presentations = Counter(previous.presentation_counts)
    combinations = Counter(previous.combination_counts)
    for choice in choices:
        poses[choice.pose_id] += 1
        cameras[choice.camera_id] += 1
        presentations[choice.presentation_id] += 1
        combinations[choice.fingerprint()] += 1
    return ReferenceUsage(
        catalog_fingerprint=previous.catalog_fingerprint,
        completed_batches=previous.completed_batches + 1,
        selected_scenes=previous.selected_scenes + len(choices),
        pose_counts=dict(sorted(poses.items())),
        camera_counts=dict(sorted(cameras.items())),
        presentation_counts=dict(sorted(presentations.items())),
        combination_counts=dict(sorted(combinations.items())),
    )
