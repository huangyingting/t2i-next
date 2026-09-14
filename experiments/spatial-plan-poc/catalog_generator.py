from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Annotated, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "catalogs"
Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActorSlot(StrictModel):
    slot_id: Identifier
    sex: Annotated[str, StringConstraints(pattern=r"^(female|male)$")]
    role: Identifier
    adult_only: bool


class ContactEndpoint(StrictModel):
    entity_id: Identifier
    region: Identifier


class ContactEdge(StrictModel):
    edge_id: Identifier
    source: ContactEndpoint
    target: ContactEndpoint
    state: Annotated[
        str,
        StringConstraints(pattern=r"^(external_contact|inserted)$"),
    ]
    screen_position: Identifier
    depth_plane: Identifier
    preferred_visibility: Annotated[
        str,
        StringConstraints(pattern=r"^(visible|occluded)$"),
    ]


class WearableProp(StrictModel):
    prop_id: Identifier
    owner_slot: Identifier
    category: Annotated[str, StringConstraints(pattern=r"^strap_on$")]
    mount_region: Annotated[str, StringConstraints(pattern=r"^pelvis$")]
    attachment: Annotated[str, StringConstraints(pattern=r"^pelvic_harness$")]
    orientation: Annotated[
        str,
        StringConstraints(pattern=r"^forward_from_owner_pelvis$"),
    ]
    harness_visibility: Annotated[str, StringConstraints(pattern=r"^visible$")]
    base_visibility: Annotated[str, StringConstraints(pattern=r"^visible$")]
    shaft_visibility: Annotated[
        str,
        StringConstraints(pattern=r"^partially_visible$"),
    ]


class HandheldProp(StrictModel):
    prop_id: Identifier
    controller_slot: Identifier
    category: Annotated[str, StringConstraints(pattern=r"^vibrator$")]
    grip_region: Annotated[str, StringConstraints(pattern=r"^right_hand$")]
    deployment: Annotated[
        str,
        StringConstraints(pattern=r"^external_surface_contact$"),
    ]
    orientation: Annotated[
        str,
        StringConstraints(pattern=r"^transverse_over_clitoral_surface$"),
    ]


class RestraintPlan(StrictModel):
    enabled: bool
    category: Identifier | None
    controller_slots: list[Identifier]
    restrained_slots: list[Identifier]
    body_regions: list[Identifier]
    equipment: list[Identifier]
    quick_release_visible: bool
    safeword_required: bool
    injury_required: bool


class ActivityTemplate(StrictModel):
    activity_id: Identifier
    activity_family: Identifier
    coverage_tags: list[Identifier] = Field(min_length=1, max_length=8)
    required_slots: list[Identifier] = Field(min_length=1, max_length=8)
    contact_edges: list[ContactEdge] = Field(min_length=1, max_length=6)
    handheld_props: list[HandheldProp] = Field(max_length=2)
    wearable_props: list[WearableProp] = Field(max_length=2)
    restraint: RestraintPlan
    compatible_pose_families: list[Identifier] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def activity_is_coherent(self) -> ActivityTemplate:
        occupied_endpoints: set[tuple[str, str]] = set()
        for edge in self.contact_edges:
            for endpoint in (edge.source, edge.target):
                key = (endpoint.entity_id, endpoint.region)
                if key in occupied_endpoints:
                    raise ValueError(f"contact endpoint assigned twice: {key}")
                occupied_endpoints.add(key)
        wearable_ids = [prop.prop_id for prop in self.wearable_props]
        if len(wearable_ids) != len(set(wearable_ids)):
            raise ValueError("wearable prop IDs must be unique")
        handheld_ids = [prop.prop_id for prop in self.handheld_props]
        if len(handheld_ids) != len(set(handheld_ids)):
            raise ValueError("handheld prop IDs must be unique")
        if set(wearable_ids).intersection(handheld_ids):
            raise ValueError("a prop cannot be both handheld and wearable")
        for prop in self.handheld_props:
            if prop.controller_slot not in self.required_slots:
                raise ValueError("handheld prop controller is not in required cast")
            matching_edges = [
                edge
                for edge in self.contact_edges
                if edge.source.entity_id == prop.prop_id
            ]
            if len(matching_edges) != 1:
                raise ValueError("handheld prop requires exactly one contact edge")
            edge = matching_edges[0]
            if (
                edge.source.region != "contact_surface"
                or edge.target.region != "clitoris"
                or edge.state != "external_contact"
            ):
                raise ValueError(
                    "clitoral vibrator must remain an external surface contact"
                )
        if self.activity_id == "vibrator_clitoral":
            if len(self.handheld_props) != 1:
                raise ValueError(
                    "vibrator_clitoral requires one controlled handheld prop"
                )
        elif self.handheld_props:
            raise ValueError(
                "handheld vibrator topology belongs only to vibrator_clitoral"
            )
        has_strap_on_tag = has_tag(self.activity_id, "strap_on")
        if (has_strap_on_tag and len(self.wearable_props) != 1) or (
            not has_strap_on_tag and self.wearable_props
        ):
            raise ValueError(
                "strap-on activities require exactly one explicit wearable prop"
            )
        for prop in self.wearable_props:
            if prop.owner_slot not in self.required_slots:
                raise ValueError("wearable prop owner is not in required cast")
            matching_edges = [
                edge
                for edge in self.contact_edges
                if edge.source.entity_id == prop.prop_id
            ]
            if len(matching_edges) != 1 or any(
                edge.source.region != "shaft" for edge in matching_edges
            ):
                raise ValueError(
                    "wearable prop must connect through its shaft endpoint"
                )
            if matching_edges[0].target.entity_id == prop.owner_slot:
                raise ValueError("wearable prop owner cannot also be its target")
        if any(
            endpoint.region == "strap_on"
            for edge in self.contact_edges
            for endpoint in (edge.source, edge.target)
        ):
            raise ValueError("strap-on is a wearable prop, not a body region")
        if self.restraint.enabled:
            if (
                not self.restraint.category
                or not self.restraint.equipment
                or not self.restraint.restrained_slots
                or not self.restraint.quick_release_visible
                or not self.restraint.safeword_required
                or self.restraint.injury_required
            ):
                raise ValueError("BDSM activities require reversible safety metadata")
        elif any(
            (
                self.restraint.category,
                self.restraint.controller_slots,
                self.restraint.restrained_slots,
                self.restraint.body_regions,
                self.restraint.equipment,
                self.restraint.quick_release_visible,
                self.restraint.safeword_required,
                self.restraint.injury_required,
            )
        ):
            raise ValueError("non-BDSM activities cannot carry restraint metadata")
        return self


class CentralPose(StrictModel):
    family: Identifier
    variant: Identifier
    body_level: Identifier
    torso_orientation: Identifier
    pelvis_orientation: Identifier
    leg_configuration: Identifier
    arm_configuration: Identifier
    primary_surface: Identifier
    support_points: list[Identifier] = Field(min_length=1, max_length=8)
    compatible_camera_views: list[Identifier] = Field(min_length=3, max_length=6)


