"""Compile neutral reference intentions into independently checked geometry."""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from scipy.spatial.transform import Rotation

from t2i_pose_geometry.arm_seeds import arm_seed_candidates
from t2i_pose_geometry.kinematics import forward_kinematics
from t2i_pose_geometry.models import (
    JOINT_LIMITS,
    ActorPose,
    AnchorTarget,
    BodyContact,
    BodySpec,
    Box,
    Contact,
    JointAngles,
    Scene,
    ValidationReport,
    Vec3,
)
from t2i_pose_geometry.solver import solve_actor
from t2i_pose_geometry.validation import validate_scene

from .pose_reference_presentation import ReferencePresentation, ReferenceSubject
from .pose_reference_types import ReferenceModel

if TYPE_CHECKING:
    from .pose_reference import NeutralPose

GEOMETRY_COMPILER_VERSION = "1.0"
_YAW = {"front": 0.0, "left_three_quarter": 45.0, "right_three_quarter": -45.0}
_MAT_TOP = 0.02
_ARM_BEAM_WIDTH = 4


class ReferenceJointPosition(ReferenceModel):
    actor_id: str
    joint: str
    position: Vec3


@lru_cache(maxsize=512)
def reference_geometry_report(scene: Scene) -> ValidationReport:
    return validate_scene(scene)


@lru_cache(maxsize=512)
def reference_joint_positions(scene: Scene) -> tuple[ReferenceJointPosition, ...]:
    return tuple(
        ReferenceJointPosition(actor_id=actor.actor_id, joint=joint, position=position)
        for actor in sorted(scene.actors, key=lambda item: item.actor_id)
        for joint, position in sorted(forward_kinematics(actor).joints.items())
    )


class ReferenceGeometryError(ValueError):
    def __init__(self, pose_id: str, geometry: Scene, report: ValidationReport) -> None:
        self.pose_id = pose_id
        self.geometry = geometry
        self.report = report
        super().__init__(
            f"{pose_id}: geometry rejected: "
            + "; ".join(
                f"{issue.code} ({', '.join(issue.parts)}): {issue.details}"
                for issue in report.issues
            )
        )


def geometry_implementation_fingerprint() -> str:
    import t2i_pose_geometry

    package_file = t2i_pose_geometry.__file__
    if package_file is None:
        raise RuntimeError("geometry package has no implementation path")
    digest = hashlib.sha256()
    for path in (
        *sorted(Path(package_file).parent.glob("*.py")),
        Path(__file__),
    ):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    for package in ("numpy", "scipy", "python-fcl"):
        digest.update(f"{package}:{version(package)}".encode())
    return digest.hexdigest()


def _replace_actor(actor: ActorPose, **changes: object) -> ActorPose:
    return ActorPose.model_validate(actor.model_dump() | changes)


def _vector(values: np.ndarray) -> tuple[float, float, float]:
    return float(values[0]), float(values[1]), float(values[2])


