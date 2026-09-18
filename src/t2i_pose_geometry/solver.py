"""Bounded least-squares inverse kinematics, not a collision certificate.

Only root transforms and named joint angles are optimization variables. Bone
lengths and all joint coordinates remain FK-derived on every evaluation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType

import numpy as np
from scipy.optimize import least_squares

from .kinematics import forward_kinematics
from .models import (
    JOINT_LIMITS,
    ActorPose,
    AnchorTarget,
    JointAngles,
    SolveResult,
    TargetError,
    Tolerances,
)

ROOT_VARIABLES = (
    "root_x",
    "root_y",
    "root_z",
    "root_rotation_x",
    "root_rotation_y",
    "root_rotation_z",
)


def _variable_groups() -> Mapping[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for name in JOINT_LIMITS:
        group = name.rsplit("_", 1)[0]
        groups.setdefault(group, []).append(name)
    groups["root_position"] = list(ROOT_VARIABLES[:3])
    groups["root_rotation"] = list(ROOT_VARIABLES[3:])
    return MappingProxyType({name: tuple(values) for name, values in groups.items()})


VARIABLE_GROUPS = _variable_groups()


def expand_variable_names(variable_names: tuple[str, ...]) -> tuple[str, ...]:
    """Expand joint groups and ``group.component`` selectors into flat variables.

    Examples: left_shoulder, left_elbow, left_wrist, torso, head, root_position,
    root_rotation; left_shoulder.flex, left_hip.yaw, root_position.z. Unknown
    selectors and duplicate variables after expansion raise ValueError.
    """
    if isinstance(variable_names, str):
        raise ValueError("IK variables must be a sequence of selectors, not a string")
    expanded: list[str] = []
    known = set(JOINT_LIMITS) | set(ROOT_VARIABLES)
    for selector in variable_names:
        if not isinstance(selector, str):
            raise ValueError("IK variable selectors must be strings")
        if selector in VARIABLE_GROUPS:
            expanded.extend(VARIABLE_GROUPS[selector])
            continue
        name = selector
        if "." in selector:
            group, component = selector.split(".", maxsplit=1)
            prefix = "root" if group == "root_position" else group
            name = f"{prefix}_{component}"
            if name not in VARIABLE_GROUPS.get(group, ()):
                raise ValueError(f"Unknown IK variables: {selector!r}")
        if name not in known:
            raise ValueError(f"Unknown IK variables: {selector!r}")
        expanded.append(name)
    if len(set(expanded)) != len(expanded):
        raise ValueError("Duplicate IK variable names after group expansion")
    return tuple(expanded)


def solve_actor(
    actor: ActorPose,
    targets: tuple[AnchorTarget, ...],
    variable_names: tuple[str, ...] = tuple(JOINT_LIMITS),
    max_nfev: int = 200,
    *,
    tolerances: Tolerances | None = None,
    root_translation_bound_m: float = 2.0,
) -> SolveResult:
    """Fit anchor positions/normals within explicit bounded numerical tolerances.

    Variables are flat JointAngles fields, ROOT_VARIABLES, VARIABLE_GROUPS, or
    ``group.component`` selectors. Translation bounds are relative to the
    supplied root and capped at 10m; rotations are within +/-180 degrees of the
    supplied root. Joint bounds are JOINT_LIMITS.
    Unknown anchors/variables and invalid inputs raise ValueError. A finite,
    reachable fit reports ``converged`` only when *all* target errors pass;
    least-squares termination alone never establishes convergence or geometry.
    """
    actor = ActorPose.model_validate(actor.model_dump())
    targets = tuple(AnchorTarget.model_validate(t.model_dump()) for t in targets)
    tolerances = Tolerances.model_validate((tolerances or Tolerances()).model_dump())
    if isinstance(max_nfev, bool) or not isinstance(max_nfev, int):
        raise ValueError("max_nfev must be an integer")
    if not 1 <= max_nfev <= 2000:
        raise ValueError("max_nfev must be within [1, 2000]")
    if (
        not math.isfinite(root_translation_bound_m)
        or not 0 < root_translation_bound_m <= 10
    ):
        raise ValueError("root_translation_bound_m must be within (0, 10]")
    if not targets:
        raise ValueError("At least one target is required")
    skeleton = forward_kinematics(actor, include_shapes=False)
    unknown = {target.anchor for target in targets} - skeleton.anchors.keys()
    if unknown:
        raise ValueError(f"Unknown anchors: {sorted(unknown)}")
    variable_names = expand_variable_names(variable_names)
    for name, (lower, upper) in JOINT_LIMITS.items():
        if (
            name not in variable_names
            and not lower <= getattr(actor.angles, name) <= upper
        ):
            raise ValueError(f"Fixed joint {name} is outside its limits")
    initial, lower_bounds, upper_bounds = [], [], []
    angle_values = actor.angles.model_dump()
    for name in variable_names:
        if name in JOINT_LIMITS:
            lower, upper = JOINT_LIMITS[name]
            value = angle_values[name]
        elif name.startswith("root_rotation_"):
            index = "xyz".index(name[-1])
            value = actor.root_rotation[index]
            lower, upper = value - 180, value + 180
        else:
            index = "xyz".index(name[-1])
            value = actor.root_position[index]
            lower = value - root_translation_bound_m
            upper = value + root_translation_bound_m
        initial.append(float(np.clip(value, lower, upper)))
        lower_bounds.append(lower)
        upper_bounds.append(upper)

    def candidate(values: np.ndarray) -> ActorPose:
        angles = dict(angle_values)
        position, rotation = list(actor.root_position), list(actor.root_rotation)
        for name, value in zip(variable_names, values, strict=True):
            if name in JOINT_LIMITS:
                angles[name] = float(value)
            elif name.startswith("root_rotation_"):
                rotation["xyz".index(name[-1])] = float(value)
            else:
                position["xyz".index(name[-1])] = float(value)
        return ActorPose(
            actor_id=actor.actor_id,
            body=actor.body,
            root_position=tuple(position),
            root_rotation=tuple(rotation),
            angles=JointAngles(**angles),
        )

    normal_scale = 2 * math.sin(math.radians(tolerances.normal_degrees) / 2)

    def residual(values: np.ndarray) -> np.ndarray:
        current = forward_kinematics(candidate(values), include_shapes=False)
        result = []
        for target in targets:
            anchor = current.anchors[target.anchor]
            result.extend(
                (np.asarray(anchor.position) - target.position) / tolerances.contact_m
            )
            if target.normal is not None:
                result.extend(
                    (np.asarray(anchor.normal) - target.normal) / normal_scale
                )
        return np.asarray(result)

    initial_array = np.asarray(initial)
    if variable_names:
        fit = least_squares(
            residual,
            initial_array,
            bounds=(np.asarray(lower_bounds), np.asarray(upper_bounds)),
            max_nfev=max_nfev,
            x_scale="jac",
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
        )
        fitted = candidate(fit.x)
        nfev, message = int(fit.nfev), str(fit.message)
    else:
        fitted, nfev, message = actor, 0, "No variables requested"
    current = forward_kinematics(fitted, include_shapes=False)
    errors: list[TargetError] = []
    for target in targets:
        anchor = current.anchors[target.anchor]
        distance = float(np.linalg.norm(np.asarray(anchor.position) - target.position))
        normal_error = (
            math.degrees(
                math.acos(
                    float(np.clip(np.asarray(anchor.normal) @ target.normal, -1, 1))
                )
            )
            if target.normal is not None
            else None
        )
        errors.append(
            TargetError(
                anchor=target.anchor,
                error_m=distance,
                normal_error_degrees=normal_error,
            )
        )
    converged = all(
        error.error_m <= tolerances.contact_m
        and (
            error.normal_error_degrees is None
            or error.normal_error_degrees <= tolerances.normal_degrees
        )
        for error in errors
    )
    return SolveResult(
        actor=fitted,
        converged=converged,
        errors=tuple(errors),
        message=message,
        nfev=nfev,
    )
