from __future__ import annotations

import math
import subprocess
import sys

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.spatial.transform import Rotation

from t2i_pose_geometry import (
    JOINT_LIMITS,
    VARIABLE_GROUPS,
    ActorPose,
    AnchorTarget,
    BodyContact,
    BodySpec,
    Box,
    Contact,
    JointAngles,
    JointRegion,
    Scene,
    Shape,
    Tolerances,
    expand_variable_names,
    face_frame,
    forward_kinematics,
    solve_actor,
    validate_scene,
)
from t2i_pose_geometry.collision import (
    Collider,
    ContactPoint,
    PairResult,
    localized_overlap_proven,
    query_pair,
    shallow_overlap_proven,
)
from t2i_pose_geometry.kinematics import capsule, matrix


def standing_scene() -> Scene:
    return Scene(
        actors=(ActorPose(actor_id="adult"),),
        objects=(Box(object_id="floor", center=(0, 0, -0.1), size=(3, 3, 0.2)),),
        contacts=tuple(
            Contact(actor_id="adult", anchor=f"{side}_sole", object_id="floor")
            for side in ("left", "right")
        ),
    )


def issue_pairs(scene: Scene, code: str) -> set[frozenset[str]]:
    return {
        frozenset(issue.parts[1:])
        for issue in validate_scene(scene).issues
        if issue.code == code
    }


def test_neutral_standing_has_solid_clearance_and_both_sole_contacts() -> None:
    scene = standing_scene()
    report = validate_scene(scene)
    assert report.passed, report
    skeleton = forward_kinematics(scene.actors[0])
    for side in ("left", "right"):
        sole = skeleton.anchors[f"{side}_sole"]
        assert sole.position[2] == pytest.approx(0, abs=1e-12)
        assert sole.normal == pytest.approx((0, 0, -1))
    assert {shape.kind for shape in skeleton.shapes} == {"capsule", "ellipsoid", "box"}


def test_neutral_body_volumes_form_one_connected_solid() -> None:
    shapes = forward_kinematics(ActorPose(actor_id="adult")).shapes
    reached = {shapes[0].shape_id}
    pending = list(shapes[1:])
    while pending:
        connected = [
            shape
            for shape in pending
            if any(
                other.shape_id in reached
                and query_pair(shape, other).distance_m <= Tolerances().penetration_m
                for other in shapes
            )
        ]
        assert connected, f"Disconnected body volumes: {[s.shape_id for s in pending]}"
        reached.update(shape.shape_id for shape in connected)
        pending = [shape for shape in pending if shape.shape_id not in reached]


@pytest.mark.parametrize("side,rotation", [("left", -90), ("right", 90)])
def test_side_lying_shoulder_envelope_and_floor_contact(
    side: str, rotation: float
) -> None:
    body = BodySpec()
    actor = ActorPose(
        actor_id="adult",
        body=body,
        root_position=(0, 0, body.upper_torso_half_width),
        root_rotation=(0, rotation, 0),
    )
    skeleton = forward_kinematics(actor)
    torso = next(s for s in skeleton.shapes if s.shape_id == "upper_torso")
    for shoulder in ("left_shoulder", "right_shoulder"):
        local = matrix(torso.rotation).T @ np.subtract(
            skeleton.joints[shoulder], torso.center
        )
        assert np.linalg.norm(local / torso.radii) < 1
    anchor = skeleton.anchors[f"{side}_side"]
    assert anchor.position[2] == pytest.approx(0, abs=1e-12)
    assert anchor.normal == pytest.approx((0, 0, -1), abs=1e-12)
    shoulder = next(
        shape for shape in skeleton.shapes if shape.shape_id == f"{side}_shoulder_joint"
    )
    assert Collider(shoulder).bounds()[0][2] == pytest.approx(0, abs=1e-12)
    report = validate_scene(
        Scene(
            actors=(actor,),
            objects=(Box(object_id="floor", center=(0, 0, -0.1), size=(4, 4, 0.2)),),
            contacts=(
                Contact(actor_id="adult", anchor=f"{side}_side", object_id="floor"),
            ),
        )
    )
    assert report.passed, report


@pytest.mark.parametrize("pitch", [-40, -20, 0, 25])
@pytest.mark.parametrize("yaw", [-35, 0, 40])
def test_back_anchor_is_upper_thorax_root_posterior_support_with_true_normal(
    pitch: float, yaw: float
) -> None:
    actor = ActorPose(
        actor_id="adult",
        root_rotation=(17, -22, 41),
        angles=JointAngles(torso_pitch=pitch, torso_yaw=yaw),
    )
    skeleton = forward_kinematics(actor)
    back = skeleton.anchors["back"]
    normal = matrix(actor.root_rotation) @ np.array([0, -1, 0])
    assert back.normal == pytest.approx(normal, abs=1e-12)
    assert back.shape_id == "upper_torso"
    posterior = float(np.asarray(back.position) @ normal)
    shape = next(shape for shape in skeleton.shapes if shape.shape_id == back.shape_id)
    maximum = float(np.asarray(shape.center) @ normal) + Collider(shape).extent(normal)
    assert posterior == pytest.approx(maximum, abs=1e-12)
    rotation = matrix(shape.rotation)
    local = rotation.T @ np.subtract(back.position, shape.center)
    gradient = rotation @ (local / np.square(shape.radii))
    gradient /= np.linalg.norm(gradient)
    assert back.normal == pytest.approx(gradient, abs=1e-12)


