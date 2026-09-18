"""Bounded two-bone arm initializations with explicit elbow-pole choices.

These are candidate rotations, not collision or reachability certificates.
Every returned candidate is checked against FK and the model's joint bounds.
"""

from __future__ import annotations

import math
import warnings
from typing import Literal

import numpy as np
from scipy.spatial.transform import Rotation

from .kinematics import forward_kinematics, matrix
from .models import JOINT_LIMITS, ActorPose, AnchorTarget, JointAngles


def arm_seed_candidates(
    actor: ActorPose,
    side: Literal["left", "right"],
    target: AnchorTarget,
    *,
    max_candidates: int = 24,
) -> tuple[ActorPose, ...]:
    if side not in {"left", "right"} or target.anchor != f"{side}_palm":
        raise ValueError("arm target must name the selected side's palm")
    if (
        isinstance(max_candidates, bool)
        or not isinstance(max_candidates, int)
        or not 1 <= max_candidates <= 256
    ):
        raise ValueError("max_candidates must be an integer within [1, 256]")
    skeleton = forward_kinematics(actor, include_shapes=False)
    shoulder = np.asarray(skeleton.joints[f"{side}_shoulder"])
    position = np.asarray(target.position)
    normal = np.asarray(
        target.normal
        if target.normal is not None
        else skeleton.anchors[target.anchor].normal
    )
    normal /= np.linalg.norm(normal)
    preferred = position - shoulder
    preferred -= normal * float(preferred @ normal)
    if np.linalg.norm(preferred) < 1e-10:
        basis = np.eye(3)[int(np.argmin(np.abs(normal)))]
        preferred = basis - normal * float(basis @ normal)
    preferred /= np.linalg.norm(preferred)
    body = actor.body
    upper, lower = body.upper_arm_length, body.forearm_length
    torso = (
        matrix(actor.root_rotation)
        @ Rotation.from_euler("z", actor.angles.torso_yaw, degrees=True).as_matrix()
        @ Rotation.from_euler("x", -actor.angles.torso_pitch, degrees=True).as_matrix()
    )
    sign = -1.0 if side == "left" else 1.0
    front, up, outward = torso[:, 1], torso[:, 2], sign * torso[:, 0]
    poles = (
        front,
        front + up,
        front + outward,
        up,
        outward,
        front - up,
        -up,
        -front,
    )
    candidate_groups: list[list[ActorPose]] = []
    seen: set[tuple[float, ...]] = set()
    for azimuth in (0, 90, -90, 180, 45, -45, 135, -135, 15, -15, 30, -30):
        group: list[ActorPose] = []
        candidate_groups.append(group)
        finger = Rotation.from_rotvec(normal * math.radians(azimuth)).apply(preferred)
        wrist = (
            position - normal * body.hand_thickness / 2 - finger * body.hand_length / 2
        )
        delta = wrist - shoulder
        distance = float(np.linalg.norm(delta))
        if not abs(upper - lower) + 1e-9 < distance < upper + lower - 1e-9:
            continue
        direction = delta / distance
        along = (upper * upper - lower * lower + distance * distance) / (2 * distance)
        radius = math.sqrt(max(0.0, upper * upper - along * along))
        center = shoulder + direction * along
        elbow_flex = math.degrees(
            math.acos(
                float(
                    np.clip(
                        (distance * distance - upper * upper - lower * lower)
                        / (2 * upper * lower),
                        -1.0,
                        1.0,
                    )
                )
            )
        )
        hand_rotation = np.column_stack((np.cross(normal, -finger), normal, -finger))
        for pole in poles:
            perpendicular = pole - direction * float(pole @ direction)
            length = float(np.linalg.norm(perpendicular))
            if length < 1e-9:
                continue
            elbow = center + radius * perpendicular / length
            arm_local = torso.T @ ((elbow - shoulder) / upper)
            abduction = math.degrees(
                math.asin(float(np.clip(sign * arm_local[0], -1.0, 1.0)))
            )
            flex = math.degrees(math.atan2(arm_local[1], -arm_local[2]))
            base = (
                torso
                @ Rotation.from_euler("x", flex, degrees=True).as_matrix()
                @ Rotation.from_euler("y", -sign * abduction, degrees=True).as_matrix()
            )
            forearm_local = base.T @ ((wrist - elbow) / lower)
            axial = math.degrees(math.atan2(forearm_local[0], forearm_local[1]))
            forearm_rotation = (
                base
                @ Rotation.from_euler("z", -axial, degrees=True).as_matrix()
                @ Rotation.from_euler("x", elbow_flex, degrees=True).as_matrix()
            )
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Gimbal lock detected.*")
                wrist_euler = Rotation.from_matrix(
                    forearm_rotation.T @ hand_rotation
                ).as_euler("XYZ", degrees=True)
            updates = {
                f"{side}_shoulder_flex": flex,
                f"{side}_shoulder_abduction": abduction,
                f"{side}_shoulder_rotation": axial,
                f"{side}_elbow_flex": elbow_flex,
                f"{side}_wrist_flex": float(wrist_euler[0]),
                f"{side}_wrist_abduction": float(-sign * wrist_euler[1]),
                f"{side}_wrist_rotation": float(-wrist_euler[2]),
            }
            if any(
                not (
                    JOINT_LIMITS[name][0] - 1e-8
                    <= value
                    <= JOINT_LIMITS[name][1] + 1e-8
                )
                for name, value in updates.items()
            ):
                continue
            updates = {
                name: min(max(value, JOINT_LIMITS[name][0]), JOINT_LIMITS[name][1])
                for name, value in updates.items()
            }
            key = tuple(round(value, 9) for value in updates.values())
            if key in seen:
                continue
            angles = JointAngles.model_validate(actor.angles.model_dump() | updates)
            candidate = ActorPose.model_validate(
                actor.model_dump() | {"angles": angles.model_dump()}
            )
            actual = forward_kinematics(candidate, include_shapes=False).anchors[
                target.anchor
            ]
            if (
                np.linalg.norm(np.asarray(actual.position) - position) > 1e-7
                or np.linalg.norm(np.asarray(actual.normal) - normal) > 1e-7
            ):
                continue
            seen.add(key)
            group.append(candidate)
    candidates = [
        group[index]
        for index in range(max(map(len, candidate_groups), default=0))
        for group in candidate_groups
        if index < len(group)
    ]
    return tuple(candidates[:max_candidates])