def _initial_actor(pose: NeutralPose, body: BodySpec) -> ActorPose:
    angles = JointAngles().model_dump()
    angles["torso_yaw"] = _YAW[pose.facing] - _YAW[pose.pelvis_facing]
    if pose.spine == "forward_inclined":
        angles["torso_pitch"] = 70.0 if pose.body_level == "crouched" else 16.0
    elif pose.spine == "reclined":
        angles["torso_pitch"] = -6.0
    angles["head_yaw"] = {
        "aligned": 0.0, "gentle_left": 20.0, "gentle_right": -20.0,
    }[pose.head_orientation.yaw]
    angles["head_pitch"] = (
        0.0 if pose.head_orientation.pitch == "neutral" else 10.0
    )
    for side in ("left", "right"):
        angles[f"{side}_shoulder_flex"] = 0.0
        angles[f"{side}_shoulder_abduction"] = 6.0
        angles[f"{side}_elbow_flex"] = 5.0
    if pose.legs in {"left_foot_forward", "right_foot_forward"}:
        front = "left" if pose.legs == "left_foot_forward" else "right"
        back = "right" if front == "left" else "left"
        angles[f"{front}_hip_flex"] = 15.0
        angles[f"{back}_hip_flex"] = -15.0
        angles[f"{front}_ankle_flex"] = -15.0
        angles[f"{back}_ankle_flex"] = 15.0
    elif pose.legs in {"left_foot_on_step", "right_foot_on_step"}:
        side = "left" if pose.legs == "left_foot_on_step" else "right"
        angles[f"{side}_hip_flex"] = 90.0
        angles[f"{side}_knee_flex"] = 115.0
        angles[f"{side}_ankle_flex"] = 25.0
    elif pose.legs.startswith("seated_"):
        for side in ("left", "right"):
            angles[f"{side}_hip_flex"] = 90.0
            angles[f"{side}_knee_flex"] = 90.0
        if pose.legs != "seated_parallel":
            side = "left" if pose.legs == "seated_left_forward" else "right"
            angles[f"{side}_knee_flex"] = 70.0
            angles[f"{side}_ankle_flex"] = -20.0
    elif pose.legs in {"knees_and_toes_on_mat", "left_half_kneel", "right_half_kneel"}:
        knee_flex = math.degrees(math.acos(
            -(0.75 * body.foot_length - body.knee_radius) / body.shin_length
        ))
        for side in ("left", "right"):
            angles[f"{side}_knee_flex"] = knee_flex
            angles[f"{side}_ankle_flex"] = knee_flex - 90.0
        if pose.legs != "knees_and_toes_on_mat":
            side = "right" if pose.legs == "left_half_kneel" else "left"
            angles[f"{side}_hip_flex"] = 90.0
            angles[f"{side}_knee_flex"] = 90.0
            angles[f"{side}_ankle_flex"] = 0.0
    elif pose.legs == "bent_knees_feet_flat":
        for side in ("left", "right"):
            heading = 40.0 if side == "left" else -40.0
            orientation = (
                Rotation.from_euler("z", heading, degrees=True)
                * Rotation.from_euler("x", 110.0, degrees=True)
            ).as_euler("XYZ", degrees=True)
            angles[f"{side}_hip_flex"] = float(orientation[0])
            angles[f"{side}_hip_abduction"] = float(
                orientation[1] if side == "left" else -orientation[1]
            )
            angles[f"{side}_hip_yaw"] = float(orientation[2])
            angles[f"{side}_knee_flex"] = 130.0
            angles[f"{side}_ankle_flex"] = 20.0
    elif pose.legs == "floor_seated_bent_knees":
        shin_angle = math.degrees(math.acos(
            (
                body.pelvis_half_height
                - body.thigh_length * math.cos(math.radians(125.0))
                - body.foot_thickness
            ) / body.shin_length
        ))
        for side in ("left", "right"):
            angles[f"{side}_hip_flex"] = 125.0
            angles[f"{side}_knee_flex"] = 125.0 - shin_angle
            angles[f"{side}_ankle_flex"] = -shin_angle
    elif pose.legs == "staggered_bent_knees":
        for side in ("left", "right"):
            flex = 35.0 if side == pose.resting_side else 45.0
            angles[f"{side}_hip_flex"] = flex
            angles[f"{side}_knee_flex"] = flex + 30.0
            angles[f"{side}_ankle_flex"] = 30.0
    for side, hand in (("left", pose.left_hand), ("right", pose.right_hand)):
        if hand == "forward_gesture":
            angles[f"{side}_shoulder_flex"] = 45.0
            angles[f"{side}_shoulder_abduction"] = 15.0
            angles[f"{side}_elbow_flex"] = 35.0
        elif hand == "on_mat_forward":
            incline = math.degrees(math.asin(
                (
                    body.shoulder_radius
                    + body.upper_arm_length * math.sin(math.radians(15))
                    - body.hand_thickness / 2
                ) / body.forearm_length
            ))
            angles[f"{side}_shoulder_flex"] = 90.0
            angles[f"{side}_shoulder_abduction"] = -15.0
            angles[f"{side}_shoulder_rotation"] = -90.0 if side == "left" else 90.0
            angles[f"{side}_elbow_flex"] = 15.0 + incline
            angles[f"{side}_wrist_flex"] = -incline
        elif hand == "across_forearm":
            angles[f"{side}_shoulder_flex"] = 55.0
            angles[f"{side}_shoulder_abduction"] = -25.0
            angles[f"{side}_shoulder_rotation"] = 70.0 if side == "left" else -70.0
            angles[f"{side}_elbow_flex"] = 70.0
        elif hand == "relaxed_in_front":
            angles[f"{side}_shoulder_flex"] = 15.0
            angles[f"{side}_shoulder_abduction"] = 0.0
            angles[f"{side}_elbow_flex"] = 50.0
        elif hand in {"on_knee", "on_lap", "on_table", "on_floor"}:
            angles[f"{side}_shoulder_flex"] = 35.0
            angles[f"{side}_shoulder_abduction"] = 20.0
            angles[f"{side}_elbow_flex"] = 55.0
    roll = (
        -90.0 if pose.resting_side == "left"
        else 90.0 if pose.resting_side == "right" else 0.0
    )
    return ActorPose(
        actor_id="subject", body=body, angles=JointAngles.model_validate(angles),
        root_position=(0.0, 0.0, 1.0), root_rotation=(0.0, roll, 0.0),
    )