@pytest.mark.parametrize("torso_pitch,head_pitch", [(-20, 40), (-6, 10)])
def test_reclined_back_contact_on_vertical_wall_uses_root_frame_normal(
    torso_pitch: float, head_pitch: float
) -> None:
    actor = ActorPose(
        actor_id="adult",
        angles=JointAngles(torso_pitch=torso_pitch, head_pitch=head_pitch),
    )
    back = forward_kinematics(actor).anchors["back"]
    wall = Box(
        object_id="wall",
        center=(0, back.position[1] - 0.05, 1),
        size=(2, 0.1, 2),
    )
    report = validate_scene(
        Scene(
            actors=(actor,),
            objects=(wall,),
            contacts=(
                Contact(
                    actor_id="adult",
                    anchor="back",
                    object_id="wall",
                    face="front",
                ),
            ),
        )
    )
    assert report.passed, report


@pytest.mark.parametrize("side", ["left", "right"])
def test_forearm_back_is_opposite_capsule_surface_at_same_segment_midpoint(
    side: str,
) -> None:
    actor = ActorPose(
        actor_id="adult",
        root_rotation=(20, -30, 40),
        angles=JointAngles(
            **{
                f"{side}_shoulder_flex": 60,
                f"{side}_shoulder_abduction": 20,
                f"{side}_shoulder_rotation": 40,
                f"{side}_elbow_flex": 75,
            }
        ),
    )
    skeleton = forward_kinematics(actor)
    front = skeleton.anchors[f"{side}_forearm"]
    back = skeleton.anchors[f"{side}_forearm_back"]
    midpoint = (
        np.asarray(skeleton.joints[f"{side}_elbow"]) + skeleton.joints[f"{side}_wrist"]
    ) / 2
    assert front.shape_id == back.shape_id == f"{side}_forearm"
    assert back.normal == pytest.approx(-np.asarray(front.normal), abs=1e-12)
    assert back.position == pytest.approx(
        midpoint - actor.body.forearm_radius * np.asarray(front.normal), abs=1e-12
    )
    assert (np.asarray(front.position) + back.position) / 2 == pytest.approx(
        midpoint, abs=1e-12
    )


def test_upper_back_contact_does_not_exempt_lower_torso_wall_penetration() -> None:
    actor = ActorPose(actor_id="adult", angles=JointAngles(torso_pitch=25))
    back = forward_kinematics(actor).anchors["back"]
    report = validate_scene(
        Scene(
            actors=(actor,),
            objects=(
                Box(
                    object_id="wall",
                    center=(0, back.position[1] - 0.05, 1),
                    size=(2, 0.1, 2),
                ),
            ),
            contacts=(
                Contact(
                    actor_id="adult",
                    anchor="back",
                    object_id="wall",
                    face="front",
                ),
            ),
        )
    )
    assert not report.passed
    assert not any(issue.code.startswith("contact_") for issue in report.issues)
    assert any(
        issue.code == "object_collision" and issue.parts == ("adult", "torso", "wall")
        for issue in report.issues
    )


@pytest.mark.parametrize("gap", [0.02, 0.0, -0.03])
@pytest.mark.parametrize("reverse", [False, True])
def test_rotated_capsule_box_analytic_gap(gap: float, reverse: bool) -> None:
    rotation = Rotation.from_euler("xyz", [27, -19, 41], degrees=True)
    transform = rotation.as_matrix()
    offset = np.array([1.2, -0.7, 0.5])
    start = transform @ np.array([-0.4, 0, 0.6 + gap]) + offset
    end = transform @ np.array([0.4, 0, 0.6 + gap]) + offset
    tube = capsule("tube", tuple(start), tuple(end), 0.1)
    box = Box(
        object_id="slab",
        center=tuple(offset),
        size=(2, 2, 1),
        rotation=(27, -19, 41),
    )
    first, second = (box, tube) if reverse else (tube, box)
    result = query_pair(first, second)
    if gap > 0:
        assert not result.colliding
        assert result.distance_m == pytest.approx(gap, abs=2e-6)
    elif gap < 0:
        assert result.colliding
        assert result.penetration_m == pytest.approx(-gap, abs=2e-6)
        assert not shallow_overlap_proven(Collider(tube), Collider(box), 1e-5, result)
    else:
        assert result.distance_m == pytest.approx(0, abs=2e-6)
        assert shallow_overlap_proven(Collider(tube), Collider(box), 1e-5, result)


@pytest.mark.parametrize("length", [0.0, 1e-12, 1e-8])
@pytest.mark.parametrize("gap", [0.002, 0.0, -0.002])
@pytest.mark.parametrize("reverse", [False, True])
def test_rotated_near_spherical_capsule_against_box(
    length: float, gap: float, reverse: bool
) -> None:
    rotation = Rotation.from_euler("xyz", [31, -14, 57], degrees=True)
    offset = np.array([-0.3, 0.9, 0.2])
    tube = capsule(
        "near_sphere",
        tuple(rotation.apply((-length / 2, 0, 0.6 + gap)) + offset),
        tuple(rotation.apply((length / 2, 0, 0.6 + gap)) + offset),
        0.1,
    )
    box = Box(
        object_id="slab",
        center=tuple(offset),
        size=(2, 2, 1),
        rotation=(31, -14, 57),
    )
    first, second = (box, tube) if reverse else (tube, box)
    result = query_pair(first, second)
    assert math.isfinite(result.distance_m)
    if gap > 0:
        assert not result.colliding
        assert result.distance_m == pytest.approx(gap, abs=2e-6)
    elif gap < 0:
        assert result.colliding
        assert result.penetration_m == pytest.approx(-gap, abs=2e-6)
        assert not shallow_overlap_proven(
            Collider(first), Collider(second), 1e-5, result
        )
    else:
        assert result.distance_m <= 2e-6
        assert shallow_overlap_proven(Collider(first), Collider(second), 1e-5, result)


def test_unsigned_distance_sentinel_is_never_a_penetration_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = capsule("capsule", (0, 0, 0), (0, 0, 0.3), 0.04)
    second = Box(object_id="box", center=(2, 0, 0), size=(1, 1, 1))
    monkeypatch.setattr("t2i_pose_geometry.collision.fcl.distance", lambda *_: -1.0)
    result = query_pair(first, second)
    assert result.colliding
    assert result.distance_m == 0
    assert result.penetration_m is None
    assert not result.contacts


