from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from .catalog import (
    CASTS,
    ActivityTemplate,
    ContactEdge,
    HandheldProp,
    PoseCatalog,
    PoseEntry,
    WearableProp,
    pose_activity_issues,
)
from .layers import (
    CharacterProfile,
    PresentationPreset,
    ResolvedSceneLayers,
    SettingPreset,
    StylePreset,
    resolve_scene_layers,
)

ROOT = Path(__file__).resolve().parent
CATALOGS = ROOT / "catalogs"
PROMPT_AUDIT_VERSION = 5


class SceneSpec(NamedTuple):
    scene_id: str
    cast_key: str
    family: str
    variant: str
    activity_id: str
    viewpoint: str
    shot_scale: str
    setting_id: str


def phrase(value: str) -> str:
    return value.replace("_", " ")


def camera_distance(shot_scale: str) -> str:
    return {
        "medium_close": "at a near distance",
        "medium": "at a near-medium distance",
        "medium_wide": "at a medium-far distance",
        "full_body": "at a far distance that retains every body",
        "wide": "at a far environmental distance",
    }.get(shot_scale, "at a geometry-appropriate distance")


def natural_pose(value: str) -> str:
    return {
        "bridge_elevated": "elevated bridge",
        "kneeling_upright": "upright kneeling",
        "seated_reclined": "reclined seated",
        "lifted_supported": "supported lifted",
        "all_fours": "all-fours",
    }.get(value, phrase(value))


def natural_component(value: str) -> str:
    return {
        "frog_kneel": "knees spread in a frog kneel",
        "knees_wide": "knees spread wider than the hips",
        "arms_shoulders": "arms wrapped around the partner's shoulders",
        "hands_straight": "both hands planted shoulder-width apart",
        "hands_on_thighs": (
            "the left hand resting on the inner thigh and the right hand "
            "positioned beside the pelvis"
        ),
        "one_hand_headboard": "one hand gripping the headboard",
        "one_hand_thigh": (
            "one hand resting on a thigh and the other positioned near the pelvis"
        ),
    }.get(value, phrase(value))


def natural_activity(value: str) -> str:
    return {
        "vibrator_clitoral": "clitoral stimulation with a vibrator",
        "rope_harness_self_touch": "rope-harnessed self-stimulation",
        "wrist_cuffs_quick_release": (
            "self-stimulation with quick-release wrist cuffs"
        ),
        "spreader_bar_self_play": (
            "manual clitoral self-stimulation while a padded spreader bar "
            "holds the ankles apart"
        ),
        "vaginal_lifted": "lifted vaginal intercourse",
        "double_penetration_vaginal_anal": (
            "simultaneous vaginal and anal double penetration"
        ),
        "vaginal_plus_fellatio": ("simultaneous vaginal intercourse and fellatio"),
        "strap_on_vaginal_rear_entry": (
            "rear-entry vaginal intercourse with a strap-on"
        ),
        "dual_cunnilingus": "simultaneous cunnilingus by both partners",
        "oral_and_manual_on_central": (
            "oral stimulation with simultaneous manual breast contact"
        ),
        "mutual_manual_side_by_side": (
            "side-by-side simultaneous self-stimulation"
        ),
        "mutual_manual_face_to_face": (
            "simultaneous self-stimulation while face-to-face"
        ),
        "mutual_manual_seated": "seated simultaneous self-stimulation",
    }.get(value, phrase(value))