def _support_anchor(
    body_part: str, resting_side: Literal["none", "left", "right"],
) -> str:
    names = {
        "left_foot": "left_sole", "right_foot": "right_sole",
        "left_hand": "left_palm", "right_hand": "right_palm",
        "left_knee": "left_knee_ground", "right_knee": "right_knee_ground",
        "pelvis": "seat", "upper_back": "back",
    }
    if body_part == "head":
        return f"{resting_side}_head"
    return names.get(body_part, body_part)


def _ground_actor(pose: NeutralPose, actor: ActorPose) -> ActorPose:
    skeleton = forward_kinematics(actor)
    if pose.body_level == "lying":
        base = skeleton.anchors[f"{pose.resting_side}_side"].position[2] - _MAT_TOP
    elif pose.legs == "floor_seated_bent_knees":
        base = skeleton.anchors["seat"].position[2] - _MAT_TOP
    elif pose.body_level == "kneeling":
        side = "right" if pose.legs == "right_half_kneel" else "left"
        base = skeleton.anchors[f"{side}_knee_ground"].position[2] - _MAT_TOP
    else:
        ground_feet = [
            _support_anchor(c.body_part, pose.resting_side)
            for c in pose.supports if c.surface == "floor" and "foot" in c.body_part
        ]
        base = min(skeleton.anchors[name].position[2] for name in ground_feet)
    root = actor.root_position
    actor = _replace_actor(actor, root_position=(root[0], root[1], root[2] - base))
    skeleton = forward_kinematics(actor)
    targets = []
    variables = []
    for contact in pose.supports:
        if contact.surface == "floor" and "foot" in contact.body_part:
            anchor = _support_anchor(contact.body_part, pose.resting_side)
            position = skeleton.anchors[anchor].position
            if abs(position[2]) > 0.0005:
                side = contact.body_part.split("_")[0]
                targets.append(AnchorTarget(
                    anchor=anchor, position=(position[0], position[1], 0.0),
                    normal=(0.0, 0.0, -1.0),
                ))
                variables.extend((
                    f"{side}_hip_flex", f"{side}_knee_flex", f"{side}_ankle_flex",
                ))
    if targets:
        actor = solve_actor(
            actor, tuple(targets), variable_names=tuple(variables), max_nfev=160,
        ).actor
    return actor


def _box(
    name: str, center: tuple[float, float, float], size: tuple[float, float, float],
) -> Box:
    return Box(object_id=name, center=center, size=size, rotation=(0.0, 0.0, 0.0))