def test_rotated_ellipsoid_uses_solid_support_not_centerline() -> None:
    rotation = matrix((35, 20, 15))
    radii = (0.09, 0.13, 0.24)
    extent = np.linalg.norm(np.asarray(radii) * rotation.T[:, 2])
    shape = Shape(
        shape_id="body",
        kind="ellipsoid",
        center=(0, 0, 0.5 + extent - 0.01),
        rotation=(35, 20, 15),
        radii=radii,
    )
    box = Box(object_id="slab", center=(0, 0, 0), size=(2, 2, 1))
    result = query_pair(shape, box)
    assert result.colliding
    assert result.penetration_m == pytest.approx(0.01, abs=2e-5)


def test_one_shallow_fcl_contact_cannot_certify_deep_overlap() -> None:
    a = Collider(Box(object_id="a", center=(0, 0, 0), size=(1, 1, 1)))
    b = Collider(Box(object_id="b", center=(0, 0, 0.5), size=(1, 1, 1)))
    incomplete = PairResult(
        colliding=True,
        distance_m=0,
        penetration_m=0,
        contacts=(ContactPoint((0, 0, 0), (0, 0, 1), 0),),
    )
    assert not shallow_overlap_proven(a, b, 0.001, incomplete)


@pytest.mark.parametrize("elbow", [15, 65, 100])
def test_local_joint_overlap_does_not_reject_ordinary_elbow_bend(elbow: float) -> None:
    actor = ActorPose(actor_id="adult", angles=JointAngles(left_elbow_flex=elbow))
    report = validate_scene(Scene(actors=(actor,)))
    assert report.passed, report


def test_adjacent_limb_overlap_outside_joint_region_is_not_whitelisted() -> None:
    actor = ActorPose(actor_id="adult", angles=JointAngles(left_elbow_flex=150))
    pairs = issue_pairs(Scene(actors=(actor,)), "self_collision")
    assert frozenset(("left_upper_arm", "left_forearm")) in pairs


def test_nonadjacent_self_penetration_is_rejected() -> None:
    actor = ActorPose(actor_id="adult", angles=JointAngles(left_shoulder_abduction=-30))
    pairs = issue_pairs(Scene(actors=(actor,)), "self_collision")
    assert frozenset(("torso", "left_upper_arm")) in pairs


def test_joint_region_proof_cannot_hide_distant_crossing_capsules() -> None:
    first = capsule("a", (0, 0, 0), (1, 0, 0), 0.03)
    second = capsule("b", (0.8, -0.5, 0), (0.8, 0.5, 0), 0.03)
    region = JointRegion(
        joint="joint", center=(0, 0, 0), radius=0.15, shapes=("a", "b")
    )
    assert query_pair(first, second).colliding
    assert not localized_overlap_proven(Collider(first), Collider(second), (region,))


def test_joint_region_proves_covered_capsule_overlap_and_fails_closed_at_budget() -> (
    None
):
    first = capsule("a", (0, 0, 0), (0.4, 0, 0), 0.04)
    second = capsule("b", (0, 0, 0), (0, 0.4, 0), 0.04)
    region = JointRegion(joint="j", center=(0, 0, 0), radius=0.15, shapes=("a", "b"))
    assert localized_overlap_proven(Collider(first), Collider(second), (region,))
    narrow = region.model_copy(update={"radius": 0.041})
    assert not localized_overlap_proven(
        Collider(first), Collider(second), (narrow,), max_depth=0
    )


def test_forearm_through_table_rejected_despite_exact_declared_palm_contact() -> None:
    actor = ActorPose(actor_id="adult", root_rotation=(-90, 0, 0))
    skeleton = forward_kinematics(actor)
    palm = skeleton.anchors["left_palm"]
    table = Box(
        object_id="table",
        center=(palm.position[0], palm.position[1] + 0.18, palm.position[2] - 0.02),
        size=(0.18, 0.56, 0.04),
    )
    scene = Scene(
        actors=(actor,),
        objects=(table,),
        contacts=(Contact(actor_id="adult", anchor="left_palm", object_id="table"),),
    )
    report = validate_scene(scene)
    assert not report.passed
    assert not any(issue.code.startswith("contact_") for issue in report.issues)
    assert any(
        issue.code == "object_collision"
        and issue.parts == ("adult", "left_forearm", "table")
        and issue.penetration_m > 0.005
        for issue in report.issues
    )


def test_sole_contact_never_exempts_foot_from_penetrating_floor() -> None:
    scene = standing_scene()
    actor = scene.actors[0].model_copy(update={"root_position": (0, 0, 0.885)})
    report = validate_scene(scene.model_copy(update={"actors": (actor,)}))
    assert any(
        issue.code == "object_collision" and "left_foot" in issue.parts
        for issue in report.issues
    )
    assert any(issue.code == "contact_distance" for issue in report.issues)


def test_contact_normal_mismatch_is_rejected_at_exact_surface_position() -> None:
    actor = ActorPose(actor_id="adult")
    palm = forward_kinematics(actor).anchors["left_palm"]
    wrong_face = Box(
        object_id="panel",
        center=(palm.position[0], palm.position[1] - 0.005, palm.position[2]),
        size=(0.01, 0.01, 0.01),
    )
    report = validate_scene(
        Scene(
            actors=(actor,),
            objects=(wrong_face,),
            contacts=(
                Contact(
                    actor_id="adult",
                    anchor="left_palm",
                    object_id="panel",
                    face="front",
                ),
            ),
        )
    )
    assert any(issue.code == "contact_normal" for issue in report.issues)
    assert not any(issue.code == "contact_distance" for issue in report.issues)


