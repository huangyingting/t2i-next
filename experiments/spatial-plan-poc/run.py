from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.errors import StoryStructuredOutputError
from t2i_story_pipeline.models import StoryStage
from t2i_story_pipeline.provider import (
    ChatMessage,
    ModelResponse,
    OpenAIStoryModel,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_SCENARIO = ROOT / "scenario.json"
DEFAULT_OUTPUT = ROOT / "output"
Semantic = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]
RegionRef = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=129,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*\.[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]
ALLOWED_ACTOR_IDS = {"f1", "m1"}
ALLOWED_SCREEN_POSITIONS = {"center", "center_left", "center_right"}
ALLOWED_DEPTH_PLANES = {"foreground", "midground", "background"}
ALLOWED_POSES = {"kneeling_forward", "kneeling_upright"}
ALLOWED_BODY_PARTS = {
    "head",
    "pubic_region",
    "left_knee",
    "right_knee",
    "left_hand",
    "right_hand",
}
ALLOWED_REGION_REFS = {
    "f1.head",
    "f1.mouth",
    "f1.torso",
    "f1.arms",
    "f1.legs",
    "m1.pubic_region",
    "m1.near_thigh",
    "m1.torso",
    "m1.arms",
    "m1.legs",
}
ALLOWED_SUPPORT_IDS = {
    "f1_knee_support",
    "f1_hand_support",
    "m1_knee_support",
    "m1_hand_support",
}
ALLOWED_SUPPORT_REGIONS = {"both_knees", "both_hands", "mattress"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"


class ContactState(StrEnum):
    SEPARATED = "separated"
    EXTERNAL_CONTACT = "external_contact"
    INSERTED = "inserted"


class Visibility(StrEnum):
    VISIBLE = "visible"
    OCCLUDED = "occluded"


class AssignmentPurpose(StrEnum):
    POSE = "pose"
    SUPPORT = "support"
    CONTACT = "contact"


class LimbAssignment(StrictModel):
    body_part: Semantic
    purpose: AssignmentPurpose
    target_id: Semantic | None


class ActorGeometry(StrictModel):
    actor_id: Semantic
    sex: Sex
    description: str = Field(min_length=1, max_length=200)
    screen_position: Semantic
    depth_plane: Semantic
    pose: Semantic
    limb_assignments: list[LimbAssignment] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def body_parts_have_one_role(self) -> ActorGeometry:
        if self.actor_id not in ALLOWED_ACTOR_IDS:
            raise ValueError(f"unknown actor ID: {self.actor_id}")
        if self.screen_position not in ALLOWED_SCREEN_POSITIONS:
            raise ValueError(f"unknown screen position: {self.screen_position}")
        if self.depth_plane not in ALLOWED_DEPTH_PLANES:
            raise ValueError(f"unknown depth plane: {self.depth_plane}")
        if self.pose not in ALLOWED_POSES:
            raise ValueError(f"unknown pose: {self.pose}")
        parts = [assignment.body_part for assignment in self.limb_assignments]
        unknown_parts = sorted(set(parts) - ALLOWED_BODY_PARTS)
        if unknown_parts:
            raise ValueError(f"unknown body parts: {unknown_parts}")
        if len(parts) != len(set(parts)):
            raise ValueError(f"{self.actor_id} assigns one body part more than once")
        return self


class CameraGeometry(StrictModel):
    viewpoint: Semantic
    shot_scale: Semantic
    visible_regions: list[RegionRef] = Field(max_length=12)
    occluded_regions: list[RegionRef] = Field(max_length=4)
    visible_contacts: list[Semantic] = Field(max_length=1)
    occluded_contacts: list[Semantic] = Field(max_length=1)


class ContactGeometry(StrictModel):
    contact_id: Semantic
    activity: Semantic
    state: ContactState
    actor_a: Semantic
    region_a: Semantic
    actor_b: Semantic
    region_b: Semantic
    screen_position: Semantic
    depth_plane: Semantic
    visibility: Visibility
    occluders: list[RegionRef] = Field(max_length=8)

    @model_validator(mode="after")
    def visibility_matches_occluders(self) -> ContactGeometry:
        if self.visibility == Visibility.OCCLUDED and not self.occluders:
            raise ValueError("an occluded contact requires at least one occluder")
        if self.visibility == Visibility.VISIBLE and self.occluders:
            raise ValueError("a visible contact cannot declare occluders")
        return self


class SupportGeometry(StrictModel):
    support_id: Semantic
    supported_actor: Semantic
    supported_region: Semantic
    supporter_actor: Semantic | None
    supporter_region: Semantic
    environmental_surface: Semantic | None
    screen_position: Semantic
    depth_plane: Semantic

    @model_validator(mode="after")
    def has_one_support_source(self) -> SupportGeometry:
        sources = (
            self.supporter_actor is not None,
            self.environmental_surface is not None,
        )
        if sum(sources) != 1:
            raise ValueError(
                "a support must use exactly one actor or environmental surface"
            )
        if (
            self.environmental_surface is not None
            and self.supported_region == self.supporter_region
        ):
            raise ValueError(
                "an environmental support must distinguish body and surface regions"
            )
        return self


class GeometrySnapshot(StrictModel):
    frame_id: Annotated[str, StringConstraints(pattern=r"^F\d{2}$")]
    camera: CameraGeometry
    actors: list[ActorGeometry] = Field(min_length=2, max_length=2)
    contacts: list[ContactGeometry] = Field(min_length=1, max_length=1)
    supports: list[SupportGeometry] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def geometry_is_coherent(self) -> GeometrySnapshot:
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("actor IDs must be unique")
        if {actor.sex for actor in self.actors} != {Sex.FEMALE, Sex.MALE}:
            raise ValueError("this proof requires exactly one woman and one man")

        actor_id_set = set(actor_ids)
        contact_ids = [contact.contact_id for contact in self.contacts]
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("contact IDs must be unique")
        contact_id_set = set(contact_ids)
        support_ids = [support.support_id for support in self.supports]
        if len(support_ids) != len(set(support_ids)):
            raise ValueError("support IDs must be unique")
        support_id_set = set(support_ids)
        if support_id_set != ALLOWED_SUPPORT_IDS:
            raise ValueError("the plan must contain all four required supports")

        visible_contacts = set(self.camera.visible_contacts)
        occluded_contacts = set(self.camera.occluded_contacts)
        if visible_contacts & occluded_contacts:
            raise ValueError("one contact cannot be both visible and occluded")
        if visible_contacts | occluded_contacts != contact_id_set:
            raise ValueError("the camera must classify every contact exactly once")
        if visible_contacts or occluded_contacts != {"primary_contact"}:
            raise ValueError("primary_contact must be camera-occluded")

        visible_regions = set(self.camera.visible_regions)
        occluded_regions = set(self.camera.occluded_regions)
        if self.camera.viewpoint != "side_rear_three_quarter":
            raise ValueError("camera viewpoint changed")
        if self.camera.shot_scale != "medium_wide":
            raise ValueError("camera shot scale changed")
        unknown_regions = sorted(
            (visible_regions | occluded_regions) - ALLOWED_REGION_REFS
        )
        if unknown_regions:
            raise ValueError(f"camera uses unknown regions: {unknown_regions}")
        if occluded_regions != {"f1.mouth", "m1.pubic_region"}:
            raise ValueError("camera occluded regions changed")
        if not {"f1.head", "m1.near_thigh"}.issubset(visible_regions):
            raise ValueError("contact occluders must remain camera-visible")
        if visible_regions & occluded_regions:
            raise ValueError("one actor region cannot be both visible and occluded")
        self._validate_region_refs(visible_regions | occluded_regions, actor_id_set)

        occupied_contact_regions: set[str] = set()
        for contact in self.contacts:
            if (
                contact.contact_id != "primary_contact"
                or contact.activity != "fellatio"
                or contact.state != ContactState.INSERTED
                or contact.visibility != Visibility.OCCLUDED
                or contact.occluders != ["f1.head", "m1.near_thigh"]
                or contact.actor_a != "f1"
                or contact.region_a != "mouth"
                or contact.actor_b != "m1"
                or contact.region_b != "pubic_region"
                or contact.screen_position != "center"
                or contact.depth_plane != "midground"
            ):
                raise ValueError("primary contact changed required plan values")
            if (
                contact.actor_a not in actor_id_set
                or contact.actor_b not in actor_id_set
                or contact.actor_a == contact.actor_b
            ):
                raise ValueError(f"{contact.contact_id} has invalid participants")
            endpoints = {
                f"{contact.actor_a}.{contact.region_a}",
                f"{contact.actor_b}.{contact.region_b}",
            }
            if occupied_contact_regions & endpoints:
                raise ValueError("one body region cannot enter two contact states")
            occupied_contact_regions.update(endpoints)
            self._validate_region_refs(set(contact.occluders), actor_id_set)
            classified_as_occluded = contact.contact_id in occluded_contacts
            if classified_as_occluded != (contact.visibility == Visibility.OCCLUDED):
                raise ValueError(
                    f"{contact.contact_id} visibility conflicts with the camera"
                )

        for support in self.supports:
            if support.support_id not in ALLOWED_SUPPORT_IDS:
                raise ValueError(f"unknown support ID: {support.support_id}")
            if (
                support.supported_region not in ALLOWED_SUPPORT_REGIONS
                or support.supporter_region not in ALLOWED_SUPPORT_REGIONS
            ):
                raise ValueError(f"{support.support_id} uses an unknown support region")
            expected_actor, expected_region = {
                "f1_knee_support": ("f1", "both_knees"),
                "f1_hand_support": ("f1", "both_hands"),
                "m1_knee_support": ("m1", "both_knees"),
                "m1_hand_support": ("m1", "both_hands"),
            }[support.support_id]
            if (
                support.supported_actor != expected_actor
                or support.supported_region != expected_region
                or support.supporter_actor is not None
                or support.supporter_region != "mattress"
                or support.environmental_surface != "bed"
            ):
                raise ValueError(f"{support.support_id} endpoints changed")
            if support.supported_actor not in actor_id_set:
                raise ValueError(f"{support.support_id} has an unknown supported actor")
            if (
                support.supporter_actor is not None
                and support.supporter_actor not in actor_id_set
            ):
                raise ValueError(f"{support.support_id} has an unknown supporter")

        for actor in self.actors:
            expected_sex, expected_description, expected_pose = {
                "f1": (
                    Sex.FEMALE,
                    "F1, woman 1, a 29-year-old Chinese woman",
                    "kneeling_forward",
                ),
                "m1": (
                    Sex.MALE,
                    "M1, man 1, a 32-year-old Chinese man",
                    "kneeling_upright",
                ),
            }[actor.actor_id]
            if (
                actor.sex != expected_sex
                or actor.description != expected_description
                or actor.pose != expected_pose
            ):
                raise ValueError(f"{actor.actor_id} identity or pose changed")
            assigned_parts = {
                assignment.body_part for assignment in actor.limb_assignments
            }
            if f"{actor.actor_id}.arms" in visible_regions and not {
                "left_hand",
                "right_hand",
            }.issubset(assigned_parts):
                raise ValueError(f"{actor.actor_id} has visible unassigned hands")
            if f"{actor.actor_id}.legs" in visible_regions and not {
                "left_knee",
                "right_knee",
            }.issubset(assigned_parts):
                raise ValueError(f"{actor.actor_id} has visible unassigned legs")
            for assignment in actor.limb_assignments:
                if assignment.purpose == AssignmentPurpose.POSE:
                    if assignment.target_id is not None:
                        raise ValueError("pose assignments cannot have a target")
                elif assignment.purpose == AssignmentPurpose.CONTACT:
                    if assignment.target_id not in contact_id_set:
                        raise ValueError("contact assignment target does not exist")
                else:
                    if assignment.target_id not in support_id_set:
                        raise ValueError("support assignment target does not exist")
                    support_kind = (
                        "knee" if assignment.body_part.endswith("knee") else "hand"
                    )
                    expected_target = f"{actor.actor_id}_{support_kind}_support"
                    if assignment.target_id != expected_target:
                        raise ValueError(
                            f"{actor.actor_id}.{assignment.body_part} uses "
                            "the wrong support"
                        )
        return self

    @staticmethod
    def _validate_region_refs(
        references: set[str],
        actor_ids: set[str],
    ) -> None:
        unknown = sorted(
            reference
            for reference in references
            if reference.split(".", 1)[0] not in actor_ids
        )
        if unknown:
            raise ValueError(f"region references use unknown actors: {unknown}")


class SpatialPlan(GeometrySnapshot):
    setting: str = Field(min_length=1, max_length=600)
    lighting: str = Field(min_length=1, max_length=400)
    style: str = Field(min_length=1, max_length=300)

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(payload).hexdigest()


class NarrativeDraft(StrictModel):
    frame_id: Annotated[str, StringConstraints(pattern=r"^F\d{2}$")]
    plan_fingerprint: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    prose: str = Field(min_length=1, max_length=8000)


class CheckName(StrEnum):
    CAST = "cast"
    CAMERA = "camera"
    CONTACT = "contact"
    VISIBILITY = "visibility"
    LIMB_ASSIGNMENTS = "limb_assignments"
    SUPPORTS = "supports"


class ConformanceCheck(StrictModel):
    check: CheckName
    passed: bool
    evidence: str = Field(min_length=1, max_length=300)


class ConformanceReport(StrictModel):
    checks: list[ConformanceCheck] = Field(min_length=6, max_length=6)
    contradictions: list[str] = Field(max_length=6)

    @model_validator(mode="after")
    def contains_each_check_once(self) -> ConformanceReport:
        names = [check.check for check in self.checks]
        if len(names) != len(set(names)) or set(names) != set(CheckName):
            raise ValueError("the audit must contain every check exactly once")
        if all(check.passed for check in self.checks) and self.contradictions:
            raise ValueError("a passing audit cannot report contradictions")
        if not all(check.passed for check in self.checks) and not self.contradictions:
            raise ValueError("a failing audit must report its contradictions")
        return self

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


PROSE_SYSTEM = """
Render the validated spatial plan as one concise standalone English image
prompt using ASCII characters only. The plan is immutable: do not add people,
cameras, contacts, support points, body-part roles, visible regions, or
occluded regions. Include each actor's description verbatim. State the word
"camera" exactly once near the beginning, with its planned viewpoint and shot
scale. Describe every actor pose, every non-contact limb assignment, and every
support record in natural language. Describe only regions classified visible.
Do not list occluded regions or name contact-assigned body parts. For an
occluded contact, name its activity once, state its physical state verbatim,
state body-scale alignment and the visible occluders, and do not name or
describe either local contact endpoint. Preserve each complete actor
description, including the F/M code and woman/man ordinal. Add no crop
endpoints. Return only schema data.
""".strip()

AUDIT_SYSTEM = """
Compare the supplied validated spatial plan with the supplied image prompt.
Use the supplied audit_contract as the exact scoring definition.
Audit exactly six dimensions once each: cast, camera, contact, visibility,
limb_assignments, and supports. Mark a check passed only when the prose
preserves the plan without adding, removing, moving, or reclassifying facts.
Internal enum labels need not appear literally when the same physical state is
expressed. A visible region may correctly act as an occluder; do not confuse an
occluder with an occluded region. Hidden local contact endpoints should be
omitted from prose. Contact limb assignments may remain implicit when the
activity and body alignment preserve them, but every non-contact limb role and
support must be expressed.
Use one short evidence sentence per check. Report every contradiction. Do not
rewrite the prompt or plan. Return only schema data.
""".strip()


def _messages(system: str, payload: object) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        ),
    ]