class ActorPlan(StrictModel):
    slot_id: Identifier
    pose_role: Identifier
    screen_position: Identifier
    depth_plane: Identifier
    limb_roles: list[Identifier] = Field(min_length=2, max_length=8)
    support_points: list[Identifier] = Field(min_length=1, max_length=8)


class PoseEntry(StrictModel):
    pose_id: Identifier
    cast_key: Identifier
    central_slot: Identifier
    central_pose: CentralPose
    actor_plans: list[ActorPlan] = Field(min_length=1, max_length=8)
    compatible_activity_ids: list[Identifier] = Field(min_length=1, max_length=32)
    exact_cast: list[Identifier] = Field(min_length=1, max_length=8)
    consent_required: bool
    signature: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def entry_is_coherent(self) -> PoseEntry:
        plan_slots = [plan.slot_id for plan in self.actor_plans]
        if plan_slots != self.exact_cast:
            raise ValueError("actor plans must cover exact_cast in order")
        if self.central_slot not in self.exact_cast:
            raise ValueError("central slot is not in exact_cast")
        if not self.consent_required:
            raise ValueError("every catalog entry requires adult consent")
        return self


class PoseCatalog(StrictModel):
    schema_version: Annotated[str, StringConstraints(pattern=r"^2\.0$")]
    cast_key: Identifier
    cast_slots: list[ActorSlot] = Field(min_length=1, max_length=8)
    requested_entry_count: int
    activities: list[ActivityTemplate] = Field(min_length=32, max_length=32)
    entries: list[PoseEntry]
    coverage: dict[str, dict[str, int] | int]

    @model_validator(mode="after")
    def catalog_has_exact_coverage(self) -> PoseCatalog:
        if self.requested_entry_count != 256 or len(self.entries) != 256:
            raise ValueError("each catalog must contain exactly 256 entries")
        expected_slots = [slot.slot_id for slot in self.cast_slots]
        if not all(slot.adult_only for slot in self.cast_slots):
            raise ValueError("all actor slots must be adult-only")
        pose_ids = [entry.pose_id for entry in self.entries]
        if len(pose_ids) != len(set(pose_ids)):
            raise ValueError("pose IDs must be unique")
        signatures = [entry.signature for entry in self.entries]
        if len(signatures) != len(set(signatures)):
            raise ValueError("central pose signatures must be unique")
        central_topologies = {
            (
                entry.central_pose.family,
                entry.central_pose.variant,
                tuple(entry.central_pose.support_points),
            )
            for entry in self.entries
        }
        if len(central_topologies) != 256:
            raise ValueError("catalog requires 256 unique central pose topologies")
        if any(
            entry.cast_key != self.cast_key or entry.exact_cast != expected_slots
            for entry in self.entries
        ):
            raise ValueError("entry cast differs from catalog cast")
        family_counts = Counter(entry.central_pose.family for entry in self.entries)
        if len(family_counts) != 16 or set(family_counts.values()) != {16}:
            raise ValueError("catalog requires 16 families with 16 poses each")
        activity_ids = [activity.activity_id for activity in self.activities]
        if len(activity_ids) != len(set(activity_ids)):
            raise ValueError("catalog activity IDs must be unique")
        if sum(activity.restraint.enabled for activity in self.activities) != 8:
            raise ValueError("catalog requires exactly eight BDSM activity templates")
        activity_map = {activity.activity_id: activity for activity in self.activities}
        used_activities: set[str] = set()
        for entry in self.entries:
            compatible = set(entry.compatible_activity_ids)
            if not compatible or not compatible.issubset(activity_map):
                raise ValueError(f"{entry.pose_id} has unknown compatible activities")
            if any(
                entry.central_pose.family
                not in activity_map[activity_id].compatible_pose_families
                for activity_id in compatible
            ):
                raise ValueError(f"{entry.pose_id} has incompatible activities")
            used_activities.update(compatible)
        if used_activities != set(activity_ids):
            raise ValueError("every activity must be reachable from at least one pose")
        actor_sexes = {slot.slot_id: slot.sex for slot in self.cast_slots}
        valid_entities = set(expected_slots) | {
            "prop_a",
            "prop_b",
            "environment",
        }
        for activity in self.activities:
            if activity.required_slots != expected_slots:
                raise ValueError(f"{activity.activity_id} required cast changed")
            for edge in activity.contact_edges:
                for endpoint in (edge.source, edge.target):
                    if endpoint.entity_id not in valid_entities:
                        raise ValueError(
                            f"{activity.activity_id} uses unknown entity "
                            f"{endpoint.entity_id}"
                        )
                    sex = actor_sexes.get(endpoint.entity_id)
                    if sex == "female" and endpoint.region == "penis":
                        raise ValueError("female actor cannot own a penis region")
                    if sex == "male" and endpoint.region in {
                        "clitoris",
                        "vagina",
                        "vulva",
                    }:
                        raise ValueError(f"male actor cannot own {endpoint.region}")
            regions = {
                endpoint.region
                for edge in activity.contact_edges
                for endpoint in (edge.source, edge.target)
            }
            entities = {
                endpoint.entity_id
                for edge in activity.contact_edges
                for endpoint in (edge.source, edge.target)
            }
            if "penetration" in activity.coverage_tags and not any(
                edge.state == "inserted" for edge in activity.contact_edges
            ):
                raise ValueError(f"{activity.activity_id} lacks an inserted contact")
            if "oral" in activity.coverage_tags and "mouth" not in regions:
                raise ValueError(f"{activity.activity_id} lacks an oral endpoint")
            if "toy" in activity.coverage_tags and not {
                "prop_a",
                "prop_b",
            }.intersection(entities):
                raise ValueError(f"{activity.activity_id} lacks a toy entity")
            semantic_regions = {
                "vaginal": "vagina",
                "anal": "anus",
                "fellatio": "penis",
                "cunnilingus": "vulva",
            }
            for token, required_region in semantic_regions.items():
                if (
                    has_tag(activity.activity_id, token)
                    and required_region not in regions
                ):
                    raise ValueError(f"{activity.activity_id} lacks {required_region}")
            if has_tag(activity.activity_id, "strap_on"):
                if len(activity.wearable_props) != 1:
                    raise ValueError(
                        f"{activity.activity_id} lacks one wearable strap-on"
                    )
                prop = activity.wearable_props[0]
                if prop.prop_id not in entities or "shaft" not in regions:
                    raise ValueError(
                        f"{activity.activity_id} lacks a mounted shaft contact"
                    )
        catalog_tags = {
            tag for activity in self.activities for tag in activity.coverage_tags
        }
        required_tags = {"masturbation", "toy", "bdsm", "penetration"}
        if self.cast_key != "one_woman":
            required_tags.add("oral")
        if not required_tags.issubset(catalog_tags):
            raise ValueError(
                f"catalog is missing coverage tags: {required_tags - catalog_tags}"
            )
        return self


