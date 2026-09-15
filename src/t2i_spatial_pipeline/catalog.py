from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Annotated, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]
RoleCode = Annotated[str, StringConstraints(pattern=r"^[fm][1-9][0-9]*$")]
TOPOLOGY_AUDIT_VERSION = 1


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    preferred_visibility: Annotated[
        str,
        StringConstraints(pattern=r"^(visible|occluded)$"),
    ]


class WearableProp(StrictModel):
    prop_id: Identifier
    owner_role: RoleCode
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
    controller_role: RoleCode
    category: Annotated[
        str,
        StringConstraints(pattern=r"^(vibrator|insertable_toy|surface_tool)$"),
    ]
    grip_region: Annotated[str, StringConstraints(pattern=r"^right_hand$")]
    deployment: Annotated[
        str,
        StringConstraints(pattern=r"^(external_surface_contact|inserted)$"),
    ]
    orientation: Annotated[
        str,
        StringConstraints(
            pattern=(
                r"^(transverse_over_clitoral_surface|aligned_to_target_canal|"
                r"aligned_to_target_surface)$"
            )
        ),
    ]


class RestraintPlan(StrictModel):
    category: Identifier
    controller_roles: list[RoleCode]
    restrained_roles: list[RoleCode]
    body_regions: list[Identifier]
    equipment: list[Identifier]


class ActivityTemplate(StrictModel):
    activity_id: Identifier
    focus_role: RoleCode
    contact_edges: list[ContactEdge] = Field(min_length=1, max_length=6)
    handheld_props: list[HandheldProp] = Field(default_factory=list, max_length=2)
    wearable_props: list[WearableProp] = Field(default_factory=list, max_length=2)
    restraint: RestraintPlan | None = None

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
        controller_grips = [
            (prop.controller_role, prop.grip_region) for prop in self.handheld_props
        ]
        if len(controller_grips) != len(set(controller_grips)):
            raise ValueError("a controller hand cannot operate two handheld props")
        if set(wearable_ids).intersection(handheld_ids):
            raise ValueError("a prop cannot be both handheld and wearable")
        for prop in self.handheld_props:
            matching_edges = [
                edge
                for edge in self.contact_edges
                if edge.source.entity_id == prop.prop_id
            ]
            if len(matching_edges) != 1:
                raise ValueError("handheld prop requires exactly one contact edge")
            edge = matching_edges[0]
            if edge.source.region != "contact_surface":
                raise ValueError("handheld prop must use its contact surface")
            if prop.category == "vibrator" and (
                edge.target.region != "clitoris"
                or edge.state != "external_contact"
                or prop.deployment != "external_surface_contact"
                or prop.orientation != "transverse_over_clitoral_surface"
            ):
                raise ValueError(
                    "clitoral vibrator must remain an external surface contact"
                )
            if prop.category == "insertable_toy" and (
                edge.target.region not in {"vagina", "anus"}
                or edge.state != "inserted"
                or prop.deployment != "inserted"
                or prop.orientation != "aligned_to_target_canal"
            ):
                raise ValueError(
                    "insertable handheld prop must align with a target canal"
                )
            if prop.category == "surface_tool" and (
                edge.state != "external_contact"
                or prop.deployment != "external_surface_contact"
                or prop.orientation != "aligned_to_target_surface"
            ):
                raise ValueError(
                    "handheld surface tool must align with an external target"
                )
        has_strap_on_tag = has_tag(self.activity_id, "strap_on")
        if (has_strap_on_tag and len(self.wearable_props) != 1) or (
            not has_strap_on_tag and self.wearable_props
        ):
            raise ValueError(
                "strap-on activities require exactly one explicit wearable prop"
            )
        for prop in self.wearable_props:
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
            if matching_edges[0].target.entity_id == prop.owner_role:
                raise ValueError("wearable prop owner cannot also be its target")
        if any(
            endpoint.region == "strap_on"
            for edge in self.contact_edges
            for endpoint in (edge.source, edge.target)
        ):
            raise ValueError("strap-on is a wearable prop, not a body region")
        if self.restraint is not None:
            if not self.restraint.equipment or not self.restraint.restrained_roles:
                raise ValueError("BDSM activities require reversible safety metadata")
        elif activity_family(self.activity_id) == "bdsm":
            raise ValueError("BDSM activity requires restraint topology")
        if self.restraint is not None and activity_family(self.activity_id) != "bdsm":
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
    role: RoleCode
    pose_function: Identifier
    screen_position: Identifier
    depth_plane: Identifier
    limb_roles: list[Identifier] = Field(min_length=2, max_length=8)
    support_points: list[Identifier] = Field(min_length=1, max_length=8)


