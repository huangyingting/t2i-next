from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, NamedTuple

from catalog_generator import (
    CASTS,
    ActivityTemplate,
    ContactEdge,
    HandheldProp,
    PoseCatalog,
    PoseEntry,
    WearableProp,
)
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from run import _generate_with_repair
from scene_layers import (
    CHARACTER_PROFILES,
    SETTING_PRESETS,
    ResolvedSceneLayers,
    SettingPreset,
    layer_issues,
    resolve_scene_layers,
)

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.provider import OpenAIStoryModel

ROOT = Path(__file__).resolve().parent
CATALOGS = ROOT / "catalogs"
OUTPUT = ROOT / "demo-output"
SceneId = Annotated[str, StringConstraints(pattern=r"^D\d{2}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SceneEvaluation(StrictModel):
    scene_id: SceneId
    geometry_coherence: int = Field(ge=1, le=10)
    visual_impact: int = Field(ge=1, le=10)
    cast_clarity: int = Field(ge=1, le=10)
    contact_clarity: int = Field(ge=1, le=10)
    style_integration: int = Field(ge=1, le=10)
    strengths: list[str] = Field(min_length=1, max_length=4)
    issues: list[str] = Field(
        max_length=4,
        description=(
            "Actionable material defects only; must be [] when verdict is pass."
        ),
    )
    verdict: Annotated[
        str,
        StringConstraints(pattern=r"^(pass|revise|reject)$"),
    ]

    @model_validator(mode="after")
    def verdict_matches_issues(self) -> SceneEvaluation:
        if self.verdict == "pass" and self.issues:
            raise ValueError("passing evaluations cannot contain issues")
        if self.verdict != "pass" and not self.issues:
            raise ValueError("non-passing evaluations require an issue")
        return self


class EvaluationBatch(StrictModel):
    evaluations: list[SceneEvaluation] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def scene_ids_are_complete(self) -> EvaluationBatch:
        ids = [evaluation.scene_id for evaluation in self.evaluations]
        if ids != [f"D{index:02d}" for index in range(1, 7)]:
            raise ValueError("evaluation IDs must be D01 through D06")
        return self


class DemoSpec(NamedTuple):
    scene_id: str
    cast_key: str
    family: str
    variant: str
    activity_id: str
    viewpoint: str
    shot_scale: str
    setting_id: str


SPECS = (
    DemoSpec(
        "D01",
        "one_woman",
        "supine",
        "knees_bent_wide_hands_on_thighs",
        "vibrator_clitoral",
        "high_three_quarter",
        "medium",
        "rainy_neon_apartment",
    ),
    DemoSpec(
        "D02",
        "one_woman",
        "seated_reclined",
        "knees_wide_one_hand_thigh",
        "spreader_bar_self_play",
        "front_three_quarter",
        "medium_wide",
        "amber_restraint_studio",
    ),
    DemoSpec(
        "D03",
        "one_woman_one_man",
        "lifted_supported",
        "legs_wrapped_arms_shoulders",
        "vaginal_lifted",
        "low_three_quarter",
        "full_body",
        "burgundy_modern_corridor",
    ),
    DemoSpec(
        "D04",
        "one_woman_two_men",
        "supine",
        "knees_bent_wide_arms_outward",
        "vaginal_plus_fellatio",
        "high_three_quarter",
        "medium_wide",
        "midnight_luxury_hotel",
    ),
    DemoSpec(
        "D05",
        "two_women",
        "all_fours",
        "knees_wide_hands_straight",
        "strap_on_vaginal_rear_entry",
        "rear_three_quarter",
        "medium",
        "soft_morning_bedroom",
    ),
    DemoSpec(
        "D06",
        "three_women",
        "seated_reclined",
        "knees_wide_one_hand_thigh",
        "oral_and_manual_on_central",
        "front_three_quarter",
        "medium_wide",
        "demon_sovereign_palace",
    ),
)

EVALUATION_SYSTEM = """
Evaluate each complete image prompt independently. Score geometry coherence,
visual impact, cast clarity, contact clarity, and style integration from 1 to
10. Check whether the stated camera can show the planned pose, whether supports
are credible, whether every actor has one coherent role, whether visible and
occluded contacts remain consistent, whether every wearable prop is visibly
anchored to its owner, whether limb tasks conflict with support points, and
whether lighting strengthens the silhouette. Verify that the body ledger has
exactly one continuous body per coded actor and that upper-body, lower-body,
support, and contact tasks do not split one actor into duplicate bodies. Use
pass only when no material correction is required. Return exactly D01 through
D06 in order and only schema data. A pass verdict MUST use an empty issues
array. Never put a pass rationale, summary, minor observation, or praise in
issues. Any non-empty issues array MUST use revise or reject. Report an issue
only for a deterministic contradiction, an anatomically impossible 2D
relationship, a disconnected ownership/contact chain, or a limb assigned to
incompatible simultaneous tasks. Do not report speculative rendering
difficulty, reduced prominence, possible overlap, or a contact being fully
hidden when its plan explicitly requires occluded local endpoints.
""".strip()


def phrase(value: str) -> str:
    return value.replace("_", " ")


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
    }.get(value, phrase(value))


def joined(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f" and {values[-1]}"


def role_sex(role: str) -> str:
    return "woman" if role.startswith("f") else "man"


def role_label(role: str) -> str:
    return f"{role_sex(role)} {role[1:]}"


def role_description(role: str) -> str:
    profile = CHARACTER_PROFILES[role]
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
    noun = "body" if len(bodies) == 1 else "bodies"
    return (
        f"The complete body ledger contains exactly {len(bodies)} continuous "
        f"{noun}: {joined(bodies)}. Each coded body has one head, one torso, "
        "two arms ending in two hands, and two legs ending in two feet. Every "
        "visible face and limb belongs to exactly one coded body."
    )


def cast_descriptions(cast_key: str) -> tuple[str, ...]:
    return tuple(role_description(role) for role in CASTS[cast_key])


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
    surface = {
        "bed": "the bed",
        "bed_edge": "the edge of the bed",
        "floor": "the floor",
        "wall": "the wall",
        "chair": "the chair",
        "sofa": "the sofa",
    }.get(pose.primary_surface, f"the {phrase(pose.primary_surface)}")
    return f"supported at {joined(points)} on {surface}"


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
            f"supports her left thigh and {possessive} left hand secures her "
            f"outer left hip; {possessive} right forearm supports her right "
            f"thigh and {possessive} right hand secures her outer right hip."
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
            "both hands securing the outer hips."
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
        and edge.source.region == "mouth"
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


def resolved_partner_supports(
    actor_plan,
    activity: ActivityTemplate,
) -> list[str]:
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
            if edge.source.region == "mouth":
                side = (
                    "left" if actor_plan.screen_position == "center_left" else "right"
                )
                if "both_feet" in actor_plan.support_points:
                    relation = (
                        f"holds a low standing crouch beside {central_name}'s "
                        f"{side} thigh and approaches her pelvis from the {side}, "
                        "lowering the torso until the mouth reaches its assigned "
                        "contact"
                    )
                else:
                    relation = (
                        f"kneels beside {central_name}'s {side} thigh and "
                        f"approaches her pelvis from the {side}, lowering the "
                        "torso until the mouth reaches its assigned contact"
                    )
                break
            if edge.source.region in {"hand", "left_hand", "right_hand"}:
                relation = f"aligns beside {central_name}'s upper body"
                break
        if edge.target.entity_id == role and edge.source.entity_id == central_role:
            if edge.source.region == "mouth" and edge.target.region in {
                "penis",
                "vulva",
            }:
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
                    f"kneels on all fours to {central_name}'s {side}, with the "
                    f"pelvis angled inward within reach of {central_name}'s "
                    "assigned hand"
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
            .replace("is positioned", "positioned", 1)
            if relation
            else ""
        )
        detail = f" while {supporting_relation}" if supporting_relation else ""
        return f"supports {central_name} with both arms{detail}"
    return relation or f"aligned with {central_name}"


def partner_limb_clause(
    actor_plan,
    activity: ActivityTemplate,
    central_name: str,
    support_surface: str,
) -> str:
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
                    f", with the contacting hand maintained at {central_name}'s "
                    f"{target} and the other hand stabilizing "
                    f"{central_name}'s torso"
                )
            return (
                f", with the contacting hand maintained at {central_name}'s "
                f"{target} and the other hand braced on the "
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


def load_catalog(cast_key: str) -> PoseCatalog:
    return PoseCatalog.model_validate_json(
        (CATALOGS / f"{cast_key}.json").read_text(encoding="utf-8")
    )


def select_plan(
    catalog: PoseCatalog,
    spec: DemoSpec,
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
    if spec.viewpoint not in entry.central_pose.compatible_camera_views:
        raise ValueError(f"{spec.scene_id} camera and pose are incompatible")
    return entry, activity


def plan_fingerprint(
    spec: DemoSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
) -> str:
    payload = {
        "spec": spec._asdict(),
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
    if "mouth" in edge_regions:
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
    if prop.category == "insertable_toy":
        target_region = phrase(edge.target.region)
        sentences = [
            (
                f"{controller}'s right hand visibly grips the base of "
                f"{prop.prop_id}; her left hand remains braced for support."
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
    sentences = [
        (
            f"{controller}'s right hand grips the vibrator body and controls "
            "its pressure; her left hand remains visibly on her inner thigh."
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
                and endpoint.region in {"vagina", "anus"}
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
    return (
        f"{focus_name} remains one continuous body along the bed's long axis: "
        f"her pelvis stays at {phrase(pelvic_position)} in the "
        f"{phrase(pelvic_depth)} beside {actor_name(pelvic_partner, cast_key)}, "
        f"and her torso connects continuously to her only head at "
        f"{phrase(mouth_position)} in the {phrase(mouth_depth)} beside "
        f"{actor_name(mouth_partner, cast_key)}. No additional head, torso, "
        "partial body or person occupies either contact zone."
    )


def compile_geometry(
    spec: DemoSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
) -> str:
    descriptions = cast_descriptions(spec.cast_key)
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
            f"{phrase(spec.shot_scale)} composition."
        ),
        (
            f"{central_name} holds {article} "
            f"{pose_name} pose at image center with "
            f"{natural_component(pose.leg_configuration)} and "
            f"{natural_component(pose.arm_configuration)}; "
            f"she is {support_clause(entry)}."
        ),
    ]
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
            continue
        screen_position, depth_plane = contact_projection(entry, activity, edge)
        ownership = anatomical_endpoint_ownership(edge, spec.cast_key)
        if ownership:
            sentences.append(ownership)
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
    spec: DemoSpec,
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
    spec: DemoSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
    fingerprint: str,
    geometry: str,
    setting: SettingPreset,
) -> ResolvedSceneLayers:
    required, visible = region_visibility_maps(spec, activity)
    return resolve_scene_layers(
        scene_id=spec.scene_id,
        spatial_fingerprint=fingerprint,
        geometry=geometry,
        cast_roles=list(CASTS[spec.cast_key]),
        body_level=entry.central_pose.body_level,
        setting=setting,
        required_regions_by_role=required,
        visible_regions_by_role=visible,
        layer_budget_tokens=200,
    )


def combine_prompt(geometry: str, layers: ResolvedSceneLayers) -> str:
    return f"{geometry} {layers.compact_suffix}"


def prompt_issues(
    spec: DemoSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
    prompt: str,
) -> list[str]:
    issues: list[str] = []
    descriptions = cast_descriptions(spec.cast_key)
    central_name = actor_name(activity.focus_role, spec.cast_key)
    if not prompt.isascii() or "\n" in prompt or "\r" in prompt:
        issues.append("prompt is not one ASCII paragraph")
    if len(re.findall(r"\bcamera\b", prompt, re.I)) != 1:
        issues.append("camera is not stated exactly once")
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
        edge_sentence = next(
            (
                sentence
                for sentence in prompt.split(". ")
                if phrase(edge.edge_id) in sentence
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
        else:
            required_prop_phrases = (
                f"{controller}'s right hand grips the vibrator body",
                "left hand remains visibly on her inner thigh",
                "lies transversely across",
                "external clitoral surface",
                "parallel to the pubic line",
                "entirely outside the vaginal opening",
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
        elif (
            edge.source.entity_id != prop.prop_id
            or edge.state != "external_contact"
            or edge.target.region != "clitoris"
        ):
            issues.append("handheld vibrator contact topology changed")
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
        actor_sentence = next(
            (
                sentence
                for sentence in prompt.split(". ")
                if sentence.startswith(name) and "positioned at" in sentence
            ),
            "",
        )
        if actor_gives_oral(activity, actor_plan.role):
            if (
                "approaches her pelvis from" not in actor_sentence
                or "lowering the torso" not in actor_sentence
                or "both palms braced" not in actor_sentence
            ):
                issues.append(f"{name} lacks a resolved oral reach path")
        if actor_receives_oral(
            activity,
            actor_plan.role,
        ) and not actor_gives_oral(activity, actor_plan.role):
            if (
                "high half-kneel" not in actor_sentence
                or "both hands resting on the thighs" not in actor_sentence
                or "supported by one knee and opposite foot" not in actor_sentence
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
                "contacting hand maintained" in actor_sentence
                and (
                    (
                        "both_hands" in actor_plan.support_points
                        and "other hand braced" in actor_sentence
                        and "supported by both knees and one braced hand"
                        in actor_sentence
                    )
                    or (
                        "both_hands" not in actor_plan.support_points
                        and "other hand stabilizing" in actor_sentence
                    )
                )
            )
            if not manual_support_resolved:
                issues.append(f"{name} has conflicting manual-contact hand tasks")
    return issues


def evaluation_contract_issues(
    evaluations: EvaluationBatch,
) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {}
    speculative = re.compile(
        r"\b(?:may|might|could|potential|possibly|depending|risk|plausible|"
        r"likely|unlikely|challenge|not definitive|not impossible)\b",
        re.I,
    )
    for evaluation in evaluations.evaluations:
        scores = (
            evaluation.geometry_coherence,
            evaluation.visual_impact,
            evaluation.cast_clarity,
            evaluation.contact_clarity,
            evaluation.style_integration,
        )
        if evaluation.verdict == "pass" and min(scores) < 7:
            issues[evaluation.scene_id] = [
                "pass verdict has a score below 7 without an actionable defect"
            ]
        if evaluation.verdict != "pass" and speculative.search(
            " ".join(evaluation.issues)
        ):
            issues[evaluation.scene_id] = [
                "non-passing verdict relies on speculative rendering risk"
            ]
    return issues


async def run() -> dict[str, object]:
    selected = []
    prompts = []
    resolved_layers = []
    layer_validation_issues: dict[str, list[str]] = {}
    hard_issues: dict[str, list[str]] = {}
    for spec in SPECS:
        catalog = load_catalog(spec.cast_key)
        entry, activity = select_plan(catalog, spec)
        fingerprint = plan_fingerprint(spec, entry, activity)
        geometry = compile_geometry(spec, entry, activity)
        setting = SETTING_PRESETS[spec.setting_id]
        layers = compile_scene_layers(
            spec,
            entry,
            activity,
            fingerprint,
            geometry,
            setting,
        )
        prompt = combine_prompt(geometry, layers)
        selected.append((spec, entry, activity))
        resolved_layers.append(layers)
        prompts.append(prompt)
        current_layer_issues = layer_issues(
            layers,
            list(CASTS[spec.cast_key]),
        )
        if current_layer_issues:
            layer_validation_issues[spec.scene_id] = current_layer_issues
        current_hard_issues = prompt_issues(spec, entry, activity, prompt)
        if current_hard_issues:
            hard_issues[spec.scene_id] = current_hard_issues

    settings = load_story_provider_settings()
    async with OpenAIStoryModel(settings) as model:
        evaluation_payload: dict[str, object] = {
            "scenes": [
                {"scene_id": spec.scene_id, "prompt": prompt}
                for (spec, _, _), prompt in zip(
                    selected,
                    prompts,
                    strict=True,
                )
            ]
        }
        evaluation_rejections: list[list[str]] = []
        evaluation_validation_issues: dict[str, list[str]] = {}
        evaluation_attempts = 0
        for _ in range(3):
            evaluation_attempts += 1
            evaluation_response, rejections = await _generate_with_repair(
                model,
                system=EVALUATION_SYSTEM,
                payload=evaluation_payload,
                response_model=EvaluationBatch,
                max_output_tokens=min(8000, settings.output_token_limit),
            )
            evaluation_rejections.extend(rejections)
            evaluations = EvaluationBatch.model_validate(evaluation_response.value)
            evaluation_validation_issues = evaluation_contract_issues(evaluations)
            if not evaluation_validation_issues:
                break
            evaluation_payload = {
                "scenes": evaluation_payload["scenes"],
                "previous_evaluations": evaluations.model_dump(mode="json"),
                "validation_issues": evaluation_validation_issues,
                "repair_requirement": (
                    "Re-evaluate all six scenes. A non-passing verdict must "
                    "identify a deterministic contradiction, not a possible "
                    "rendering difficulty."
                ),
            }

    average_impact = sum(
        evaluation.visual_impact for evaluation in evaluations.evaluations
    ) / len(evaluations.evaluations)
    evaluation_passed = all(
        evaluation.verdict == "pass" for evaluation in evaluations.evaluations
    )
    report = {
        "model": settings.model,
        "scene_count": len(prompts),
        "cast_keys": [spec.cast_key for spec in SPECS],
        "setting_ids": [spec.setting_id for spec in SPECS],
        "layer_validation_issues": layer_validation_issues,
        "hard_geometry_issues": hard_issues,
        "token_metrics": {
            "geometry_estimated_tokens": sum(
                layers.token_metrics.geometry_estimated_tokens
                for layers in resolved_layers
            ),
            "layer_estimated_tokens": sum(
                layers.token_metrics.layer_estimated_tokens
                for layers in resolved_layers
            ),
            "verbose_layer_estimated_tokens": sum(
                layers.token_metrics.verbose_layer_estimated_tokens
                for layers in resolved_layers
            ),
            "compact_saved_tokens": sum(
                layers.token_metrics.compact_saved_tokens for layers in resolved_layers
            ),
            "final_estimated_tokens": sum(
                layers.token_metrics.final_estimated_tokens
                for layers in resolved_layers
            ),
            "saved_style_generation_calls": len(prompts),
        },
        "average_visual_impact": average_impact,
        "evaluations": evaluations.model_dump(mode="json")["evaluations"],
        "evaluation_attempts": evaluation_attempts,
        "evaluation_validation_issues": evaluation_validation_issues,
        "evaluation_structured_rejections": evaluation_rejections,
        "passed": (
            not layer_validation_issues
            and not hard_issues
            and not evaluation_validation_issues
            and evaluation_passed
        ),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "prompts.txt").write_text(
        "\n".join(prompts) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "layers.json").write_text(
        json.dumps(
            [layers.model_dump(mode="json") for layers in resolved_layers],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "evaluations.json").write_text(
        evaluations.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = asyncio.run(run())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