async def _generate_with_repair(
    model: OpenAIStoryModel,
    *,
    system: str,
    payload: object,
    response_model: type[BaseModel],
    max_output_tokens: int,
) -> tuple[ModelResponse, list[list[str]]]:
    messages = _messages(system, payload)
    rejected_issues: list[list[str]] = []
    for attempt in range(2):
        try:
            response = await model.generate(
                stage=StoryStage.FRAMES,
                messages=messages,
                response_model=response_model,
                max_output_tokens=max_output_tokens,
            )
        except StoryStructuredOutputError as exc:
            rejected_issues.append(list(exc.validation_issues))
            if attempt == 1:
                raise
            messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        "The validator rejected that data. Generate a fresh complete "
                        "schema that corrects only the reported structural conflicts. "
                        "Do not repeat fields or add detail. Issues: "
                        + "; ".join(exc.validation_issues)
                    ),
                )
            )
        else:
            return response, rejected_issues
    raise AssertionError("unreachable")


def _prose_issues(plan: SpatialPlan, draft: NarrativeDraft) -> list[str]:
    issues: list[str] = []
    if draft.frame_id != plan.frame_id:
        issues.append("frame_id changed")
    if draft.plan_fingerprint != plan.fingerprint():
        issues.append("plan fingerprint changed")
    if "\n" in draft.prose or "\r" in draft.prose:
        issues.append("prose is not one paragraph")
    if not draft.prose.isascii():
        issues.append("prose contains non-ASCII characters")
    if len(re.findall(r"\bcamera\b", draft.prose, flags=re.IGNORECASE)) != 1:
        issues.append("camera is not stated exactly once")
    if re.search(
        r"\b(?:frame|framing|crop|cropping)\b.{0,100}\bfrom\b.{0,100}\bto\b",
        draft.prose,
        flags=re.IGNORECASE,
    ):
        issues.append("prose reintroduced explicit crop endpoints")
    for contact in plan.contacts:
        activity = contact.activity.replace("_", " ")
        if len(re.findall(rf"\b{re.escape(activity)}\b", draft.prose, re.I)) != 1:
            issues.append(f"{contact.contact_id} activity is not stated exactly once")
        if contact.visibility == Visibility.OCCLUDED and re.search(
            r"\b(?:mouth|lips?|tongue|penis|shaft|glans|pubic|genitals?)\b",
            draft.prose,
            flags=re.IGNORECASE,
        ):
            issues.append(
                f"{contact.contact_id} exposes forbidden local anatomy while occluded"
            )
    for actor in plan.actors:
        if actor.description not in draft.prose:
            issues.append(f"{actor.actor_id} description changed or is incomplete")
    return issues