class PoseFamily(NamedTuple):
    body_level: str
    torso: str
    pelvis: str
    surface: str
    supports: tuple[str, ...]
    legs: tuple[str, ...]
    arms: tuple[str, ...]
    cameras: tuple[str, ...]


CAMERAS = (
    "front_three_quarter",
    "rear_three_quarter",
    "side_three_quarter",
    "high_three_quarter",
    "low_three_quarter",
    "overhead_three_quarter",
)

POSE_FAMILIES: dict[str, PoseFamily] = {
    "supine": PoseFamily(
        "low",
        "horizontal_up",
        "neutral",
        "bed",
        ("back", "pelvis"),
        ("knees_bent_wide", "legs_extended_v", "knees_to_chest", "legs_vertical"),
        ("arms_beside", "arms_overhead", "arms_outward", "hands_on_thighs"),
        CAMERAS[:4],
    ),
    "prone": PoseFamily(
        "low",
        "horizontal_down",
        "neutral",
        "bed",
        ("chest", "abdomen", "thighs"),
        ("legs_together", "legs_wide", "one_knee_drawn", "diamond_bent"),
        ("arms_forward", "arms_folded", "arms_beside", "hands_grip_edge"),
        CAMERAS[1:5],
    ),
    "side_lying_left": PoseFamily(
        "low",
        "horizontal_left",
        "side_tilted",
        "bed",
        ("left_shoulder", "left_hip", "left_thigh"),
        ("knees_stacked", "top_leg_bent", "fetal_tuck", "top_leg_raised"),
        ("lower_arm_forward", "upper_arm_overhead", "upper_hand_hip", "arms_folded"),
        CAMERAS[:4],
    ),
    "side_lying_right": PoseFamily(
        "low",
        "horizontal_right",
        "side_tilted",
        "bed",
        ("right_shoulder", "right_hip", "right_thigh"),
        ("knees_stacked", "top_leg_bent", "fetal_tuck", "top_leg_raised"),
        ("lower_arm_forward", "upper_arm_overhead", "upper_hand_hip", "arms_folded"),
        CAMERAS[:4],
    ),
    "all_fours": PoseFamily(
        "middle",
        "horizontal_down",
        "raised",
        "bed",
        ("both_knees", "both_hands"),
        ("knees_narrow", "knees_wide", "one_knee_forward", "toes_planted"),
        ("hands_straight", "elbows_soft", "one_hand_headboard", "hands_wide"),
        CAMERAS[1:],
    ),
    "kneeling_upright": PoseFamily(
        "middle",
        "vertical",
        "neutral",
        "bed",
        ("both_knees", "both_shins"),
        ("knees_together", "knees_wide", "frog_kneel", "one_foot_planted"),
        ("hands_thighs", "arms_overhead", "hands_behind", "arms_outward"),
        CAMERAS,
    ),
    "kneeling_forward": PoseFamily(
        "middle",
        "diagonal_down",
        "raised",
        "bed",
        ("both_knees", "forearms"),
        ("knees_together", "knees_wide", "frog_kneel", "one_knee_forward"),
        ("forearms_parallel", "arms_extended", "one_hand_headboard", "hands_wall"),
        CAMERAS[1:],
    ),
    "seated_upright": PoseFamily(
        "middle",
        "vertical",
        "forward_tilt",
        "chair",
        ("buttocks", "both_feet"),
        ("knees_together", "knees_wide", "legs_extended", "ankles_crossed"),
        ("hands_thighs", "hands_behind", "arms_overhead", "one_hand_chair"),
        CAMERAS[:5],
    ),
    "seated_reclined": PoseFamily(
        "middle",
        "diagonal_back",
        "forward_tilt",
        "sofa",
        ("buttocks", "upper_back", "both_feet"),
        ("knees_bent", "knees_wide", "one_leg_raised", "legs_extended"),
        ("elbows_support", "hands_behind", "arms_outward", "one_hand_thigh"),
        CAMERAS[:5],
    ),
    "seated_edge": PoseFamily(
        "middle",
        "vertical",
        "edge_tilted",
        "bed_edge",
        ("buttocks", "both_feet"),
        ("knees_wide", "one_leg_extended", "feet_staggered", "ankles_crossed"),
        ("hands_edge", "hands_thighs", "arms_overhead", "one_arm_reaching"),
        CAMERAS[:5],
    ),
    "standing_upright": PoseFamily(
        "high",
        "vertical",
        "neutral",
        "floor",
        ("both_feet",),
        ("feet_together", "feet_wide", "staggered_stance", "one_knee_raised"),
        ("arms_beside", "arms_overhead", "hands_wall", "hands_behind"),
        CAMERAS,
    ),
    "standing_bent": PoseFamily(
        "high",
        "horizontal_forward",
        "rearward",
        "floor",
        ("both_feet",),
        ("feet_together", "feet_wide", "staggered_stance", "tiptoe_stance"),
        ("hands_knees", "hands_wall", "hands_furniture", "arms_hanging"),
        CAMERAS[1:],
    ),
    "standing_wall_supported": PoseFamily(
        "high",
        "vertical",
        "forward_tilt",
        "wall",
        ("both_feet", "back"),
        ("feet_together", "feet_wide", "one_leg_raised", "ankles_crossed"),
        ("palms_wall", "arms_overhead", "hands_behind", "one_hand_wall"),
        CAMERAS[:5],
    ),
    "deep_squat": PoseFamily(
        "low",
        "vertical",
        "lowered",
        "floor",
        ("both_feet",),
        ("heels_flat", "heels_raised", "feet_wide", "staggered_squat"),
        ("hands_knees", "arms_forward", "hands_behind", "one_hand_floor"),
        CAMERAS[:5],
    ),
    "lifted_supported": PoseFamily(
        "high",
        "vertical",
        "elevated",
        "partner_support",
        ("partner_arms", "wall"),
        ("legs_wrapped", "knees_bent_wide", "one_leg_hooked", "thighs_supported"),
        ("arms_shoulders", "hands_wall", "arms_overhead", "one_arm_partner"),
        CAMERAS,
    ),
    "bridge_elevated": PoseFamily(
        "low",
        "arched_up",
        "elevated",
        "bed",
        ("shoulders", "both_feet"),
        ("knees_bent", "knees_wide", "one_leg_extended", "feet_elevated"),
        ("arms_beside", "arms_overhead", "hands_hips", "hands_grip_edge"),
        CAMERAS[:5],
    ),
}


def edge(
    edge_id: str,
    source_entity: str,
    source_region: str,
    target_entity: str,
    target_region: str,
    state: str,
) -> tuple[str, str, str, str, str, str]:
    return (
        edge_id,
        source_entity,
        source_region,
        target_entity,
        target_region,
        state,
    )