class PoseEntry(StrictModel):
    pose_id: Identifier
    central_pose: CentralPose
    actor_plans: list[ActorPlan] = Field(min_length=1, max_length=8)
    compatible_activity_ids: list[Identifier] = Field(
        default_factory=list,
        max_length=32,
    )
    signature: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def entry_is_coherent(self) -> PoseEntry:
        plan_roles = [plan.role for plan in self.actor_plans]
        if len(plan_roles) != len(set(plan_roles)):
            raise ValueError("actor plans must use unique roles")
        if sum(plan.pose_function == "central_pose" for plan in self.actor_plans) != 1:
            raise ValueError("actor plans require exactly one central pose function")
        return self


class PoseCatalog(StrictModel):
    schema_version: Annotated[str, StringConstraints(pattern=r"^5\.0$")]
    cast_key: Identifier
    cast_roles: list[RoleCode] = Field(min_length=1, max_length=8)
    activities: list[ActivityTemplate] = Field(min_length=32, max_length=32)
    entries: list[PoseEntry]

    @model_validator(mode="after")
    def catalog_has_exact_coverage(self) -> PoseCatalog:
        expected_entry_count = len(POSE_FAMILIES) * 16
        if len(self.entries) != expected_entry_count:
            raise ValueError(
                f"each catalog must contain exactly {expected_entry_count} entries"
            )
        expected_roles = self.cast_roles
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
        if len(central_topologies) != expected_entry_count:
            raise ValueError(
                f"catalog requires {expected_entry_count} unique central pose "
                "topologies"
            )
        if any(
            [plan.role for plan in entry.actor_plans] != expected_roles
            for entry in self.entries
        ):
            raise ValueError("entry cast differs from catalog cast")
        family_counts = Counter(entry.central_pose.family for entry in self.entries)
        if (
            set(family_counts) != set(POSE_FAMILIES)
            or set(family_counts.values()) != {16}
        ):
            raise ValueError(
                f"catalog requires {len(POSE_FAMILIES)} families with 16 poses each"
            )
        activity_ids = [activity.activity_id for activity in self.activities]
        if len(activity_ids) != len(set(activity_ids)):
            raise ValueError("catalog activity IDs must be unique")
        if sum(activity.restraint is not None for activity in self.activities) != 8:
            raise ValueError("catalog requires exactly eight BDSM activity templates")
        activity_map = {activity.activity_id: activity for activity in self.activities}
        used_activities: set[str] = set()
        for entry in self.entries:
            compatible = set(entry.compatible_activity_ids)
            if not compatible.issubset(activity_map):
                raise ValueError(f"{entry.pose_id} has unknown compatible activities")
            if any(
                entry.central_pose.family not in compatible_pose_families(activity_id)
                for activity_id in compatible
            ):
                raise ValueError(f"{entry.pose_id} has incompatible activities")
            for activity_id in compatible:
                compatibility_issues = pose_activity_issues(
                    activity_map[activity_id],
                    entry.central_pose,
                    self.cast_roles,
                )
                if compatibility_issues:
                    raise ValueError(
                        f"{entry.pose_id} has unresolved {activity_id} topology: "
                        f"{compatibility_issues}"
                    )
            used_activities.update(compatible)
        if len(used_activities) < 8:
            raise ValueError("catalog must retain at least eight reachable activities")
        actor_sexes = {
            role: "female" if role.startswith("f") else "male"
            for role in self.cast_roles
        }
        valid_entities = set(expected_roles) | {
            "prop_a",
            "prop_b",
            "environment",
        }
        for activity in self.activities:
            if activity.focus_role != expected_roles[0]:
                raise ValueError(f"{activity.activity_id} focus role changed")
            referenced_roles = {
                endpoint.entity_id
                for edge in activity.contact_edges
                for endpoint in (edge.source, edge.target)
                if endpoint.entity_id not in {"prop_a", "prop_b", "environment"}
            }
            if activity.restraint is not None:
                referenced_roles.update(activity.restraint.controller_roles)
                referenced_roles.update(activity.restraint.restrained_roles)
            referenced_roles.update(prop.owner_role for prop in activity.wearable_props)
            referenced_roles.update(
                prop.controller_role for prop in activity.handheld_props
            )
            if not referenced_roles.issubset(expected_roles):
                raise ValueError(f"{activity.activity_id} uses a role outside its cast")
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
            tags = activity_tags(activity.activity_id)
            if "penetration" in tags and not any(
                edge.state == "inserted" for edge in activity.contact_edges
            ):
                raise ValueError(f"{activity.activity_id} lacks an inserted contact")
            if "oral" in tags and not {"mouth", "tongue"}.intersection(regions):
                raise ValueError(f"{activity.activity_id} lacks an oral endpoint")
            if "toy" in tags and not {
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
            tag
            for activity in self.activities
            for tag in activity_tags(activity.activity_id)
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
    "supine_hips_raised": PoseFamily(
        "low",
        "horizontal_up",
        "elevated",
        "bed",
        ("shoulders", "upper_back", "both_feet"),
        ("knees_high_wide", "one_leg_vertical", "legs_in_v", "heels_near_hips"),
        ("arms_beside", "hands_grip_edge", "one_hand_thigh", "arms_overhead"),
        CAMERAS[:5],
    ),
    "prone_hips_raised": PoseFamily(
        "middle",
        "diagonal_down",
        "elevated",
        "bed",
        ("chest", "forearms", "both_knees"),
        ("knees_wide", "one_knee_forward", "toes_planted", "thighs_open"),
        (
            "forearms_parallel",
            "arms_extended",
            "one_hand_headboard",
            "hands_grip_edge",
        ),
        CAMERAS[1:],
    ),
    "kneeling_backbend": PoseFamily(
        "middle",
        "arched_back",
        "forward_tilt",
        "bed",
        ("both_knees", "both_shins"),
        ("knees_wide", "frog_kneel", "one_foot_planted", "thighs_open"),
        ("arms_overhead", "one_hand_thigh", "one_arm_partner", "arms_outward"),
        CAMERAS,
    ),
    "standing_one_leg_supported": PoseFamily(
        "high",
        "vertical",
        "side_tilted",
        "wall",
        ("planted_foot", "wall"),
        ("one_leg_raised", "one_leg_extended", "one_knee_high", "one_leg_hooked"),
        ("palms_wall", "one_hand_wall", "arms_overhead", "one_arm_partner"),
        CAMERAS[:5],
    ),
    "seated_straddle": PoseFamily(
        "middle",
        "vertical",
        "forward_tilt",
        "chair",
        ("buttocks", "both_feet"),
        ("knees_wide", "one_leg_extended", "feet_staggered", "thighs_open"),
        ("hands_thighs", "hands_behind", "one_arm_reaching", "arms_overhead"),
        CAMERAS[:5],
    ),
    "side_lying_open": PoseFamily(
        "low",
        "horizontal_left",
        "side_tilted",
        "bed",
        ("left_shoulder", "left_hip", "left_thigh"),
        ("top_leg_raised", "top_leg_extended", "knees_open", "scissor_split"),
        (
            "lower_arm_forward",
            "upper_arm_overhead",
            "upper_hand_hip",
            "arms_outward",
        ),
        CAMERAS[:4],
    ),
    "inverted_hips_elevated": PoseFamily(
        "low",
        "inverted",
        "elevated",
        "bed",
        ("shoulders", "upper_back"),
        ("legs_vertical", "legs_in_v", "knees_bent_wide", "one_leg_lowered"),
        ("arms_beside", "hands_grip_edge", "arms_overhead", "hands_hips"),
        CAMERAS[:5],
    ),
    "sling_reclined": PoseFamily(
        "middle",
        "diagonal_back",
        "elevated",
        "support_sling",
        ("support_sling", "wall"),
        ("knees_wide", "legs_in_v", "one_leg_extended", "thighs_supported"),
        ("arms_beside", "arms_overhead", "one_hand_wall", "arms_outward"),
        CAMERAS,
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
    "mutual_manual_side_by_side",
    "mutual_manual_face_to_face",
    "mutual_manual_seated",
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
    "mutual_manual_side_by_side",
    "mutual_manual_face_to_face",
    "mutual_manual_seated",
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
    "one_woman": ("f1",),
    "one_woman_one_man": ("f1", "m1"),
    "one_woman_two_men": ("f1", "m1", "m2"),
    "two_women": ("f1", "f2"),
    "three_women": ("f1", "f2", "f3"),
}
CAST_KEYS_BY_COUNTS = {
    (1, 0): "one_woman",
    (1, 1): "one_woman_one_man",
    (1, 2): "one_woman_two_men",
    (2, 0): "two_women",
    (3, 0): "three_women",
}


def cast_key_for_counts(female_count: int, male_count: int) -> str:
    try:
        return CAST_KEYS_BY_COUNTS[(female_count, male_count)]
    except KeyError as exc:
        supported = ", ".join(
            f"{women}F+{men}M" for women, men in CAST_KEYS_BY_COUNTS
        )
        raise ValueError(
            "unsupported spatial cast counts "
            f"({female_count}F, {male_count}M); supported: {supported}"
        ) from exc

LOGICAL_ACTOR_ROLES = ("central", "partner_a", "partner_b")


def resolve_actor_role(cast_key: str, entity_id: str) -> str:
    if entity_id not in LOGICAL_ACTOR_ROLES:
        return entity_id
    index = LOGICAL_ACTOR_ROLES.index(entity_id)
    cast = CASTS[cast_key]
    if index >= len(cast):
        raise ValueError(f"{cast_key} has no actor for {entity_id}")
    return cast[index]


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
                    "contact_surface",
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

    partner_is_male = CASTS[cast_key][1].startswith("m")
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
            "mutual_manual_side_by_side",
            "mutual_manual_face_to_face",
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
) -> RestraintPlan | None:
    if activity_family(activity_id) != "bdsm":
        return None
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
    roles = list(CASTS[cast_key])
    return RestraintPlan(
        category=activity_id,
        controller_roles=roles[1:] or [roles[0]],
        restrained_roles=[roles[0]],
        body_regions=(
            ["wrists"]
            if has_tag(activity_id, "wrist")
            else ["ankles"]
            if has_tag(activity_id, "ankle", "spreader")
            else ["torso"]
        ),
        equipment=[equipment],
    )