def _audit_contract(plan: SpatialPlan) -> dict[str, object]:
    contact = plan.contacts[0]
    return {
        "actor_descriptions_required_verbatim": [
            actor.description for actor in plan.actors
        ],
        "camera": {
            "viewpoint": plan.camera.viewpoint,
            "shot_scale": plan.camera.shot_scale,
            "state_once": True,
        },
        "contact": {
            "activity": contact.activity,
            "physical_state": contact.state,
            "visibility": contact.visibility,
            "activity_stated_once": True,
            "hidden_endpoints_must_be_omitted": [
                f"{contact.actor_a}.{contact.region_a}",
                f"{contact.actor_b}.{contact.region_b}",
            ],
            "visible_occluders_must_be_named": contact.occluders,
        },
        "non_contact_limb_assignments": [
            {
                "actor_id": actor.actor_id,
                **assignment.model_dump(mode="json"),
            }
            for actor in plan.actors
            for assignment in actor.limb_assignments
            if assignment.purpose != AssignmentPurpose.CONTACT
        ],
        "supports": [support.model_dump(mode="json") for support in plan.supports],
    }


def _invalid_plan_rejection(plan: SpatialPlan) -> str:
    payload = plan.model_dump(mode="json")
    contact_id = payload["contacts"][0]["contact_id"]
    payload["camera"]["visible_contacts"] = [contact_id]
    payload["camera"]["occluded_contacts"] = []
    try:
        SpatialPlan.model_validate(payload)
    except ValidationError as exc:
        return str(exc)
    raise AssertionError("the contradictory visibility fixture was accepted")


