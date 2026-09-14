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

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.provider import OpenAIStoryModel

ROOT = Path(__file__).resolve().parent
CATALOGS = ROOT / "catalogs"
OUTPUT = ROOT / "demo-output"
SceneId = Annotated[str, StringConstraints(pattern=r"^D\d{2}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StyleLayer(StrictModel):
    scene_id: SceneId
    plan_fingerprint: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    setting: str = Field(min_length=20, max_length=220)
    lighting: str = Field(min_length=20, max_length=180)
    palette: str = Field(min_length=10, max_length=150)
    atmosphere: str = Field(min_length=10, max_length=150)


class StyleBatch(StrictModel):
    styles: list[StyleLayer] = Field(min_length=6, max_length=6)


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
    style_direction: str


class ActorIdentity(NamedTuple):
    code: str
    role_label: str
    age: int
    nationality: str
    sex: str

    def description(self) -> str:
        return (
            f"{self.code}, {self.role_label}, a {self.age}-year-old "
            f"{self.nationality} {self.sex}"
        )


SPECS = (
    DemoSpec(
        "D01",
        "one_woman",
        "supine",
        "knees_bent_wide_hands_on_thighs",
        "vibrator_clitoral",
        "high_three_quarter",
        "medium",
        "rainy neon apartment, reflective surfaces, magenta and cyan edge light",
    ),
    DemoSpec(
        "D02",
        "one_woman",
        "seated_reclined",
        "knees_wide_one_hand_thigh",
        "spreader_bar_self_play",
        "front_three_quarter",
        "medium_wide",
        "minimal amber studio, sculptural restraint shadows, fine-art mood",
    ),
    DemoSpec(
        "D03",
        "one_woman_one_man",
        "lifted_supported",
        "legs_wrapped_arms_shoulders",
        "vaginal_lifted",
        "low_three_quarter",
        "full_body",
        "modern corridor, hard side light, deep burgundy and warm skin palette",
    ),
    DemoSpec(
        "D04",
        "one_woman_two_men",
        "supine",
        "knees_bent_wide_arms_outward",
        "vaginal_plus_fellatio",
        "high_three_quarter",
        "medium_wide",
        "luxury hotel suite, focused overhead pool of light, dark emerald accents",
    ),
    DemoSpec(
        "D05",
        "two_women",
        "all_fours",
        "knees_wide_hands_straight",
        "strap_on_vaginal_rear_entry",
        "rear_three_quarter",
        "medium",
        "soft morning bedroom, pale linen, warm rim light and quiet editorial tone",
    ),
    DemoSpec(
        "D06",
        "three_women",
        "seated_reclined",
        "knees_wide_one_hand_thigh",
        "oral_and_manual_on_central",
        "front_three_quarter",
        "medium_wide",
        "contemporary loft, theatrical triangular light, black gold and ivory",
    ),
)

CAST_IDENTITIES = {
    "one_woman": (ActorIdentity("F1", "woman 1", 29, "Chinese", "woman"),),
    "one_woman_one_man": (
        ActorIdentity("F1", "woman 1", 29, "Chinese", "woman"),
        ActorIdentity("M1", "man 1", 32, "Chinese", "man"),
    ),
    "one_woman_two_men": (
        ActorIdentity("F1", "woman 1", 29, "Chinese", "woman"),
        ActorIdentity("M1", "man 1", 32, "Chinese", "man"),
        ActorIdentity("M2", "man 2", 30, "Chinese", "man"),
    ),
    "two_women": (
        ActorIdentity("F1", "woman 1", 29, "Chinese", "woman"),
        ActorIdentity("F2", "woman 2", 30, "Chinese", "woman"),
    ),
    "three_women": (
        ActorIdentity("F1", "woman 1", 29, "Chinese", "woman"),
        ActorIdentity("F2", "woman 2", 30, "Chinese", "woman"),
        ActorIdentity("F3", "woman 3", 31, "Chinese", "woman"),
    ),
}

STYLE_SYSTEM = """
Generate only a non-geometric visual style layer for each supplied scene.
Return exactly D01 through D06 in order and copy each plan fingerprint. Describe
only the room, materials, motivated lighting, palette, and atmosphere. Do not
mention any person, body, pose, activity, contact, camera, framing, viewpoint,
screen position, or anatomy. Keep each field to one concise phrase without a
trailing period. Do not put lighting, palette, or atmosphere content in the
setting field. Use precise ASCII English and no line breaks. Return only schema
data.
""".strip()

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


def body_ledger(cast_key: str) -> str:
    identities = CAST_IDENTITIES[cast_key]
    bodies = [
        (
            f"one continuous {identity.sex} body identified as "
            f"{identity.code} ({identity.role_label})"
        )
        for identity in identities
    ]
    noun = "body" if len(bodies) == 1 else "bodies"
    return (
        f"The complete body ledger contains exactly {len(bodies)} continuous "
        f"{noun}: {joined(bodies)}. Each coded body has one head, one torso, "
        "two arms ending in two hands, and two legs ending in two feet. Every "
        "visible face and limb belongs to exactly one coded body."
    )


def cast_descriptions(cast_key: str) -> tuple[str, ...]:
    return tuple(identity.description() for identity in CAST_IDENTITIES[cast_key])


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
        return (
            "supported by two continuous bilateral cradles: the standing "
            "partner's left forearm supports her left thigh and his left hand "
            "cups her left buttock, while his right forearm supports her right "
            "thigh and his right hand cups her right buttock; his back and "
            "shoulders brace against the wall while both feet remain planted"
        )
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
    if (
        pose.family != "lifted_supported"
        or pose.leg_configuration != "legs_wrapped"
        or pose.arm_configuration != "arms_shoulders"
    ):
        return None
    return (
        f"{central_name}'s single torso faces {partner_name}; her left arm "
        f"circles {partner_name}'s left shoulder and her right arm circles his "
        "right shoulder. Her left thigh wraps around his left side and her "
        "right thigh wraps around his right side, with both knees bent behind "
        f"his hips. {partner_name}'s left forearm supports her left thigh and "
        "his left hand cups her left buttock; his right forearm supports her "
        "right thigh and his right hand cups her right buttock."
    )


def active_regions(activity: ActivityTemplate, slot_id: str) -> set[str]:
    return {
        endpoint.region
        for edge in activity.contact_edges
        for endpoint in (edge.source, edge.target)
        if endpoint.entity_id == slot_id
    }


def actor_is_pelvic_penetrator(
    activity: ActivityTemplate,
    slot_id: str,
) -> bool:
    prop = wearable_prop_for_owner(activity, slot_id)
    central_slot = activity.required_slots[0]
    return any(
        edge.target.entity_id == central_slot
        and edge.target.region in {"vagina", "anus"}
        and (
            (edge.source.entity_id == slot_id and edge.source.region == "penis")
            or (prop is not None and edge.source.entity_id == prop.prop_id)
        )
        for edge in activity.contact_edges
    )


def actor_gives_oral(activity: ActivityTemplate, slot_id: str) -> bool:
    central_slot = activity.required_slots[0]
    return any(
        edge.source.entity_id == slot_id
        and edge.source.region == "mouth"
        and edge.target.entity_id == central_slot
        for edge in activity.contact_edges
    )


def actor_receives_oral(activity: ActivityTemplate, slot_id: str) -> bool:
    central_slot = activity.required_slots[0]
    return any(
        edge.source.entity_id == central_slot
        and edge.source.region == "mouth"
        and edge.target.entity_id == slot_id
        for edge in activity.contact_edges
    )


def actor_manual_contact(
    activity: ActivityTemplate,
    slot_id: str,
) -> ContactEdge | None:
    central_slot = activity.required_slots[0]
    return next(
        (
            edge
            for edge in activity.contact_edges
            if edge.source.entity_id == slot_id
            and edge.source.region in {"hand", "left_hand", "right_hand"}
            and edge.target.entity_id == central_slot
        ),
        None,
    )


def resolved_partner_supports(
    actor_plan,
    activity: ActivityTemplate,
) -> list[str]:
    supports = list(actor_plan.support_points)
    if wearable_prop_for_owner(
        activity, actor_plan.slot_id
    ) or actor_is_pelvic_penetrator(activity, actor_plan.slot_id):
        return [
            "one_braced_hand" if support == "both_hands" else support
            for support in supports
        ]
    if actor_receives_oral(
        activity,
        actor_plan.slot_id,
    ) and not actor_gives_oral(activity, actor_plan.slot_id):
        return ["one_knee", "opposite_foot"]
    if actor_manual_contact(activity, actor_plan.slot_id):
        return [
            "one_braced_hand" if support == "both_hands" else support
            for support in supports
        ]
    regions = active_regions(activity, actor_plan.slot_id)
    if {"hand", "left_hand", "right_hand"}.intersection(regions):
        supports = [
            "one_braced_hand" if support == "both_hands" else support
            for support in supports
            for support in supports
        ]
    return supports


def wearable_prop_for_owner(
    activity: ActivityTemplate,
    slot_id: str,
) -> WearableProp | None:
    return next(
        (prop for prop in activity.wearable_props if prop.owner_slot == slot_id),
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


def partner_relationship(
    actor_plan,
    activity: ActivityTemplate,
    central_name: str,
) -> str:
    slot_id = actor_plan.slot_id
    central_slot = activity.required_slots[0]
    prop = wearable_prop_for_owner(activity, slot_id)
    if prop:
        stance = "stands" if "both_feet" in actor_plan.support_points else "kneels"
        if actor_plan.pose_role == "supporting_central":
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
    relation: str | None = None
    for edge in activity.contact_edges:
        if edge.source.entity_id == slot_id and edge.target.entity_id == central_slot:
            if edge.source.region == "penis":
                relation = (
                    f"kneels between {central_name}'s raised thighs with his "
                    f"pelvis centered on {central_name}'s pelvic contact axis"
                )
                break
            if edge.source.region == "mouth":
                relation = (
                    f"kneels between {central_name}'s knees and lowers the "
                    f"torso between her thighs until the mouth reaches her "
                    "pelvis"
                )
                break
            if edge.source.region in {"hand", "left_hand", "right_hand"}:
                relation = f"aligns beside {central_name}'s upper body"
                break
        if edge.target.entity_id == slot_id and edge.source.entity_id == central_slot:
            if edge.target.region in {"penis", "vulva"}:
                relation = (
                    f"holds a high half-kneel beside {central_name}'s head, "
                    "with one knee down and the opposite foot planted so the "
                    "pelvis rises to her mouth level"
                )
                break
    if actor_plan.pose_role == "supporting_central":
        if actor_is_pelvic_penetrator(activity, actor_plan.slot_id):
            return (
                "stands with his back and shoulders against the wall, facing "
                f"{central_name} with feet shoulder-width apart, and supports "
                "her through a left-side forearm-and-hand cradle and a matching "
                "right-side cradle while keeping their pelvises aligned"
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
    if not wearable_prop_for_owner(activity, actor_plan.slot_id):
        if actor_plan.pose_role == "supporting_central":
            return ""
        if actor_is_pelvic_penetrator(activity, actor_plan.slot_id):
            if "both_hands" in actor_plan.support_points:
                return (
                    f", with one hand braced on the {phrase(support_surface)} "
                    f"and the other stabilizing {central_name}'s thigh"
                )
            return f", with both hands stabilizing {central_name}'s hips"
        if actor_gives_oral(activity, actor_plan.slot_id):
            return (
                f", with both palms braced on the {phrase(support_surface)} "
                f"beside {central_name}'s hips"
            )
        if actor_receives_oral(activity, actor_plan.slot_id):
            return ", with both hands resting on the thighs"
        manual_edge = actor_manual_contact(activity, actor_plan.slot_id)
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
        return ""
    if actor_plan.pose_role == "supporting_central":
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
    slots = [slot[0] for slot in CASTS[cast_key]]
    if entity_id in slots:
        index = slots.index(entity_id)
        identities = CAST_IDENTITIES[cast_key]
        if index < len(identities):
            return identities[index].code
    if entity_id.startswith("prop_"):
        return "the selected toy or wearable prop"
    return entity_id


def occluders_for(edge_regions: set[str]) -> str:
    if {"mouth", "penis"}.issubset(edge_regions):
        return "the receiving actor's single head silhouette"
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
    activity: ActivityTemplate,
    prop: WearableProp,
    cast_key: str,
) -> tuple[list[str], str]:
    edge = wearable_edge(activity, prop)
    owner = actor_name(prop.owner_slot, cast_key)
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
            f"{phrase(edge.screen_position)} in the "
            f"{phrase(edge.depth_plane)} remains occluded by "
            f"{occluders_for({edge.source.region, edge.target.region})}; "
            "the actual insertion point is not shown."
        )
    else:
        sentences.append(
            f"The visible {phrase(edge.edge_id)} {phrase(edge.state)} contact "
            f"continues directly from the fixed base at "
            f"{phrase(edge.screen_position)} in the "
            f"{phrase(edge.depth_plane)}."
        )
    return sentences, edge.edge_id


def compile_handheld_prop(
    activity: ActivityTemplate,
    prop: HandheldProp,
    cast_key: str,
) -> tuple[list[str], str]:
    edge = handheld_edge(activity, prop)
    controller = actor_name(prop.controller_slot, cast_key)
    target = actor_name(edge.target.entity_id, cast_key)
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
            f"the external clitoral surface at {phrase(edge.screen_position)} "
            f"in the {phrase(edge.depth_plane)}."
        ),
    ]
    return sentences, edge.edge_id