SOLO_ACTIVITIES = (
    "manual_clitoral",
    "manual_vaginal",
    "manual_anal",
    "dual_manual",
    "vibrator_clitoral",
    "wand_external",
    "dildo_vaginal",
    "dildo_anal",
    "dual_toy_vaginal_clitoral",
    "anal_plug_clitoral",
    "nipple_clitoral",
    "mirror_masturbation",
    "shower_masturbation",
    "chair_masturbation",
    "bed_edge_masturbation",
    "standing_wall_masturbation",
    "prone_toy_grinding",
    "pillow_grinding",
    "thigh_squeeze",
    "breast_self_touch",
    "suction_toy",
    "remote_toy",
    "stability_ball_toy",
    "wedge_supported_toy",
    "blindfolded_manual",
    "wrist_cuffs_quick_release",
    "ankle_cuffs_quick_release",
    "spreader_bar_self_play",
    "collar_leash_self_pose",
    "rope_harness_self_touch",
    "low_temp_wax_sensory",
    "ice_sensory",
)

PAIR_WM_ACTIVITIES = (
    "vaginal_face_to_face",
    "vaginal_rear_entry",
    "vaginal_side_lying",
    "vaginal_seated",
    "vaginal_standing",
    "vaginal_lifted",
    "anal_rear_entry",
    "anal_side_lying",
    "cunnilingus",
    "fellatio",
    "mutual_oral",
    "manual_clitoral",
    "manual_penile",
    "mutual_masturbation",
    "breast_licking",
    "nipple_manual",
    "pubic_grinding",
    "toy_vaginal",
    "toy_anal",
    "dual_toy",
    "edging_manual",
    "mirror_mutual",
    "shower_mutual",
    "chair_mutual",
    "wrist_bondage_oral",
    "ankle_bondage_penetration",
    "spreader_bar_manual",
    "blindfold_sensory",
    "collar_guided_kneeling",
    "impact_over_furniture",
    "rope_harness_partial_suspension",
    "low_temp_wax_sensory",
)

PAIR_WW_ACTIVITIES = (
    "strap_on_vaginal_face_to_face",
    "strap_on_vaginal_rear_entry",
    "strap_on_vaginal_side_lying",
    "strap_on_vaginal_seated",
    "strap_on_vaginal_standing",
    "strap_on_vaginal_lifted",
    "strap_on_anal_rear_entry",
    "strap_on_anal_side_lying",
    "cunnilingus_receiving",
    "cunnilingus_giving",
    "mutual_oral",
    "manual_clitoral_receiving",
    "manual_clitoral_giving",
    "mutual_masturbation",
    "breast_licking",
    "nipple_manual",
    "tribadism",
    "toy_vaginal",
    "toy_anal",
    "dual_toy",
    "edging_manual",
    "mirror_mutual",
    "shower_mutual",
    "chair_mutual",
    "wrist_bondage_oral",
    "ankle_bondage_strap_on",
    "spreader_bar_manual",
    "blindfold_sensory",
    "collar_guided_kneeling",
    "impact_over_furniture",
    "rope_harness_partial_suspension",
    "low_temp_wax_sensory",
)

GROUP_WM2_ACTIVITIES = (
    "vaginal_plus_fellatio",
    "anal_plus_fellatio",
    "double_penetration_vaginal_anal",
    "vaginal_plus_manual",
    "anal_plus_manual",
    "dual_oral_on_woman",
    "woman_oral_one_manual_other",
    "woman_manual_both_men",
    "oral_and_manual_on_woman",
    "supported_standing_penetration",
    "lifted_group_penetration",
    "side_lying_group",
    "seated_group",
    "kneeling_group",
    "penetration_plus_breast_stimulation",
    "oral_plus_breast_stimulation",
    "toy_plus_oral",
    "toy_plus_manual",
    "mirrored_dual_manual",
    "crossed_support_group",
    "sofa_group",
    "shower_group",
    "wall_supported_group",
    "bed_edge_group",
    "dual_controller_wrist_bondage",
    "spreader_bar_double_stimulation",
    "blindfold_group_sensory",
    "collar_guided_group_kneeling",
    "impact_and_manual_group",
    "rope_harness_group_support",
    "low_temp_wax_and_oral",
    "cuffs_double_penetration",
)

GROUP_WWW_ACTIVITIES = (
    "strap_on_vaginal_plus_oral",
    "strap_on_anal_plus_oral",
    "double_toy_vaginal_anal",
    "strap_on_vaginal_plus_manual",
    "strap_on_anal_plus_manual",
    "dual_cunnilingus",
    "central_oral_one_manual_other",
    "central_manual_both_partners",
    "oral_and_manual_on_central",
    "supported_standing_strap_on",
    "lifted_group_strap_on",
    "side_lying_group",
    "seated_group",
    "kneeling_group",
    "strap_on_plus_breast_stimulation",
    "oral_plus_breast_stimulation",
    "toy_plus_oral",
    "toy_plus_manual",
    "mirrored_dual_manual",
    "crossed_support_group",
    "sofa_group",
    "shower_group",
    "wall_supported_group",
    "bed_edge_group",
    "dual_controller_wrist_bondage",
    "spreader_bar_double_stimulation",
    "blindfold_group_sensory",
    "collar_guided_group_kneeling",
    "impact_and_manual_group",
    "rope_harness_group_support",
    "low_temp_wax_and_oral",
    "cuffs_double_toy_penetration",
)

BDSM_EQUIPMENT = (
    "blindfold",
    "plush_wrist_cuffs",
    "plush_ankle_cuffs",
    "padded_spreader_bar",
    "quick_release_collar",
    "soft_rope_harness",
    "low_temperature_candle",
    "ice_cube",
)


CASTS = {
    "one_woman": (("f1", "female", "central"),),
    "one_woman_one_man": (
        ("f1", "female", "central"),
        ("m1", "male", "partner"),
    ),
    "one_woman_two_men": (
        ("f1", "female", "central"),
        ("m1", "male", "partner"),
        ("m2", "male", "partner"),
    ),
    "two_women": (
        ("f1", "female", "central"),
        ("f2", "female", "partner"),
    ),
    "three_women": (
        ("f1", "female", "central"),
        ("f2", "female", "partner"),
        ("f3", "female", "partner"),
    ),
}

LOGICAL_ACTOR_ROLES = ("central", "partner_a", "partner_b")


def resolve_actor_role(cast_key: str, entity_id: str) -> str:
    if entity_id not in LOGICAL_ACTOR_ROLES:
        return entity_id
    index = LOGICAL_ACTOR_ROLES.index(entity_id)
    cast = CASTS[cast_key]
    if index >= len(cast):
        raise ValueError(f"{cast_key} has no actor for {entity_id}")
    return cast[index][0]


def activity_ids(cast_key: str) -> tuple[str, ...]:
    if cast_key == "one_woman":
        return SOLO_ACTIVITIES
    if cast_key == "one_woman_one_man":
        return PAIR_WM_ACTIVITIES
    if cast_key == "two_women":
        return PAIR_WW_ACTIVITIES
    if cast_key == "one_woman_two_men":
        return GROUP_WM2_ACTIVITIES
    return GROUP_WWW_ACTIVITIES