def test_contact_is_on_bounded_face_not_infinite_plane() -> None:
    scene = standing_scene()
    floor = scene.objects[0].model_copy(update={"center": (5, 0, -0.1)})
    report = validate_scene(scene.model_copy(update={"objects": (floor,)}))
    errors = [i for i in report.issues if i.code == "contact_distance"]
    assert errors and all(i.error_m > 3 for i in errors)


@pytest.mark.parametrize("angle", [-1, 151])
def test_knee_limit_violation_is_independent_of_collision(angle: float) -> None:
    actor = ActorPose(actor_id="adult", angles=JointAngles(left_knee_flex=angle))
    report = validate_scene(Scene(actors=(actor,)))
    assert not report.passed
    assert any(
        i.code == "joint_limit" and i.parts == ("adult", "left_knee_flex")
        for i in report.issues
    )


def test_interactor_overlap_and_separation() -> None:
    first = ActorPose(actor_id="first")
    second = ActorPose(actor_id="second", root_position=(0.05, 0, 0.895))
    report = validate_scene(Scene(actors=(first, second)))
    assert any(
        i.code == "inter_actor_collision"
        and i.parts == ("first", "torso", "second", "torso")
        for i in report.issues
    )
    second = second.model_copy(update={"root_position": (1, 0, 0.895)})
    assert validate_scene(Scene(actors=(first, second))).passed


def test_projected_body_overlap_does_not_imply_solid_collision() -> None:
    first = ActorPose(actor_id="first")
    second = ActorPose(actor_id="second", root_position=(0, 1, 0.895))
    first_joints = forward_kinematics(first).joints
    second_joints = forward_kinematics(second).joints
    for joint, position in first_joints.items():
        other = second_joints[joint]
        assert (position[0], position[2]) == (other[0], other[2])

    assert validate_scene(Scene(actors=(first, second))).passed


def back_contact_scene() -> Scene:
    return Scene(
        actors=(
            ActorPose(actor_id="first"),
            ActorPose(
                actor_id="second",
                root_position=(0, -0.21, 0.895),
                root_rotation=(0, 0, 180),
            ),
        ),
        body_contacts=(
            BodyContact(
                actor_id="first",
                anchor="back",
                target_actor_id="second",
                target_anchor="back",
            ),
        ),
    )


def test_independent_body_contact_passes_and_roundtrips() -> None:
    scene = back_contact_scene()
    assert Scene.model_validate_json(scene.model_dump_json()) == scene
    report = validate_scene(scene)
    assert report.passed, report


def test_body_contact_never_exempts_shallow_interactor_penetration() -> None:
    scene = back_contact_scene()
    overlapping = scene.actors[1].model_copy(
        update={"root_position": (0, -0.209, 0.895)}
    )
    report = validate_scene(
        scene.model_copy(update={"actors": (scene.actors[0], overlapping)})
    )
    assert not report.passed
    assert not any(issue.code.startswith("body_contact_") for issue in report.issues)
    assert any(
        issue.code == "inter_actor_collision" and "torso" in issue.parts
        for issue in report.issues
    )


def test_body_contact_recomputes_anchor_positions_after_actor_changes() -> None:
    scene = back_contact_scene()
    moved = scene.actors[1].model_copy(update={"root_position": (0, -0.25, 0.895)})
    report = validate_scene(
        scene.model_copy(update={"actors": (scene.actors[0], moved)})
    )
    errors = [issue for issue in report.issues if issue.code == "body_contact_distance"]
    assert len(errors) == 1
    assert errors[0].error_m == pytest.approx(0.04)


def test_body_contact_requires_opposing_normals_even_at_identical_position() -> None:
    actor = ActorPose(actor_id="adult")
    report = validate_scene(
        Scene(
            actors=(actor,),
            body_contacts=(
                BodyContact(
                    actor_id="adult",
                    anchor="left_knee",
                    target_actor_id="adult",
                    target_anchor="left_knee_top",
                ),
            ),
        )
    )
    assert not report.passed
    assert any(issue.code == "body_contact_normal" for issue in report.issues)
    assert not any(issue.code == "body_contact_distance" for issue in report.issues)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"actor_id": "missing"}, "unknown_actor"),
        ({"target_actor_id": "missing"}, "unknown_actor"),
        ({"anchor": "missing"}, "unknown_anchor"),
        ({"target_anchor": "missing"}, "unknown_anchor"),
    ],
)
def test_unknown_body_contact_endpoints_fail_explicitly(
    changes: dict[str, str], code: str
) -> None:
    scene = back_contact_scene()
    contact = scene.body_contacts[0].model_copy(update=changes)
    report = validate_scene(scene.model_copy(update={"body_contacts": (contact,)}))
    assert not report.passed
    assert any(issue.code == code for issue in report.issues)


def test_seated_lap_knee_and_forearm_anchors_face_upward() -> None:
    actor = ActorPose(
        actor_id="adult",
        angles=JointAngles(
            left_hip_flex=90,
            left_knee_flex=90,
            right_hip_flex=90,
            right_knee_flex=90,
            left_elbow_flex=90,
            right_elbow_flex=90,
        ),
    )
    skeleton = forward_kinematics(actor)
    for side in ("left", "right"):
        for surface in ("lap", "knee_top", "forearm"):
            anchor = skeleton.anchors[f"{side}_{surface}"]
            assert anchor.normal == pytest.approx((0, 0, 1), abs=1e-12)
        lap = skeleton.anchors[f"{side}_lap"]
        hip = skeleton.joints[f"{side}_hip"]
        assert lap.position[1] - hip[1] == pytest.approx(0.35 * actor.body.thigh_length)
        assert lap.position[2] - hip[2] == pytest.approx(actor.body.thigh_radius)