def _environment(
    pose: NeutralPose, actor: ActorPose,
) -> tuple[tuple[Box, ...], dict[str, str]]:
    anchors = forward_kinematics(actor).anchors
    surfaces = {c.surface for c in pose.supports}
    scale = actor.body.thigh_length / BodySpec().thigh_length
    objects = [_box("floor", (0.0, 0.0, -0.05), (8.0, 8.0, 0.1))]
    faces: dict[str, str] = {"floor": "top", "mat": "top"}
    if "mat" in surfaces:
        mat_y = -0.9 * scale if "half_kneel" in pose.legs else 0.0
        objects.append(_box("mat", (0.0, mat_y, _MAT_TOP / 2), (
            3.0 * scale, 2.0 * scale, _MAT_TOP,
        )))
    if "table" in surfaces:
        height = actor.root_position[2] - 0.02 * scale
        depth, width = 0.5 * scale, 1.0 * scale
        center_y = 0.45 * scale
        objects.append(_box("table", (0.0, center_y, height - 0.02 * scale), (
            width, depth, 0.04 * scale,
        )))
        for side, x in (("left", -width / 2 + 0.03 * scale),
                        ("right", width / 2 - 0.03 * scale)):
            for edge, y in (("front", center_y + depth / 2 - 0.03 * scale),
                            ("back", center_y - depth / 2 + 0.03 * scale)):
                objects.append(_box(
                    f"table_leg_{side}_{edge}", (x, y, (height - 0.04 * scale) / 2),
                    (0.04 * scale, 0.04 * scale, height - 0.04 * scale),
                ))
        faces["table"] = "top"
    if "step" in surfaces:
        side = "left" if pose.legs == "left_foot_on_step" else "right"
        foot = anchors[f"{side}_sole"].position
        objects.append(_box("step", (foot[0], foot[1], foot[2] / 2), (
            0.18 * scale, 0.34 * scale, foot[2],
        )))
        faces["step"] = "top"
    if "chair_seat" in surfaces:
        seat = anchors["seat"].position
        height = seat[2]
        objects.append(_box("chair_seat", (seat[0], seat[1] + 0.06 * scale,
                                          height - 0.02 * scale), (
            0.55 * scale, 0.36 * scale, 0.04 * scale,
        )))
        for side, x in (("left", -0.235 * scale), ("right", 0.235 * scale)):
            for edge, y in (("front", 0.21 * scale), ("back", -0.09 * scale)):
                objects.append(_box(
                    f"chair_leg_{side}_{edge}", (x, y, (height - 0.04 * scale) / 2),
                    (0.04 * scale, 0.04 * scale, height - 0.04 * scale),
                ))
        faces["chair_seat"] = "top"
    if "chair_back" in surfaces:
        back = anchors["back"].position
        low = anchors["seat"].position[2]
        height = back[2] - low + 0.16 * scale
        objects.append(_box("chair_back", (0.0, back[1] - 0.025 * scale,
                                          low + height / 2), (
            0.55 * scale, 0.05 * scale, height,
        )))
        faces["chair_back"] = "front"
    if "wall" in surfaces:
        if any(c.body_part == "upper_back" for c in pose.supports):
            y = anchors["back"].position[1]
            objects.append(_box("wall", (0.0, y - 0.025 * scale, 1.0 * scale), (
                2.0 * scale, 0.05 * scale, 2.0 * scale,
            )))
            faces["wall"] = "front"
        else:
            left = pose.left_hand == "on_wall"
            x = (-0.525 if left else 0.525) * scale
            objects.append(_box("wall", (x, 0.0, 1.0 * scale), (
                0.05 * scale, 2.0 * scale, 2.0 * scale,
            )))
            faces["wall"] = "right" if left else "left"
    if "headrest" in surfaces:
        head = anchors[f"{pose.resting_side}_head"].position
        height = head[2] - _MAT_TOP
        if height <= 0:
            raise ValueError("lying head leaves no positive headrest clearance")
        objects.append(_box("headrest", (head[0], head[1], _MAT_TOP + height / 2), (
            2.2 * actor.body.head_radius, 2.2 * actor.body.head_radius, height,
        )))
        faces["headrest"] = "top"
    return tuple(objects), faces


