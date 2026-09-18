"""Curated whole-body recipes; no activity topology or Cartesian expansion."""

from __future__ import annotations

from typing import Literal

from .pose_reference import (
    BalanceBias,
    BodyLevel,
    Facing,
    HandPlacement,
    HeadOrientation,
    Legs,
    NeutralPose,
    NeutralPoseLibrary,
    Silhouette,
    Spine,
    SupportContact,
    SupportPlacement,
    required_support_positions,
)
from .pose_reference_presentation import (
    reference_cameras,
    reference_presentations,
    reference_subjects,
)

_UPRIGHT_CAMERAS = ("front_eye", "left_eye", "right_eye")
_LOW_CAMERAS = ("left_eye", "right_eye", "left_high", "right_high")

_LEFT_FOOT = SupportContact(body_part="left_foot", surface="floor")
_RIGHT_FOOT = SupportContact(body_part="right_foot", surface="floor")
_SEAT = SupportContact(body_part="pelvis", surface="chair_seat")
_MAT_SEAT = SupportContact(body_part="pelvis", surface="mat")
_LEFT_KNEE = SupportContact(body_part="left_knee", surface="mat")
_RIGHT_KNEE = SupportContact(body_part="right_knee", surface="mat")


def _pose(
    family: str,
    variant: str,
    *,
    level: BodyLevel = "standing",
    spine: Spine = "upright",
    facing: Facing = "front",
    silhouette: Silhouette = "column",
    bias: BalanceBias = "unbiased",
    resting_side: Literal["none", "left", "right"] = "none",
    legs: Legs = "parallel_feet",
    left: HandPlacement = "at_side",
    right: HandPlacement = "at_side",
    supports: tuple[SupportContact, ...] = (_LEFT_FOOT, _RIGHT_FOOT),
    cameras: tuple[str, ...] = _UPRIGHT_CAMERAS,
) -> NeutralPose:
    return NeutralPose(
        pose_id=f"{family}_{variant}",
        family=family,
        body_level=level,
        spine=spine,
        pelvis_facing="front" if spine == "gentle_twist" else facing,
        facing=facing,
        head_orientation=HeadOrientation(
            yaw="aligned",
            pitch="slightly_lowered" if spine == "reclined" else "neutral",
        ),
        silhouette=silhouette,
        balance_bias=bias,
        resting_side=resting_side,
        legs=legs,
        left_hand=left,
        right_hand=right,
        gaze="forward",
        supports=supports,
        support_layout=tuple(
            SupportPlacement(surface=surface, position=position)
            for surface, position in sorted(
                required_support_positions(supports).items()
            )
        ),
        compatible_camera_ids=cameras,
    )