def test_own_lap_palm_ik_is_independently_validated_without_collision_exemptions() -> (
    None
):
    actor = ActorPose(
        actor_id="adult",
        angles=JointAngles(
            left_hip_flex=90,
            left_knee_flex=90,
            right_hip_flex=90,
            right_knee_flex=90,
            left_shoulder_flex=20,
            left_shoulder_abduction=10,
            left_shoulder_rotation=60,
            left_elbow_flex=90,
            left_wrist_rotation=150,
        ),
    )
    lap = forward_kinematics(actor).anchors["left_lap"]
    result = solve_actor(
        actor,
        (
            AnchorTarget(
                anchor="left_palm",
                position=lap.position,
                normal=tuple(-value for value in lap.normal),
            ),
        ),
        ("left_shoulder", "left_elbow", "left_wrist"),
        max_nfev=100,
    )
    assert result.converged, result
    report = validate_scene(
        Scene(
            actors=(result.actor,),
            body_contacts=(
                BodyContact(
                    actor_id="adult",
                    anchor="left_palm",
                    target_actor_id="adult",
                    target_anchor="left_lap",
                ),
            ),
        )
    )
    assert report.passed, report
    assert_lengths(result.actor)


def test_rigid_scene_rotation_preserves_contacts_and_clearance() -> None:
    scene = standing_scene()
    rotation = Rotation.from_euler("xyz", (32, -17, 49), degrees=True)
    translation = np.array([2.0, -1.0, 0.4])
    actor = scene.actors[0]
    transformed_actor = actor.model_copy(
        update={
            "root_position": tuple(rotation.apply(actor.root_position) + translation),
            "root_rotation": tuple(rotation.as_euler("xyz", degrees=True)),
        }
    )
    floor = scene.objects[0]
    transformed_floor = floor.model_copy(
        update={
            "center": tuple(rotation.apply(floor.center) + translation),
            "rotation": tuple(rotation.as_euler("xyz", degrees=True)),
        }
    )
    report = validate_scene(
        scene.model_copy(
            update={"actors": (transformed_actor,), "objects": (transformed_floor,)}
        )
    )
    assert report.passed, report


def assert_lengths(actor: ActorPose) -> None:
    skeleton = forward_kinematics(actor)
    for side in ("left", "right"):
        for first, second, length in (
            ("shoulder", "elbow", actor.body.upper_arm_length),
            ("elbow", "wrist", actor.body.forearm_length),
            ("hip", "knee", actor.body.thigh_length),
            ("knee", "ankle", actor.body.shin_length),
        ):
            delta = np.subtract(
                skeleton.joints[f"{side}_{first}"],
                skeleton.joints[f"{side}_{second}"],
            )
            assert np.linalg.norm(delta) == pytest.approx(length, abs=2e-12)
    assert np.linalg.norm(
        np.subtract(skeleton.joints["shoulder_center"], skeleton.joints["root"])
    ) == pytest.approx(actor.body.torso_length, abs=2e-12)


def test_fixed_bone_lengths_under_arbitrary_rotations_and_scaling() -> None:
    rng = np.random.default_rng(614)
    for _ in range(15):
        actor = ActorPose(
            actor_id="adult",
            body=BodySpec().scaled(float(rng.uniform(0.8, 1.2))),
            root_position=tuple(rng.uniform(-2, 2, size=3)),
            root_rotation=tuple(rng.uniform(-180, 180, size=3)),
            angles=JointAngles(
                **{
                    name: rng.uniform(lower, upper)
                    for name, (lower, upper) in JOINT_LIMITS.items()
                }
            ),
        )
        assert_lengths(actor)
        assert all(
            np.linalg.norm(anchor.normal) == pytest.approx(1)
            for anchor in forward_kinematics(actor).anchors.values()
        )


def test_shape_free_fk_has_identical_joints_and_anchors_across_transforms() -> None:
    rng = np.random.default_rng(8034)
    for _ in range(25):
        actor = ActorPose(
            actor_id="adult",
            body=BodySpec().scaled(float(rng.uniform(0.8, 1.2))),
            root_position=tuple(rng.uniform(-2, 2, size=3)),
            root_rotation=tuple(rng.uniform(-180, 180, size=3)),
            angles=JointAngles(
                **{
                    name: rng.uniform(lower, upper)
                    for name, (lower, upper) in JOINT_LIMITS.items()
                }
            ),
        )
        full = forward_kinematics(actor)
        fast = forward_kinematics(actor, include_shapes=False)
        assert fast.joints == full.joints
        assert fast.anchors == full.anchors
        assert not fast.shapes and not fast.joint_regions
        assert full.shapes and full.joint_regions