def actor_plans(
    cast_key: str,
    family: PoseFamily,
    central_support_points: list[str],
) -> list[ActorPlan]:
    central_role = CASTS[cast_key][0]
    plans = [
        ActorPlan(
            role=central_role,
            pose_function="central_pose",
            screen_position="center",
            depth_plane="midground",
            limb_roles=["pose_hold", "balance_support"],
            support_points=central_support_points,
        )
    ]
    positions = ("center_left", "center_right")
    for index, role in enumerate(CASTS[cast_key][1:]):
        plans.append(
            ActorPlan(
                role=role,
                pose_function=(
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


def resolved_support_points(
    family: PoseFamily,
    leg_configuration: str,
) -> list[str]:
    points = list(family.supports)
    if leg_configuration in {
        "one_leg_extended",
        "one_leg_raised",
        "one_knee_raised",
    }:
        points = ["planted_foot" if point == "both_feet" else point for point in points]
    if leg_configuration == "one_foot_planted":
        points = [
            point for point in points if point not in {"both_knees", "both_shins"}
        ]
        points.extend(("supporting_knee", "planted_foot"))
    return points


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
        if (
            source_region == "mouth"
            and target_region in {"breast", "clitoris", "vulva"}
            and state == "external_contact"
        ):
            source_region = "tongue"
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
            owner_role=CASTS[cast_key][1],
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
    wearable_ids = {"prop_a"} if has_tag(activity_id, "strap_on") else set()
    prop_specs = []
    for spec in contact_specs(cast_key, activity_id):
        _, source_entity, _, _, target_region, state = spec
        if (
            source_entity.startswith("prop_")
            and source_entity not in wearable_ids
            and all(existing[0] != source_entity for existing in prop_specs)
        ):
            prop_specs.append((source_entity, target_region, state))
    if not prop_specs:
        return []

    roles = list(CASTS[cast_key])
    controller_roles = roles[1:] + roles[:1]
    props = []
    for index, (prop_id, target_region, state) in enumerate(prop_specs):
        if state == "inserted":
            category = "insertable_toy"
            deployment = "inserted"
            orientation = "aligned_to_target_canal"
        elif (
            target_region == "clitoris"
            and has_tag(
                activity_id,
                "vibrator",
                "wand",
                "suction",
                "remote",
            )
        ):
            category = "vibrator"
            deployment = "external_surface_contact"
            orientation = "transverse_over_clitoral_surface"
        else:
            category = "surface_tool"
            deployment = "external_surface_contact"
            orientation = "aligned_to_target_surface"
        props.append(
            HandheldProp(
                prop_id=prop_id,
                controller_role=controller_roles[index % len(controller_roles)],
                category=category,
                grip_region="right_hand",
                deployment=deployment,
                orientation=orientation,
            )
        )
    return props


def compatible_pose_families(activity_id: str) -> list[str]:
    all_families = set(POSE_FAMILIES)
    if activity_id == "mutual_oral":
        allowed = {"side_lying_left", "side_lying_right"}
    elif has_tag(activity_id, "plus_fellatio"):
        allowed = {"prone", "all_fours", "kneeling_forward"}
    elif activity_id == "fellatio":
        allowed = {
            "kneeling_upright",
            "seated_edge",
        }
    elif has_tag(activity_id, "cunnilingus", "dual_oral", "dual_cunnilingus"):
        allowed = {
            "supine",
            "side_lying_left",
            "side_lying_right",
            "kneeling_upright",
            "seated_reclined",
            "seated_edge",
        }
    elif has_tag(activity_id, "lifted"):
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
    elif has_tag(activity_id, "impact"):
        allowed = {
            "prone",
            "all_fours",
            "kneeling_forward",
            "standing_bent",
        }
    elif has_tag(activity_id, "breast", "nipple"):
        allowed = {
            "supine",
            "side_lying_left",
            "side_lying_right",
            "kneeling_upright",
            "seated_upright",
            "seated_reclined",
            "seated_edge",
            "standing_upright",
            "standing_wall_supported",
        }
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


_CLOSED_PELVIC_CONFIGURATIONS = {
    "ankles_crossed",
    "feet_together",
    "knees_stacked",
    "knees_together",
    "legs_together",
}
_TWO_FREE_HAND_CONFIGURATIONS = {
    "arms_beside",
    "arms_forward",
    "arms_hanging",
    "arms_outward",
}
_ONE_FREE_HAND_CONFIGURATIONS = {
    "lower_arm_forward",
    "one_arm_partner",
    "one_arm_reaching",
    "one_hand_chair",
    "one_hand_floor",
    "one_hand_headboard",
    "one_hand_thigh",
    "one_hand_wall",
    "upper_arm_overhead",
    "upper_hand_hip",
}
_PELVIC_REGIONS = {
    "anus",
    "clitoris",
    "penis",
    "pubic_region",
    "vagina",
    "vulva",
}
_ORAL_REGIONS = {"mouth", "tongue"}


def _central_hand_capacity(pose: CentralPose) -> int:
    if pose.arm_configuration in _TWO_FREE_HAND_CONFIGURATIONS:
        return 2
    if pose.arm_configuration in _ONE_FREE_HAND_CONFIGURATIONS:
        return 1
    return 0


def _role_contact_regions(
    activity: ActivityTemplate,
) -> dict[str, set[str]]:
    regions: dict[str, set[str]] = {}
    for edge in activity.contact_edges:
        for endpoint in (edge.source, edge.target):
            regions.setdefault(endpoint.entity_id, set()).add(endpoint.region)
    return regions


def pose_activity_issues(
    activity: ActivityTemplate,
    pose: CentralPose,
    cast_roles: list[str],
) -> list[str]:
    issues: list[str] = []
    if pose.family not in compatible_pose_families(activity.activity_id):
        issues.append("activity topology is incompatible with pose family")
        return issues

    focus_role = activity.focus_role
    contact_regions = _role_contact_regions(activity)
    distributed_roles = {
        role
        for role, regions in contact_regions.items()
        if regions.intersection(_ORAL_REGIONS)
        and regions.intersection(_PELVIC_REGIONS)
    }
    if distributed_roles:
        if len(cast_roles) == 2:
            if (
                activity.activity_id != "mutual_oral"
                or pose.family not in {"side_lying_left", "side_lying_right"}
            ):
                issues.append("reciprocal head-pelvis contacts lack a side-lying plan")
        elif distributed_roles != {focus_role} or pose.family not in {
            "prone",
            "all_fours",
            "kneeling_forward",
        }:
            issues.append("distributed group contacts lack a longitudinal body plan")

    central_pelvic_contact = any(
        endpoint.entity_id == focus_role
        and endpoint.region in _PELVIC_REGIONS
        for edge in activity.contact_edges
        for endpoint in (edge.source, edge.target)
    )
    if (
        central_pelvic_contact
        and pose.leg_configuration in _CLOSED_PELVIC_CONFIGURATIONS
    ):
        issues.append("closed leg configuration blocks the pelvic contact zone")

    central_hand_regions = {
        endpoint.region
        for edge in activity.contact_edges
        for endpoint in (edge.source, edge.target)
        if endpoint.entity_id == focus_role
        and endpoint is edge.source
        and endpoint.region in {"hand", "left_hand", "right_hand"}
    }
    central_hand_demand = len(central_hand_regions)
    central_hand_demand += sum(
        prop.controller_role == focus_role for prop in activity.handheld_props
    )
    if central_hand_demand > _central_hand_capacity(pose):
        issues.append("central pose does not leave enough hands for contact tasks")

    declared_props = {
        prop.prop_id
        for prop in (*activity.handheld_props, *activity.wearable_props)
    }
    unrooted_props = {
        edge.source.entity_id
        for edge in activity.contact_edges
        if edge.source.entity_id.startswith("prop_")
        and edge.source.entity_id not in declared_props
    }
    if unrooted_props:
        issues.append("contact prop has no explicit owner and hand or harness chain")

    if pose.family == "lifted_supported" and pose.primary_surface == "partner_support":
        occupied_lift_roles = set(cast_roles[:2])
        if any(
            edge.source.entity_id in occupied_lift_roles
            and edge.source.region in {"hand", "left_hand", "right_hand", "mouth"}
            for edge in activity.contact_edges
        ):
            issues.append("lift support conflicts with partner hand or mouth contact")
        supported_limb_pairs = {
            ("legs_wrapped", "arms_shoulders"),
            ("thighs_supported", "one_arm_partner"),
        }
        if (
            pose.leg_configuration,
            pose.arm_configuration,
        ) not in supported_limb_pairs:
            issues.append("lifted pose lacks a resolved bilateral limb chain")

    if activity.restraint is not None:
        restrained_regions = set(activity.restraint.body_regions)
        if "wrists" in restrained_regions and pose.arm_configuration not in {
            "arms_overhead",
            "arms_outward",
            "hands_behind",
            "hands_wall",
            "palms_wall",
        }:
            issues.append("wrist restraint does not match the arm configuration")
        if (
            "ankles" in restrained_regions
            and pose.leg_configuration in _CLOSED_PELVIC_CONFIGURATIONS
        ):
            issues.append("ankle restraint does not match the leg configuration")
    return issues


def activity_compatible_with_pose(
    activity: ActivityTemplate,
    pose: CentralPose,
    cast_roles: list[str],
) -> bool:
    return not pose_activity_issues(activity, pose, cast_roles)


def build_activity_templates(cast_key: str) -> list[ActivityTemplate]:
    return [
        ActivityTemplate(
            activity_id=activity_id,
            focus_role=CASTS[cast_key][0],
            contact_edges=make_contact_edges(
                cast_key,
                activity_id,
                activity_index,
            ),
            handheld_props=handheld_props(cast_key, activity_id),
            wearable_props=wearable_props(cast_key, activity_id),
            restraint=restraint_plan(cast_key, activity_id),
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
    roles = list(CASTS[cast_key])
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
                support_points=resolved_support_points(
                    family,
                    family.legs[leg_index],
                ),
                compatible_camera_views=list(family.cameras),
            )
            plans = actor_plans(
                cast_key,
                family,
                central_pose.support_points,
            )
            compatible_activities = [
                activity.activity_id
                for activity in activity_templates
                if activity_compatible_with_pose(
                    activity,
                    central_pose,
                    roles,
                )
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
                    central_pose=central_pose,
                    actor_plans=plans,
                    compatible_activity_ids=compatible_activities,
                    signature=entry_signature(signature_payload),
                )
            )
    return PoseCatalog(
        schema_version="5.0",
        cast_key=cast_key,
        cast_roles=roles,
        activities=activity_templates,
        entries=entries,
    )