def build_neutral_pose_library() -> NeutralPoseLibrary:
    feet = (_LEFT_FOOT, _RIGHT_FOOT)
    seated = (_SEAT, *feet)
    wall_back = SupportContact(body_part="upper_back", surface="wall")
    chair_back = SupportContact(body_part="upper_back", surface="chair_back")
    left_wall = SupportContact(
        body_part="left_hand", surface="wall", load_bearing=False
    )
    right_wall = SupportContact(
        body_part="right_hand", surface="wall", load_bearing=False
    )
    left_table = SupportContact(body_part="left_hand", surface="table")
    right_table = SupportContact(body_part="right_hand", surface="table")
    left_floor = SupportContact(body_part="left_hand", surface="floor")
    right_floor = SupportContact(body_part="right_hand", surface="floor")
    left_step = SupportContact(body_part="left_foot", surface="step")
    right_step = SupportContact(body_part="right_foot", surface="step")
    headrest = SupportContact(body_part="head", surface="headrest")
    kneeling = (
        _LEFT_KNEE, _RIGHT_KNEE,
        SupportContact(body_part="left_toes", surface="mat"),
        SupportContact(body_part="right_toes", surface="mat"),
    )
    floor_seated = (
        _MAT_SEAT,
        SupportContact(body_part="left_foot", surface="mat"),
        SupportContact(body_part="right_foot", surface="mat"),
    )
    left_mat = SupportContact(
        body_part="left_hand", surface="mat", load_bearing=False
    )
    right_mat = SupportContact(
        body_part="right_hand", surface="mat", load_bearing=False
    )
    poses = (
        _pose("standing_parallel", "relaxed"),
        _pose(
            "standing_parallel", "turn_left", spine="gentle_twist",
            facing="left_three_quarter",
            left="across_forearm", right="relaxed_in_front",
        ),
        _pose(
            "standing_parallel", "turn_right", spine="gentle_twist",
            facing="right_three_quarter",
            right="across_forearm", left="relaxed_in_front",
        ),
        _pose(
            "standing_shifted", "left", silhouette="arc", bias="left",
            left="across_forearm", right="relaxed_in_front",
        ),
        _pose(
            "standing_shifted", "right", silhouette="arc", bias="right",
            right="across_forearm", left="relaxed_in_front",
        ),
        _pose(
            "standing_shifted", "inclined", spine="forward_inclined",
            silhouette="diagonal", bias="left", right="forward_gesture",
        ),
        _pose(
            "standing_staggered", "left", silhouette="diagonal",
            bias="left", legs="left_foot_forward",
            facing="left_three_quarter",
        ),
        _pose(
            "standing_staggered", "right", silhouette="diagonal",
            bias="right", legs="right_foot_forward",
            facing="right_three_quarter",
        ),
        _pose(
            "standing_staggered", "centered", legs="left_foot_forward",
            silhouette="triangle", left="forward_gesture",
        ),
        _pose(
            "wall_supported", "back", silhouette="diagonal",
            spine="reclined", supports=(*feet, wall_back),
        ),
        _pose(
            "wall_supported", "left", spine="gentle_twist",
            facing="left_three_quarter", bias="right", left="on_wall",
            supports=(*feet, left_wall),
        ),
        _pose(
            "wall_supported", "right", spine="gentle_twist",
            facing="right_three_quarter", bias="left", right="on_wall",
            supports=(*feet, right_wall),
        ),
        _pose(
            "table_supported", "left", spine="forward_inclined",
            silhouette="diagonal",
            left="on_table", right="at_side", supports=(*feet, left_table),
        ),
        _pose(
            "table_supported", "right", spine="forward_inclined",
            silhouette="diagonal",
            left="at_side", right="on_table", supports=(*feet, right_table),
        ),
        _pose(
            "table_supported", "both", spine="forward_inclined",
            silhouette="triangle",
            left="on_table", right="on_table",
            supports=(*feet, left_table, right_table),
        ),
        _pose(
            "step_supported", "right", silhouette="triangle", bias="left",
            legs="right_foot_on_step", right="on_knee",
            supports=(_LEFT_FOOT, right_step),
        ),
        _pose(
            "step_supported", "left", silhouette="triangle", bias="right",
            legs="left_foot_on_step", left="on_knee",
            supports=(left_step, _RIGHT_FOOT),
        ),
        _pose(
            "step_supported", "turned", spine="gentle_twist",
            facing="left_three_quarter", silhouette="diagonal",
            bias="left", legs="right_foot_on_step",
            left="across_forearm", right="relaxed_in_front",
            supports=(_LEFT_FOOT, right_step),
        ),
        _pose(
            "seated_upright", "centered", level="seated",
            silhouette="folded", legs="seated_parallel",
            left="on_lap", right="on_lap", supports=seated,
        ),
        _pose(
            "seated_upright", "left", level="seated", spine="gentle_twist",
            facing="left_three_quarter", silhouette="folded",
            legs="seated_left_forward",
            left="on_lap", right="on_knee", supports=seated,
        ),
        _pose(
            "seated_upright", "right", level="seated", spine="gentle_twist",
            facing="right_three_quarter", silhouette="folded",
            legs="seated_right_forward",
            left="on_knee", right="on_lap", supports=seated,
        ),
        _pose(
            "seated_forward", "centered", level="seated", spine="forward_inclined",
            silhouette="diagonal", legs="seated_parallel",
            left="on_knee", right="on_knee", supports=seated,
        ),
        _pose(
            "seated_forward", "left", level="seated", spine="forward_inclined",
            silhouette="diagonal",
            legs="seated_left_forward", facing="left_three_quarter",
            left="on_knee", right="forward_gesture", supports=seated,
        ),
        _pose(
            "seated_forward", "right", level="seated", spine="forward_inclined",
            silhouette="diagonal",
            legs="seated_right_forward", facing="right_three_quarter",
            left="forward_gesture", right="on_knee", supports=seated,
        ),
        _pose(
            "seated_reclined", "centered", level="seated", spine="reclined",
            silhouette="arc", legs="seated_parallel",
            left="on_lap", right="on_lap", supports=(*seated, chair_back),
        ),
        _pose(
            "seated_reclined", "left", level="seated", spine="reclined",
            facing="left_three_quarter", silhouette="arc",
            legs="seated_left_forward", left="across_forearm", right="on_lap",
            supports=(*seated, chair_back),
        ),
        _pose(
            "seated_reclined", "right", level="seated", spine="reclined",
            facing="right_three_quarter", silhouette="arc",
            legs="seated_right_forward", left="on_lap", right="across_forearm",
            supports=(*seated, chair_back),
        ),
        _pose(
            "seated_sideways", "left", level="seated",
            facing="left_three_quarter", silhouette="diagonal",
            legs="seated_parallel",
            left="on_knee", right="on_lap", supports=seated,
        ),
        _pose(
            "seated_sideways", "right", level="seated",
            facing="right_three_quarter", silhouette="diagonal",
            legs="seated_parallel",
            left="on_lap", right="on_knee", supports=seated,
        ),
        _pose(
            "seated_sideways", "extended", level="seated",
            facing="left_three_quarter", silhouette="diagonal",
            legs="seated_left_forward",
            left="on_lap", right="forward_gesture", supports=seated,
        ),
        _pose(
            "floor_seated", "centered", level="seated",
            silhouette="triangle", legs="floor_seated_bent_knees",
            left="on_knee", right="on_knee", supports=floor_seated,
            cameras=_LOW_CAMERAS,
        ),
        _pose(
            "floor_seated", "left", level="seated", spine="gentle_twist",
            facing="left_three_quarter", silhouette="triangle",
            legs="floor_seated_bent_knees",
            left="on_knee", right="across_forearm", supports=floor_seated,
            cameras=_LOW_CAMERAS,
        ),
        _pose(
            "floor_seated", "right", level="seated", spine="gentle_twist",
            facing="right_three_quarter", silhouette="triangle",
            legs="floor_seated_bent_knees",
            left="across_forearm", right="on_knee", supports=floor_seated,
            cameras=_LOW_CAMERAS,
        ),
        _pose(
            "kneeling_upright", "centered", level="kneeling",
            legs="knees_and_toes_on_mat",
            left="at_side", right="at_side", supports=kneeling,
            cameras=_LOW_CAMERAS,
        ),
        _pose(
            "kneeling_upright", "left", level="kneeling", spine="gentle_twist",
            facing="left_three_quarter", legs="knees_and_toes_on_mat",
            left="forward_gesture", right="at_side",
            supports=kneeling, cameras=_LOW_CAMERAS,
        ),
        _pose(
            "kneeling_upright", "right", level="kneeling", spine="gentle_twist",
            facing="right_three_quarter", legs="knees_and_toes_on_mat",
            left="at_side", right="forward_gesture",
            supports=kneeling, cameras=_LOW_CAMERAS,
        ),
        _pose(
            "half_kneeling", "left", level="kneeling", silhouette="triangle",
            legs="left_half_kneel",
            right="on_knee", supports=(_LEFT_KNEE, _RIGHT_FOOT),
            cameras=_LOW_CAMERAS,
        ),
        _pose(
            "half_kneeling", "right", level="kneeling", silhouette="triangle",
            legs="right_half_kneel",
            left="on_knee", supports=(_RIGHT_KNEE, _LEFT_FOOT),
            cameras=_LOW_CAMERAS,
        ),
        _pose(
            "half_kneeling", "turned", level="kneeling", spine="gentle_twist",
            facing="right_three_quarter", silhouette="diagonal",
            legs="left_half_kneel",
            left="across_forearm", right="on_knee",
            supports=(_LEFT_KNEE, _RIGHT_FOOT), cameras=_LOW_CAMERAS,
        ),
        _pose(
            "crouched_supported", "left", level="crouched", spine="forward_inclined",
            silhouette="folded",
            legs="bent_knees_feet_flat", left="on_floor", right="on_knee",
            supports=(*feet, left_floor), cameras=_LOW_CAMERAS,
        ),
        _pose(
            "crouched_supported", "right", level="crouched", spine="forward_inclined",
            silhouette="folded",
            legs="bent_knees_feet_flat", left="on_knee", right="on_floor",
            supports=(*feet, right_floor), cameras=_LOW_CAMERAS,
        ),
        _pose(
            "crouched_supported", "both", level="crouched", spine="forward_inclined",
            silhouette="triangle",
            legs="bent_knees_feet_flat", left="on_floor", right="on_floor",
            supports=(*feet, left_floor, right_floor), cameras=_LOW_CAMERAS,
        ),
        _pose(
            "side_lying_rest", "left", level="lying", spine="neutral_horizontal",
            silhouette="horizontal", resting_side="left", legs="staggered_bent_knees",
            left="on_mat_forward", right="on_lap",
            supports=(
                SupportContact(body_part="left_side", surface="mat"),
                headrest, left_mat,
            ),
            cameras=("right_high",),
        ),
        _pose(
            "side_lying_rest", "right", level="lying", spine="neutral_horizontal",
            silhouette="horizontal", resting_side="right", legs="staggered_bent_knees",
            left="on_lap", right="on_mat_forward",
            supports=(
                SupportContact(body_part="right_side", surface="mat"),
                headrest, right_mat,
            ),
            cameras=("left_high",),
        ),
        _pose(
            "side_lying_rest", "folded", level="lying", spine="neutral_horizontal",
            silhouette="folded", resting_side="left", legs="staggered_bent_knees",
            left="on_mat_forward", right="across_forearm",
            supports=(
                SupportContact(body_part="left_side", surface="mat"),
                headrest, left_mat,
            ),
            cameras=("right_high",),
        ),
        _pose(
            "standing_gesture", "left", silhouette="triangle",
            left="forward_gesture", right="at_side",
            facing="left_three_quarter", legs="right_foot_forward",
        ),
        _pose(
            "standing_gesture", "right", silhouette="triangle",
            left="at_side", right="forward_gesture",
            facing="right_three_quarter", legs="left_foot_forward",
        ),
        _pose(
            "standing_gesture", "open", silhouette="arc",
            left="forward_gesture", right="forward_gesture",
            legs="parallel_feet",
        ),
    )
    return NeutralPoseLibrary(
        cameras=reference_cameras(),
        subjects=reference_subjects(),
        presentations=reference_presentations(),
        poses=poses,
    )