def _arm_targets(
    pose: NeutralPose, actor: ActorPose, objects: tuple[Box, ...],
) -> tuple[tuple[AnchorTarget, ...], tuple[BodyContact, ...], tuple[str, ...]]:
    skeleton = forward_kinematics(actor)
    boxes = {box.object_id: box for box in objects}
    targets: list[AnchorTarget] = []
    contacts: list[BodyContact] = []
    variables: list[str] = []
    scale = actor.body.thigh_length / BodySpec().thigh_length
    for side, placement in (("left", pose.left_hand), ("right", pose.right_hand)):
        anchor = f"{side}_palm"
        sign = -1.0 if side == "left" else 1.0
        target_anchor = None
        if placement == "on_knee":
            target_anchor = f"{side}_knee_top"
        elif placement == "on_lap":
            target_anchor = f"{side}_lap"
        elif placement == "across_forearm":
            opposite = "right" if side == "left" else "left"
            other_hand = pose.right_hand if side == "left" else pose.left_hand
            suffix = (
                "forearm_back"
                if other_hand in {"on_lap", "on_knee", "on_mat_forward"}
                else "forearm"
            )
            target_anchor = f"{opposite}_{suffix}"
        if target_anchor is not None:
            target = skeleton.anchors[target_anchor]
            targets.append(AnchorTarget(
                anchor=anchor, position=target.position,
                normal=(-target.normal[0], -target.normal[1], -target.normal[2]),
            ))
            contacts.append(BodyContact(
                actor_id="subject", anchor=anchor,
                target_actor_id="subject", target_anchor=target_anchor,
            ))
        elif placement == "on_table":
            table = boxes["table"]
            targets.append(AnchorTarget(
                anchor=anchor,
                position=(sign * 0.22 * scale, 0.38 * scale,
                          table.center[2] + table.size[2] / 2),
                normal=(0.0, 0.0, -1.0),
            ))
        elif placement == "on_wall":
            targets.append(AnchorTarget(
                anchor=anchor,
                position=(sign * 0.5 * scale, 0.05 * scale,
                          skeleton.joints[f"{side}_shoulder"][2] - 0.1 * scale),
                normal=(sign, 0.0, 0.0),
            ))
        elif placement == "on_floor":
            foot_shape = next(
                shape for shape in skeleton.shapes
                if shape.shape_id == skeleton.anchors[f"{side}_sole"].shape_id
            )
            rotation = Rotation.from_euler(
                "xyz", foot_shape.rotation, degrees=True
            ).as_matrix()
            foot_front = foot_shape.center[1] + float(
                np.abs(rotation[1]) @ (np.asarray(foot_shape.size) / 2)
            )
            hand_clearance = math.hypot(
                actor.body.hand_length / 2, actor.body.hand_width / 2
            ) + 0.02 * scale
            targets.append(AnchorTarget(
                anchor=anchor,
                position=(sign * 0.38 * scale, foot_front + hand_clearance, 0.0),
                normal=(0.0, 0.0, -1.0),
            ))
        elif placement == "on_mat_forward":
            shoulder = skeleton.joints[f"{side}_shoulder"]
            incline = getattr(actor.angles, f"{side}_elbow_flex") - 15.0
            reach = (
                actor.body.upper_arm_length * math.cos(math.radians(15))
                + actor.body.forearm_length * math.cos(math.radians(incline))
                + actor.body.hand_length / 2
            )
            targets.append(AnchorTarget(
                anchor=anchor,
                position=(shoulder[0], shoulder[1] + reach, _MAT_TOP),
                normal=(0.0, 0.0, -1.0),
            ))
            continue
        elif placement == "on_seat":
            seat = boxes["chair_seat"]
            targets.append(AnchorTarget(
                anchor=anchor,
                position=(sign * 0.23 * scale, seat.center[1],
                          seat.center[2] + seat.size[2] / 2),
                normal=(0.0, 0.0, -1.0),
            ))
        else:
            continue
        variables.extend(
            name for name in JOINT_LIMITS
            if name.startswith(
                (f"{side}_shoulder_", f"{side}_elbow_", f"{side}_wrist_")
            )
        )
    return tuple(targets), tuple(contacts), tuple(variables)


def _rotate_scene(scene: Scene, yaw: float) -> Scene:
    matrix = Rotation.from_euler("z", yaw, degrees=True).as_matrix()
    return Scene(
        actors=tuple(
            _replace_actor(
                actor,
                root_position=_vector(matrix @ np.array(actor.root_position)),
                root_rotation=(
                    actor.root_rotation[0], actor.root_rotation[1],
                    actor.root_rotation[2] + yaw,
                ),
            )
            for actor in scene.actors
        ),
        objects=tuple(
            Box(
                object_id=box.object_id,
                center=_vector(matrix @ np.array(box.center)), size=box.size,
                rotation=(box.rotation[0], box.rotation[1], box.rotation[2] + yaw),
            )
            for box in scene.objects
        ),
        contacts=scene.contacts,
        body_contacts=scene.body_contacts,
    )