def compile_geometry(
    spec: DemoSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
) -> str:
    descriptions = cast_descriptions(spec.cast_key)
    central_name = actor_name(entry.central_slot, spec.cast_key)
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
            actor_name(entry.actor_plans[1].slot_id, spec.cast_key),
        )
        if chain:
            sentences.append(chain)
    for actor_plan in entry.actor_plans[1:]:
        actor_name_value = actor_name(actor_plan.slot_id, spec.cast_key)
        relationship = partner_relationship(
            actor_plan,
            activity,
            central_name,
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
        if actor_plan.pose_role == "supporting_central" and actor_is_pelvic_penetrator(
            activity, actor_plan.slot_id
        ):
            sentences.append(
                "The front-to-back order is the wall, "
                f"{actor_name_value}, {central_name}, "
                "then the viewer."
            )
    sentences.append(
        f"The primary activity is {natural_activity(activity.activity_id)}."
    )
    handled_prop_edges: set[str] = set()
    for prop in activity.handheld_props:
        prop_sentences, edge_id = compile_handheld_prop(
            activity,
            prop,
            spec.cast_key,
        )
        sentences.extend(prop_sentences)
        handled_prop_edges.add(edge_id)
    for prop in activity.wearable_props:
        prop_sentences, edge_id = compile_wearable_prop(
            activity,
            prop,
            spec.cast_key,
        )
        sentences.extend(prop_sentences)
        handled_prop_edges.add(edge_id)
    for edge in activity.contact_edges:
        if edge.edge_id in handled_prop_edges:
            continue
        regions = {edge.source.region, edge.target.region}
        ownership = anatomical_endpoint_ownership(edge, spec.cast_key)
        if ownership:
            sentences.append(ownership)
        if edge.preferred_visibility == "occluded":
            sentences.append(
                f"The {phrase(edge.edge_id)} {phrase(edge.state)} contact "
                f"at {phrase(edge.screen_position)} in the "
                f"{phrase(edge.depth_plane)} remains occluded by "
                f"{occluders_for(regions)}; its local endpoints are not shown."
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
                f"{phrase(edge.screen_position)} in the "
                f"{phrase(edge.depth_plane)}."
            )
    if activity.restraint.enabled:
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


def style_issues(
    expected: dict[str, str],
    style: StyleLayer,
) -> list[str]:
    issues: list[str] = []
    if style.scene_id != expected["scene_id"]:
        issues.append("scene_id changed")
    if style.plan_fingerprint != expected["plan_fingerprint"]:
        issues.append("plan fingerprint changed")
    text = " ".join((style.setting, style.lighting, style.palette, style.atmosphere))
    if not text.isascii():
        issues.append("style layer contains non-ASCII text")
    forbidden = re.compile(
        r"\b(?:camera|frame|framing|viewpoint|woman|man|person|body|skin|pose|"
        r"contact|intercourse|fellatio|cunnilingus|masturbation|penis|vagina|"
        r"vulva|anus|breast|clitoris)\b",
        re.I,
    )
    matches = sorted({match.group(0).lower() for match in forbidden.finditer(text)})
    if matches:
        issues.append(f"style layer changed geometry vocabulary: {matches}")
    if re.search(
        r"\b(?:lighting|palette|atmosphere|motivated)\b",
        style.setting,
        re.I,
    ):
        issues.append("setting contains another style field")
    for field_name, value in (
        ("setting", style.setting),
        ("lighting", style.lighting),
        ("palette", style.palette),
        ("atmosphere", style.atmosphere),
    ):
        if value.rstrip().endswith("."):
            issues.append(f"{field_name} has a trailing period")
        if re.search(r"\b[a-z]{1,2}\.?$", value.rstrip(), re.I):
            issues.append(f"{field_name} ends with a truncated word")
    return issues


def combine_prompt(geometry: str, style: StyleLayer) -> str:
    setting = style.setting.strip().rstrip(".")
    lighting = style.lighting.strip().rstrip(".")
    palette = style.palette.strip().rstrip(".")
    atmosphere = style.atmosphere.strip().rstrip(".")
    return " ".join(
        (
            geometry,
            f"Setting: {setting}.",
            f"Lighting: {lighting}.",
            f"Palette: {palette}.",
            f"Atmosphere: {atmosphere}.",
        )
    )


def prompt_issues(
    spec: DemoSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
    prompt: str,
) -> list[str]:
    issues: list[str] = []
    descriptions = cast_descriptions(spec.cast_key)
    central_name = actor_name(entry.central_slot, spec.cast_key)
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
        if visibility == "occluded":
            local_terms = {edge.source.region, edge.target.region}
            geometry_contact = next(
                (
                    sentence
                    for sentence in prompt.split(". ")
                    if phrase(edge.edge_id) in sentence and "contact" in sentence
                ),
                "",
            )
            if any(phrase(term) in geometry_contact for term in local_terms):
                issues.append(f"{edge.edge_id} exposes an occluded endpoint")
        expected_ownership = anatomical_endpoint_ownership(
            edge,
            spec.cast_key,
        )
        if expected_ownership and expected_ownership not in prompt:
            issues.append(f"{edge.edge_id} lacks anatomical endpoint ownership")
    expected_lift_chain = (
        lifted_bilateral_chain(
            entry,
            central_name,
            actor_name(entry.actor_plans[1].slot_id, spec.cast_key),
        )
        if len(descriptions) > 1
        else None
    )
    if expected_lift_chain and expected_lift_chain not in prompt:
        issues.append("lifted pose lacks a bilateral limb chain")
    for prop in activity.wearable_props:
        owner = actor_name(prop.owner_slot, spec.cast_key)
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
            plan for plan in entry.actor_plans if plan.slot_id == prop.owner_slot
        )
        if owner_plan.pose_role == "supporting_central":
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
        controller = actor_name(prop.controller_slot, spec.cast_key)
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
        if (
            edge.source.entity_id != prop.prop_id
            or edge.state != "external_contact"
            or edge.target.region != "clitoris"
        ):
            issues.append("handheld vibrator contact topology changed")
    if activity.restraint.equipment == [
        "padded_spreader_bar"
    ] and activity.restraint.body_regions == ["ankles"]:
        restraint_chain = (
            f"spreader bar spans directly between {central_name}'s ankles",
            "left end is visibly secured to her left ankle",
            "right end to her right ankle by padded cuffs",
            "Both cuff release tabs remain visible",
        )
        if any(value not in prompt for value in restraint_chain):
            issues.append("spreader bar lacks a visible ankle attachment chain")
    for actor_plan in entry.actor_plans[1:]:
        name = actor_name(actor_plan.slot_id, spec.cast_key)
        actor_sentence = next(
            (
                sentence
                for sentence in prompt.split(". ")
                if sentence.startswith(name) and "positioned at" in sentence
            ),
            "",
        )
        if actor_gives_oral(activity, actor_plan.slot_id):
            if (
                "lowers the torso" not in actor_sentence
                or "both palms braced" not in actor_sentence
            ):
                issues.append(f"{name} lacks a resolved oral reach path")
        if actor_receives_oral(
            activity,
            actor_plan.slot_id,
        ) and not actor_gives_oral(activity, actor_plan.slot_id):
            if (
                "high half-kneel" not in actor_sentence
                or "both hands resting on the thighs" not in actor_sentence
                or "supported by one knee and opposite foot" not in actor_sentence
            ):
                issues.append(f"{name} has conflicting oral recipient supports")
        if actor_is_pelvic_penetrator(
            activity, actor_plan.slot_id
        ) and not wearable_prop_for_owner(activity, actor_plan.slot_id):
            if actor_plan.pose_role == "supporting_central":
                if (
                    "stands with his back and shoulders against the wall"
                    not in actor_sentence
                    or "front-to-back order is the wall" not in prompt
                ):
                    issues.append(f"{name} lacks a stable lifted support topology")
            elif "both_hands" in actor_plan.support_points and (
                "one hand braced" not in actor_sentence
                or "other stabilizing" not in actor_sentence
                or "supported by both knees and one braced hand" not in actor_sentence
            ):
                issues.append(f"{name} has conflicting penetration support tasks")
        if actor_manual_contact(activity, actor_plan.slot_id):
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
        if evaluation.verdict != "pass" and speculative.search(
            " ".join(evaluation.issues)
        ):
            issues[evaluation.scene_id] = [
                "non-passing verdict relies on speculative rendering risk"
            ]
    return issues


