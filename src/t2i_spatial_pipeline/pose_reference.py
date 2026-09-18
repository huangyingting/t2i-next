"""Offline, clothed figure-study poses, independent of activity catalogs."""

from __future__ import annotations

import random
from collections import Counter
from itertools import combinations
from typing import Literal

from pydantic import Field, model_validator

from t2i_pose_geometry.models import Scene, ValidationReport

from .pose_reference_geometry import (
    ReferenceGeometryError,
    compile_reference_geometry,
    geometry_implementation_fingerprint,
)
from .pose_reference_history import (
    Digest,
    ReferenceChoice,
    ReferenceUsage,
    advance_reference_usage,
    reference_digest,
)
from .pose_reference_presentation import (
    SUPPORT_PROFILES,
    ReferenceCamera,
    ReferencePresentation,
    ReferenceSubject,
    presentation_accepts_camera,
    presentation_supports,
    render_reference_camera,
    render_reference_presentation,
    render_reference_subject,
)
from .pose_reference_types import Identifier, ReferenceModel, Surface

BodyLevel = Literal["standing", "seated", "kneeling", "crouched", "lying"]
Spine = Literal[
    "upright", "forward_inclined", "reclined", "gentle_twist", "neutral_horizontal"
]
Facing = Literal["front", "left_three_quarter", "right_three_quarter"]
Silhouette = Literal["column", "diagonal", "triangle", "folded", "horizontal", "arc"]
BalanceBias = Literal["unbiased", "left", "right"]
Legs = Literal[
    "parallel_feet", "left_foot_forward", "right_foot_forward",
    "right_foot_on_step", "left_foot_on_step", "seated_parallel",
    "seated_left_forward", "seated_right_forward", "crossed_on_mat",
    "knees_on_mat", "left_half_kneel", "right_half_kneel",
    "bent_knees_feet_flat", "staggered_bent_knees",
]
HandPlacement = Literal[
    "at_side", "on_lap", "on_knee", "across_forearm", "forward_gesture",
    "on_wall", "on_table", "on_seat", "on_floor", "on_mat_forward",
]
BodyPart = Literal[
    "left_foot", "right_foot", "left_knee", "right_knee",
    "left_hand", "right_hand", "pelvis", "upper_back", "left_side", "right_side",
    "head",
    "left_shin", "right_shin", "left_instep", "right_instep",
]
_CONTACT_SURFACES: dict[BodyPart, frozenset[Surface]] = {
    "left_foot": frozenset(("floor", "step")),
    "right_foot": frozenset(("floor", "step")),
    "left_knee": frozenset(("mat",)),
    "right_knee": frozenset(("mat",)),
    "left_hand": frozenset(("floor", "mat", "wall", "table", "chair_seat")),
    "right_hand": frozenset(("floor", "mat", "wall", "table", "chair_seat")),
    "pelvis": frozenset(("mat", "chair_seat")),
    "upper_back": frozenset(("wall", "chair_back")),
    "left_side": frozenset(("mat",)),
    "right_side": frozenset(("mat",)),
    "head": frozenset(("headrest",)),
    "left_shin": frozenset(("mat",)),
    "right_shin": frozenset(("mat",)),
    "left_instep": frozenset(("mat",)),
    "right_instep": frozenset(("mat",)),
}


class SupportContact(ReferenceModel):
    body_part: BodyPart
    surface: Surface
    load_bearing: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def surface_is_supported(self) -> SupportContact:
        if self.surface not in _CONTACT_SURFACES[self.body_part]:
            raise ValueError("body part cannot use this reference support surface")
        return self


_HAND_SURFACES: dict[HandPlacement, Surface] = {
    "on_wall": "wall",
    "on_table": "table",
    "on_seat": "chair_seat",
    "on_floor": "floor",
    "on_mat_forward": "mat",
}
_LEG_LEVELS: dict[Legs, BodyLevel] = {
    "parallel_feet": "standing",
    "left_foot_forward": "standing",
    "right_foot_forward": "standing",
    "right_foot_on_step": "standing",
    "left_foot_on_step": "standing",
    "seated_parallel": "seated",
    "seated_left_forward": "seated",
    "seated_right_forward": "seated",
    "crossed_on_mat": "seated",
    "knees_on_mat": "kneeling",
    "left_half_kneel": "kneeling",
    "right_half_kneel": "kneeling",
    "bent_knees_feet_flat": "crouched",
    "staggered_bent_knees": "lying",
}


class HeadOrientation(ReferenceModel):
    yaw: Literal["aligned", "gentle_left", "gentle_right"]
    pitch: Literal["neutral", "slightly_lowered"]


SupportPosition = Literal[
    "under_body", "under_pelvis", "behind_upper_back",
    "in_front_within_forearm_reach", "left_within_forearm_reach",
    "right_within_forearm_reach", "under_left_raised_foot",
    "under_right_raised_foot", "under_aligned_head",
]


class SupportPlacement(ReferenceModel):
    surface: Surface
    coordinate_frame: Literal["anatomical"] = "anatomical"
    position: SupportPosition


