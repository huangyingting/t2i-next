from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from run import _generate_with_repair

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.provider import OpenAIStoryModel

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "diversity-scenarios.json"
OUTPUT = ROOT / "diversity-output"
Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]
CaseId = Annotated[str, StringConstraints(pattern=r"^C\d{2}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiversityCase(StrictModel):
    case_id: CaseId
    activity: Identifier
    contact_state: Identifier
    visibility: Identifier
    viewpoint: Identifier
    shot_scale: Identifier
    central_pose: Identifier
    partner_pose: Identifier
    support_topology: Identifier
    central_screen_position: Identifier
    partner_screen_position: Identifier
    depth_plane: Identifier
    occluders: list[Identifier] = Field(max_length=4)
    forbidden_local_terms: list[Identifier] = Field(max_length=10)

    @model_validator(mode="after")
    def contact_visibility_is_coherent(self) -> DiversityCase:
        if self.contact_state not in {"external_contact", "inserted"}:
            raise ValueError("unsupported contact state")
        if self.visibility not in {"visible", "occluded"}:
            raise ValueError("unsupported visibility")
        if self.visibility == "occluded" and not self.occluders:
            raise ValueError("occluded contact requires occluders")
        if self.visibility == "visible" and self.occluders:
            raise ValueError("visible contact cannot have occluders")
        return self

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def signature(self) -> tuple[str, ...]:
        return (
            self.activity,
            self.contact_state,
            self.visibility,
            self.viewpoint,
            self.shot_scale,
            self.central_pose,
            self.partner_pose,
            self.support_topology,
            self.central_screen_position,
            self.partner_screen_position,
            self.depth_plane,
            *self.occluders,
        )


class DiversityMatrix(StrictModel):
    actors: list[str] = Field(min_length=2, max_length=2)
    cases: list[DiversityCase] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def matrix_has_material_diversity(self) -> DiversityMatrix:
        ids = [case.case_id for case in self.cases]
        if ids != [f"C{index:02d}" for index in range(1, 9)]:
            raise ValueError("case IDs must be C01 through C08 in order")
        signatures = [case.signature() for case in self.cases]
        if len(set(signatures)) != len(signatures):
            raise ValueError("every geometry signature must be unique")
        thresholds = {
            "activity": 8,
            "contact_state": 2,
            "visibility": 2,
            "viewpoint": 8,
            "shot_scale": 4,
            "central_pose": 8,
            "partner_pose": 7,
            "support_topology": 8,
        }
        for field, minimum in thresholds.items():
            count = len({getattr(case, field) for case in self.cases})
            if count < minimum:
                raise ValueError(f"{field} diversity is {count}, expected {minimum}")
        return self


class DiversityDraft(StrictModel):
    case_id: CaseId
    plan_fingerprint: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    prose: str = Field(min_length=1, max_length=4000)


class DiversityDraftBatch(StrictModel):
    drafts: list[DiversityDraft] = Field(min_length=8, max_length=8)


SYSTEM = """
Convert each supplied spatial case into one concise standalone English image
prompt. Return exactly C01 through C08 in order. Copy each required fingerprint.
Use exactly the two supplied adult descriptions in every prompt. Use ASCII only
and one paragraph per prompt. State the word camera exactly once. Express the
activity, camera viewpoint, shot scale, both poses, support topology, screen
positions, depth plane, contact state, and visibility using the exact supplied
snake_case phrase with underscores changed to spaces. For visible contact,
state that the contact is visible. For occluded contact, state that the contact
is occluded, name every supplied occluder, and never use any forbidden local
term. Add no people, contact, camera, support, or crop endpoint. Return only
schema data.
""".strip()


def phrase(value: str) -> str:
    return value.replace("_", " ")


def audit_draft(
    actors: list[str],
    case: DiversityCase,
    draft: DiversityDraft,
) -> list[str]:
    issues: list[str] = []
    if draft.case_id != case.case_id:
        issues.append("case_id changed")
    if draft.plan_fingerprint != case.fingerprint():
        issues.append("plan fingerprint changed")
    if not draft.prose.isascii():
        issues.append("prose contains non-ASCII characters")
    if "\n" in draft.prose or "\r" in draft.prose:
        issues.append("prose is not one paragraph")
    if len(re.findall(r"\bcamera\b", draft.prose, re.I)) != 1:
        issues.append("camera is not stated exactly once")
    for actor in actors:
        if actor not in draft.prose:
            issues.append(f"actor description changed: {actor}")
    required_values = (
        case.activity,
        case.viewpoint,
        case.shot_scale,
        case.central_pose,
        case.partner_pose,
        case.central_screen_position,
        case.partner_screen_position,
        case.depth_plane,
        case.contact_state,
        case.visibility,
        *case.occluders,
    )
    lowered = draft.prose.lower()
    for value in required_values:
        if phrase(value) not in lowered:
            issues.append(f"missing planned phrase: {value}")
    pose_terms = set(case.central_pose.split("_")) | set(
        case.partner_pose.split("_")
    )
    ignored_support_terms = {"woman", "man"} | pose_terms
    support_terms = set(case.support_topology.split("_")) - ignored_support_terms
    for support_term in support_terms:
        if re.search(rf"\b{re.escape(support_term)}\b", lowered) is None:
            issues.append(
                f"support topology omits semantic term: {support_term}"
            )
    expected_positions = (
        (
            actors[0].split(",", 1)[0],
            phrase(case.central_screen_position),
        ),
        (
            actors[1].split(",", 1)[0],
            phrase(case.partner_screen_position),
        ),
    )
    for actor_name, expected_position in expected_positions:
        if re.search(
            rf"{re.escape(actor_name)}[^.]{{0,180}}"
            rf"\b(?:at|in|on)(?: the)? {re.escape(expected_position)}\b",
            draft.prose,
            re.I,
        ) is None:
            issues.append(
                f"screen position changed: {actor_name} -> {expected_position}"
            )
    for term in case.forbidden_local_terms:
        if re.search(rf"\b{re.escape(term)}s?\b", draft.prose, re.I):
            issues.append(f"occluded contact exposes forbidden term: {term}")
    if re.search(
        r"\b(?:frame|framing|crop|cropping)\b.{0,100}\bfrom\b.{0,100}\bto\b",
        draft.prose,
        re.I,
    ):
        issues.append("prose adds explicit crop endpoints")
    return issues


def diversity_metrics(matrix: DiversityMatrix) -> dict[str, object]:
    fields = (
        "activity",
        "contact_state",
        "visibility",
        "viewpoint",
        "shot_scale",
        "central_pose",
        "partner_pose",
        "support_topology",
    )
    return {
        "cases": len(matrix.cases),
        "unique_geometry_signatures": len(
            {case.signature() for case in matrix.cases}
        ),
        "axis_cardinality": {
            field: len({getattr(case, field) for case in matrix.cases})
            for field in fields
        },
    }


def render_case(actors: list[str], case: DiversityCase) -> DiversityDraft:
    occlusion = (
        " by " + " and ".join(phrase(item) for item in case.occluders)
        if case.occluders
        else ""
    )
    prose = (
        f"The camera uses a {phrase(case.viewpoint)} viewpoint and a "
        f"{phrase(case.shot_scale)} shot. "
        f"{actors[0]} is at {phrase(case.central_screen_position)} in the "
        f"{phrase(case.depth_plane)} in a {phrase(case.central_pose)} pose. "
        f"{actors[1]} is at {phrase(case.partner_screen_position)} in the "
        f"{phrase(case.depth_plane)} in a {phrase(case.partner_pose)} pose. "
        f"The support topology is {phrase(case.support_topology)}. "
        f"The {phrase(case.contact_state)} {phrase(case.activity)} contact is "
        f"{phrase(case.visibility)}{occlusion}."
    )
    return DiversityDraft(
        case_id=case.case_id,
        plan_fingerprint=case.fingerprint(),
        prose=prose,
    )


async def run() -> dict[str, object]:
    matrix = DiversityMatrix.model_validate_json(INPUT.read_text(encoding="utf-8"))
    payload = {
        "actors": matrix.actors,
        "cases": [
            {
                **case.model_dump(mode="json"),
                "required_fingerprint": case.fingerprint(),
            }
            for case in matrix.cases
        ],
    }
    settings = load_story_provider_settings()
    responses = []
    all_rejections: list[list[str]] = []
    semantic_attempts = 0
    llm_issues: dict[str, list[str]] = {}
    async with OpenAIStoryModel(settings) as model:
        for _ in range(2):
            semantic_attempts += 1
            response, rejections = await _generate_with_repair(
                model,
                system=SYSTEM,
                payload=payload,
                response_model=DiversityDraftBatch,
                max_output_tokens=min(12000, settings.output_token_limit),
            )
            responses.append(response)
            all_rejections.extend(rejections)
            batch = DiversityDraftBatch.model_validate(response.value)
            llm_issues = {}
            for case, draft in zip(matrix.cases, batch.drafts, strict=True):
                draft_issues = audit_draft(matrix.actors, case, draft)
                if draft_issues:
                    llm_issues[case.case_id] = draft_issues
            if not llm_issues:
                break
            payload = {
                **payload,
                "previous_drafts": batch.model_dump(mode="json"),
                "semantic_validation_issues": llm_issues,
                "repair_requirement": (
                    "Return the complete eight-draft batch with every listed "
                    "semantic issue corrected and all other plan facts unchanged."
                ),
            }
    llm_batch = batch
    compiled_batch = DiversityDraftBatch(
        drafts=[render_case(matrix.actors, case) for case in matrix.cases]
    )
    compiled_issues: dict[str, list[str]] = {}
    for case, draft in zip(matrix.cases, compiled_batch.drafts, strict=True):
        draft_issues = audit_draft(matrix.actors, case, draft)
        if draft_issues:
            compiled_issues[case.case_id] = draft_issues
    metrics = diversity_metrics(matrix)
    report = {
        "model": settings.model,
        **metrics,
        "llm_prompts_valid": not llm_issues,
        "llm_prompt_issues": llm_issues,
        "compiled_prompts_valid": not compiled_issues,
        "compiled_prompt_issues": compiled_issues,
        "semantic_attempts": semantic_attempts,
        "structured_rejections": all_rejections,
        "usage_by_attempt": [
            response.usage.model_dump(mode="json") for response in responses
        ],
        "passed": (
            metrics["unique_geometry_signatures"] == len(matrix.cases)
            and not compiled_issues
        ),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "prompts.txt").write_text(
        "\n".join(draft.prose for draft in compiled_batch.drafts) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "drafts.json").write_text(
        compiled_batch.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "llm-prompts.txt").write_text(
        "\n".join(draft.prose for draft in llm_batch.drafts) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "llm-drafts.json").write_text(
        llm_batch.model_dump_json(indent=2) + "\n",
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