def test_ik_fast_path_never_constructs_collision_models_or_converts_to_euler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = ActorPose(actor_id="adult")
    target = AnchorTarget(
        anchor="left_sole", position=(-actor.body.hip_half_width, 0.2, 0.1)
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Collision-only work ran during shape-free IK")

    for name in ("Shape", "JointRegion", "capsule", "euler"):
        monkeypatch.setattr(f"t2i_pose_geometry.kinematics.{name}", forbidden)
    skeleton = forward_kinematics(actor, include_shapes=False)
    assert skeleton.anchors["left_sole"].position[2] == pytest.approx(0)
    result = solve_actor(actor, (target,), ("root_position",), max_nfev=30)
    assert result.converged, result
    assert result.actor.angles == actor.angles


def test_shape_free_fk_still_revalidates_unchecked_actor_parameters() -> None:
    invalid_body = BodySpec().model_copy(update={"shin_length": math.nan})
    actor = ActorPose(actor_id="adult").model_copy(update={"body": invalid_body})
    with pytest.raises(ValidationError):
        forward_kinematics(actor, include_shapes=False)


def test_scene_validation_always_rebuilds_full_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def checked_fk(actor):
        skeleton = forward_kinematics(actor)
        assert skeleton.shapes and skeleton.joint_regions
        calls.append(actor.actor_id)
        return skeleton

    monkeypatch.setattr("t2i_pose_geometry.validation.forward_kinematics", checked_fk)
    report = validate_scene(standing_scene())
    assert report.passed, report
    assert calls == ["adult"]


def test_flexion_and_bilateral_abduction_conventions() -> None:
    actor = ActorPose(
        actor_id="adult",
        angles=JointAngles(
            left_hip_flex=30,
            right_hip_flex=30,
            left_shoulder_flex=20,
            right_shoulder_flex=20,
            left_hip_abduction=15,
            right_hip_abduction=15,
            left_knee_flex=60,
            right_knee_flex=60,
            left_elbow_flex=30,
            right_elbow_flex=30,
        ),
    )
    joints = forward_kinematics(actor).joints
    for side, sign in (("left", -1), ("right", 1)):
        assert joints[f"{side}_knee"][1] > joints[f"{side}_hip"][1]
        assert sign * (joints[f"{side}_knee"][0] - joints[f"{side}_hip"][0]) > 0
        assert joints[f"{side}_ankle"][1] < joints[f"{side}_knee"][1]
        assert joints[f"{side}_wrist"][1] > joints[f"{side}_elbow"][1]


def test_ankle_dorsiflexion_and_wrist_flexion_conventions() -> None:
    neutral = ActorPose(actor_id="adult")
    flexed = neutral.model_copy(
        update={"angles": JointAngles(left_ankle_flex=25, left_wrist_flex=30)}
    )
    before, after = forward_kinematics(neutral), forward_kinematics(flexed)
    assert (
        after.anchors["left_instep"].position[2]
        > before.anchors["left_instep"].position[2]
    )
    assert (
        after.anchors["left_palm"].position[1] > before.anchors["left_palm"].position[1]
    )


@pytest.mark.parametrize("side", ["left", "right"])
def test_toe_anchor_is_exact_foot_front_face_with_rotated_outward_normal(
    side: str,
) -> None:
    actor = ActorPose(
        actor_id="adult",
        root_rotation=(15, -30, 45),
        angles=JointAngles(**{f"{side}_knee_flex": 107, f"{side}_ankle_flex": 17}),
    )
    skeleton = forward_kinematics(actor)
    foot = next(shape for shape in skeleton.shapes if shape.shape_id == f"{side}_foot")
    toe = skeleton.anchors[f"{side}_toes"]
    rotation = matrix(foot.rotation)
    expected_normal = rotation @ np.array([0, 1, 0])
    expected_position = (
        np.asarray(foot.center) + expected_normal * actor.body.foot_length / 2
    )
    assert toe.shape_id == foot.shape_id
    assert toe.normal == pytest.approx(expected_normal, abs=1e-12)
    assert toe.position == pytest.approx(expected_position, abs=1e-12)


@pytest.mark.parametrize("side", ["left", "right"])
def test_knee_ground_is_root_down_sphere_surface_independent_of_shin(
    side: str,
) -> None:
    actor = ActorPose(
        actor_id="adult",
        root_rotation=(15, -30, 45),
        angles=JointAngles(**{f"{side}_hip_flex": 25, f"{side}_knee_flex": 107}),
    )
    skeleton = forward_kinematics(actor)
    anchor = skeleton.anchors[f"{side}_knee_ground"]
    normal = matrix(actor.root_rotation) @ np.array([0, 0, -1])
    center = np.asarray(skeleton.joints[f"{side}_knee"])
    assert anchor.normal == pytest.approx(normal, abs=1e-12)
    assert anchor.position == pytest.approx(
        center + normal * actor.body.knee_radius, abs=1e-12
    )
    assert anchor.shape_id == f"{side}_knee_joint"
    assert np.linalg.norm(np.asarray(anchor.position) - center) == pytest.approx(
        actor.body.knee_radius, abs=1e-12
    )
    assert not np.allclose(anchor.normal, skeleton.anchors[f"{side}_knee"].normal)


def test_knee_ground_and_vertical_toes_contact_mat_without_relaxing_limits() -> None:
    body = BodySpec()
    knee_angle = math.degrees(
        math.acos(-(0.75 * body.foot_length - body.knee_radius) / body.shin_length)
    )
    actor = ActorPose(
        actor_id="adult",
        root_position=(0, 0, body.thigh_length + body.knee_radius),
        angles=JointAngles(
            left_knee_flex=knee_angle,
            right_knee_flex=knee_angle,
            left_ankle_flex=knee_angle - 90,
            right_ankle_flex=knee_angle - 90,
        ),
    )
    skeleton = forward_kinematics(actor)
    for side in ("left", "right"):
        for site in ("knee_ground", "toes"):
            anchor = skeleton.anchors[f"{side}_{site}"]
            assert anchor.position[2] == pytest.approx(0, abs=1e-12)
            assert anchor.normal == pytest.approx((0, 0, -1), abs=1e-12)
    scene = Scene(
        actors=(actor,),
        objects=(Box(object_id="mat", center=(0, 0, -0.025), size=(3, 3, 0.05)),),
        contacts=tuple(
            Contact(actor_id="adult", anchor=f"{side}_{site}", object_id="mat")
            for side in ("left", "right")
            for site in ("knee_ground", "toes")
        ),
    )
    report = validate_scene(scene)
    assert report.passed, report


@pytest.mark.parametrize(
    "variables",
    [
        ("left_shoulder_flex", "left_elbow_flex", "left_wrist_flex"),
        ("left_shoulder.flex", "left_elbow.flex", "left_wrist.flex"),
    ],
)
def test_reachable_bounded_ik_preserves_bones_and_fits_normals(
    variables: tuple[str, ...],
) -> None:
    desired = ActorPose(
        actor_id="adult",
        angles=JointAngles(
            left_shoulder_flex=40, left_elbow_flex=55, left_wrist_flex=25
        ),
    )
    palm = forward_kinematics(desired).anchors["left_palm"]
    initial = ActorPose(
        actor_id="adult",
        angles=JointAngles(left_shoulder_flex=20, left_elbow_flex=25),
    )
    result = solve_actor(
        initial,
        (AnchorTarget(anchor="left_palm", position=palm.position, normal=palm.normal),),
        variables,
        max_nfev=100,
    )
    assert result.converged, result
    assert result.errors[0].error_m < 1e-5
    assert result.errors[0].normal_error_degrees < 1e-3
    assert result.nfev <= 100
    assert_lengths(result.actor)
    assert result.actor.body == initial.body
    assert result.actor.root_position == initial.root_position


def test_unreachable_ik_remains_explicit_and_bounded() -> None:
    result = solve_actor(
        ActorPose(actor_id="adult"),
        (AnchorTarget(anchor="left_palm", position=(-0.2, 20, 1)),),
        ("left_shoulder_flex", "left_elbow_flex"),
        max_nfev=20,
    )
    assert not result.converged
    assert result.errors[0].error_m > 18
    assert result.nfev <= 20
    assert_lengths(result.actor)
    for name in ("left_shoulder_flex", "left_elbow_flex"):
        assert (
            JOINT_LIMITS[name][0]
            <= getattr(result.actor.angles, name)
            <= JOINT_LIMITS[name][1]
        )


@pytest.mark.parametrize(
    "variables",
    [
        ("root_x", "root_y", "root_z"),
        ("root_position",),
        ("root_position.x", "root_position.y", "root_position.z"),
    ],
)
def test_root_only_ik_and_no_variable_normal_failure(
    variables: tuple[str, ...],
) -> None:
    actor = ActorPose(actor_id="adult")
    sole = forward_kinematics(actor).anchors["left_sole"]
    target = tuple(np.asarray(sole.position) + (0.2, 0.1, 0.3))
    result = solve_actor(
        actor,
        (AnchorTarget(anchor="left_sole", position=target),),
        variables,
    )
    assert result.converged
    assert result.actor.root_position == pytest.approx((0.2, 0.1, 1.195))
    assert result.actor.angles == actor.angles
    failed = solve_actor(
        actor,
        (AnchorTarget(anchor="left_sole", position=sole.position, normal=(0, 0, 1)),),
        (),
    )
    assert not failed.converged
    assert failed.errors[0].error_m == 0
    assert failed.errors[0].normal_error_degrees == 180


def test_ik_success_is_not_a_geometry_certificate() -> None:
    actor = ActorPose(actor_id="adult", angles=JointAngles(left_shoulder_abduction=-30))
    palm = forward_kinematics(actor).anchors["left_palm"]
    result = solve_actor(
        actor, (AnchorTarget(anchor="left_palm", position=palm.position),), ()
    )
    assert result.converged
    assert not validate_scene(Scene(actors=(result.actor,))).passed


@pytest.mark.parametrize(
    ("actor_id", "anchor", "object_id", "code"),
    [
        ("missing", "left_sole", "floor", "unknown_actor"),
        ("adult", "missing", "floor", "unknown_anchor"),
        ("adult", "left_sole", "missing", "unknown_object"),
    ],
)
def test_unknown_contact_targets_fail_explicitly(
    actor_id: str, anchor: str, object_id: str, code: str
) -> None:
    scene = standing_scene().model_copy(
        update={
            "contacts": (
                Contact(actor_id=actor_id, anchor=anchor, object_id=object_id),
            )
        }
    )
    report = validate_scene(scene)
    assert not report.passed
    assert any(issue.code == code for issue in report.issues)


@pytest.mark.parametrize(
    "variable",
    [
        "independent_knee_x",
        "left_knee.translation_x",
        "root_roll",
        "head.rotation",
        "left.shoulder_flex",
        "root.x",
    ],
)
def test_unknown_ik_variables_cannot_move_independent_joints(variable: str) -> None:
    with pytest.raises(ValueError, match="Unknown IK variables"):
        solve_actor(
            ActorPose(actor_id="adult"),
            (AnchorTarget(anchor="left_palm", position=(0, 0, 1)),),
            (variable,),
        )


def test_unknown_ik_anchor_and_unbounded_budgets_fail() -> None:
    actor = ActorPose(actor_id="adult")
    with pytest.raises(ValueError, match="Unknown anchors"):
        solve_actor(actor, (AnchorTarget(anchor="imaginary", position=(0, 0, 0)),))
    target = AnchorTarget(anchor="left_palm", position=(0, 0, 1))
    for budget in (0, 2001, 1.5, True):
        with pytest.raises(ValueError, match="max_nfev"):
            solve_actor(actor, (target,), max_nfev=budget)
    with pytest.raises(ValueError, match="root_translation_bound_m"):
        solve_actor(actor, (target,), root_translation_bound_m=math.inf)


def test_ik_groups_are_explicit_immutable_and_expand_in_requested_order() -> None:
    assert VARIABLE_GROUPS["left_shoulder"] == (
        "left_shoulder_flex",
        "left_shoulder_abduction",
        "left_shoulder_rotation",
    )
    assert VARIABLE_GROUPS["right_knee"] == ("right_knee_flex",)
    assert expand_variable_names(
        ("right_knee", "left_shoulder", "torso.pitch", "root_rotation.z")
    ) == (
        "right_knee_flex",
        "left_shoulder_flex",
        "left_shoulder_abduction",
        "left_shoulder_rotation",
        "torso_pitch",
        "root_rotation_z",
    )
    with pytest.raises(TypeError):
        VARIABLE_GROUPS["left_shoulder"] = ()


@pytest.mark.parametrize(
    "variables",
    [
        ("left_shoulder", "left_shoulder.flex"),
        ("root_position", "root_z"),
        ("left_elbow", "left_elbow"),
    ],
)
def test_overlapping_ik_variable_selections_fail_explicitly(
    variables: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="Duplicate IK variable"):
        solve_actor(
            ActorPose(actor_id="adult"),
            (AnchorTarget(anchor="left_palm", position=(0, 0, 1)),),
            variables,
        )


def test_root_rotation_group_fits_rigid_anchor_transform() -> None:
    actor = ActorPose(actor_id="adult")
    desired = actor.model_copy(update={"root_rotation": (10, -15, 20)})
    skeleton = forward_kinematics(desired)
    targets = tuple(
        AnchorTarget(
            anchor=f"{side}_sole",
            position=skeleton.anchors[f"{side}_sole"].position,
            normal=skeleton.anchors[f"{side}_sole"].normal,
        )
        for side in ("left", "right")
    )
    result = solve_actor(actor, targets, ("root_rotation",), max_nfev=100)
    assert result.converged, result
    assert result.actor.root_rotation == pytest.approx((10, -15, 20), abs=1e-5)
    assert result.actor.root_position == actor.root_position
    assert result.actor.angles == actor.angles
    assert_lengths(result.actor)


def test_finite_frozen_models_dimensions_and_roundtrip() -> None:
    scene = standing_scene()
    assert Scene.model_validate_json(scene.model_dump_json()) == scene
    assert BodySpec().scaled(1.2).upper_arm_length == pytest.approx(0.36)
    with pytest.raises(ValidationError):
        scene.actors[0].root_position = (1, 2, 3)
    with pytest.raises(TypeError):
        forward_kinematics(scene.actors[0]).joints["left_knee"] = (0, 0, 0)
    for value in (math.inf, -math.inf, math.nan, 0, -1):
        with pytest.raises(ValidationError):
            BodySpec(thigh_length=value)
    with pytest.raises(ValidationError, match="twice"):
        BodySpec(thigh_length=0.1)
    with pytest.raises(ValidationError):
        JointAngles(left_knee_flex=math.nan)
    with pytest.raises(ValidationError):
        ActorPose(actor_id="adult", root_rotation=(0, math.inf, 0))
    with pytest.raises(ValidationError):
        Box(object_id="box", center=(0, 0, 0), size=(0, 1, 1))
    with pytest.raises(ValidationError):
        AnchorTarget(anchor="left_sole", position=(0, 0, 0), normal=(0, 0, 2))
    for factor in (0, -1, math.inf, math.nan):
        with pytest.raises(ValueError):
            BodySpec().scaled(factor)


def test_unchecked_model_copy_is_revalidated_and_shapes_cannot_be_injected() -> None:
    scene = standing_scene()
    body = BodySpec().model_copy(update={"thigh_length": math.nan})
    actor = scene.actors[0].model_copy(update={"body": body})
    report = validate_scene(scene.model_copy(update={"actors": (actor,)}))
    assert not report.passed
    assert report.issues[0].code == "invalid_model"
    payload = scene.model_dump()
    payload["actors"][0]["shapes"] = []
    with pytest.raises(ValidationError):
        Scene.model_validate(payload)


@pytest.mark.parametrize(
    "tolerance",
    [
        {"contact_m": 0.0021},
        {"penetration_m": 0.0011},
        {"normal_degrees": 5.1},
        {"contact_m": math.nan},
    ],
)
def test_validation_tolerances_are_small_and_bounded(tolerance: dict) -> None:
    with pytest.raises(ValidationError):
        Tolerances(**tolerance)


def test_all_anchors_are_on_their_named_solid_surfaces() -> None:
    actor = ActorPose(
        actor_id="adult",
        root_rotation=(20, -35, 17),
        angles=JointAngles(
            torso_pitch=25,
            head_yaw=20,
            left_hip_flex=30,
            left_knee_flex=75,
            right_shoulder_flex=45,
            right_elbow_flex=60,
        ),
    )
    skeleton = forward_kinematics(actor)
    shapes = {shape.shape_id: shape for shape in skeleton.shapes}
    for anchor in skeleton.anchors.values():
        shape = shapes[anchor.shape_id]
        local = matrix(shape.rotation).T @ (np.asarray(anchor.position) - shape.center)
        if shape.kind == "box":
            ratios = np.abs(local) / (np.asarray(shape.size) / 2)
            assert ratios.max() == pytest.approx(1, abs=1e-10)
        elif shape.kind == "ellipsoid":
            assert np.linalg.norm(local / shape.radii) == pytest.approx(1)
        else:
            on_axis = np.array(
                [0, 0, np.clip(local[2], -shape.length / 2, shape.length / 2)]
            )
            assert np.linalg.norm(local - on_axis) == pytest.approx(shape.radius)


def test_face_frame_uses_rotated_box_outward_normal() -> None:
    box = Box(object_id="b", center=(1, 2, 3), size=(2, 4, 6), rotation=(90, 0, 0))
    position, normal = face_frame(box, "top")
    assert normal == pytest.approx((0, -1, 0), abs=1e-12)
    assert position == pytest.approx((1, -1, 3), abs=1e-12)


def test_duplicate_identifiers_and_empty_scenes_fail_closed() -> None:
    actor = ActorPose(actor_id="adult")
    assert not validate_scene(Scene(actors=())).passed
    report = validate_scene(Scene(actors=(actor, actor)))
    assert report.issues[0].code == "duplicate_id"


def test_kernel_import_does_not_import_any_pipeline_provider_or_network_module() -> (
    None
):
    script = """
import builtins
original = builtins.__import__
def restricted(name, *args, **kwargs):
    if name.startswith(('t2i_spatial_pipeline', 't2i_film_style_pipeline',
                        't2i_model_provider', 't2i_story_pipeline',
                        't2i_prompt_pipeline', 'httpx', 'requests')):
        raise AssertionError(name)
    return original(name, *args, **kwargs)
builtins.__import__ = restricted
from t2i_pose_geometry import ActorPose, Scene, validate_scene
assert validate_scene(Scene(actors=(ActorPose(actor_id='adult'),))).passed
"""
    subprocess.run([sys.executable, "-c", script], check=True, timeout=30)