def required_support_positions(
    supports: tuple[SupportContact, ...],
) -> dict[Surface, SupportPosition]:
    """Resolve relative staging requirements, not measured contact coordinates."""
    parts = {contact.body_part for contact in supports}
    positions: dict[Surface, SupportPosition] = {}
    for contact in supports:
        match contact.surface:
            case "floor" | "mat":
                position: SupportPosition = "under_body"
            case "chair_seat":
                position = "under_pelvis"
            case "chair_back":
                position = "behind_upper_back"
            case "headrest":
                position = "under_aligned_head"
            case "table":
                position = "in_front_within_forearm_reach"
            case "step":
                position = (
                    "under_left_raised_foot"
                    if contact.body_part == "left_foot"
                    else "under_right_raised_foot"
                )
            case "wall":
                if "upper_back" in parts:
                    position = "behind_upper_back"
                elif contact.body_part == "left_hand":
                    position = "left_within_forearm_reach"
                else:
                    position = "right_within_forearm_reach"
        if contact.surface in positions and positions[contact.surface] != position:
            raise ValueError("one support object cannot occupy conflicting positions")
        positions[contact.surface] = position
    return positions


class NeutralPose(ReferenceModel):
    pose_id: Identifier
    family: Identifier
    body_level: BodyLevel
    spine: Spine
    coordinate_frame: Literal["room_axes"] = "room_axes"
    pelvis_facing: Facing
    facing: Facing
    head_orientation: HeadOrientation
    silhouette: Silhouette
    balance_bias: BalanceBias
    resting_side: Literal["none", "left", "right"]
    legs: Legs
    left_hand: HandPlacement
    right_hand: HandPlacement
    gaze: Literal["forward", "downward"]
    supports: tuple[SupportContact, ...] = Field(min_length=1)
    support_layout: tuple[SupportPlacement, ...] = Field(min_length=1)
    compatible_camera_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def support_and_limb_consistency(self) -> NeutralPose:
        parts = [contact.body_part for contact in self.supports]
        if len(parts) != len(set(parts)):
            raise ValueError("each support body part must have one surface")
        if len(self.compatible_camera_ids) != len(set(self.compatible_camera_ids)):
            raise ValueError("compatible cameras must be unique")
        bearing = {
            contact.body_part for contact in self.supports if contact.load_bearing
        }
        if _LEG_LEVELS[self.legs] != self.body_level:
            raise ValueError("leg configuration contradicts body level")
        if self.spine == "gentle_twist":
            if self.pelvis_facing == self.facing or "front" not in {
                self.pelvis_facing, self.facing
            }:
                raise ValueError(
                    "gentle twist requires adjacent pelvis/chest directions"
                )
        elif self.pelvis_facing != self.facing:
            raise ValueError("untwisted pelvis and chest must face the same direction")
        if self.balance_bias != "unbiased":
            bias_foot = (
                "left_foot" if self.balance_bias == "left" else "right_foot"
            )
            if self.body_level != "standing" or bias_foot not in bearing:
                raise ValueError("balance bias requires a standing load-bearing foot")
        if self.body_level == "lying" and self.spine != "neutral_horizontal":
            raise ValueError("lying reference requires a neutral horizontal spine")
        if self.body_level != "lying" and self.spine == "neutral_horizontal":
            raise ValueError("horizontal spine is reserved for lying references")
        if (self.body_level == "lying") != (self.resting_side != "none"):
            raise ValueError("resting side must be declared only for lying references")
        contacts = {contact.body_part: contact for contact in self.supports}
        for body_part, placement in (
            ("left_hand", self.left_hand), ("right_hand", self.right_hand)
        ):
            contact = contacts.get(body_part)
            if placement in _HAND_SURFACES:
                if contact is None or contact.surface != _HAND_SURFACES[placement]:
                    raise ValueError(
                        "hand placement lacks its matching surface contact"
                    )
            elif contact is not None:
                raise ValueError("a supported hand cannot also perform a free gesture")
            if placement in {"on_table", "on_floor"} and body_part not in bearing:
                raise ValueError("table and floor hand supports must bear weight")
            if placement == "on_floor" and self.body_level != "crouched":
                raise ValueError("floor hand support requires a crouched reference")
            if placement == "on_mat_forward" and self.body_level != "lying":
                raise ValueError(
                    "forward mat hand placement requires a lying reference"
                )
            if placement == "on_seat" and self.body_level != "seated":
                raise ValueError("seat hand support requires a seated reference")
        expected_leg_contacts: dict[BodyPart, Surface] = {}
        if self.legs == "left_half_kneel":
            expected_leg_contacts = {"left_knee": "mat", "right_foot": "floor"}
        elif self.legs == "right_half_kneel":
            expected_leg_contacts = {"right_knee": "mat", "left_foot": "floor"}
        elif self.legs == "right_foot_on_step":
            expected_leg_contacts = {"right_foot": "step", "left_foot": "floor"}
        elif self.legs == "left_foot_on_step":
            expected_leg_contacts = {"left_foot": "step", "right_foot": "floor"}
        elif self.body_level in {"standing", "crouched"}:
            expected_leg_contacts = {"left_foot": "floor", "right_foot": "floor"}
        elif self.legs == "knees_on_mat":
            expected_leg_contacts = {
                "left_knee": "mat", "right_knee": "mat",
                "left_shin": "mat", "right_shin": "mat",
                "left_instep": "mat", "right_instep": "mat",
            }
        elif self.legs == "crossed_on_mat":
            expected_leg_contacts = {"pelvis": "mat"}
        elif self.body_level == "seated":
            expected_leg_contacts = {
                "pelvis": "chair_seat", "left_foot": "floor", "right_foot": "floor"
            }
        elif self.resting_side == "left":
            expected_leg_contacts = {"left_side": "mat", "head": "headrest"}
        elif self.resting_side == "right":
            expected_leg_contacts = {"right_side": "mat", "head": "headrest"}
        for part, surface in expected_leg_contacts.items():
            if part not in contacts or contacts[part].surface != surface:
                raise ValueError("leg configuration lacks its declared support surface")
            if part not in bearing:
                raise ValueError("posture lacks its required load-bearing contacts")
        if self.body_level == "crouched" and not bearing.intersection(
            {"left_hand", "right_hand"}
        ):
            raise ValueError("supported crouch requires a load-bearing hand")
        if self.body_level == "lying":
            lower_hand = (
                self.left_hand if self.resting_side == "left" else self.right_hand
            )
            if lower_hand != "on_mat_forward":
                raise ValueError("lying lower hand must rest ahead of the torso")
            if self.head_orientation != HeadOrientation(yaw="aligned", pitch="neutral"):
                raise ValueError("resting head must stay aligned with the lying torso")
            if bearing.intersection({"left_hand", "right_hand"}):
                raise ValueError(
                    "resting hands must not replace lying body/head support"
                )
        allowed_parts = set(expected_leg_contacts)
        if self.left_hand in _HAND_SURFACES:
            allowed_parts.add("left_hand")
        if self.right_hand in _HAND_SURFACES:
            allowed_parts.add("right_hand")
        if self.body_level in {"standing", "seated"}:
            allowed_parts.add("upper_back")
        if not set(contacts).issubset(allowed_parts):
            raise ValueError("support body part contradicts the posture")
        if self.spine == "reclined" and "upper_back" not in bearing:
            raise ValueError("reclined references require a load-bearing back support")
        if "upper_back" in contacts:
            expected_back = "wall" if self.body_level == "standing" else "chair_back"
            if contacts["upper_back"].surface != expected_back:
                raise ValueError("back support surface contradicts body level")
            if self.spine == "forward_inclined":
                raise ValueError("forward-inclined torso cannot use a back support")
            if "wall" in {c.surface for c in self.supports if "hand" in c.body_part}:
                raise ValueError("back wall support cannot also require a side wall")
        layout = {item.surface: item.position for item in self.support_layout}
        if len(layout) != len(self.support_layout):
            raise ValueError("each required surface must have one support placement")
        if layout != required_support_positions(self.supports):
            raise ValueError(
                "support placement contradicts the anatomical contact layout"
            )
        return self

    def structural_key(self) -> tuple[object, ...]:
        return (
            self.body_level,
            self.spine,
            (
                self.pelvis_facing, self.facing,
                self.head_orientation.yaw, self.head_orientation.pitch,
            ),
            self.silhouette,
            (self.balance_bias, self.resting_side),
            self.legs,
            (self.left_hand, self.right_hand),
            tuple(sorted(
                (contact.body_part, contact.surface, contact.load_bearing)
                for contact in self.supports
            )),
        )