def has_tag(activity_id: str, *tags: str) -> bool:
    parts = activity_id.split("_")
    for tag in tags:
        tag_parts = tag.split("_")
        width = len(tag_parts)
        if any(
            parts[index : index + width] == tag_parts
            for index in range(len(parts) - width + 1)
        ):
            return True
    return False


def activity_family(activity_id: str) -> str:
    if has_tag(
        activity_id,
        "bondage",
        "blindfold",
        "blindfolded",
        "collar",
        "cuffs",
        "impact",
        "rope_harness",
        "spreader_bar",
        "wax",
        "ice_sensory",
    ):
        return "bdsm"
    if has_tag(activity_id, "vaginal", "anal", "penetration"):
        return "penetration"
    if has_tag(activity_id, "oral", "fellatio", "cunnilingus"):
        return "oral"
    if has_tag(activity_id, "manual", "masturbation", "edging"):
        return "masturbation"
    if has_tag(activity_id, "toy", "plug", "vibrator", "wand"):
        return "toy"
    return "body_contact"


def activity_tags(activity_id: str) -> list[str]:
    tags: set[str] = set()
    family = activity_family(activity_id)
    tags.add(family)
    if has_tag(
        activity_id,
        "vaginal",
        "anal",
        "penetration",
        "strap_on",
        "dildo",
        "plug",
    ):
        tags.add("penetration")
    if has_tag(activity_id, "oral", "fellatio", "cunnilingus", "licking"):
        tags.add("oral")
    if has_tag(
        activity_id,
        "manual",
        "masturbation",
        "edging",
        "self_touch",
        "self_play",
        "grinding",
        "squeeze",
    ):
        tags.add("masturbation")
    if has_tag(
        activity_id,
        "toy",
        "dildo",
        "plug",
        "vibrator",
        "wand",
        "suction",
        "remote",
    ):
        tags.add("toy")
    if activity_family(activity_id) == "bdsm":
        tags.add("bdsm")
    return sorted(tags)


