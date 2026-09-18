"""Finite, immutable inputs for a synthetic static humanoid geometry model.

Distances are meters. Angles are degrees; world axes are right/front/up (x/y/z).
The reference dimensions below describe a synthetic clothed adult, not measured
anatomy. Neither dimensions nor joint ranges establish biological safety.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Finite = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Vec3 = tuple[Finite, Finite, Finite]
Positive3 = tuple[Positive, Positive, Positive]
Identifier = Annotated[str, Field(min_length=1)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)


class BodySpec(FrozenModel):
    """Synthetic reference body; ``scaled`` scales every linear dimension."""

    upper_arm_length: Positive = 0.30
    forearm_length: Positive = 0.26
    thigh_length: Positive = 0.42
    shin_length: Positive = 0.42
    torso_length: Positive = 0.50
    shoulder_half_width: Positive = 0.215
    hip_half_width: Positive = 0.095
    head_radius: Positive = 0.095
    neck_length: Positive = 0.07
    neck_radius: Positive = 0.035
    torso_half_width: Positive = 0.155
    torso_depth: Positive = 0.105
    pelvis_half_width: Positive = 0.145
    pelvis_depth: Positive = 0.10
    pelvis_half_height: Positive = 0.095
    upper_arm_radius: Positive = 0.045
    forearm_radius: Positive = 0.036
    thigh_radius: Positive = 0.063
    shin_radius: Positive = 0.047
    shoulder_radius: Positive = 0.050
    elbow_radius: Positive = 0.045
    wrist_radius: Positive = 0.025
    hip_radius: Positive = 0.070
    knee_radius: Positive = 0.065
    ankle_radius: Positive = 0.047
    hand_length: Positive = 0.18
    hand_width: Positive = 0.085
    hand_thickness: Positive = 0.05
    foot_length: Positive = 0.25
    foot_width: Positive = 0.10
    foot_thickness: Positive = 0.055

    @model_validator(mode="after")
    def coherent_dimensions(self) -> Self:
        for segment in ("upper_arm", "forearm", "thigh", "shin"):
            if getattr(self, f"{segment}_length") <= (
                2 * getattr(self, f"{segment}_radius")
            ):
                raise ValueError(f"{segment}_length must exceed twice its radius")
        if self.torso_length <= self.pelvis_half_height:
            raise ValueError("torso_length must exceed pelvis_half_height")
        if self.neck_length < 2 * self.neck_radius:
            raise ValueError("neck_length must be at least twice neck_radius")
        if self.hip_half_width >= self.pelvis_half_width:
            raise ValueError("hips must lie within the pelvis width")
        return self

    def scaled(self, factor: float) -> Self:
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("scale must be finite and positive")
        return type(self).model_validate(
            {name: value * factor for name, value in self.model_dump().items()}
        )


class JointAngles(FrozenModel):
    """Neutral limbs point down; flexion moves arms/thighs forward.

    Knee flexion bends the shin backward; elbow flexion bends the forearm
    forward. Abduction moves either side outward. Hip yaw is local +z rotation;
    shoulder/wrist rotation is right-handed about the distal (-z) axis.
    Ankle flexion raises the toes (dorsiflexion). Wrist flexion bends the hand
    forward and wrist abduction moves it outward. Positive torso/head pitch
    tilts their upward axis forward. See ``JOINT_LIMITS`` for model bounds.
    """

    torso_pitch: Finite = 0
    torso_yaw: Finite = 0
    head_pitch: Finite = 0
    head_yaw: Finite = 0
    left_hip_flex: Finite = 0
    left_hip_abduction: Finite = 0
    left_hip_yaw: Finite = 0
    left_knee_flex: Finite = 0
    left_ankle_flex: Finite = 0
    right_hip_flex: Finite = 0
    right_hip_abduction: Finite = 0
    right_hip_yaw: Finite = 0
    right_knee_flex: Finite = 0
    right_ankle_flex: Finite = 0
    left_shoulder_flex: Finite = 0
    left_shoulder_abduction: Finite = 0
    left_shoulder_rotation: Finite = 0
    left_elbow_flex: Finite = 0
    left_wrist_flex: Finite = 0
    left_wrist_abduction: Finite = 0
    left_wrist_rotation: Finite = 0
    right_shoulder_flex: Finite = 0
    right_shoulder_abduction: Finite = 0
    right_shoulder_rotation: Finite = 0
    right_elbow_flex: Finite = 0
    right_wrist_flex: Finite = 0
    right_wrist_abduction: Finite = 0
    right_wrist_rotation: Finite = 0


def _joint_limits() -> Mapping[str, tuple[float, float]]:
    limits = {
        "torso_pitch": (-45.0, 85.0),
        "torso_yaw": (-80.0, 80.0),
        "head_pitch": (-60.0, 60.0),
        "head_yaw": (-85.0, 85.0),
    }
    side_limits = {
        "hip_flex": (-35.0, 135.0),
        "hip_abduction": (-30.0, 80.0),
        "hip_yaw": (-55.0, 55.0),
        "knee_flex": (0.0, 150.0),
        "ankle_flex": (-50.0, 35.0),
        "shoulder_flex": (-60.0, 180.0),
        "shoulder_abduction": (-35.0, 170.0),
        "shoulder_rotation": (-90.0, 90.0),
        "elbow_flex": (0.0, 150.0),
        "wrist_flex": (-75.0, 75.0),
        "wrist_abduction": (-35.0, 35.0),
        "wrist_rotation": (-90.0, 90.0),
    }
    for side in ("left", "right"):
        limits.update({f"{side}_{key}": value for key, value in side_limits.items()})
    return MappingProxyType(limits)


JOINT_LIMITS = _joint_limits()


class ActorPose(FrozenModel):
    actor_id: Identifier
    body: BodySpec = Field(default_factory=BodySpec)
    root_position: Vec3 = (0.0, 0.0, 0.895)
    root_rotation: Vec3 = (0.0, 0.0, 0.0)
    angles: JointAngles = Field(default_factory=JointAngles)


class Box(FrozenModel):
    """A solid box, with full side lengths and extrinsic xyz Euler rotation."""

    object_id: Identifier
    center: Vec3
    size: Positive3
    rotation: Vec3 = (0.0, 0.0, 0.0)


Face = Literal["top", "front", "back", "left", "right", "bottom"]


class Contact(FrozenModel):
    actor_id: Identifier
    anchor: Identifier
    object_id: Identifier
    face: Face = "top"


class Scene(FrozenModel):
    actors: tuple[ActorPose, ...]
    objects: tuple[Box, ...] = ()
    contacts: tuple[Contact, ...] = ()


class Tolerances(FrozenModel):
    """Numerical tolerances, strictly capped; not anatomical uncertainty."""

    contact_m: Annotated[float, Field(gt=0, le=0.002, allow_inf_nan=False)] = 0.002
    penetration_m: Annotated[float, Field(ge=0, le=0.001, allow_inf_nan=False)] = (
        0.00001
    )
    normal_degrees: Annotated[float, Field(gt=0, le=5.0, allow_inf_nan=False)] = 5.0


class Anchor(FrozenModel):
    position: Vec3
    normal: Vec3
    shape_id: Identifier

    @model_validator(mode="after")
    def unit_normal(self) -> Self:
        if not math.isclose(math.hypot(*self.normal), 1.0, abs_tol=1e-8):
            raise ValueError("anchor normal must be a unit vector")
        return self


class Shape(FrozenModel):
    """Derived convex solid. Ellipsoid radii are semiaxes; box size is full.

    A capsule's ``length`` is its cylindrical centerline length, excluding the
    two hemispheres; its local cylinder axis is z. FK is the authority for body
    shapes. Scene validation never accepts a caller-supplied collider cache.
    """

    shape_id: Identifier
    kind: Literal["capsule", "ellipsoid", "box"]
    center: Vec3
    rotation: Vec3 = (0.0, 0.0, 0.0)
    size: Positive3 = (1.0, 1.0, 1.0)
    radii: Positive3 = (1.0, 1.0, 1.0)
    radius: Positive = 1.0
    length: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0


class JointRegion(FrozenModel):
    """A derived sphere permitting overlap only for its explicitly named pair."""

    joint: Identifier
    center: Vec3
    radius: Positive
    shapes: tuple[Identifier, Identifier]


class AnchorTarget(FrozenModel):
    anchor: Identifier
    position: Vec3
    normal: Vec3 | None = None

    @model_validator(mode="after")
    def unit_normal(self) -> Self:
        if self.normal is not None and not math.isclose(
            math.hypot(*self.normal), 1.0, abs_tol=1e-8
        ):
            raise ValueError("target normal must be a unit vector")
        return self


class Issue(FrozenModel):
    code: str
    parts: tuple[str, ...]
    details: str
    penetration_m: Finite | None = None
    error_m: Finite | None = None


class ValidationReport(FrozenModel):
    passed: bool
    issues: tuple[Issue, ...] = ()


class TargetError(FrozenModel):
    anchor: str
    error_m: Finite
    normal_error_degrees: Finite | None = None


class SolveResult(FrozenModel):
    actor: ActorPose
    converged: bool
    errors: tuple[TargetError, ...]
    message: str
    nfev: int = 0