class NeutralPoseLibrary(ReferenceModel):
    schema_version: Literal["4.0"] = "4.0"
    scope: Literal["clothed_adult_figure_study"] = "clothed_adult_figure_study"
    validation_status: Literal["geometry_required"] = "geometry_required"
    visual_validation: Literal[False] = False
    physical_validation: Literal[False] = False
    requires_render_review: Literal[True] = True
    cameras: tuple[ReferenceCamera, ...] = Field(min_length=1)
    subjects: tuple[ReferenceSubject, ...] = Field(min_length=1)
    presentations: tuple[ReferencePresentation, ...] = Field(min_length=1)
    poses: tuple[NeutralPose, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_and_resolved(self) -> NeutralPoseLibrary:
        pose_ids = [pose.pose_id for pose in self.poses]
        keys = [pose.structural_key() for pose in self.poses]
        camera_ids = [camera.camera_id for camera in self.cameras]
        if len(pose_ids) != len(set(pose_ids)):
            raise ValueError("pose IDs must be unique")
        if len(keys) != len(set(keys)):
            raise ValueError("poses must differ structurally, not just by ID or gaze")
        if len(camera_ids) != len(set(camera_ids)):
            raise ValueError("camera IDs must be unique")
        camera_keys = {
            camera.model_dump_json(exclude={"camera_id"}) for camera in self.cameras
        }
        if len(camera_keys) != len(self.cameras):
            raise ValueError("camera recipes must differ, not just their IDs")
        for pose in self.poses:
            if not set(pose.compatible_camera_ids).issubset(camera_ids):
                raise ValueError(f"{pose.pose_id} references an unknown camera")
            if any(
                camera.camera_id in pose.compatible_camera_ids
                and not pose_accepts_camera(pose, camera)
                for camera in self.cameras
            ):
                raise ValueError(f"{pose.pose_id} declares an incompatible camera view")
            if not _presentation_options(self, pose):
                raise ValueError(f"{pose.pose_id} has no compatible presentation")
        if len({subject.subject_id for subject in self.subjects}) != len(self.subjects):
            raise ValueError("subject IDs must be unique")
        presentation_ids = {item.presentation_id for item in self.presentations}
        if len(presentation_ids) != len(self.presentations):
            raise ValueError("presentation IDs must be unique")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        payload["geometry_implementation"] = geometry_implementation_fingerprint()
        payload["poses"] = [
            pose.model_dump(mode="json")
            for pose in sorted(self.poses, key=lambda item: item.pose_id)
        ]
        payload["cameras"] = [
            camera.model_dump(mode="json")
            for camera in sorted(self.cameras, key=lambda item: item.camera_id)
        ]
        payload["subjects"] = [
            subject.model_dump(mode="json")
            for subject in sorted(self.subjects, key=lambda item: item.subject_id)
        ]
        payload["presentations"] = [
            presentation.model_dump(mode="json")
            for presentation in sorted(
                self.presentations, key=lambda item: item.presentation_id
            )
        ]
        return reference_digest(payload)


class PoseReferenceScene(ReferenceModel):
    pose: NeutralPose
    camera: ReferenceCamera
    subject: ReferenceSubject
    presentation: ReferencePresentation
    geometry: Scene
    prompt: str = Field(min_length=1)

    @model_validator(mode="after")
    def camera_is_compatible(self) -> PoseReferenceScene:
        if not pose_accepts_camera(self.pose, self.camera):
            raise ValueError("reference camera is incompatible with pose")
        if self.geometry != compile_reference_geometry(
            self.pose, self.subject, self.presentation
        ):
            raise ValueError("reference geometry differs from its validated recipe")
        if self.prompt != render_pose_reference(
            self.pose, self.camera, self.subject, self.presentation
        ):
            raise ValueError("reference prompt differs from its pose and camera")
        return self


class PoseReferenceReport(ReferenceModel):
    evidence: Literal["symbolic_structure_only"] = "symbolic_structure_only"
    visual_validation: Literal[False] = False
    physical_validation: Literal[False] = False
    requires_render_review: Literal[True] = True
    geometry_checked_scenes: int = Field(default=0, ge=0)
    pose_count: int = Field(ge=1)
    family_counts: dict[str, int]
    body_level_counts: dict[str, int]
    spine_counts: dict[str, int]
    balance_bias_counts: dict[str, int]
    load_bearing_contact_counts: dict[str, int]
    camera_counts: dict[str, int] = Field(default_factory=dict)
    presentation_counts: dict[str, int] = Field(default_factory=dict)
    subject_counts: dict[str, int] = Field(default_factory=dict)
    previously_used_pose_scenes: int = Field(default=0, ge=0)
    previously_used_combination_scenes: int = Field(default=0, ge=0)
    pair_count: int = Field(ge=0)
    minimum_structural_distance: float | None = Field(default=None, ge=0, le=1)
    mean_structural_distance: float | None = Field(default=None, ge=0, le=1)


class ReferenceGeometryRejection(ReferenceModel):
    pose_id: Identifier
    subject_id: Identifier
    presentation_id: Identifier
    report: ValidationReport

    @model_validator(mode="after")
    def report_is_a_rejection(self) -> ReferenceGeometryRejection:
        if self.report.passed:
            raise ValueError("geometry rejection must contain failed checks")
        return self


class PoseReferenceBatch(ReferenceModel):
    schema_version: Literal["4.0"] = "4.0"
    scope: Literal["clothed_adult_figure_study"] = "clothed_adult_figure_study"
    selection_algorithm: Literal["geometry_gated_family_maximin_v4"] = (
        "geometry_gated_family_maximin_v4"
    )
    renderer_version: Literal[4] = 4
    seed: int
    family_filter: Identifier | None = None
    presentation_filter: Identifier | None = None
    catalog_fingerprint: Digest
    subject: ReferenceSubject
    history_before: ReferenceUsage
    history_after: ReferenceUsage
    scenes: tuple[PoseReferenceScene, ...] = Field(min_length=1)
    report: PoseReferenceReport
    geometry_rejections: tuple[ReferenceGeometryRejection, ...] = ()

    @model_validator(mode="after")
    def report_matches_scenes(self) -> PoseReferenceBatch:
        poses = tuple(scene.pose for scene in self.scenes)
        if len({pose.pose_id for pose in poses}) != len(poses):
            raise ValueError("reference batch requires distinct poses")
        if len({pose.structural_key() for pose in poses}) != len(poses):
            raise ValueError("reference batch requires distinct pose structures")
        if any(scene.subject != self.subject for scene in self.scenes):
            raise ValueError("all reference scenes must preserve the batch subject")
        if self.family_filter is not None and any(
            pose.family != self.family_filter for pose in poses
        ):
            raise ValueError("reference scene does not match the family filter")
        if self.presentation_filter is not None and any(
            scene.presentation.presentation_id != self.presentation_filter
            for scene in self.scenes
        ):
            raise ValueError("reference scene does not match the presentation filter")
        if self.history_before.catalog_fingerprint != self.catalog_fingerprint:
            raise ValueError("history does not match the batch catalog fingerprint")
        if self.history_after != advance_reference_usage(
            self.history_before, tuple(_scene_choice(scene) for scene in self.scenes)
        ):
            raise ValueError("reference history differs from its scenes")
        if self.report != describe_reference_scenes(self.scenes, self.history_before):
            raise ValueError("reference report differs from its scenes")
        return self


class ReferenceLibraryAudit(ReferenceModel):
    schema_version: Literal["4.0"] = "4.0"
    catalog_fingerprint: Digest
    evidence: Literal["symbolic_structure_only"] = "symbolic_structure_only"
    visual_validation: Literal[False] = False
    physical_validation: Literal[False] = False
    requires_render_review: Literal[True] = True
    pose_report: PoseReferenceReport
    camera_count: int = Field(ge=1)
    subject_count: int = Field(ge=1)
    presentation_count: int = Field(ge=1)
    compatible_pose_camera_presentation_count: int = Field(ge=1)
    geometry_checked_scenes: int = Field(ge=0)
    geometry_rejections: tuple[ReferenceGeometryRejection, ...] = ()


def audit_reference_library(library: NeutralPoseLibrary) -> ReferenceLibraryAudit:
    combinations_checked = 0
    geometry_checked = 0
    rejections: dict[tuple[str, str, str], ReferenceGeometryRejection] = {}
    for pose in library.poses:
        for camera, presentation in _presentation_options(library, pose):
            for subject in library.subjects:
                try:
                    geometry = compile_reference_geometry(pose, subject, presentation)
                except ReferenceGeometryError as exc:
                    key = (
                        pose.pose_id, subject.subject_id, presentation.presentation_id
                    )
                    rejections[key] = ReferenceGeometryRejection(
                        pose_id=pose.pose_id, subject_id=subject.subject_id,
                        presentation_id=presentation.presentation_id, report=exc.report,
                    )
                    continue
                PoseReferenceScene(
                    pose=pose,
                    camera=camera,
                    presentation=presentation,
                    subject=subject,
                    geometry=geometry,
                    prompt=render_pose_reference(pose, camera, subject, presentation),
                )
                geometry_checked += 1
            combinations_checked += 1
    return ReferenceLibraryAudit(
        catalog_fingerprint=library.fingerprint(),
        pose_report=describe_reference_poses(library.poses),
        camera_count=len(library.cameras),
        subject_count=len(library.subjects),
        presentation_count=len(library.presentations),
        compatible_pose_camera_presentation_count=combinations_checked,
        geometry_checked_scenes=geometry_checked,
        geometry_rejections=tuple(rejections.values()),
    )


def structural_distance(left: NeutralPose, right: NeutralPose) -> float:
    left_key, right_key = left.structural_key(), right.structural_key()
    return sum(a != b for a, b in zip(left_key, right_key, strict=True)) / len(left_key)


def describe_reference_poses(poses: tuple[NeutralPose, ...]) -> PoseReferenceReport:
    if not poses:
        raise ValueError("reference report requires at least one pose")
    distances = [structural_distance(a, b) for a, b in combinations(poses, 2)]
    return PoseReferenceReport(
        pose_count=len(poses),
        family_counts=dict(sorted(Counter(pose.family for pose in poses).items())),
        body_level_counts=dict(sorted(
            Counter(pose.body_level for pose in poses).items()
        )),
        spine_counts=dict(sorted(Counter(pose.spine for pose in poses).items())),
        balance_bias_counts=dict(sorted(
            Counter(pose.balance_bias for pose in poses).items()
        )),
        load_bearing_contact_counts=dict(sorted(
            Counter(
                contact.body_part for pose in poses
                for contact in pose.supports if contact.load_bearing
            ).items()
        )),
        pair_count=len(distances),
        minimum_structural_distance=min(distances) if distances else None,
        mean_structural_distance=sum(distances) / len(distances) if distances else None,
    )


def _scene_choice(scene: PoseReferenceScene) -> ReferenceChoice:
    return ReferenceChoice(
        pose_id=scene.pose.pose_id,
        camera_id=scene.camera.camera_id,
        presentation_id=scene.presentation.presentation_id,
    )


def describe_reference_scenes(
    scenes: tuple[PoseReferenceScene, ...],
    history: ReferenceUsage,
) -> PoseReferenceReport:
    report = describe_reference_poses(tuple(scene.pose for scene in scenes))
    return PoseReferenceReport(
        **report.model_dump(exclude={
            "camera_counts", "presentation_counts", "subject_counts",
            "previously_used_pose_scenes", "previously_used_combination_scenes",
            "geometry_checked_scenes",
        }),
        geometry_checked_scenes=len(scenes),
        camera_counts=dict(sorted(Counter(
            scene.camera.camera_id for scene in scenes
        ).items())),
        presentation_counts=dict(sorted(Counter(
            scene.presentation.presentation_id for scene in scenes
        ).items())),
        subject_counts=dict(sorted(Counter(
            scene.subject.subject_id for scene in scenes
        ).items())),
        previously_used_pose_scenes=sum(
            scene.pose.pose_id in history.pose_counts for scene in scenes
        ),
        previously_used_combination_scenes=sum(
            _scene_choice(scene).fingerprint() in history.combination_counts
            for scene in scenes
        ),
    )


def _pose_surfaces(pose: NeutralPose) -> tuple[Surface, ...]:
    return tuple(sorted({contact.surface for contact in pose.supports}))


def pose_accepts_camera(pose: NeutralPose, camera: ReferenceCamera) -> bool:
    """Check declared view sectors; this does not calculate image occlusion."""
    if camera.camera_id not in pose.compatible_camera_ids:
        return False
    if pose.body_level == "lying" and (
        camera.height != "slightly_above_subject"
        or camera.focus != "whole_figure_and_supports"
    ):
        return False
    if pose.facing == "left_three_quarter" and (
        pose.head_orientation.yaw == "gentle_left"
        and camera.view in {"right_three_quarter", "right_profile"}
    ):
        return False
    if pose.facing == "right_three_quarter" and (
        pose.head_orientation.yaw == "gentle_right"
        and camera.view in {"left_three_quarter", "left_profile"}
    ):
        return False
    if camera.view == "right_profile" and (
        pose.facing == "left_three_quarter"
        or (pose.facing == "front" and pose.head_orientation.yaw == "gentle_left")
    ):
        return False
    if camera.view == "left_profile" and (
        pose.facing == "right_three_quarter"
        or (pose.facing == "front" and pose.head_orientation.yaw == "gentle_right")
    ):
        return False
    return True


def presentation_fits_pose(
    presentation: ReferencePresentation, pose: NeutralPose,
) -> bool:
    available = {item.surface: item for item in presentation.supports}
    return all(
        surface in available
        and (
            available[surface].height,
            available[surface].extent,
            available[surface].orientation,
        ) == SUPPORT_PROFILES[surface]
        for surface in _pose_surfaces(pose)
    )


def _presentation_options(
    library: NeutralPoseLibrary,
    pose: NeutralPose,
    presentation_id: str | None = None,
) -> list[tuple[ReferenceCamera, ReferencePresentation]]:
    return [
        (camera, presentation)
        for camera in sorted(library.cameras, key=lambda item: item.camera_id)
        if pose_accepts_camera(pose, camera)
        for presentation in sorted(
            library.presentations, key=lambda item: item.presentation_id
        )
        if (presentation_id is None or presentation.presentation_id == presentation_id)
        and presentation_fits_pose(presentation, pose)
        and presentation_accepts_camera(presentation, camera)
    ]


def _render_hand(side: Literal["left", "right"], placement: HandPlacement) -> str:
    opposite = "right" if side == "left" else "left"
    match placement:
        case "on_knee":
            return f"The {side} hand rests on the subject's own {side} knee."
        case "across_forearm":
            return (
                f"The {side} hand rests across the subject's own {opposite} forearm, "
                "without gripping or supporting body weight."
            )
        case "on_mat_forward":
            return (
                f"The {side} forearm and palm rest on the mat in front of the ribs, "
                "with the elbow ahead of the torso, not trapped underneath it."
            )
        case "on_floor":
            return (
                f"The {side} palm rests flat on the floor ahead of the same-side "
                "foot, with room for the forearm outside the bent knee."
            )
        case _:
            return f"The {side} hand is {placement.replace('_', ' ')}."


def _render_support_layout(
    pose: NeutralPose, presentation: ReferencePresentation,
) -> str:
    realizations = {item.surface: item for item in presentation.supports}
    positions: dict[SupportPosition, str] = {
        "under_body": "beneath the body",
        "under_pelvis": "beneath the pelvis",
        "behind_upper_back": "behind the upper back",
        "in_front_within_forearm_reach": (
            "in front of the torso, within forearm reach "
            "without straightening the elbows"
        ),
        "left_within_forearm_reach": (
            "to the subject's anatomical left, within forearm reach"
        ),
        "right_within_forearm_reach": (
            "to the subject's anatomical right, within forearm reach"
        ),
        "under_left_raised_foot": "under the subject's raised left foot",
        "under_right_raised_foot": "under the subject's raised right foot",
        "under_aligned_head": "beneath the head without lifting or dropping the neck",
    }
    return " ".join(
        f"Use {realizations[item.surface].description}. "
        f"Its {realizations[item.surface].orientation} contact surface stays "
        f"{positions[item.position]}, at "
        f"{realizations[item.surface].height.replace('_', ' ')} level, "
        f"with clear space for the "
        f"{realizations[item.surface].extent.replace('_', ' ')}."
        for item in pose.support_layout
    )


def render_pose_reference(
    pose: NeutralPose,
    camera: ReferenceCamera,
    subject: ReferenceSubject,
    presentation: ReferencePresentation,
) -> str:
    if not pose_accepts_camera(pose, camera):
        raise ValueError("reference camera is incompatible with pose")
    if not presentation_supports(presentation, _pose_surfaces(pose)):
        raise ValueError("reference environment lacks a required support surface")
    if not presentation_fits_pose(presentation, pose):
        raise ValueError("support height, extent or orientation cannot fit the pose")
    if not presentation_accepts_camera(presentation, camera):
        raise ValueError("reference camera requires more space than the environment")
    geometry = compile_reference_geometry(pose, subject, presentation)
    realizations = {item.surface: item.description for item in presentation.supports}
    supports = "; ".join(
        f"{contact.body_part.replace('_', ' ')} on {realizations[contact.surface]}"
        + (" bears weight" if contact.load_bearing else " makes light contact")
        for contact in pose.supports
    )
    balance = (
        "Distribute the standing load without favoring either foot. "
        if pose.balance_bias == "unbiased"
        else f"Favor the subject's {pose.balance_bias} planted foot without lifting "
        "the other foot or releasing the declared supports. "
    )
    if pose.body_level != "standing":
        balance = ""
    head = (
        "Keep the head aligned with the chest"
        if pose.head_orientation.yaw == "aligned"
        else "Turn the head gently toward the subject's "
        + ("left" if pose.head_orientation.yaw == "gentle_left" else "right")
        + " relative to the chest"
    )
    head += (
        ", with the neck in a neutral position."
        if pose.head_orientation.pitch == "neutral"
        else ", with the chin slightly lowered."
    )
    if pose.body_level == "lying":
        posture_detail = (
            f"The {pose.resting_side} side of the torso and pelvis rests on the mat. "
            "Keep the bent knees staggered, with the lower shin slightly forward "
            "so the leg outlines are not exactly superimposed. The headrest fills "
            "the gap beneath the head, keeping the neck in line with the spine."
        )
    elif pose.body_level == "crouched":
        posture_detail = (
            "The pelvis stays above the floor between the bent legs; both heels "
            "remain grounded, with space between the knees for the inclined torso."
        )
    elif pose.legs == "knees_on_mat":
        posture_detail = (
            "The pelvis stays above the knees, not seated on the heels; the shins "
            "and relaxed tops of the feet lie behind the knees on the same mat."
        )
    elif pose.legs == "crossed_on_mat":
        posture_detail = "The pelvis rests on the mat, not suspended above the feet."
    elif pose.spine == "reclined":
        posture_detail = (
            "Leave space between the pelvis and the back support for the torso's "
            "backward incline; keep the hands in their declared positions, "
            "not inserted behind the supported back."
        )
    else:
        posture_detail = ""
    if posture_detail:
        posture_detail += " "
    return (
        "A non-sexual figure-study image of exactly one fully clothed adult. "
        f"{render_reference_presentation(presentation)} "
        f"{render_reference_subject(subject)} "
        f"The pelvis is {geometry.actors[0].root_position[2]:.3f} metres "
        "above the room floor. "
        f"The figure uses a {pose.body_level} posture with a "
        f"{pose.spine.replace('_', ' ')} spine, "
        f"forming a {pose.silhouette} silhouette. "
        "Room front is the fixed scene reference, not the camera's current view. "
        f"The pelvis faces room {pose.pelvis_facing.replace('_', ' ')} and the "
        f"chest faces room {pose.facing.replace('_', ' ')}. "
        "Limb left and right always mean the subject's own anatomical sides, "
        "never image-frame sides. "
        f"{head} The eyes look {pose.gaze} relative to the head, not toward the lens. "
        f"The legs use {pose.legs.replace('_', ' ')}. {balance}"
        f"{_render_hand('left', pose.left_hand)} "
        f"{_render_hand('right', pose.right_hand)} {posture_detail}"
        f"{_render_support_layout(pose, presentation)} "
        f"The support chain is {supports}. "
        "All supporting furniture stays stable in its declared position. "
        f"{render_reference_camera(camera)} "
        "Show the face, action-relevant hands and accessible contact boundaries. "
        "Allow natural overlap of crossed legs and hidden undersides of contacts; "
        "do not expose them by moving supports or adding limbs. "
        "Preserve the declared body orientation and "
        "support chain; place the camera toward the visible side of the face "
        "rather than twisting the head toward the lens."
    )


def sample_pose_references(
    library: NeutralPoseLibrary,
    *,
    seed: int,
    count: int = 12,
    family: str | None = None,
    subject_id: str | None = None,
    presentation_id: str | None = None,
    history: ReferenceUsage | None = None,
) -> PoseReferenceBatch:
    fingerprint = library.fingerprint()
    history = (
        ReferenceUsage(catalog_fingerprint=fingerprint) if history is None else history
    )
    if history.catalog_fingerprint != fingerprint:
        raise ValueError("reference history belongs to a different catalog definition")
    subjects = {subject.subject_id: subject for subject in library.subjects}
    if subject_id is not None and subject_id not in subjects:
        raise ValueError(f"unknown reference subject: {subject_id}")
    identity_rng = random.Random(seed)
    subject = subjects[
        subject_id if subject_id is not None else identity_rng.choice(sorted(subjects))
    ]
    if presentation_id is not None and presentation_id not in {
        presentation.presentation_id for presentation in library.presentations
    }:
        raise ValueError(f"unknown reference presentation: {presentation_id}")
    if (
        not set(history.pose_counts).issubset(pose.pose_id for pose in library.poses)
        or not set(history.camera_counts).issubset(c.camera_id for c in library.cameras)
        or not set(history.presentation_counts).issubset(
            p.presentation_id for p in library.presentations
        )
    ):
        raise ValueError("reference history contains unknown catalog IDs")
    candidates = sorted(
        (pose for pose in library.poses if family is None or pose.family == family),
        key=lambda pose: pose.pose_id,
    )
    if not candidates:
        raise ValueError(f"unknown reference pose family: {family}")
    options: dict[str, list[tuple[ReferenceCamera, ReferencePresentation]]] = {}
    rejections: dict[tuple[str, str], ReferenceGeometryRejection] = {}
    for pose in candidates:
        options[pose.pose_id] = []
        for camera, presentation in _presentation_options(
            library, pose, presentation_id
        ):
            try:
                compile_reference_geometry(pose, subject, presentation)
            except ReferenceGeometryError as exc:
                key = (pose.pose_id, presentation.presentation_id)
                rejections[key] = ReferenceGeometryRejection(
                    pose_id=pose.pose_id, subject_id=subject.subject_id,
                    presentation_id=presentation.presentation_id, report=exc.report,
                )
                continue
            options[pose.pose_id].append((camera, presentation))
    candidates = [pose for pose in candidates if options[pose.pose_id]]
    if not candidates:
        raise ValueError(
            "no reference poses fit the selected environment and cameras; "
            f"{len(rejections)} geometry configurations rejected"
        )
    if not 1 <= count <= len(candidates):
        raise ValueError(
            f"count must be between 1 and {len(candidates)}; "
            f"{len(rejections)} geometry configurations rejected"
        )
    rng = random.Random(seed)
    rng.shuffle(candidates)
    selected: list[NeutralPose] = []
    family_counts: Counter[str] = Counter()
    while len(selected) < count:
        pose = max(
            candidates,
            key=lambda candidate: (
                -family_counts[candidate.family],
                -history.pose_counts.get(candidate.pose_id, 0),
                min(
                    (structural_distance(candidate, previous) for previous in selected),
                    default=1.0,
                ),
            ),
        )
        selected.append(pose)
        family_counts[pose.family] += 1
        candidates.remove(pose)
    camera_counts = Counter(history.camera_counts)
    presentation_counts = Counter(history.presentation_counts)
    combination_counts = Counter(history.combination_counts)
    scenes: list[PoseReferenceScene] = []
    for pose in selected:
        compatible = list(options[pose.pose_id])
        rng.shuffle(compatible)
        camera, presentation = min(
            compatible,
            key=lambda option: (
                combination_counts[ReferenceChoice(
                    pose_id=pose.pose_id,
                    camera_id=option[0].camera_id,
                    presentation_id=option[1].presentation_id,
                ).fingerprint()],
                presentation_counts[option[1].presentation_id],
                camera_counts[option[0].camera_id],
            ),
        )
        scenes.append(PoseReferenceScene(
            pose=pose,
            camera=camera,
            subject=subject,
            presentation=presentation,
            geometry=compile_reference_geometry(pose, subject, presentation),
            prompt=render_pose_reference(pose, camera, subject, presentation),
        ))
        camera_counts[camera.camera_id] += 1
        presentation_counts[presentation.presentation_id] += 1
        combination_counts[_scene_choice(scenes[-1]).fingerprint()] += 1
    return PoseReferenceBatch(
        seed=seed,
        family_filter=family,
        presentation_filter=presentation_id,
        catalog_fingerprint=fingerprint,
        subject=subject,
        history_before=history,
        history_after=advance_reference_usage(
            history, tuple(_scene_choice(scene) for scene in scenes)
        ),
        scenes=tuple(scenes),
        report=describe_reference_scenes(tuple(scenes), history),
        geometry_rejections=tuple(rejections.values()),
    )