def contact_specs(
    cast_key: str,
    activity_id: str,
) -> list[tuple[str, str, str, str, str, str]]:
    if cast_key == "one_woman":
        if activity_id == "dual_manual":
            return [
                edge(
                    "primary",
                    "central",
                    "left_hand",
                    "central",
                    "clitoris",
                    "external_contact",
                ),
                edge(
                    "secondary",
                    "central",
                    "right_hand",
                    "central",
                    "vagina",
                    "inserted",
                ),
            ]
        if activity_id in {"dual_toy_vaginal_clitoral", "anal_plug_clitoral"}:
            inserted_region = "anus" if has_tag(activity_id, "anal") else "vagina"
            return [
                edge(
                    "primary",
                    "prop_a",
                    "contact_surface",
                    "central",
                    inserted_region,
                    "inserted",
                ),
                edge(
                    "secondary",
                    "central",
                    "hand",
                    "central",
                    "clitoris",
                    "external_contact",
                ),
            ]
        if activity_id == "nipple_clitoral":
            return [
                edge(
                    "primary",
                    "central",
                    "left_hand",
                    "central",
                    "clitoris",
                    "external_contact",
                ),
                edge(
                    "secondary",
                    "central",
                    "right_hand",
                    "central",
                    "breast",
                    "external_contact",
                ),
            ]
        if activity_id in {"low_temp_wax_sensory", "ice_sensory"}:
            return [
                edge(
                    "primary",
                    "prop_a",
                    "contact_surface",
                    "central",
                    "torso",
                    "external_contact",
                )
            ]
        if activity_id == "wrist_cuffs_quick_release":
            return [
                edge(
                    "primary",
                    "prop_a",
                    "vibrator_surface",
                    "central",
                    "clitoris",
                    "external_contact",
                )
            ]
        target_region = (
            "anus"
            if has_tag(activity_id, "anal", "plug")
            else "vagina"
            if has_tag(activity_id, "vaginal", "dildo")
            else "clitoris"
        )
        source_entity = (
            "prop_a"
            if has_tag(
                activity_id,
                "toy",
                "plug",
                "vibrator",
                "wand",
                "dildo",
                "suction",
                "remote",
                "wax",
                "ice",
            )
            else "central"
        )
        source_region = "contact_surface" if source_entity == "prop_a" else "hand"
        state = (
            "inserted" if target_region in {"vagina", "anus"} else "external_contact"
        )
        return [
            edge(
                "primary",
                source_entity,
                source_region,
                "central",
                target_region,
                state,
            )
        ]

    partner_is_male = CASTS[cast_key][1][1] == "male"
    penetration_source = "partner_a" if partner_is_male else "prop_a"
    penetration_region = "penis" if partner_is_male else "shaft"
    if len(CASTS[cast_key]) == 2:
        if has_tag(activity_id, "cunnilingus"):
            if activity_id.endswith("giving"):
                return [
                    edge(
                        "primary",
                        "central",
                        "mouth",
                        "partner_a",
                        "vulva",
                        "external_contact",
                    )
                ]
            return [
                edge(
                    "primary",
                    "partner_a",
                    "mouth",
                    "central",
                    "vulva",
                    "external_contact",
                )
            ]
        if activity_id == "fellatio":
            return [
                edge(
                    "primary",
                    "central",
                    "mouth",
                    "partner_a",
                    penetration_region,
                    "inserted",
                )
            ]
        if activity_id == "mutual_oral":
            second_target = "penis" if partner_is_male else "vulva"
            return [
                edge(
                    "primary",
                    "partner_a",
                    "mouth",
                    "central",
                    "vulva",
                    "external_contact",
                ),
                edge(
                    "secondary",
                    "central",
                    "mouth",
                    "partner_a",
                    second_target,
                    "inserted" if partner_is_male else "external_contact",
                ),
            ]
        if activity_id == "mutual_masturbation" or has_tag(
            activity_id,
            "mirror_mutual",
            "shower_mutual",
        ):
            return [
                edge(
                    "primary",
                    "central",
                    "hand",
                    "central",
                    "clitoris",
                    "external_contact",
                ),
                edge(
                    "secondary",
                    "partner_a",
                    "hand",
                    "partner_a",
                    "penis" if partner_is_male else "clitoris",
                    "external_contact",
                ),
            ]
        if activity_id == "manual_penile":
            return [
                edge(
                    "primary",
                    "central",
                    "hand",
                    "partner_a",
                    "penis",
                    "external_contact",
                )
            ]
        if has_tag(activity_id, "manual_clitoral_giving"):
            return [
                edge(
                    "primary",
                    "central",
                    "hand",
                    "partner_a",
                    "clitoris",
                    "external_contact",
                )
            ]
        if has_tag(
            activity_id,
            "manual_clitoral",
            "edging_manual",
            "spreader_bar_manual",
        ):
            return [
                edge(
                    "primary",
                    "partner_a",
                    "hand",
                    "central",
                    "clitoris",
                    "external_contact",
                )
            ]
        if has_tag(activity_id, "toy"):
            target = "anus" if has_tag(activity_id, "anal") else "vagina"
            if has_tag(activity_id, "dual_toy"):
                return [
                    edge(
                        "primary",
                        "prop_a",
                        "contact_surface",
                        "central",
                        target,
                        "inserted",
                    ),
                    edge(
                        "secondary",
                        "prop_b",
                        "contact_surface",
                        "partner_a",
                        "clitoris" if not partner_is_male else "penis",
                        "external_contact",
                    ),
                ]
            return [
                edge(
                    "primary",
                    "prop_a",
                    "contact_surface",
                    "central",
                    target,
                    "inserted",
                )
            ]
        if has_tag(activity_id, "anal"):
            return [
                edge(
                    "primary",
                    penetration_source,
                    penetration_region,
                    "central",
                    "anus",
                    "inserted",
                )
            ]
        if has_tag(
            activity_id,
            "vaginal",
            "strap_on",
            "penetration",
        ):
            return [
                edge(
                    "primary",
                    penetration_source,
                    penetration_region,
                    "central",
                    "vagina",
                    "inserted",
                )
            ]
        if has_tag(activity_id, "wrist_bondage_oral"):
            if partner_is_male:
                return [
                    edge(
                        "primary",
                        "central",
                        "mouth",
                        "partner_a",
                        "penis",
                        "inserted",
                    )
                ]
            return [
                edge(
                    "primary",
                    "partner_a",
                    "mouth",
                    "central",
                    "vulva",
                    "external_contact",
                )
            ]
        if has_tag(activity_id, "oral"):
            return [
                edge(
                    "primary",
                    "partner_a",
                    "mouth",
                    "central",
                    "vulva",
                    "external_contact",
                )
            ]
        if has_tag(activity_id, "tribadism", "grinding"):
            target = "vulva" if not partner_is_male else "pubic_region"
            return [
                edge(
                    "primary",
                    "central",
                    "pubic_region",
                    "partner_a",
                    target,
                    "external_contact",
                )
            ]
        if has_tag(activity_id, "breast", "nipple"):
            source_region = "mouth" if has_tag(activity_id, "licking") else "hand"
            return [
                edge(
                    "primary",
                    "partner_a",
                    source_region,
                    "central",
                    "breast",
                    "external_contact",
                )
            ]
        if has_tag(activity_id, "low_temp_wax"):
            return [
                edge(
                    "primary",
                    "prop_a",
                    "contact_surface",
                    "central",
                    "torso",
                    "external_contact",
                )
            ]
        if has_tag(activity_id, "impact"):
            target_region = "buttock"
        elif has_tag(activity_id, "collar", "rope_harness"):
            target_region = "torso"
        else:
            target_region = "clitoris"
        return [
            edge(
                "primary",
                "partner_a",
                "hand",
                "central",
                target_region,
                "external_contact",
            )
        ]

    partner_a_region = "penis" if cast_key == "one_woman_two_men" else "shaft"
    partner_b_region = partner_a_region
    source_a = "partner_a" if cast_key == "one_woman_two_men" else "prop_a"
    source_b = "partner_b" if cast_key == "one_woman_two_men" else "prop_b"
    if has_tag(activity_id, "double") and has_tag(
        activity_id,
        "penetration",
        "toy",
    ):
        if has_tag(activity_id, "toy"):
            source_a = "prop_a"
            source_b = "prop_b"
            partner_a_region = "contact_surface"
            partner_b_region = "contact_surface"
        return [
            edge(
                "primary",
                source_a,
                partner_a_region,
                "central",
                "vagina",
                "inserted",
            ),
            edge(
                "secondary",
                source_b,
                partner_b_region,
                "central",
                "anus",
                "inserted",
            ),
        ]
    if has_tag(activity_id, "toy_plus"):
        secondary_region = "mouth" if has_tag(activity_id, "oral") else "hand"
        return [
            edge(
                "primary",
                "prop_a",
                "contact_surface",
                "central",
                "vagina",
                "inserted",
            ),
            edge(
                "secondary",
                "partner_b",
                secondary_region,
                "central",
                "clitoris" if secondary_region == "mouth" else "breast",
                "external_contact",
            ),
        ]
    if has_tag(activity_id, "anal"):
        secondary_is_oral = has_tag(activity_id, "fellatio") or has_tag(
            activity_id, "plus_oral"
        )
        if secondary_is_oral and cast_key == "one_woman_two_men":
            secondary_source = "central"
            secondary_target = "partner_b"
            secondary_target_region = "penis"
            secondary_state = "inserted"
        else:
            secondary_source = "partner_b"
            secondary_target = "central"
            secondary_target_region = "clitoris" if secondary_is_oral else "breast"
            secondary_state = "external_contact"
        return [
            edge("primary", source_a, partner_a_region, "central", "anus", "inserted"),
            edge(
                "secondary",
                secondary_source,
                "mouth" if secondary_is_oral else "hand",
                secondary_target,
                secondary_target_region,
                secondary_state,
            ),
        ]
    if has_tag(
        activity_id,
        "vaginal",
        "strap_on",
        "penetration",
    ):
        secondary_is_oral = has_tag(
            activity_id,
            "fellatio",
            "plus_oral",
        )
        if secondary_is_oral and cast_key == "one_woman_two_men":
            secondary_source = "central"
            secondary_target = "partner_b"
            secondary_target_region = "penis"
            secondary_state = "inserted"
        else:
            secondary_source = "partner_b"
            secondary_target = "central"
            secondary_target_region = "clitoris" if secondary_is_oral else "breast"
            secondary_state = "external_contact"
        return [
            edge(
                "primary",
                source_a,
                partner_a_region,
                "central",
                "vagina",
                "inserted",
            ),
            edge(
                "secondary",
                secondary_source,
                "mouth" if secondary_is_oral else "hand",
                secondary_target,
                secondary_target_region,
                secondary_state,
            ),
        ]
    if has_tag(activity_id, "dual_oral", "dual_cunnilingus"):
        return [
            edge(
                "primary",
                "partner_a",
                "mouth",
                "central",
                "vulva",
                "external_contact",
            ),
            edge(
                "secondary",
                "partner_b",
                "mouth",
                "central",
                "clitoris",
                "external_contact",
            ),
        ]
    if has_tag(activity_id, "oral_one_manual_other"):
        target_region = "penis" if cast_key == "one_woman_two_men" else "vulva"
        return [
            edge(
                "primary",
                "central",
                "mouth",
                "partner_a",
                target_region,
                "inserted" if cast_key == "one_woman_two_men" else "external_contact",
            ),
            edge(
                "secondary",
                "central",
                "left_hand",
                "partner_b",
                partner_b_region,
                "external_contact",
            ),
        ]
    if has_tag(activity_id, "manual_both"):
        target_region = "penis" if cast_key == "one_woman_two_men" else "clitoris"
        return [
            edge(
                "primary",
                "central",
                "left_hand",
                "partner_a",
                target_region,
                "external_contact",
            ),
            edge(
                "secondary",
                "central",
                "right_hand",
                "partner_b",
                target_region,
                "external_contact",
            ),
        ]
    return [
        edge(
            "primary",
            "partner_a",
            "mouth",
            "central",
            "vulva",
            "external_contact",
        ),
        edge(
            "secondary",
            "partner_b",
            "hand",
            "central",
            "breast",
            "external_contact",
        ),
    ]


