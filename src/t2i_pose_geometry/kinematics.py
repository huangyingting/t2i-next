"""Fixed-length forward kinematics; never relocates independent joint points.

Root is the hip midpoint. Euler rotations are SciPy extrinsic xyz rotations.
Torso/head pitch is about -x; limb flexion is about +x. Abduction is about -y
on the right and +y on the left, followed by axial rotation. The left side has
negative world x in the neutral pose. Angles are composed in local frames.
"""

from __future__ import annotations

import itertools
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
from scipy.spatial.transform import Rotation

from .models import ActorPose, Anchor, JointRegion, Shape, Vec3


def vector(values: np.ndarray) -> Vec3:
    return tuple(float(value) for value in values)


def matrix(angles: Vec3) -> np.ndarray:
    return Rotation.from_euler("xyz", angles, degrees=True).as_matrix()


def euler(rotation: np.ndarray) -> Vec3:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return vector(Rotation.from_matrix(rotation).as_euler("xyz", degrees=True))


def _axis(axis: str, degrees: float) -> np.ndarray:
    return Rotation.from_euler(axis, degrees, degrees=True).as_matrix()


@dataclass(frozen=True)
class Skeleton:
    joints: Mapping[str, Vec3]
    anchors: Mapping[str, Anchor]
    shapes: tuple[Shape, ...]
    joint_regions: tuple[JointRegion, ...]


def capsule(
    shape_id: str, start: Vec3, end: Vec3, radius: float, *, shorten: bool = False
) -> Shape:
    """Construct an oriented capsule; optionally trim each bone end by radius."""
    a, b = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    difference = b - a
    distance = float(np.linalg.norm(difference))
    if distance <= 1e-12:
        rotation = np.eye(3)
    else:
        direction = difference / distance
        reference = np.array([1.0, 0.0, 0.0])
        if abs(float(direction @ reference)) > 0.9:
            reference = np.array([0.0, 1.0, 0.0])
        x_axis = np.cross(reference, direction)
        x_axis /= np.linalg.norm(x_axis)
        rotation = np.column_stack((x_axis, np.cross(direction, x_axis), direction))
    length = max(0.0, distance - 2 * radius) if shorten else distance
    return Shape(
        shape_id=shape_id,
        kind="capsule",
        center=vector((a + b) / 2),
        rotation=euler(rotation),
        radius=radius,
        length=length,
    )