async def run() -> dict[str, object]:
    selected = []
    style_requests = []
    for spec in SPECS:
        catalog = load_catalog(spec.cast_key)
        entry, activity = select_plan(catalog, spec)
        fingerprint = plan_fingerprint(spec, entry, activity)
        geometry = compile_geometry(spec, entry, activity)
        selected.append((spec, entry, activity, fingerprint, geometry))
        style_requests.append(
            {
                "scene_id": spec.scene_id,
                "plan_fingerprint": fingerprint,
                "style_direction": spec.style_direction,
            }
        )

    settings = load_story_provider_settings()
    style_attempts = 0
    style_rejections: list[list[str]] = []
    style_validation_issues: dict[str, list[str]] = {}
    payload: dict[str, object] = {"scenes": style_requests}
    async with OpenAIStoryModel(settings) as model:
        for _ in range(3):
            style_attempts += 1
            style_response, rejections = await _generate_with_repair(
                model,
                system=STYLE_SYSTEM,
                payload=payload,
                response_model=StyleBatch,
                max_output_tokens=min(8000, settings.output_token_limit),
            )
            style_rejections.extend(rejections)
            style_batch = StyleBatch.model_validate(style_response.value)
            style_validation_issues = {}
            for request, style in zip(
                style_requests,
                style_batch.styles,
                strict=True,
            ):
                issues = style_issues(request, style)
                if issues:
                    style_validation_issues[request["scene_id"]] = issues
            if not style_validation_issues:
                break
            payload = {
                "scenes": style_requests,
                "previous_styles": style_batch.model_dump(mode="json"),
                "validation_issues": style_validation_issues,
                "repair_requirement": (
                    "Return all six corrected style layers without geometry words."
                ),
            }

        prompts = [
            combine_prompt(geometry, style)
            for (_, _, _, _, geometry), style in zip(
                selected,
                style_batch.styles,
                strict=True,
            )
        ]
        hard_issues: dict[str, list[str]] = {}
        for (spec, entry, activity, _, _), prompt in zip(
            selected,
            prompts,
            strict=True,
        ):
            issues = prompt_issues(spec, entry, activity, prompt)
            if issues:
                hard_issues[spec.scene_id] = issues
        evaluation_payload: dict[str, object] = {
            "scenes": [
                {"scene_id": spec.scene_id, "prompt": prompt}
                for (spec, _, _, _, _), prompt in zip(
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
        "style_attempts": style_attempts,
        "style_validation_issues": style_validation_issues,
        "style_structured_rejections": style_rejections,
        "hard_geometry_issues": hard_issues,
        "average_visual_impact": average_impact,
        "evaluations": evaluations.model_dump(mode="json")["evaluations"],
        "evaluation_attempts": evaluation_attempts,
        "evaluation_validation_issues": evaluation_validation_issues,
        "evaluation_structured_rejections": evaluation_rejections,
        "passed": (
            not style_validation_issues
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
    (OUTPUT / "styles.json").write_text(
        style_batch.model_dump_json(indent=2) + "\n",
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