def restraint_plan(
    cast_key: str,
    activity_id: str,
) -> RestraintPlan:
    if activity_family(activity_id) != "bdsm":
        return RestraintPlan(
            enabled=False,
            category=None,
            controller_slots=[],
            restrained_slots=[],
            body_regions=[],
            equipment=[],
            quick_release_visible=False,
            safeword_required=False,
            injury_required=False,
        )
    equipment_index = next(
        (
            index
            for index, token in enumerate(
                (
                    "blindfold",
                    "wrist",
                    "ankle",
                    "spreader",
                    "collar",
                    "rope",
                    "wax",
                    "ice",
                )
            )
            if has_tag(activity_id, token)
        ),
        5 if has_tag(activity_id, "impact") else 0,
    )
    equipment = (
        "padded_paddle"
        if has_tag(activity_id, "impact")
        else BDSM_EQUIPMENT[equipment_index]
    )
    slots = [slot[0] for slot in CASTS[cast_key]]
    return RestraintPlan(
        enabled=True,
        category=activity_id,
        controller_slots=slots[1:] or [slots[0]],
        restrained_slots=[slots[0]],
        body_regions=(
            ["wrists"]
            if has_tag(activity_id, "wrist")
            else ["ankles"]
            if has_tag(activity_id, "ankle", "spreader")
            else ["torso"]
        ),
        equipment=[equipment],
        quick_release_visible=True,
        safeword_required=True,
        injury_required=False,
    )


def actor_plans(
    cast_key: str,
    family: PoseFamily,
) -> list[ActorPlan]:
    central_slot = CASTS[cast_key][0][0]
    plans = [
        ActorPlan(
            slot_id=central_slot,
            pose_role="central_pose",
            screen_position="center",
            depth_plane="midground",
            limb_roles=["pose_hold", "balance_support"],
            support_points=list(family.supports),
        )
    ]
    positions = ("center_left", "center_right")
    for index, (slot_id, _, _) in enumerate(CASTS[cast_key][1:]):
        plans.append(
            ActorPlan(
                slot_id=slot_id,
                pose_role=(
                    "supporting_central"
                    if family.surface == "partner_support" and index == 0
                    else "secondary_aligned_with_central"
                    if index == 1
                    else "aligned_with_central"
                ),
                screen_position=positions[index],
                depth_plane="midground" if index == 0 else "foreground",
                limb_roles=["primary_contact", "balance_support"],
                support_points=(
                    ["both_feet"]
                    if family.body_level == "high"
                    else ["both_knees", "both_hands"]
                ),
            )
        )
    return plans


def make_contact_edges(
    cast_key: str,
    activity_id: str,
    activity_index: int,
) -> list[ContactEdge]:
    specs = contact_specs(cast_key, activity_id)
    edges = []
    for edge_index, spec in enumerate(specs):
        (
            edge_id,
            source_entity,
            source_region,
            target_entity,
            target_region,
            state,
        ) = spec
        visibility = (
            "occluded"
            if state == "inserted" and (activity_index + edge_index) % 3
            else "visible"
        )
        edges.append(
            ContactEdge(
                edge_id=edge_id,
                source=ContactEndpoint(
                    entity_id=resolve_actor_role(cast_key, source_entity),
                    region=source_region,
                ),
                target=ContactEndpoint(
                    entity_id=resolve_actor_role(cast_key, target_entity),
                    region=target_region,
                ),
                state=state,
                screen_position="center",
                depth_plane="midground",
                preferred_visibility=visibility,
            )
        )
    return edges


def wearable_props(cast_key: str, activity_id: str) -> list[WearableProp]:
    if not has_tag(activity_id, "strap_on"):
        return []
    if cast_key not in {"two_women", "three_women"}:
        raise ValueError(
            f"{activity_id} has no eligible wearable prop owner in {cast_key}"
        )
    return [
        WearableProp(
            prop_id="prop_a",
            owner_slot=CASTS[cast_key][1][0],
            category="strap_on",
            mount_region="pelvis",
            attachment="pelvic_harness",
            orientation="forward_from_owner_pelvis",
            harness_visibility="visible",
            base_visibility="visible",
            shaft_visibility="partially_visible",
        )
    ]


def handheld_props(cast_key: str, activity_id: str) -> list[HandheldProp]:
    if activity_id != "vibrator_clitoral":
        return []
    if cast_key != "one_woman":
        raise ValueError(f"{activity_id} has no unambiguous controller in {cast_key}")
    return [
        HandheldProp(
            prop_id="prop_a",
            controller_slot=CASTS[cast_key][0][0],
            category="vibrator",
            grip_region="right_hand",
            deployment="external_surface_contact",
            orientation="transverse_over_clitoral_surface",
        )
    ]


def compatible_pose_families(activity_id: str) -> list[str]:
    all_families = set(POSE_FAMILIES)
    if has_tag(activity_id, "lifted"):
        allowed = {"lifted_supported"}
    elif has_tag(activity_id, "partial_suspension"):
        allowed = {
            "kneeling_upright",
            "standing_wall_supported",
            "deep_squat",
        }
    elif has_tag(activity_id, "side_lying"):
        allowed = {"side_lying_left", "side_lying_right"}
    elif has_tag(activity_id, "seated", "chair"):
        allowed = {"seated_upright", "seated_reclined", "seated_edge"}
    elif has_tag(activity_id, "standing"):
        allowed = {
            "standing_upright",
            "standing_bent",
            "standing_wall_supported",
        }
    elif has_tag(activity_id, "rear_entry"):
        allowed = {
            "prone",
            "all_fours",
            "kneeling_forward",
            "standing_bent",
        }
    elif has_tag(activity_id, "bed_edge"):
        allowed = {"seated_edge", "supine", "prone"}
    elif has_tag(activity_id, "wall"):
        allowed = {
            "standing_upright",
            "standing_bent",
            "standing_wall_supported",
            "lifted_supported",
        }
    elif has_tag(activity_id, "prone"):
        allowed = {"prone"}
    elif has_tag(activity_id, "spreader"):
        allowed = {
            "supine",
            "kneeling_upright",
            "seated_reclined",
            "deep_squat",
        }
    else:
        allowed = all_families
    return [family for family in POSE_FAMILIES if family in allowed]


def activity_compatible_with_pose(
    activity: ActivityTemplate,
    pose: CentralPose,
) -> bool:
    if pose.family not in activity.compatible_pose_families:
        return False
    if pose.family == "lifted_supported" and pose.primary_surface == "partner_support":
        occupied_lift_slots = set(activity.required_slots[:2])
        if any(
            edge.source.entity_id in occupied_lift_slots
            and edge.source.region in {"hand", "left_hand", "right_hand", "mouth"}
            for edge in activity.contact_edges
        ):
            return False
    if activity.handheld_props:
        return pose.family == "supine" and pose.arm_configuration == "hands_on_thighs"
    return True