def forward_kinematics(actor: ActorPose) -> Skeleton:
    """Derive joint positions, outward-facing surface anchors, and solid volumes."""
    actor = ActorPose.model_validate(actor.model_dump())
    body, angles = actor.body, actor.angles
    origin = np.asarray(actor.root_position)
    root = matrix(actor.root_rotation)
    torso = root @ _axis("z", angles.torso_yaw) @ _axis("x", -angles.torso_pitch)
    joints: dict[str, Vec3] = {"root": actor.root_position}
    anchors: dict[str, Anchor] = {}
    shapes: list[Shape] = []
    regions: list[JointRegion] = []

    def point(name: str, value: np.ndarray) -> np.ndarray:
        joints[name] = vector(value)
        return value

    def solid(
        name: str,
        kind: str,
        center: np.ndarray,
        rotation: np.ndarray,
        dimensions: tuple[float, float, float],
    ) -> None:
        keyword = "size" if kind == "box" else "radii"
        shapes.append(
            Shape(
                shape_id=name,
                kind=kind,
                center=vector(center),
                rotation=euler(rotation),
                **{keyword: dimensions},
            )
        )

    def ball(name: str, position: np.ndarray, radius: float) -> None:
        solid(name, "ellipsoid", position, np.eye(3), (radius,) * 3)

    def anchor(
        name: str,
        shape_id: str,
        center: np.ndarray,
        rotation: np.ndarray,
        offset: tuple[float, float, float],
        normal: tuple[float, float, float],
    ) -> None:
        anchors[name] = Anchor(
            position=vector(center + rotation @ np.asarray(offset)),
            normal=vector(rotation @ np.asarray(normal)),
            shape_id=shape_id,
        )

    def joint_region(
        joint: str, center: np.ndarray, radius: float, names: tuple[str, ...]
    ) -> None:
        for pair in itertools.combinations(names, 2):
            regions.append(
                JointRegion(
                    joint=joint, center=vector(center), radius=radius, shapes=pair
                )
            )

    solid(
        "pelvis",
        "ellipsoid",
        origin,
        root,
        (body.pelvis_half_width, body.pelvis_depth, body.pelvis_half_height),
    )
    torso_z = (body.torso_length + body.pelvis_half_height) / 2
    torso_center = origin + torso @ np.array([0.0, 0.0, torso_z])
    solid(
        "torso",
        "ellipsoid",
        torso_center,
        torso,
        (
            body.torso_half_width,
            body.torso_depth,
            (body.torso_length - body.pelvis_half_height) / 2,
        ),
    )
    joint_region(
        "root",
        origin,
        1.6 * max(body.pelvis_half_height, body.pelvis_depth),
        ("pelvis", "torso"),
    )
    shoulder_center = point(
        "shoulder_center",
        origin + torso @ np.array([0.0, 0.0, body.torso_length]),
    )
    head_base = point(
        "head_base",
        shoulder_center + torso @ np.array([0.0, 0.0, body.neck_length]),
    )
    head_frame = torso @ _axis("z", angles.head_yaw) @ _axis("x", -angles.head_pitch)
    head_center = point(
        "head", head_base + head_frame @ np.array([0.0, 0.0, body.head_radius])
    )
    shapes.append(
        capsule(
            "neck",
            vector(shoulder_center),
            vector(head_base),
            body.neck_radius,
            shorten=True,
        )
    )
    solid("head", "ellipsoid", head_center, head_frame, (body.head_radius,) * 3)
    joint_region("head_base", head_base, body.head_radius, ("neck", "head"))
    joint_region(
        "neck_base", shoulder_center, body.neck_radius * 2.5, ("torso", "neck")
    )
    anchor(
        "seat",
        "pelvis",
        origin,
        root,
        (0, 0, -body.pelvis_half_height),
        (0, 0, -1),
    )
    anchor("back", "torso", torso_center, torso, (0, -body.torso_depth, 0), (0, -1, 0))
    for side, sign in (("left", -1), ("right", 1)):
        anchor(
            f"{side}_side",
            "torso",
            torso_center,
            torso,
            (sign * body.torso_half_width, 0, 0),
            (sign, 0, 0),
        )
        anchor(
            f"{side}_head",
            "head",
            head_center,
            head_frame,
            (sign * body.head_radius, 0, 0),
            (sign, 0, 0),
        )
        hip = point(
            f"{side}_hip",
            origin + root @ np.array([sign * body.hip_half_width, 0, 0]),
        )
        thigh_frame = (
            root
            @ _axis("x", getattr(angles, f"{side}_hip_flex"))
            @ _axis("y", -sign * getattr(angles, f"{side}_hip_abduction"))
            @ _axis("z", getattr(angles, f"{side}_hip_yaw"))
        )
        knee = point(
            f"{side}_knee",
            hip + thigh_frame @ np.array([0, 0, -body.thigh_length]),
        )
        shin_frame = thigh_frame @ _axis("x", -getattr(angles, f"{side}_knee_flex"))
        ankle = point(
            f"{side}_ankle",
            knee + shin_frame @ np.array([0, 0, -body.shin_length]),
        )
        foot_frame = shin_frame @ _axis("x", getattr(angles, f"{side}_ankle_flex"))
        foot_center = ankle + foot_frame @ np.array(
            [0, body.foot_length / 4, -body.foot_thickness / 2]
        )
        solid(
            f"{side}_foot",
            "box",
            foot_center,
            foot_frame,
            (body.foot_width, body.foot_length, body.foot_thickness),
        )
        for segment, a, b, radius in (
            ("thigh", hip, knee, body.thigh_radius),
            ("shin", knee, ankle, body.shin_radius),
        ):
            shapes.append(
                capsule(f"{side}_{segment}", vector(a), vector(b), radius, shorten=True)
            )
        for name, position, radius, adjacent in (
            ("hip", hip, body.hip_radius, ("pelvis", f"{side}_thigh")),
            (
                "knee",
                knee,
                body.knee_radius,
                (f"{side}_thigh", f"{side}_shin"),
            ),
            (
                "ankle",
                ankle,
                body.ankle_radius,
                (f"{side}_shin", f"{side}_foot"),
            ),
        ):
            ball(f"{side}_{name}_joint", position, radius)
            joint_region(
                f"{side}_{name}",
                position,
                2.5 * radius,
                (*adjacent, f"{side}_{name}_joint"),
            )
        anchor(
            f"{side}_sole",
            f"{side}_foot",
            foot_center,
            foot_frame,
            (0, 0, -body.foot_thickness / 2),
            (0, 0, -1),
        )
        anchor(
            f"{side}_instep",
            f"{side}_foot",
            foot_center,
            foot_frame,
            (0, 0, body.foot_thickness / 2),
            (0, 0, 1),
        )
        anchor(
            f"{side}_knee",
            f"{side}_knee_joint",
            knee,
            shin_frame,
            (0, body.knee_radius, 0),
            (0, 1, 0),
        )
        anchor(
            f"{side}_shin",
            f"{side}_shin",
            (knee + ankle) / 2,
            shin_frame,
            (0, body.shin_radius, 0),
            (0, 1, 0),
        )
        shoulder = point(
            f"{side}_shoulder",
            shoulder_center + torso @ np.array([sign * body.shoulder_half_width, 0, 0]),
        )
        arm_frame = (
            torso
            @ _axis("x", getattr(angles, f"{side}_shoulder_flex"))
            @ _axis("y", -sign * getattr(angles, f"{side}_shoulder_abduction"))
            @ _axis("z", -getattr(angles, f"{side}_shoulder_rotation"))
        )
        elbow = point(
            f"{side}_elbow",
            shoulder + arm_frame @ np.array([0, 0, -body.upper_arm_length]),
        )
        forearm_frame = arm_frame @ _axis("x", getattr(angles, f"{side}_elbow_flex"))
        wrist = point(
            f"{side}_wrist",
            elbow + forearm_frame @ np.array([0, 0, -body.forearm_length]),
        )
        hand_frame = (
            forearm_frame
            @ _axis("x", getattr(angles, f"{side}_wrist_flex"))
            @ _axis("y", -sign * getattr(angles, f"{side}_wrist_abduction"))
            @ _axis("z", -getattr(angles, f"{side}_wrist_rotation"))
        )
        hand_center = wrist + hand_frame @ np.array([0, 0, -body.hand_length / 2])
        solid(
            f"{side}_hand",
            "box",
            hand_center,
            hand_frame,
            (body.hand_width, body.hand_thickness, body.hand_length),
        )
        for segment, a, b, radius in (
            ("upper_arm", shoulder, elbow, body.upper_arm_radius),
            ("forearm", elbow, wrist, body.forearm_radius),
        ):
            shapes.append(
                capsule(f"{side}_{segment}", vector(a), vector(b), radius, shorten=True)
            )
        for name, position, radius, adjacent in (
            (
                "shoulder",
                shoulder,
                body.shoulder_radius,
                ("torso", f"{side}_upper_arm"),
            ),
            (
                "elbow",
                elbow,
                body.elbow_radius,
                (f"{side}_upper_arm", f"{side}_forearm"),
            ),
            (
                "wrist",
                wrist,
                body.wrist_radius,
                (f"{side}_forearm", f"{side}_hand"),
            ),
        ):
            ball(f"{side}_{name}_joint", position, radius)
            joint_region(
                f"{side}_{name}",
                position,
                2.5 * radius,
                (*adjacent, f"{side}_{name}_joint"),
            )
        anchor(
            f"{side}_palm",
            f"{side}_hand",
            hand_center,
            hand_frame,
            (0, body.hand_thickness / 2, 0),
            (0, 1, 0),
        )
    return Skeleton(
        joints=MappingProxyType(joints),
        anchors=MappingProxyType(anchors),
        shapes=tuple(shapes),
        joint_regions=tuple(regions),
    )