def _scene_for_actor(
    pose: NeutralPose, actor: ActorPose,
    objects: tuple[Box, ...], faces: dict[str, str],
) -> Scene:
    _, body_contacts, _ = _arm_targets(pose, actor, objects)
    return Scene(
        actors=(actor,), objects=objects, body_contacts=body_contacts,
        contacts=tuple(
            Contact(
                actor_id="subject",
                anchor=_support_anchor(contact.body_part, pose.resting_side),
                object_id=contact.surface, face=faces[contact.surface],
            )
            for contact in pose.supports
        ),
    )


def _report_score(report: ValidationReport) -> tuple[int, int, float]:
    return (
        sum(issue.code in {"self_collision", "object_collision", "actor_collision"}
            for issue in report.issues),
        len(report.issues),
        sum(abs(issue.error_m or 0.0) for issue in report.issues),
    )


def _fit_arms(
    pose: NeutralPose, actor: ActorPose,
    objects: tuple[Box, ...], faces: dict[str, str],
) -> ActorPose:
    beam = [actor]
    sides: tuple[Literal["left", "right"], ...] = (
        ("right", "left") if pose.left_hand == "across_forearm" else ("left", "right")
    )
    for side in sides:
        placement = pose.left_hand if side == "left" else pose.right_hand
        if placement in {
            "at_side", "relaxed_in_front", "forward_gesture", "on_mat_forward"
        }:
            continue
        ranked: list[tuple[tuple[int, int, float], ActorPose]] = []
        for current in beam:
            targets, _, variables = _arm_targets(pose, current, objects)
            target = next(item for item in targets if item.anchor == f"{side}_palm")
            candidates = arm_seed_candidates(current, side, target, max_candidates=16)
            if not candidates:
                fitted = solve_actor(
                    current, (target,),
                    variable_names=tuple(n for n in variables if n.startswith(side)),
                    max_nfev=100,
                )
                candidates = (fitted.actor,)
            for candidate in candidates:
                report = validate_scene(
                    _scene_for_actor(pose, candidate, objects, faces)
                )
                if report.passed:
                    return candidate
                ranked.append((_report_score(report), candidate))
        ranked.sort(key=lambda item: item[0])
        beam = [item[1] for item in ranked[:_ARM_BEAM_WIDTH]]
    return min(
        beam,
        key=lambda candidate: _report_score(
            validate_scene(_scene_for_actor(pose, candidate, objects, faces))
        ),
    )


@lru_cache(maxsize=256)
def _canonical_geometry(
    pose: NeutralPose, body_scale: float,
) -> tuple[Scene, ValidationReport]:
    if body_scale != 1.0:
        reference, _ = _canonical_geometry(pose, 1.0)
        scaled = Scene(
            actors=tuple(
                _replace_actor(
                    actor, body=actor.body.scaled(body_scale),
                    root_position=tuple(v * body_scale for v in actor.root_position),
                )
                for actor in reference.actors
            ),
            objects=tuple(
                Box(
                    object_id=box.object_id,
                    center=tuple(v * body_scale for v in box.center),
                    size=tuple(v * body_scale for v in box.size), rotation=box.rotation,
                )
                for box in reference.objects
            ),
            contacts=reference.contacts, body_contacts=reference.body_contacts,
        )
        return scaled, reference_geometry_report(scaled)
    body = BodySpec().scaled(body_scale)
    actor = _ground_actor(pose, _initial_actor(pose, body))
    objects, faces = _environment(pose, actor)
    actor = _fit_arms(pose, actor, objects, faces)
    scene = _rotate_scene(
        _scene_for_actor(pose, actor, objects, faces), _YAW[pose.pelvis_facing]
    )
    report = reference_geometry_report(scene)
    return scene, report


def compile_reference_geometry(
    pose: NeutralPose,
    subject: ReferenceSubject,
    presentation: ReferencePresentation,
) -> Scene:
    """Resolve canonical surface IDs through the presentation's support mapping."""
    from .pose_reference import presentation_fits_pose

    if not presentation_fits_pose(presentation, pose):
        raise ValueError("support height, extent or orientation cannot fit the pose")
    scene, report = _canonical_geometry(pose, subject.body_scale)
    if not report.passed:
        raise ReferenceGeometryError(pose.pose_id, scene, report)
    return scene