def build_activity_templates(cast_key: str) -> list[ActivityTemplate]:
    slots = [slot[0] for slot in CASTS[cast_key]]
    return [
        ActivityTemplate(
            activity_id=activity_id,
            activity_family=activity_family(activity_id),
            coverage_tags=activity_tags(activity_id),
            required_slots=slots,
            contact_edges=make_contact_edges(
                cast_key,
                activity_id,
                activity_index,
            ),
            handheld_props=handheld_props(cast_key, activity_id),
            wearable_props=wearable_props(cast_key, activity_id),
            restraint=restraint_plan(cast_key, activity_id),
            compatible_pose_families=compatible_pose_families(activity_id),
        )
        for activity_index, activity_id in enumerate(activity_ids(cast_key))
    ]


def entry_signature(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def build_catalog(cast_key: str) -> PoseCatalog:
    slots = [
        ActorSlot(
            slot_id=slot_id,
            sex=sex,
            role=role,
            adult_only=True,
        )
        for slot_id, sex, role in CASTS[cast_key]
    ]
    activities = activity_ids(cast_key)
    if len(activities) != 32 or len(set(activities)) != 32:
        raise ValueError(f"{cast_key} does not define 32 unique activities")
    activity_templates = build_activity_templates(cast_key)
    entries: list[PoseEntry] = []
    for family_index, (family_id, family) in enumerate(POSE_FAMILIES.items()):
        if cast_key == "one_woman" and family_id == "lifted_supported":
            family = family._replace(
                surface="support_sling",
                supports=("support_sling", "wall"),
            )
        for variant_index in range(16):
            entry_index = family_index * 16 + variant_index
            leg_index, arm_index = divmod(variant_index, 4)
            variant = f"{family.legs[leg_index]}_{family.arms[arm_index]}"
            central_pose = CentralPose(
                family=family_id,
                variant=variant,
                body_level=family.body_level,
                torso_orientation=family.torso,
                pelvis_orientation=family.pelvis,
                leg_configuration=family.legs[leg_index],
                arm_configuration=family.arms[arm_index],
                primary_surface=family.surface,
                support_points=list(family.supports),
                compatible_camera_views=list(family.cameras),
            )
            plans = actor_plans(cast_key, family)
            compatible_activities = [
                activity.activity_id
                for activity in activity_templates
                if activity_compatible_with_pose(activity, central_pose)
            ]
            signature_payload = {
                "cast_key": cast_key,
                "family": family_id,
                "variant": variant,
                "actors": [plan.model_dump(mode="json") for plan in plans],
            }
            entries.append(
                PoseEntry(
                    pose_id=f"{cast_key}_p{entry_index + 1:03d}",
                    cast_key=cast_key,
                    central_slot=slots[0].slot_id,
                    central_pose=central_pose,
                    actor_plans=plans,
                    compatible_activity_ids=compatible_activities,
                    exact_cast=[slot.slot_id for slot in slots],
                    consent_required=True,
                    signature=entry_signature(signature_payload),
                )
            )
    coverage = {
        "entry_count": len(entries),
        "pose_families": dict(
            sorted(Counter(entry.central_pose.family for entry in entries).items())
        ),
        "activity_families": dict(
            sorted(
                Counter(
                    activity.activity_family for activity in activity_templates
                ).items()
            )
        ),
        "activity_templates": dict(
            sorted(
                (
                    activity.activity_id,
                    sum(
                        activity.activity_id in entry.compatible_activity_ids
                        for entry in entries
                    ),
                )
                for activity in activity_templates
            )
        ),
        "bdsm_activity_templates": sum(
            activity.restraint.enabled for activity in activity_templates
        ),
        "visible_contacts": sum(
            edge.preferred_visibility == "visible"
            for activity in activity_templates
            for edge in activity.contact_edges
        ),
        "occluded_contacts": sum(
            edge.preferred_visibility == "occluded"
            for activity in activity_templates
            for edge in activity.contact_edges
        ),
    }
    return PoseCatalog(
        schema_version="2.0",
        cast_key=cast_key,
        cast_slots=slots,
        requested_entry_count=256,
        activities=activity_templates,
        entries=entries,
        coverage=coverage,
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalogs = {cast_key: build_catalog(cast_key) for cast_key in CASTS}
    audit_catalogs = {}
    for cast_key, catalog in catalogs.items():
        path = OUTPUT / f"{cast_key}.json"
        path.write_text(
            catalog.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        restored = PoseCatalog.model_validate_json(path.read_text(encoding="utf-8"))
        if restored != catalog:
            raise ValueError(f"{cast_key} changed during persistence")
        family_counts = Counter(entry.central_pose.family for entry in catalog.entries)
        tag_counts = Counter(
            tag for activity in catalog.activities for tag in activity.coverage_tags
        )
        audit_catalogs[cast_key] = {
            "entries": len(catalog.entries),
            "unique_central_pose_topologies": len(
                {
                    (
                        entry.central_pose.family,
                        entry.central_pose.variant,
                    )
                    for entry in catalog.entries
                }
            ),
            "pose_families": len(family_counts),
            "poses_per_family_min": min(family_counts.values()),
            "poses_per_family_max": max(family_counts.values()),
            "activity_templates": len(catalog.activities),
            "bdsm_activity_templates": sum(
                activity.restraint.enabled for activity in catalog.activities
            ),
            "coverage_tag_counts": dict(sorted(tag_counts.items())),
            "compatibility_links": sum(
                len(entry.compatible_activity_ids) for entry in catalog.entries
            ),
            "contact_edges": sum(
                len(activity.contact_edges) for activity in catalog.activities
            ),
            "wearable_props": sum(
                len(activity.wearable_props) for activity in catalog.activities
            ),
            "handheld_props": sum(
                len(activity.handheld_props) for activity in catalog.activities
            ),
            "cast_slots": [slot.model_dump(mode="json") for slot in catalog.cast_slots],
            "readback_validated": True,
        }
    audit_report = {
        "passed": True,
        "catalog_count": len(catalogs),
        "entries_per_catalog": 256,
        "total_unique_entries": sum(
            len(catalog.entries) for catalog in catalogs.values()
        ),
        "catalogs": audit_catalogs,
    }
    (OUTPUT / "audit-report.json").write_text(
        json.dumps(audit_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "2.0",
        "requested_configurations": [
            "one_woman",
            "one_woman_one_man",
            "one_woman_two_men",
            "two_women",
            "one_woman_two_men",
            "three_women",
        ],
        "deduplicated_configurations": list(CASTS),
        "duplicate_requests": {"one_woman_two_men": 2},
        "catalog_count": len(catalogs),
        "entries_per_catalog": 256,
        "total_unique_entries": sum(
            len(catalog.entries) for catalog in catalogs.values()
        ),
        "files": {cast_key: f"{cast_key}.json" for cast_key in catalogs},
        "audit_file": "audit-report.json",
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