def _tampered_prose_rejection(
    plan: SpatialPlan,
    draft: NarrativeDraft,
) -> list[str]:
    tampered = draft.model_copy(
        update={
            "prose": (
                draft.prose
                + " A second camera clearly shows his penis inside her mouth."
            )
        }
    )
    issues = _prose_issues(plan, tampered)
    required = {
        "camera is not stated exactly once",
        "primary_contact exposes forbidden local anatomy while occluded",
    }
    if not required.issubset(issues):
        raise AssertionError("the contradictory prose fixture was accepted")
    return issues


def _compile_plan(scenario: dict[str, object]) -> SpatialPlan:
    cast = {actor["actor_id"]: actor for actor in scenario["cast"]}
    actor_specs = (
        ("f1", Sex.FEMALE, "center_left", "kneeling_forward", "head"),
        ("m1", Sex.MALE, "center_right", "kneeling_upright", "pubic_region"),
    )
    actors = []
    supports = []
    for actor_id, sex, position, pose, contact_region in actor_specs:
        support_ids = (
            f"{actor_id}_knee_support",
            f"{actor_id}_hand_support",
        )
        actors.append(
            ActorGeometry(
                actor_id=actor_id,
                sex=sex,
                description=cast[actor_id]["description"],
                screen_position=position,
                depth_plane="midground",
                pose=pose,
                limb_assignments=[
                    LimbAssignment(
                        body_part="left_knee",
                        purpose=AssignmentPurpose.SUPPORT,
                        target_id=support_ids[0],
                    ),
                    LimbAssignment(
                        body_part="right_knee",
                        purpose=AssignmentPurpose.SUPPORT,
                        target_id=support_ids[0],
                    ),
                    LimbAssignment(
                        body_part="left_hand",
                        purpose=AssignmentPurpose.SUPPORT,
                        target_id=support_ids[1],
                    ),
                    LimbAssignment(
                        body_part="right_hand",
                        purpose=AssignmentPurpose.SUPPORT,
                        target_id=support_ids[1],
                    ),
                    LimbAssignment(
                        body_part=contact_region,
                        purpose=AssignmentPurpose.CONTACT,
                        target_id="primary_contact",
                    ),
                ],
            )
        )
        for support_id, region in zip(
            support_ids,
            ("both_knees", "both_hands"),
            strict=True,
        ):
            supports.append(
                SupportGeometry(
                    support_id=support_id,
                    supported_actor=actor_id,
                    supported_region=region,
                    supporter_actor=None,
                    supporter_region="mattress",
                    environmental_surface="bed",
                    screen_position=position,
                    depth_plane="midground",
                )
            )
    required = scenario["required_plan_values"]
    return SpatialPlan(
        frame_id=scenario["frame_id"],
        camera=CameraGeometry(
            viewpoint="side_rear_three_quarter",
            shot_scale="medium_wide",
            visible_regions=[
                "f1.head",
                "f1.torso",
                "f1.arms",
                "f1.legs",
                "m1.near_thigh",
                "m1.torso",
                "m1.arms",
                "m1.legs",
            ],
            occluded_regions=required["camera_occluded_regions"],
            visible_contacts=required["camera_visible_contacts"],
            occluded_contacts=required["camera_occluded_contacts"],
        ),
        actors=actors,
        contacts=[
            ContactGeometry(
                contact_id="primary_contact",
                activity="fellatio",
                state=required["primary_contact_state"],
                actor_a="f1",
                region_a="mouth",
                actor_b="m1",
                region_b="pubic_region",
                screen_position="center",
                depth_plane="midground",
                visibility=required["primary_contact_visibility"],
                occluders=required["primary_contact_occluders"],
            )
        ],
        supports=supports,
        setting=scenario["setting"],
        lighting="soft morning window light",
        style="realistic",
    )