def joined(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f" and {values[-1]}"


def role_sex(role: str) -> str:
    return "woman" if role.startswith("f") else "man"


def role_label(role: str) -> str:
    return f"{role_sex(role)} {role[1:]}"


def role_description(profile: CharacterProfile) -> str:
    role = profile.role
    return (
        f"{role.upper()}, {role_label(role)}, a {profile.adult_age}-year-old "
        f"{profile.nationality} {role_sex(role)}"
    )


def body_ledger(cast_key: str) -> str:
    roles = CASTS[cast_key]
    bodies = [
        (
            f"one continuous {role_sex(role)} body identified as "
            f"{role.upper()} ({role_label(role)})"
        )
        for role in roles
    ]
    return (
        f"The {len(bodies)} complete subjects are {joined(bodies)}. "
        "Each subject forms one connected silhouette from head through chest "
        "and waist to pelvis, with a left and right arm and a left and right "
        "leg clearly belonging to that same subject."
    )


def cast_composition_clause(entry: PoseEntry, cast_key: str) -> str:
    central_plan = entry.actor_plans[0]
    central_name = actor_name(central_plan.role, cast_key)
    pattern = phrase(central_plan.composition_pattern)
    partner_positions = [
        (
            f"{actor_name(plan.role, cast_key)} occupies "
            f"{phrase(plan.screen_position)} in the {phrase(plan.depth_plane)}"
        )
        for plan in entry.actor_plans[1:]
    ]
    if not partner_positions:
        return (
            f"The solo silhouette follows a {pattern} composition, with "
            f"{central_name}'s complete body isolated against clear negative space."
        )
    return (
        f"The cast-specific macro-layout is {pattern}: {central_name} remains "
        f"the central anchor while {joined(partner_positions)}. The complete "
        "silhouettes occupy separate readable lanes before their local contact "
        "paths converge."
    )


def cast_descriptions(
    cast_key: str,
    character_profiles: list[CharacterProfile],
) -> tuple[str, ...]:
    profile_by_role = {profile.role: profile for profile in character_profiles}
    missing_profiles = set(CASTS[cast_key]).difference(profile_by_role)
    if missing_profiles:
        raise ValueError(
            f"character blueprint lacks roles: {sorted(missing_profiles)}"
        )
    return tuple(
        role_description(profile_by_role[role]) for role in CASTS[cast_key]
    )


def support_clause(entry: PoseEntry) -> str:
    pose = entry.central_pose
    points = [
        {
            "partner_arms": "the partner's arms",
            "both_feet": "both feet",
            "both_knees": "both knees",
            "both_hands": "both hands",
            "both_shins": "both shins",
        }.get(point, phrase(point))
        for point in pose.support_points
    ]
    if pose.primary_surface == "partner_support":
        return "supported by the standing partner"
    if pose.primary_surface == "support_sling":
        return "supported by the sling with secondary support against the wall"
    if pose.primary_surface == "wall":
        load_points = [point for point in points if point != "wall"]
        return (
            f"supported through {joined(load_points)} with separate contact "
            "against the wall"
        )
    surface = {
        "bed": "the bed",
        "bed_edge": "the edge of the bed",
        "floor": "the floor",
        "wall": "the wall",
        "chair": "the chair",
        "sofa": "the sofa",
    }.get(pose.primary_surface, f"the {phrase(pose.primary_surface)}")
    return f"supported at {joined(points)} on {surface}"


def side_lying_body_chain(
    entry: PoseEntry,
    central_name: str,
) -> str | None:
    pose = entry.central_pose
    if pose.family not in {"side_lying_left", "side_lying_right"}:
        return None
    lower_side = "left" if pose.family == "side_lying_left" else "right"
    upper_side = "right" if lower_side == "left" else "left"
    leg_clause = {
        "knees_stacked": (
            f"both knees are bent and the {upper_side} knee remains stacked "
            f"directly above the {lower_side} knee"
        ),
        "top_leg_bent": (
            f"the lower {lower_side} leg extends along the bed while the upper "
            f"{upper_side} thigh bends forward from its own hip"
        ),
        "fetal_tuck": (
            "both thighs fold forward from their own hips with both knees bent "
            "and the two lower legs remaining distinct"
        ),
        "top_leg_raised": (
            f"the lower {lower_side} leg extends along the bed while the upper "
            f"{upper_side} leg rises from its own hip"
        ),
    }[pose.leg_configuration]
    return (
        f"{central_name} lies on her {lower_side} side: her {lower_side} "
        "shoulder, outer ribs, "
        f"{lower_side} hip and outer {lower_side} thigh contact the bed, while "
        f"her {upper_side} shoulder and {upper_side} hip stay stacked directly "
        f"above them. Her head, chest and pelvis form one continuous "
        f"horizontal body axis; {leg_clause}."
    )


def central_oral_reach_chain(
    entry: PoseEntry,
    activity: ActivityTemplate,
    central_name: str,
    cast_key: str,
) -> str | None:
    recipient_role = next(
        (
            role
            for role in CASTS[cast_key]
            if role != activity.focus_role
            and actor_receives_oral(activity, role)
            and not actor_gives_oral(activity, role)
        ),
        None,
    )
    if recipient_role is None:
        return None
    recipient_name = actor_name(recipient_role, cast_key)
    if entry.central_pose.family == "seated_edge":
        return (
            f"{central_name}'s buttocks and both feet keep their stated supports "
            "while her torso inclines forward from the hips; her neck and head "
            f"continue that body line until her mouth reaches {recipient_name}'s "
            "pelvis directly in front of her."
        )
    return (
        f"{central_name}'s supported torso continues through her shoulders and "
        f"neck to the head whose mouth reaches {recipient_name}'s pelvis."
    )


def lifted_bilateral_chain(
    entry: PoseEntry,
    central_name: str,
    partner_name: str,
) -> str | None:
    pose = entry.central_pose
    if pose.family != "lifted_supported":
        return None
    possessive = "his" if partner_name.startswith("M") else "her"
    if (
        pose.leg_configuration == "legs_wrapped"
        and pose.arm_configuration == "arms_shoulders"
    ):
        return (
            f"{central_name}'s single torso faces {partner_name}; her left arm "
            f"circles {partner_name}'s left shoulder and her right arm circles "
            f"{possessive} right shoulder. Her left thigh wraps around "
            f"{possessive} left side and her right thigh wraps around "
            f"{possessive} right side, with both knees bent behind "
            f"{possessive} hips. {partner_name} supports {central_name} through "
            f"two continuous bilateral cradles: {possessive} left forearm "
            f"supports the underside of her left thigh while the same continuous "
            f"left hand cups her adjacent outer left hip; {possessive} right "
            f"forearm supports the underside of her right thigh while the same "
            f"continuous right hand cups her adjacent outer right hip."
            f" {central_name}'s two-leg chain is closed and complete: left hip "
            "to left thigh, left knee, left lower leg and left foot; right hip "
            "to right thigh, right knee, right lower leg and right foot. Both "
            f"of {central_name}'s feet remain airborne behind {possessive} hips "
            f"and neither touches the floor. {partner_name}'s own left and right "
            "legs remain distinct below the pelvis with exactly two planted "
            "feet."
        )
    if (
        pose.leg_configuration == "thighs_supported"
        and pose.arm_configuration == "one_arm_partner"
    ):
        return (
            f"{central_name}'s left arm circles {partner_name}'s right shoulder "
            "while her right palm braces against the wall. "
            f"{partner_name} supports {central_name} through two continuous "
            f"bilateral cradles: {possessive} left forearm carries her right "
            f"thigh and {possessive} right forearm carries her left thigh, with "
            "both hands securing the outer hips. "
            f"{central_name}'s two-leg chain is closed and complete from each "
            "hip through one thigh, one knee, one lower leg and one foot; both "
            f"feet remain airborne. {partner_name}'s own two legs remain distinct "
            "below the pelvis with exactly two planted feet."
        )
    return None


def active_regions(activity: ActivityTemplate, role: str) -> set[str]:
    return {
        endpoint.region
        for edge in activity.contact_edges
        for endpoint in (edge.source, edge.target)
        if endpoint.entity_id == role
    }


def actor_is_pelvic_penetrator(
    activity: ActivityTemplate,
    role: str,
) -> bool:
    prop = wearable_prop_for_owner(activity, role)
    central_role = activity.focus_role
    return any(
        edge.target.entity_id == central_role
        and edge.target.region in {"vagina", "anus"}
        and (
            (edge.source.entity_id == role and edge.source.region == "penis")
            or (prop is not None and edge.source.entity_id == prop.prop_id)
        )
        for edge in activity.contact_edges
    )


def actor_gives_oral(activity: ActivityTemplate, role: str) -> bool:
    central_role = activity.focus_role
    return any(
        edge.source.entity_id == role
        and edge.source.region in {"mouth", "tongue"}
        and edge.target.entity_id == central_role
        for edge in activity.contact_edges
    )


def actor_receives_oral(activity: ActivityTemplate, role: str) -> bool:
    central_role = activity.focus_role
    return any(
        edge.source.entity_id == central_role
        and edge.source.region == "mouth"
        and edge.target.entity_id == role
        for edge in activity.contact_edges
    )


def actor_manual_contact(
    activity: ActivityTemplate,
    role: str,
) -> ContactEdge | None:
    central_role = activity.focus_role
    return next(
        (
            edge
            for edge in activity.contact_edges
            if edge.source.entity_id == role
            and edge.source.region in {"hand", "left_hand", "right_hand"}
            and edge.target.entity_id == central_role
        ),
        None,
    )


def actor_self_manual_contact(
    activity: ActivityTemplate,
    role: str,
) -> ContactEdge | None:
    return next(
        (
            edge
            for edge in activity.contact_edges
            if edge.source.entity_id == role
            and edge.target.entity_id == role
            and edge.source.region in {"hand", "left_hand", "right_hand"}
        ),
        None,
    )


def actor_receives_manual_contact(
    activity: ActivityTemplate,
    role: str,
) -> ContactEdge | None:
    central_role = activity.focus_role
    return next(
        (
            edge
            for edge in activity.contact_edges
            if edge.source.entity_id == central_role
            and edge.source.region in {"hand", "left_hand", "right_hand"}
            and edge.target.entity_id == role
        ),
        None,
    )


def resolved_partner_supports(
    actor_plan,
    activity: ActivityTemplate,
    central_pose,
) -> list[str]:
    if activity.activity_id == "mutual_oral":
        return ["side_shoulder", "side_hip", "side_thigh"]
    supports = list(actor_plan.support_points)
    if (
        wearable_prop_for_owner(activity, actor_plan.role)
        or handheld_prop_for_controller(activity, actor_plan.role)
        or actor_is_pelvic_penetrator(activity, actor_plan.role)
    ):
        return [
            "one_braced_hand" if support == "both_hands" else support
            for support in supports
        ]
    if actor_receives_oral(
        activity,
        actor_plan.role,
    ) and not actor_gives_oral(activity, actor_plan.role):
        if central_pose.family == "seated_edge":
            return ["both_feet"]
        return ["one_knee", "opposite_foot"]
    if actor_manual_contact(activity, actor_plan.role):
        return [
            "one_braced_hand" if support == "both_hands" else support
            for support in supports
        ]
    regions = active_regions(activity, actor_plan.role)
    if {"hand", "left_hand", "right_hand"}.intersection(regions):
        supports = [
            "one_braced_hand" if support == "both_hands" else support
            for support in supports
        ]
    return supports


def wearable_prop_for_owner(
    activity: ActivityTemplate,
    role: str,
) -> WearableProp | None:
    return next(
        (prop for prop in activity.wearable_props if prop.owner_role == role),
        None,
    )


def wearable_edge(
    activity: ActivityTemplate,
    prop: WearableProp,
) -> ContactEdge:
    return next(
        edge for edge in activity.contact_edges if edge.source.entity_id == prop.prop_id
    )


def handheld_edge(
    activity: ActivityTemplate,
    prop: HandheldProp,
) -> ContactEdge:
    return next(
        edge for edge in activity.contact_edges if edge.source.entity_id == prop.prop_id
    )


def handheld_prop_for_controller(
    activity: ActivityTemplate,
    role: str,
) -> HandheldProp | None:
    return next(
        (prop for prop in activity.handheld_props if prop.controller_role == role),
        None,
    )


def partner_relationship(
    actor_plan,
    activity: ActivityTemplate,
    central_name: str,
    central_pose,
) -> str:
    role = actor_plan.role
    central_role = activity.focus_role
    if activity.activity_id == "mutual_oral":
        return (
            f"lies fully visible in the opposite direction beside {central_name}; "
            "the two non-overlapping torsos stay parallel, with this actor's "
            f"only head beside {central_name}'s pelvis and this actor's pelvis "
            f"beside {central_name}'s only head"
        )
    prop = wearable_prop_for_owner(activity, role)
    if prop:
        stance = "stands" if "both_feet" in actor_plan.support_points else "kneels"
        if actor_plan.pose_function == "supporting_central":
            return (
                f"supports {central_name} with both arms while keeping her "
                f"pelvis aligned with {central_name}'s pelvis"
            )
        if "rear_entry" in activity.activity_id or "anal" in activity.activity_id:
            return (
                f"{stance} directly behind {central_name} with her pelvis "
                f"centered behind and parallel to {central_name}'s pelvis"
            )
        if "side_lying" in activity.activity_id:
            return (
                f"{stance} close behind {central_name} with her pelvis aligned "
                f"to {central_name}'s pelvis in the same lateral orientation"
            )
        return (
            f"{stance} facing {central_name} with their pelvises centered on "
            "the same contact axis"
        )
    handheld = handheld_prop_for_controller(activity, role)
    if handheld:
        edge = handheld_edge(activity, handheld)
        side = "left" if actor_plan.screen_position == "center_left" else "right"
        target = phrase(edge.target.region)
        return (
            f"kneels beside {central_name}'s {side} hip, approaching from the "
            f"{side} while guiding {handheld.prop_id} toward her {target}"
        )
    self_manual = actor_self_manual_contact(activity, role)
    if self_manual:
        side = "left" if actor_plan.screen_position == "center_left" else "right"
        if "both_feet" in actor_plan.support_points:
            return (
                f"stands beside {central_name} on the {side} in a stable "
                "staggered stance"
            )
        return f"kneels beside {central_name} on the {side}"
    relation: str | None = None
    for edge in activity.contact_edges:
        if edge.source.entity_id == role and edge.target.entity_id == central_role:
            if edge.source.region == "penis":
                if central_pose.body_level == "high":
                    relation = (
                        f"stands directly behind {central_name} with his pelvis "
                        f"centered on {central_name}'s pelvic contact axis"
                    )
                elif central_pose.family in {
                    "prone",
                    "all_fours",
                    "kneeling_forward",
                }:
                    relation = (
                        f"kneels directly behind {central_name} with his pelvis "
                        f"centered on {central_name}'s pelvic contact axis"
                    )
                else:
                    relation = (
                        f"kneels between {central_name}'s raised thighs with his "
                        f"pelvis centered on {central_name}'s pelvic contact axis"
                    )
                break
            if edge.source.region in {"mouth", "tongue"}:
                side = (
                    "left" if actor_plan.screen_position == "center_left" else "right"
                )
                oral_endpoint = edge.source.region
                if "both_feet" in actor_plan.support_points:
                    relation = (
                        f"holds a low standing crouch beside {central_name}'s "
                        f"{side} thigh and approaches her pelvis from the {side}, "
                        f"lowering the torso until the {oral_endpoint} reaches "
                        "its assigned contact"
                    )
                else:
                    relation = (
                        f"kneels beside {central_name}'s {side} thigh and "
                        f"approaches her pelvis from the {side}, lowering the "
                        f"torso until the {oral_endpoint} reaches its assigned "
                        "contact"
                    )
                break
            if edge.source.region in {"hand", "left_hand", "right_hand"}:
                side = (
                    "left" if actor_plan.screen_position == "center_left" else "right"
                )
                target_zone = (
                    "pelvis"
                    if edge.target.region
                    in {"anus", "clitoris", "pubic_region", "vagina", "vulva"}
                    else "upper body"
                )
                relation = (
                    f"stands beside {central_name}'s {target_zone} on the {side} "
                    "in a stable staggered stance"
                    if "both_feet" in actor_plan.support_points
                    else (
                        f"kneels beside {central_name}'s {target_zone} on the "
                        f"{side} with both knees on the support surface"
                    )
                )
                break
        if edge.target.entity_id == role and edge.source.entity_id == central_role:
            if edge.source.region == "mouth" and edge.target.region in {
                "penis",
                "vulva",
            }:
                if central_pose.family == "seated_edge":
                    relation = (
                        f"stands directly in front of {central_name}'s inclined "
                        "torso with both feet planted and his pelvis held at her "
                        "mouth level"
                    )
                else:
                    relation = (
                        f"holds a high half-kneel beside {central_name}'s head, "
                        "with one knee down and the opposite foot planted so the "
                        "pelvis rises to her mouth level"
                    )
                break
            if edge.source.region in {"hand", "left_hand", "right_hand"}:
                side = (
                    "left" if actor_plan.screen_position == "center_left" else "right"
                )
                relation = (
                    f"stands beside {central_name} on the {side} with his pelvis "
                    f"turned toward {central_name}'s assigned hand"
                    if "both_feet" in actor_plan.support_points
                    else (
                        f"kneels on all fours to {central_name}'s {side}, with "
                        f"the pelvis angled inward within reach of "
                        f"{central_name}'s assigned hand"
                    )
                )
                break
    if actor_plan.pose_function == "supporting_central":
        if actor_is_pelvic_penetrator(activity, actor_plan.role):
            return (
                f"stands facing {central_name} with feet shoulder-width apart "
                "and knees softly flexed while keeping their pelvises aligned"
            )
        supporting_relation = (
            relation.replace("aligns", "aligning", 1)
            .replace("kneels", "kneeling", 1)
            .replace("holds", "holding", 1)
            .replace("is positioned", "positioned", 1)
            if relation
            else ""
        )
        detail = f" while {supporting_relation}" if supporting_relation else ""
        return f"supports {central_name} with both arms{detail}"
    return relation or f"aligned with {central_name}"


def partner_body_chain_clause(
    actor_plan,
    activity: ActivityTemplate,
    central_name: str,
    cast_key: str,
) -> str:
    name = actor_name(actor_plan.role, cast_key)
    possessive = "his" if actor_plan.role.startswith("m") else "her"
    if actor_is_pelvic_penetrator(activity, actor_plan.role):
        return (
            f"{name}, the {role_sex(actor_plan.role)}, forms one continuous "
            f"body at the penetration axis: {possessive} head connects through "
            f"the neck, chest and waist to the pelvis positioned at {central_name}'s "
            f"pelvis; the anatomical endpoint projects from that same pelvis. "
            "Both shoulders, arms, hips and legs remain visibly attributable "
            f"to {name}."
        )
    if actor_gives_oral(activity, actor_plan.role):
        return (
            f"{name}, the {role_sex(actor_plan.role)}, lowers the head attached "
            f"through the neck to {possessive} visible torso; that torso continues "
            f"through the waist to {possessive} pelvis and two supported legs."
        )
    if actor_receives_oral(activity, actor_plan.role):
        return (
            f"{name}, the {role_sex(actor_plan.role)}, forms one continuous "
            f"recipient body: {possessive} head connects through neck and chest "
            "to the pelvis raised "
            f"beside {central_name}'s only head, and the anatomical endpoint "
            f"projects from that pelvis toward {central_name}'s mouth. "
            "Both shoulders connect to complete arms ending in two visible "
            "hands that perform the stated limb task."
        )
    manual_edge = actor_manual_contact(activity, actor_plan.role)
    if manual_edge:
        return (
            f"{name}'s right contact arm forms one visible shoulder-elbow-wrist-"
            f"hand chain from {possessive} single torso to "
            f"{central_name}'s {phrase(manual_edge.target.region)}; "
            f"{possessive} left support arm remains separately attached to the "
            "same torso."
        )
    received_manual = actor_receives_manual_contact(activity, actor_plan.role)
    if received_manual:
        return (
            f"{name}'s only head, chest, waist and pelvis remain vertically "
            f"connected as one body, with {central_name}'s assigned hand "
            f"reaching the {phrase(received_manual.target.region)} on that pelvis."
        )
    return (
        f"{name}, the {role_sex(actor_plan.role)}, has one continuous "
        "head-to-chest-to-waist-to-pelvis silhouette with two attributable "
        "arms and two attributable legs."
    )


def partner_limb_clause(
    actor_plan,
    activity: ActivityTemplate,
    central_name: str,
    support_surface: str,
) -> str:
    if activity.activity_id == "mutual_oral":
        return (
            ", with the left and right arms attached to the same visible torso "
            "and both legs extending from the same pelvis"
        )
    if not wearable_prop_for_owner(activity, actor_plan.role):
        if actor_plan.pose_function == "supporting_central":
            return ""
        handheld = handheld_prop_for_controller(activity, actor_plan.role)
        if handheld:
            return (
                f", with the right hand controlling {handheld.prop_id} and "
                f"the left hand braced on the {phrase(support_surface)}"
            )
        if actor_is_pelvic_penetrator(activity, actor_plan.role):
            if "both_hands" in actor_plan.support_points:
                return (
                    f", with one hand braced on the {phrase(support_surface)} "
                    f"and the other stabilizing {central_name}'s thigh"
                )
            return f", with both hands stabilizing {central_name}'s hips"
        if actor_gives_oral(activity, actor_plan.role):
            return (
                f", with both palms braced on the {phrase(support_surface)} "
                f"beside {central_name}'s hips"
            )
        if actor_receives_oral(activity, actor_plan.role):
            return ", with both hands resting on the thighs"
        manual_edge = actor_manual_contact(activity, actor_plan.role)
        if manual_edge:
            target = phrase(manual_edge.target.region)
            if "both_hands" not in actor_plan.support_points:
                return (
                    f", with the right hand maintained at {central_name}'s "
                    f"{target} and the left hand stabilizing "
                    f"{central_name}'s torso"
                )
            return (
                f", with the right hand maintained at {central_name}'s "
                f"{target} and the left hand braced on the "
                f"{phrase(support_surface)}"
            )
        self_manual = actor_self_manual_contact(activity, actor_plan.role)
        if self_manual:
            return (
                f", with the right hand maintained at their own "
                f"{phrase(self_manual.target.region)} and the left hand braced "
                f"on the {phrase(support_surface)}"
            )
        return ""
    if actor_plan.pose_function == "supporting_central":
        return ""
    if "both_hands" in actor_plan.support_points:
        return (
            f", with one hand braced on the {phrase(support_surface)} and "
            f"the other holding "
            f"{central_name}'s hip"
        )
    return f", with both hands holding {central_name}'s hips"


@lru_cache(maxsize=len(CASTS))
def load_catalog(cast_key: str) -> PoseCatalog:
    return PoseCatalog.model_validate_json(
        (CATALOGS / f"{cast_key}.json").read_text(encoding="utf-8")
    )


def select_plan(
    catalog: PoseCatalog,
    spec: SceneSpec,
) -> tuple[PoseEntry, ActivityTemplate]:
    entry = next(
        (
            candidate
            for candidate in catalog.entries
            if candidate.central_pose.family == spec.family
            and candidate.central_pose.variant == spec.variant
        ),
        None,
    )
    if entry is None:
        raise ValueError(f"{spec.scene_id} pose not found")
    activity = next(
        (
            candidate
            for candidate in catalog.activities
            if candidate.activity_id == spec.activity_id
        ),
        None,
    )
    if activity is None:
        raise ValueError(f"{spec.scene_id} activity not found")
    if activity.activity_id not in entry.compatible_activity_ids:
        raise ValueError(f"{spec.scene_id} pose and activity are incompatible")
    unresolved = pose_activity_issues(
        activity,
        entry.central_pose,
        catalog.cast_roles,
    )
    if unresolved:
        raise ValueError(
            f"{spec.scene_id} pose and activity topology is unresolved: {unresolved}"
        )
    if spec.viewpoint not in entry.central_pose.compatible_camera_views:
        raise ValueError(f"{spec.scene_id} camera and pose are incompatible")
    return entry, activity


def plan_fingerprint(
    spec: SceneSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
) -> str:
    payload = {
        "spec": {
            key: value for key, value in spec._asdict().items() if key != "setting_id"
        },
        "pose_signature": entry.signature,
        "activity": activity.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def actor_name(entity_id: str, cast_key: str) -> str:
    roles = list(CASTS[cast_key])
    if entity_id in roles:
        return entity_id.upper()
    if entity_id.startswith("prop_"):
        return "the selected toy or wearable prop"
    return entity_id


def contact_projection(
    entry: PoseEntry,
    activity: ActivityTemplate,
    edge: ContactEdge,
) -> tuple[str, str]:
    anchor_role = activity.focus_role
    if edge.edge_id != "primary":
        controlled_prop = next(
            (
                prop
                for prop in activity.handheld_props
                if prop.prop_id == edge.source.entity_id
            ),
            None,
        )
        planned_roles = {plan.role for plan in entry.actor_plans}
        anchor_role = (
            controlled_prop.controller_role
            if controlled_prop is not None
            else next(
                (
                    endpoint.entity_id
                    for endpoint in (edge.source, edge.target)
                    if endpoint.entity_id != activity.focus_role
                    and endpoint.entity_id in planned_roles
                ),
                activity.focus_role,
            )
        )
    anchor = next(plan for plan in entry.actor_plans if plan.role == anchor_role)
    return anchor.screen_position, anchor.depth_plane


def occluders_for(edge: ContactEdge, cast_key: str) -> str:
    edge_regions = {edge.source.region, edge.target.region}
    if {"mouth", "penis"}.issubset(edge_regions):
        receiver = next(
            endpoint
            for endpoint in (edge.source, edge.target)
            if endpoint.region == "mouth"
        )
        receiver_name = actor_name(receiver.entity_id, cast_key)
        return (
            f"{receiver_name}'s only head, visibly connected to {receiver_name}'s torso"
        )
    if {"mouth", "tongue"}.intersection(edge_regions):
        return "the head silhouette"
    if {"vagina", "anus"}.intersection(edge_regions):
        return "the near thigh and overlapping pelvises"
    return "the overlapping body contours"


def anatomical_endpoint_ownership(
    edge: ContactEdge,
    cast_key: str,
) -> str | None:
    endpoint = next(
        (
            endpoint
            for endpoint in (edge.source, edge.target)
            if endpoint.region == "penis"
        ),
        None,
    )
    if endpoint is None:
        return None
    owner = actor_name(endpoint.entity_id, cast_key)
    return (
        f"The {phrase(edge.edge_id)} anatomical endpoint is rooted at "
        f"{owner}'s pelvis and remains part of {owner}'s single continuous body."
    )


def tongue_continuity(
    edge: ContactEdge,
    cast_key: str,
) -> str | None:
    tongue = next(
        (
            endpoint
            for endpoint in (edge.source, edge.target)
            if endpoint.region == "tongue"
        ),
        None,
    )
    if tongue is None:
        return None
    other = edge.target if tongue is edge.source else edge.source
    owner = actor_name(tongue.entity_id, cast_key)
    target = endpoint_phrase(other.entity_id, other.region, cast_key)
    return (
        f"{owner}'s natural human tongue extends continuously "
        f"from inside their open mouth, with its base rooted behind the lower teeth; "
        f"the tongue stays slender and flat with a natural pink dorsal surface "
        f"and a tapered rounded tip touching {target}."
    )


def compile_wearable_prop(
    entry: PoseEntry,
    activity: ActivityTemplate,
    prop: WearableProp,
    cast_key: str,
) -> tuple[list[str], str]:
    edge = wearable_edge(activity, prop)
    screen_position, depth_plane = contact_projection(entry, activity, edge)
    owner = actor_name(prop.owner_role, cast_key)
    target = actor_name(edge.target.entity_id, cast_key)
    if edge.target.region == "vagina":
        route = (
            f"forward and slightly downward between {target}'s thighs toward "
            f"the vaginal canal, anatomically separate from the anus above"
        )
    elif edge.target.region == "anus":
        route = f"forward between {target}'s buttocks toward the anal canal"
    else:
        raise ValueError(
            f"{activity.activity_id} has unsupported wearable target "
            f"{edge.target.region}"
        )
    sentences = [
        (
            f"A fitted strap-on harness is visibly secured around {owner}'s "
            "hips, with its base fixed to the front of her pelvis and aligned "
            "to her pelvic axis."
        ),
        (
            f"The shaft extends from that fixed base {route}; the harness, "
            "base and proximal shaft remain visible as one connected assembly."
        ),
    ]
    if edge.preferred_visibility == "occluded":
        sentences.append(
            f"The {phrase(edge.edge_id)} {phrase(edge.state)} contact at "
            f"{phrase(screen_position)} in the "
            f"{phrase(depth_plane)} remains occluded by "
            f"{occluders_for(edge, cast_key)}; "
            "the actual insertion point is not shown."
        )
    else:
        sentences.append(
            f"The visible {phrase(edge.edge_id)} {phrase(edge.state)} contact "
            f"continues directly from the fixed base at "
            f"{phrase(screen_position)} in the "
            f"{phrase(depth_plane)}."
        )
    return sentences, edge.edge_id


def compile_handheld_prop(
    entry: PoseEntry,
    activity: ActivityTemplate,
    prop: HandheldProp,
    cast_key: str,
) -> tuple[list[str], str]:
    edge = handheld_edge(activity, prop)
    screen_position, depth_plane = contact_projection(entry, activity, edge)
    controller = actor_name(prop.controller_role, cast_key)
    target = actor_name(edge.target.entity_id, cast_key)
    possessive = "his" if prop.controller_role.startswith("m") else "her"
    if prop.category == "insertable_toy":
        target_region = phrase(edge.target.region)
        sentences = [
            (
                f"{controller}'s right hand visibly grips the base of "
                f"{prop.prop_id}; {possessive} left hand remains braced for support."
            ),
            (
                f"The shaft of {prop.prop_id} follows one continuous line from "
                f"{controller}'s right hand toward {target}'s {target_region}, "
                f"aligned to the {target_region} canal."
            ),
        ]
        if edge.preferred_visibility == "occluded":
            sentences.append(
                f"The {phrase(edge.edge_id)} inserted contact at "
                f"{phrase(screen_position)} in the {phrase(depth_plane)} "
                f"remains occluded by {occluders_for(edge, cast_key)}; the "
                "controller, gripped base and proximal shaft remain visible."
            )
        else:
            sentences.append(
                f"The visible {phrase(edge.edge_id)} inserted edge continues "
                f"from the gripped base into {target}'s {target_region} at "
                f"{phrase(screen_position)} in the {phrase(depth_plane)}."
            )
        return sentences, edge.edge_id
    if prop.category == "vibrator":
        sentences = [
            (
                f"{controller}'s right hand grips the vibrator body and controls "
                f"its pressure; {possessive} left hand remains visibly on the "
                "adjacent thigh."
            ),
            (
                "The rounded vibrator head lies transversely across "
                f"{target}'s external clitoral surface, with the device axis "
                "parallel to the pubic line and entirely outside the vaginal "
                "opening."
            ),
            (
                f"The visible {phrase(edge.edge_id)} "
                f"{phrase(edge.state)} edge is the vibrator head resting against "
                f"the external clitoral surface at {phrase(screen_position)} "
                f"in the {phrase(depth_plane)}."
            ),
        ]
        return sentences, edge.edge_id
    target_region = phrase(edge.target.region)
    sentences = [
        (
            f"{controller}'s right hand grips {prop.prop_id} while "
            f"{possessive} left hand remains available for the stated support."
        ),
        (
            f"The active surface of {prop.prop_id} follows one continuous "
            f"hand-to-tool path to {target}'s {target_region}."
        ),
        (
            f"The visible {phrase(edge.edge_id)} "
            f"{phrase(edge.state)} edge is the active surface of {prop.prop_id} "
            f"resting against {target}'s {target_region} at {phrase(screen_position)} "
            f"in the {phrase(depth_plane)}."
        ),
    ]
    return sentences, edge.edge_id


def distributed_contact_axis_clause(
    entry: PoseEntry,
    activity: ActivityTemplate,
    cast_key: str,
) -> str | None:
    mouth_edge = next(
        (
            edge
            for edge in activity.contact_edges
            if any(
                endpoint.entity_id == activity.focus_role and endpoint.region == "mouth"
                for endpoint in (edge.source, edge.target)
            )
        ),
        None,
    )
    pelvic_edge = next(
        (
            edge
            for edge in activity.contact_edges
            if any(
                endpoint.entity_id == activity.focus_role
                and endpoint.region
                in {"vagina", "vulva", "anus", "clitoris", "pubic_region"}
                for endpoint in (edge.source, edge.target)
            )
        ),
        None,
    )
    if mouth_edge is None or pelvic_edge is None:
        return None
    focus_name = actor_name(activity.focus_role, cast_key)
    mouth_partner = next(
        endpoint.entity_id
        for endpoint in (mouth_edge.source, mouth_edge.target)
        if endpoint.entity_id != activity.focus_role
    )
    pelvic_partner = next(
        endpoint.entity_id
        for endpoint in (pelvic_edge.source, pelvic_edge.target)
        if endpoint.entity_id != activity.focus_role
    )
    mouth_position, mouth_depth = contact_projection(entry, activity, mouth_edge)
    pelvic_position, pelvic_depth = contact_projection(entry, activity, pelvic_edge)
    if activity.activity_id == "mutual_oral":
        partner_role = next(
            role for role in CASTS[cast_key] if role != activity.focus_role
        )
        partner_name = actor_name(partner_role, cast_key)
        return (
            f"{focus_name} and {partner_name} form one side-lying reciprocal pair "
            "along the bed's long axis, facing opposite directions. "
            f"{focus_name}'s head is beside {partner_name}'s pelvis, and "
            f"{partner_name}'s "
            f"head is beside {focus_name}'s pelvis. Each head remains connected "
            "through one neck and chest to its own pelvis; the two torsos stay "
            "parallel."
        )
    return (
        f"{focus_name} remains one continuous body along the bed's long axis: "
        f"her pelvis stays at {phrase(pelvic_position)} in the "
        f"{phrase(pelvic_depth)} beside {actor_name(pelvic_partner, cast_key)}, "
        f"and her torso connects continuously to her head at "
        f"{phrase(mouth_position)} in the {phrase(mouth_depth)} beside "
        f"{actor_name(mouth_partner, cast_key)}."
    )


def resolved_central_arm_description(
    pose,
    activity: ActivityTemplate,
    cast_key: str,
) -> str:
    natural = natural_component(pose.arm_configuration)
    focus_role = activity.focus_role
    tasks: list[tuple[str, str]] = []
    assigned_hands: set[str] = set()
    for edge in activity.contact_edges:
        if (
            edge.source.entity_id != focus_role
            or edge.source.region not in {"hand", "left_hand", "right_hand"}
        ):
            continue
        hand = (
            edge.source.region
            if edge.source.region in {"left_hand", "right_hand"}
            else "right_hand"
            if "right_hand" not in assigned_hands
            else "left_hand"
        )
        assigned_hands.add(hand)
        tasks.append(
            (
                hand,
                f"performs the assigned contact at "
                f"{actor_name(edge.target.entity_id, cast_key)}'s "
                f"{phrase(edge.target.region)}",
            )
        )
    for prop in activity.handheld_props:
        if prop.controller_role != focus_role:
            continue
        assigned_hands.add(prop.grip_region)
        tasks.append(
            (
                prop.grip_region,
                f"holds {prop.prop_id} as one continuous hand-to-prop chain",
            )
        )
    if not tasks:
        return natural
    if len(tasks) == 1:
        hand, task = tasks[0]
        other = "left_hand" if hand == "right_hand" else "right_hand"
        return (
            f"{natural}; specifically, the {phrase(hand)} {task}, while the "
            f"{phrase(other)} alone maintains the named pose support or remains "
            "clearly visible and free"
        )
    task_text = "; ".join(
        f"the {phrase(hand)} {task}" for hand, task in tasks
    )
    return f"{natural}; specifically, {task_text}"


def compile_geometry(
    spec: SceneSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
    character_profiles: list[CharacterProfile],
) -> str:
    descriptions = cast_descriptions(spec.cast_key, character_profiles)
    central_name = actor_name(activity.focus_role, spec.cast_key)
    cast_text = "; ".join(descriptions)
    adult_noun = "adult" if len(descriptions) == 1 else "adults"
    pose = entry.central_pose
    pose_name = natural_pose(pose.family)
    article = "an" if pose_name[0].lower() in "aeiou" else "a"
    sentences = [
        f"Exactly {len(descriptions)} {adult_noun} occupies the image: {cast_text}."
        if len(descriptions) == 1
        else f"Exactly {len(descriptions)} {adult_noun} occupy the image: {cast_text}.",
        body_ledger(spec.cast_key),
        (
            f"The camera uses a {phrase(spec.viewpoint)} viewpoint and a "
            f"{phrase(spec.shot_scale)} composition "
            f"{camera_distance(spec.shot_scale)}."
        ),
        (
            f"{central_name} holds {article} "
            f"{pose_name} pose at image center with "
            f"{natural_component(pose.leg_configuration)} and "
            f"{resolved_central_arm_description(pose, activity, spec.cast_key)}; "
            f"she is {support_clause(entry)}."
        ),
        cast_composition_clause(entry, spec.cast_key),
    ]
    central_body_chain = side_lying_body_chain(entry, central_name)
    if central_body_chain:
        sentences.append(central_body_chain)
    central_oral_chain = central_oral_reach_chain(
        entry,
        activity,
        central_name,
        spec.cast_key,
    )
    if central_oral_chain:
        sentences.append(central_oral_chain)
    if len(descriptions) > 1:
        chain = lifted_bilateral_chain(
            entry,
            central_name,
            actor_name(entry.actor_plans[1].role, spec.cast_key),
        )
        if chain:
            sentences.append(chain)
    for actor_plan in entry.actor_plans[1:]:
        actor_name_value = actor_name(actor_plan.role, spec.cast_key)
        relationship = partner_relationship(
            actor_plan,
            activity,
            central_name,
            pose,
        )
        supports = resolved_partner_supports(
            actor_plan,
            activity,
            pose,
        )
        limb_clause = partner_limb_clause(
            actor_plan,
            activity,
            central_name,
            pose.primary_surface,
        )
        sentences.append(
            f"{actor_name_value} {relationship}{limb_clause}, positioned at "
            f"{phrase(actor_plan.screen_position)} in the "
            f"{phrase(actor_plan.depth_plane)}, supported by "
            f"{joined([phrase(point) for point in supports])}."
        )
        sentences.append(
            partner_body_chain_clause(
                actor_plan,
                activity,
                central_name,
                spec.cast_key,
            )
        )
    distributed_axis = distributed_contact_axis_clause(
        entry,
        activity,
        spec.cast_key,
    )
    if distributed_axis:
        sentences.append(distributed_axis)
    sentences.append(
        f"The primary activity is {natural_activity(activity.activity_id)}."
    )
    self_directed_edges = [
        edge
        for edge in activity.contact_edges
        if edge.source.region == "hand"
        and edge.source.entity_id == edge.target.entity_id
    ]
    if len(self_directed_edges) > 1:
        paths = []
        for edge in self_directed_edges:
            source = endpoint_phrase(
                edge.source.entity_id,
                "hand",
                spec.cast_key,
            )
            target = endpoint_phrase(
                edge.target.entity_id,
                edge.target.region,
                spec.cast_key,
            )
            paths.append(f"{source} stays on {target}")
        sentences.append(
            "Keep these as separate self-directed contact paths: "
            f"{joined(paths)}. Each contacting hand remains on its owner's anatomy."
        )
    handled_prop_edges: set[str] = set()
    for prop in activity.handheld_props:
        prop_sentences, edge_id = compile_handheld_prop(
            entry,
            activity,
            prop,
            spec.cast_key,
        )
        sentences.extend(prop_sentences)
        handled_prop_edges.add(edge_id)
    for prop in activity.wearable_props:
        prop_sentences, edge_id = compile_wearable_prop(
            entry,
            activity,
            prop,
            spec.cast_key,
        )
        sentences.extend(prop_sentences)
        handled_prop_edges.add(edge_id)
    for edge in activity.contact_edges:
        if edge.edge_id in handled_prop_edges:
            ownership = anatomical_endpoint_ownership(edge, spec.cast_key)
            if ownership:
                sentences.append(ownership)
            continue
        screen_position, depth_plane = contact_projection(entry, activity, edge)
        ownership = anatomical_endpoint_ownership(edge, spec.cast_key)
        if ownership:
            sentences.append(ownership)
        tongue_clause = tongue_continuity(edge, spec.cast_key)
        if tongue_clause and edge.preferred_visibility == "visible":
            sentences.append(tongue_clause)
        if edge.preferred_visibility == "occluded":
            sentences.append(
                f"The {phrase(edge.edge_id)} {phrase(edge.state)} contact "
                f"at {phrase(screen_position)} in the "
                f"{phrase(depth_plane)} remains occluded by "
                f"{occluders_for(edge, spec.cast_key)}; "
                "its local endpoints are not shown."
            )
        else:
            source = endpoint_phrase(
                edge.source.entity_id,
                edge.source.region,
                spec.cast_key,
            )
            target = endpoint_phrase(
                edge.target.entity_id,
                edge.target.region,
                spec.cast_key,
            )
            sentences.append(
                f"The visible {phrase(edge.edge_id)} "
                f"{phrase(edge.state)} edge joins "
                f"{source} to {target} "
                f"at "
                f"{phrase(screen_position)} in the "
                f"{phrase(depth_plane)}."
            )
    if activity.restraint is not None:
        if activity.restraint.equipment == [
            "padded_spreader_bar"
        ] and activity.restraint.body_regions == ["ankles"]:
            sentences.extend(
                (
                    f"A padded spreader bar spans directly between {central_name}'s "
                    "ankles; its left end is visibly secured to her left ankle "
                    "and its right end to her right ankle by padded cuffs.",
                    "Both cuff release tabs remain visible, and an established "
                    "safeword governs the consensual arrangement.",
                )
            )
        else:
            sentences.append(
                "The consensual BDSM arrangement uses "
                f"{', '.join(phrase(item) for item in activity.restraint.equipment)} "
                "with a visible quick release and an established safeword."
            )
    return " ".join(sentences)


def endpoint_phrase(entity_id: str, region: str, cast_key: str) -> str:
    if entity_id.startswith("prop_"):
        return "the active surface of the selected toy or wearable prop"
    name = actor_name(entity_id, cast_key)
    natural_region = {
        "contact_surface": "active contact surface",
        "clitoris": "clitoral area",
        "strap_on": "strap-on",
    }.get(region, phrase(region))
    return f"{name}'s {natural_region}"


def region_visibility_maps(
    spec: SceneSpec,
    activity: ActivityTemplate,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    roles = CASTS[spec.cast_key]
    required = {role: set() for role in roles}
    visible = {role: set() for role in roles}
    for edge in activity.contact_edges:
        for endpoint in (edge.source, edge.target):
            if endpoint.entity_id not in required:
                continue
            required[endpoint.entity_id].add(endpoint.region)
            if edge.preferred_visibility == "visible":
                visible[endpoint.entity_id].add(endpoint.region)
    if activity.restraint is not None:
        for role in activity.restraint.restrained_roles:
            required[role].update(activity.restraint.body_regions)
    return (
        {role: sorted(regions) for role, regions in required.items()},
        {role: sorted(regions) for role, regions in visible.items()},
    )


def compile_scene_layers(
    spec: SceneSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
    fingerprint: str,
    geometry: str,
    setting: SettingPreset,
    style: StylePreset,
    presentation: PresentationPreset,
    character_profiles: list[CharacterProfile],
) -> ResolvedSceneLayers:
    required, visible = region_visibility_maps(spec, activity)
    required_supports = environment_supports(entry)
    cast_roles = list(CASTS[spec.cast_key])
    interaction_partners: dict[str, set[str]] = {role: set() for role in cast_roles}
    for edge in activity.contact_edges:
        source_role = edge.source.entity_id
        target_role = edge.target.entity_id
        if (
            source_role in interaction_partners
            and target_role in interaction_partners
            and source_role != target_role
        ):
            interaction_partners[source_role].add(target_role)
            interaction_partners[target_role].add(source_role)
    for prop in (*activity.wearable_props, *activity.handheld_props):
        owner_role = getattr(prop, "owner_role", None) or getattr(
            prop,
            "controller_role",
            None,
        )
        if (
            owner_role in interaction_partners
            and activity.focus_role in interaction_partners
            and owner_role != activity.focus_role
        ):
            interaction_partners[owner_role].add(activity.focus_role)
            interaction_partners[activity.focus_role].add(owner_role)
    return resolve_scene_layers(
        scene_id=spec.scene_id,
        spatial_fingerprint=fingerprint,
        geometry=geometry,
        cast_roles=cast_roles,
        character_profiles=character_profiles,
        body_level=entry.central_pose.body_level,
        setting=setting,
        style=style,
        presentation_source=presentation,
        required_environment_supports=required_supports,
        required_regions_by_role=required,
        visible_regions_by_role=visible,
        activity_id=activity.activity_id,
        focus_role=activity.focus_role,
        interaction_partners_by_role={
            role: sorted(partners) for role, partners in interaction_partners.items()
        },
    )


def environment_supports(entry: PoseEntry) -> list[str]:
    supports = (
        set()
        if entry.central_pose.primary_surface == "partner_support"
        else {entry.central_pose.primary_surface}
    )
    supports.update(
        support
        for support in entry.central_pose.support_points
        if support in {"wall", "support_sling"}
    )
    if "furniture" in entry.central_pose.arm_configuration:
        supports.add("furniture")
    return sorted(supports)


def combine_prompt(geometry: str, layers: ResolvedSceneLayers) -> str:
    return f"{geometry} {layers.compact_suffix}"


def prompt_issues(
    spec: SceneSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
    prompt: str,
    character_profiles: list[CharacterProfile],
) -> list[str]:
    issues: list[str] = []
    descriptions = cast_descriptions(spec.cast_key, character_profiles)
    central_name = actor_name(activity.focus_role, spec.cast_key)
    if not prompt.isascii() or "\n" in prompt or "\r" in prompt:
        issues.append("prompt is not one ASCII paragraph")
    if prompt.count("The camera uses a ") != 1:
        issues.append("planned camera geometry is not stated exactly once")
    for description in descriptions:
        if prompt.count(description) != 1:
            issues.append(f"cast description changed: {description}")
    if body_ledger(spec.cast_key) not in prompt:
        issues.append("scene lacks the exact continuous-body ledger")
    required = (
        spec.viewpoint,
        spec.shot_scale,
    )
    lowered = prompt.lower()
    for value in required:
        if phrase(value) not in lowered:
            issues.append(f"missing plan value: {value}")
    natural_required = (
        natural_pose(entry.central_pose.family),
        natural_component(entry.central_pose.leg_configuration),
        natural_component(entry.central_pose.arm_configuration),
        natural_activity(activity.activity_id),
    )
    for value in natural_required:
        if value.lower() not in lowered:
            issues.append(f"missing naturalized plan value: {value}")
    for edge in activity.contact_edges:
        visibility = edge.preferred_visibility
        if visibility not in lowered:
            issues.append(f"missing contact visibility: {visibility}")
        edge_marker = f"{phrase(edge.edge_id)} {phrase(edge.state)}"
        edge_sentence = next(
            (
                sentence
                for sentence in prompt.split(". ")
                if edge_marker in sentence
                and "activity is" not in sentence
                and ("contact" in sentence or "edge" in sentence)
            ),
            "",
        )
        screen_position, depth_plane = contact_projection(entry, activity, edge)
        projection = f"at {phrase(screen_position)} in the {phrase(depth_plane)}"
        if projection not in edge_sentence:
            issues.append(f"{edge.edge_id} changed contact projection")
        if visibility == "occluded":
            local_terms = {edge.source.region, edge.target.region}
            if any(phrase(term) in edge_sentence for term in local_terms):
                issues.append(f"{edge.edge_id} exposes an occluded endpoint")
            expected_occluder = occluders_for(edge, spec.cast_key)
            if expected_occluder not in edge_sentence:
                issues.append(f"{edge.edge_id} changed contact occluder ownership")
        expected_ownership = anatomical_endpoint_ownership(
            edge,
            spec.cast_key,
        )
        if expected_ownership and expected_ownership not in prompt:
            issues.append(f"{edge.edge_id} lacks anatomical endpoint ownership")
    expected_axis = distributed_contact_axis_clause(entry, activity, spec.cast_key)
    if expected_axis and expected_axis not in prompt:
        issues.append("distributed contacts lack one continuous body axis")
    expected_central_chain = side_lying_body_chain(entry, central_name)
    if expected_central_chain and expected_central_chain not in prompt:
        issues.append("side-lying pose lacks a continuous horizontal body axis")
    expected_oral_chain = central_oral_reach_chain(
        entry,
        activity,
        central_name,
        spec.cast_key,
    )
    if expected_oral_chain and expected_oral_chain not in prompt:
        issues.append("central oral contact lacks a continuous reach path")
    expected_lift_chain = (
        lifted_bilateral_chain(
            entry,
            central_name,
            actor_name(entry.actor_plans[1].role, spec.cast_key),
        )
        if len(descriptions) > 1
        else None
    )
    if expected_lift_chain and expected_lift_chain not in prompt:
        issues.append("lifted pose lacks a bilateral limb chain")
    for prop in activity.wearable_props:
        owner = actor_name(prop.owner_role, spec.cast_key)
        required_prop_phrases = (
            f"strap-on harness is visibly secured around {owner}'s hips",
            "base fixed to the front of her pelvis",
            "aligned to her pelvic axis",
            "harness, base and proximal shaft remain visible as one connected assembly",
        )
        for value in required_prop_phrases:
            if value.lower() not in lowered:
                issues.append(f"missing wearable prop topology: {value}")
        edge = wearable_edge(activity, prop)
        if edge.source.entity_id != prop.prop_id or edge.source.region != "shaft":
            issues.append("wearable prop is not the contact source")
        owner_sentence = next(
            (
                sentence
                for sentence in prompt.split(". ")
                if sentence.startswith(owner) and "positioned at" in sentence
            ),
            "",
        )
        owner_plan = next(
            plan for plan in entry.actor_plans if plan.role == prop.owner_role
        )
        if owner_plan.pose_function == "supporting_central":
            if "supports" not in owner_sentence or "both arms" not in owner_sentence:
                issues.append("supporting wearable owner lacks arm tasks")
        elif "both_hands" in owner_plan.support_points:
            if (
                "one hand braced" not in owner_sentence
                or "other holding" not in owner_sentence
                or "supported by both hands" in owner_sentence
            ):
                issues.append("wearable prop owner has conflicting hand tasks")
        elif "both hands holding" not in owner_sentence:
            issues.append("standing wearable prop owner lacks hand tasks")
    for prop in activity.handheld_props:
        controller = actor_name(prop.controller_role, spec.cast_key)
        if prop.category == "insertable_toy":
            edge = handheld_edge(activity, prop)
            required_prop_phrases = (
                f"{controller}'s right hand visibly grips the base of {prop.prop_id}",
                f"shaft of {prop.prop_id} follows one continuous line",
                f"aligned to the {phrase(edge.target.region)} canal",
            )
        elif prop.category == "vibrator":
            required_prop_phrases = (
                f"{controller}'s right hand grips the vibrator body",
                "left hand remains visibly on the adjacent thigh",
                "lies transversely across",
                "external clitoral surface",
                "parallel to the pubic line",
                "entirely outside the vaginal opening",
            )
        else:
            edge = handheld_edge(activity, prop)
            target_name = actor_name(edge.target.entity_id, spec.cast_key)
            required_prop_phrases = (
                f"{controller}'s right hand grips {prop.prop_id}",
                f"active surface of {prop.prop_id} follows one continuous",
                f"hand-to-tool path to {target_name}",
            )
        for value in required_prop_phrases:
            if value.lower() not in lowered:
                issues.append(f"missing handheld prop topology: {value}")
        edge = handheld_edge(activity, prop)
        if prop.category == "insertable_toy":
            if (
                edge.source.entity_id != prop.prop_id
                or edge.state != "inserted"
                or edge.target.region not in {"vagina", "anus"}
            ):
                issues.append("insertable handheld prop topology changed")
        elif prop.category == "vibrator" and (
            edge.source.entity_id != prop.prop_id
            or edge.state != "external_contact"
            or edge.target.region != "clitoris"
        ):
            issues.append("handheld vibrator contact topology changed")
        elif prop.category == "surface_tool" and (
            edge.source.entity_id != prop.prop_id
            or edge.state != "external_contact"
        ):
            issues.append("handheld surface tool topology changed")
    if (
        activity.restraint is not None
        and activity.restraint.equipment == ["padded_spreader_bar"]
        and activity.restraint.body_regions == ["ankles"]
    ):
        restraint_chain = (
            f"spreader bar spans directly between {central_name}'s ankles",
            "left end is visibly secured to her left ankle",
            "right end to her right ankle by padded cuffs",
            "Both cuff release tabs remain visible",
        )
        if any(value not in prompt for value in restraint_chain):
            issues.append("spreader bar lacks a visible ankle attachment chain")
    for actor_plan in entry.actor_plans[1:]:
        name = actor_name(actor_plan.role, spec.cast_key)
        expected_partner_chain = partner_body_chain_clause(
            actor_plan,
            activity,
            central_name,
            spec.cast_key,
        )
        if expected_partner_chain not in prompt:
            issues.append(f"{name} lacks one continuous partner body chain")
        actor_sentence = next(
            (
                sentence
                for sentence in prompt.split(". ")
                if sentence.startswith(name) and "positioned at" in sentence
            ),
            "",
        )
        if actor_gives_oral(activity, actor_plan.role):
            if activity.activity_id == "mutual_oral":
                reaches_contact = (
                    "lies fully visible in the opposite direction"
                    in actor_sentence
                    and "only head beside" in actor_sentence
                    and "pelvis beside" in actor_sentence
                )
                has_support = (
                    "supported by side shoulder, side hip and side thigh"
                    in actor_sentence
                )
            else:
                reaches_contact = (
                    "approaches her pelvis from" in actor_sentence
                    and "lowering the torso" in actor_sentence
                )
                has_support = (
                    "supports " in actor_sentence
                    if actor_plan.pose_function == "supporting_central"
                    else "both palms braced" in actor_sentence
                )
            if not reaches_contact or not has_support:
                issues.append(f"{name} lacks a resolved oral reach path")
        if actor_receives_oral(
            activity,
            actor_plan.role,
        ) and not actor_gives_oral(activity, actor_plan.role):
            seated_recipient = entry.central_pose.family == "seated_edge"
            valid_stance = (
                "stands directly in front" in actor_sentence
                and "supported by both feet" in actor_sentence
                if seated_recipient
                else (
                    "high half-kneel" in actor_sentence
                    and "supported by one knee and opposite foot" in actor_sentence
                )
            )
            if not valid_stance or "both hands resting on the thighs" not in (
                actor_sentence
            ):
                issues.append(f"{name} has conflicting oral recipient supports")
        if actor_is_pelvic_penetrator(
            activity, actor_plan.role
        ) and not wearable_prop_for_owner(activity, actor_plan.role):
            if actor_plan.pose_function == "supporting_central":
                if (
                    "stands facing" not in actor_sentence
                    or "feet shoulder-width apart" not in actor_sentence
                    or "knees softly flexed" not in actor_sentence
                ):
                    issues.append(f"{name} lacks a stable lifted support topology")
            elif "both_hands" in actor_plan.support_points and (
                "one hand braced" not in actor_sentence
                or "other stabilizing" not in actor_sentence
                or "supported by both knees and one braced hand" not in actor_sentence
            ):
                issues.append(f"{name} has conflicting penetration support tasks")
        if actor_manual_contact(activity, actor_plan.role):
            manual_support_resolved = (
                "right hand maintained" in actor_sentence
                and (
                    (
                        "both_hands" in actor_plan.support_points
                        and "left hand braced" in actor_sentence
                        and "supported by both knees and one braced hand"
                        in actor_sentence
                    )
                    or (
                        "both_hands" not in actor_plan.support_points
                        and "left hand stabilizing" in actor_sentence
                    )
                )
            )
            if not manual_support_resolved:
                issues.append(f"{name} has conflicting manual-contact hand tasks")
    return issues
