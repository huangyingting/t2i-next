"""Bounded least-squares inverse kinematics, not a collision certificate.

Only root transforms and named joint angles are optimization variables. Bone
lengths and all joint coordinates remain FK-derived on every evaluation.
"""

from __future__ import annotations

import math

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

    Variables are flat JointAngles fields or ROOT_VARIABLES. Translation bounds
    are relative to the supplied root and capped at 10m; rotations are within
    +/-180 degrees of the supplied root. Joint bounds are JOINT_LIMITS.
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
    skeleton = forward_kinematics(actor)
    unknown = {target.anchor for target in targets} - skeleton.anchors.keys()
    if unknown:
        raise ValueError(f"Unknown anchors: {sorted(unknown)}")
    if len(set(variable_names)) != len(variable_names):
        raise ValueError("Duplicate IK variable names")
    unknown_variables = set(variable_names) - set(JOINT_LIMITS) - set(ROOT_VARIABLES)
    if unknown_variables:
        raise ValueError(f"Unknown IK variables: {sorted(unknown_variables)}")
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
        current = forward_kinematics(candidate(values))
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
    current = forward_kinematics(fitted)
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