async def run(scenario_path: Path, output_directory: Path) -> dict[str, object]:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    settings = load_story_provider_settings()
    plan = _compile_plan(scenario)
    plan_rejections: list[list[str]] = []
    async with OpenAIStoryModel(settings) as model:
        fingerprint = plan.fingerprint()
        prose_payload: dict[str, object] = {
            "spatial_plan": plan.model_dump(mode="json"),
            "required_plan_fingerprint": fingerprint,
        }
        prose_rejections: list[list[str]] = []
        prose_issues: list[str] = []
        prose_attempts = 0
        for _ in range(3):
            prose_attempts += 1
            draft_response, rejections = await _generate_with_repair(
                model,
                system=PROSE_SYSTEM,
                payload=prose_payload,
                response_model=NarrativeDraft,
                max_output_tokens=min(6000, settings.output_token_limit),
            )
            prose_rejections.extend(rejections)
            draft = NarrativeDraft.model_validate(draft_response.value)
            prose_issues = _prose_issues(plan, draft)
            if not prose_issues:
                break
            prose_payload = {
                "spatial_plan": plan.model_dump(mode="json"),
                "required_plan_fingerprint": fingerprint,
                "previous_draft": draft.model_dump(mode="json"),
                "validation_issues": prose_issues,
                "repair_requirement": (
                    "Return a corrected complete draft. Do not name any "
                    "contact-assigned local body part for an occluded contact."
                ),
            }
        output_directory.mkdir(parents=True, exist_ok=True)
        (output_directory / "plan.json").write_text(
            plan.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        (output_directory / "prompt.txt").write_text(
            draft.prose + "\n",
            encoding="utf-8",
        )
        audit_response, audit_rejections = await _generate_with_repair(
            model,
            system=AUDIT_SYSTEM,
            payload={
                "spatial_plan": plan.model_dump(mode="json"),
                "audit_contract": _audit_contract(plan),
                "prose": draft.prose,
            },
            response_model=ConformanceReport,
            max_output_tokens=min(4000, settings.output_token_limit),
        )
        audit = ConformanceReport.model_validate(audit_response.value)

    rejection = _invalid_plan_rejection(plan)
    tampered_prose_issues = _tampered_prose_rejection(plan, draft)
    report = {
        "model": settings.model,
        "plan_valid": True,
        "invalid_visibility_fixture_rejected": True,
        "tampered_prose_rejected": True,
        "tampered_prose_issues": tampered_prose_issues,
        "prose_valid": not prose_issues,
        "prose_issues": prose_issues,
        "prose_attempts": prose_attempts,
        "semantic_audit_passed": audit.passed,
        "semantic_audit": audit.model_dump(mode="json"),
        "passed": not prose_issues and audit.passed,
        "structured_rejections": {
            "plan": plan_rejections,
            "prose": prose_rejections,
            "audit": audit_rejections,
        },
        "usage": {
            "plan": {
                "mode": "deterministic",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            "prose": draft_response.usage.model_dump(mode="json"),
            "audit": audit_response.usage.model_dump(mode="json"),
        },
    }
    (output_directory / "semantic-audit.json").write_text(
        audit.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (output_directory / "invalid-plan-error.txt").write_text(
        rejection + "\n",
        encoding="utf-8",
    )
    (output_directory / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an isolated spatial-plan consistency proof."
    )
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = asyncio.run(run(args.scenario.resolve(), args.output.resolve()))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
