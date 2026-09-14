from __future__ import annotations

import json
from copy import deepcopy

from catalog_generator import ActivityTemplate, PoseCatalog, PoseEntry, has_tag
from catalog_scene_demo import (
    CATALOGS,
    OUTPUT,
    SPECS,
    DemoSpec,
    EvaluationBatch,
    body_ledger,
    compile_geometry,
    evaluation_contract_issues,
    prompt_issues,
    select_plan,
)
from pydantic import ValidationError

CAST_KEYS = (
    "one_woman",
    "one_woman_one_man",
    "one_woman_two_men",
    "two_women",
    "three_women",
)
EXPECTED_CAST_IDS = {
    "one_woman": ["f1"],
    "one_woman_one_man": ["f1", "m1"],
    "one_woman_two_men": ["f1", "m1", "m2"],
    "two_women": ["f1", "f2"],
    "three_women": ["f1", "f2", "f3"],
}
LEGACY_ACTOR_IDS = {"central", "partner_a", "partner_b"}
LEGACY_NAMES = {"Li Na", "Zhang Wei", "Chen Hao", "Chen Mei", "Zhao Yue"}


def rejected_activity(payload: dict[str, object], expected: str) -> None:
    try:
        ActivityTemplate.model_validate(payload)
    except ValidationError as exc:
        if expected not in str(exc):
            raise AssertionError(
                f"mutation failed for an unexpected reason: {exc}"
            ) from exc
    else:
        raise AssertionError(f"mutation was accepted: {expected}")


def selected_plan(
    scene_id: str,
) -> tuple[DemoSpec, PoseEntry, ActivityTemplate, str]:
    spec = next(spec for spec in SPECS if spec.scene_id == scene_id)
    catalog = PoseCatalog.model_validate_json(
        (CATALOGS / f"{spec.cast_key}.json").read_text(encoding="utf-8")
    )
    entry, activity = select_plan(catalog, spec)
    prompt = compile_geometry(spec, entry, activity)
    issues = prompt_issues(spec, entry, activity, prompt)
    if issues:
        raise AssertionError(f"{scene_id} failed exact prompt checks: {issues}")
    return spec, entry, activity, prompt


def rejected_prompt(
    spec: DemoSpec,
    entry: PoseEntry,
    activity: ActivityTemplate,
    prompt: str,
    expected: str,
) -> None:
    issues = prompt_issues(spec, entry, activity, prompt)
    if not any(expected in issue for issue in issues):
        raise AssertionError(
            f"prompt mutation was not rejected as {expected}: {issues}"
        )


def main() -> None:
    compiled_combinations = 0
    strap_on_activities = 0
    rejected_mutations = 0
    for cast_key in CAST_KEYS:
        catalog = PoseCatalog.model_validate_json(
            (CATALOGS / f"{cast_key}.json").read_text(encoding="utf-8")
        )
        if catalog.schema_version != "2.0":
            raise AssertionError(f"{cast_key} did not use schema 2.0")
        if len(catalog.entries) != 256 or len(catalog.activities) != 32:
            raise AssertionError(f"{cast_key} coverage changed")
        cast_ids = [slot.slot_id for slot in catalog.cast_slots]
        if cast_ids != EXPECTED_CAST_IDS[cast_key]:
            raise AssertionError(f"{cast_key} actor codes changed: {cast_ids}")
        activity_map = {
            activity.activity_id: activity for activity in catalog.activities
        }
        for activity in catalog.activities:
            endpoint_entities = {
                endpoint.entity_id
                for edge in activity.contact_edges
                for endpoint in (edge.source, edge.target)
            }
            restraint_entities = set(activity.restraint.controller_slots) | set(
                activity.restraint.restrained_slots
            )
            if LEGACY_ACTOR_IDS.intersection(endpoint_entities | restraint_entities):
                raise AssertionError("logical actor role leaked into catalog entities")
            if any(
                endpoint.region == "strap_on"
                for edge in activity.contact_edges
                for endpoint in (edge.source, edge.target)
            ):
                raise AssertionError("strap-on survived as a body region")
            if has_tag(activity.activity_id, "strap_on"):
                strap_on_activities += 1
                prop = activity.wearable_props[0]
                edge = next(
                    edge
                    for edge in activity.contact_edges
                    if edge.source.entity_id == prop.prop_id
                )
                if (
                    prop.owner_slot == edge.target.entity_id
                    or edge.source.region != "shaft"
                ):
                    raise AssertionError("wearable contact chain is disconnected")
        for entry in catalog.entries:
            for activity_id in entry.compatible_activity_ids:
                activity = activity_map[activity_id]
                spec = DemoSpec(
                    "D99",
                    cast_key,
                    entry.central_pose.family,
                    entry.central_pose.variant,
                    activity_id,
                    entry.central_pose.compatible_camera_views[0],
                    "medium",
                    "",
                )
                prompt = compile_geometry(spec, entry, activity)
                if any(name in prompt for name in LEGACY_NAMES):
                    raise AssertionError("legacy personal name leaked into prompt")
                issues = prompt_issues(spec, entry, activity, prompt)
                if issues:
                    raise AssertionError(f"{entry.pose_id}/{activity_id}: {issues}")
                compiled_combinations += 1

    d01_spec, d01_entry, d01_activity, d01_prompt = selected_plan("D01")
    d01_required = (
        "complete body ledger contains exactly 1 continuous body",
        "one continuous woman body identified as F1 (woman 1)",
        "Every visible face and limb belongs to exactly one coded body",
        "F1's right hand grips the vibrator body",
        "left hand remains visibly on her inner thigh",
        "lies transversely across F1's external clitoral surface",
        "entirely outside the vaginal opening",
    )
    if any(value not in d01_prompt for value in d01_required):
        raise AssertionError("D01 lost exact cast or handheld topology")

    d02_spec, d02_entry, d02_activity, d02_prompt = selected_plan("D02")
    if (
        "manual clitoral self-stimulation while a padded spreader bar "
        "holds the ankles apart"
    ) not in d02_prompt:
        raise AssertionError("D02 conflates restraint equipment with stimulation")
    d02_restraint_required = (
        "spreader bar spans directly between F1's ankles",
        "left end is visibly secured to her left ankle",
        "right end to her right ankle by padded cuffs",
        "Both cuff release tabs remain visible",
    )
    if any(value not in d02_prompt for value in d02_restraint_required):
        raise AssertionError("D02 has a disconnected restraint chain")

    d03_spec, d03_entry, d03_activity, d03_prompt = selected_plan("D03")
    d03_required = (
        "two continuous bilateral cradles",
        "left arm circles M1's left shoulder",
        "right arm circles his right shoulder",
        "left thigh wraps around his left side",
        "right thigh wraps around his right side",
        "left forearm supports her left thigh",
        "left hand cups her left buttock",
        "right forearm supports her right thigh",
        "right hand cups her right buttock",
        "his back and shoulders brace against the wall",
        "both feet remain planted",
        "stands with his back and shoulders against the wall",
        "feet shoulder-width apart",
        "left-side forearm-and-hand cradle",
        "matching right-side cradle",
        "their pelvises aligned",
        "front-to-back order is the wall, M1, F1",
        "then the viewer",
    )
    if any(value not in d03_prompt for value in d03_required):
        raise AssertionError("D03 lacks an explicit wall support contact")

    d04_spec, d04_entry, d04_activity, d04_prompt = selected_plan("D04")
    d04_required = (
        "exactly 3 continuous bodies",
        "one continuous woman body identified as F1 (woman 1)",
        "one continuous man body identified as M1 (man 1)",
        "one continuous man body identified as M2 (man 2)",
        "kneels between F1's raised thighs",
        "one hand braced on the bed and the other stabilizing F1's thigh",
        "supported by both knees and one braced hand",
        "holds a high half-kneel beside F1's head",
        "opposite foot planted so the pelvis rises to her mouth level",
        "with both hands resting on the thighs",
        "supported by one knee and opposite foot",
        "primary anatomical endpoint is rooted at M1's pelvis",
        "secondary anatomical endpoint is rooted at M2's pelvis",
        "receiving actor's single head silhouette",
    )
    if any(value not in d04_prompt for value in d04_required):
        raise AssertionError("D04 has unresolved partner limbs or alignment")

    d05_spec, d05_entry, d05_activity, d05_prompt = selected_plan("D05")
    d05_required = (
        "one hand braced on the bed and the other holding F1's hip",
        "strap-on harness is visibly secured around F2's hips",
        "base fixed to the front of her pelvis",
        "aligned to her pelvic axis",
        "anatomically separate from the anus above",
        "proximal shaft remain visible as one connected assembly",
        "actual insertion point is not shown",
    )
    if any(value not in d05_prompt for value in d05_required):
        raise AssertionError("D05 lost mounted strap-on topology")

    d06_spec, d06_entry, d06_activity, d06_prompt = selected_plan("D06")
    d06_required = (
        "kneels between F1's knees and lowers the torso between her thighs",
        "until the mouth reaches her pelvis",
        "both palms braced on the sofa beside F1's hips",
        "contacting hand maintained at F1's breast",
        "other hand braced on the sofa",
        "supported by both knees and one braced hand",
    )
    if any(value not in d06_prompt for value in d06_required):
        raise AssertionError("D06 has an unresolved oral reach path")

    d01_without_controller = deepcopy(d01_activity.model_dump(mode="json"))
    d01_without_controller["handheld_props"] = []
    rejected_activity(
        d01_without_controller,
        "vibrator_clitoral requires one controlled handheld prop",
    )
    rejected_mutations += 1

    d01_missing_limb_ownership = d01_prompt.replace(
        f"{body_ledger('one_woman')} ",
        "",
    )
    rejected_prompt(
        d01_spec,
        d01_entry,
        d01_activity,
        d01_missing_limb_ownership,
        "scene lacks the exact continuous-body ledger",
    )

    d02_disconnected_restraint = d02_prompt.replace(
        "its left end is visibly secured to her left ankle",
        "its left end lies near her left ankle",
    )
    rejected_prompt(
        d02_spec,
        d02_entry,
        d02_activity,
        d02_disconnected_restraint,
        "spreader bar lacks a visible ankle attachment chain",
    )

    d05_missing_base = d05_prompt.replace(
        "base fixed to the front of her pelvis",
        "base near the front of her pelvis",
    )
    rejected_prompt(
        d05_spec,
        d05_entry,
        d05_activity,
        d05_missing_base,
        "missing wearable prop topology",
    )

    d06_missing_support_hand = d06_prompt.replace(
        "and the other hand braced on the sofa",
        "while the other hand remains free",
    )
    rejected_prompt(
        d06_spec,
        d06_entry,
        d06_activity,
        d06_missing_support_hand,
        "conflicting manual-contact hand tasks",
    )

    d03_missing_bilateral_chain = d03_prompt.replace(
        (
            "F1's single torso faces M1; her left arm circles "
            "M1's left shoulder and her right arm circles his right "
            "shoulder. Her left thigh wraps around his left side and her "
            "right thigh wraps around his right side, with both knees bent "
            "behind his hips. M1's left forearm supports her left "
            "thigh and his left hand cups her left buttock; his right forearm "
            "supports her right thigh and his right hand cups her right "
            "buttock. "
        ),
        "",
    )
    rejected_prompt(
        d03_spec,
        d03_entry,
        d03_activity,
        d03_missing_bilateral_chain,
        "lifted pose lacks a bilateral limb chain",
    )

    d04_missing_endpoint_owner = d04_prompt.replace(
        (
            "The secondary anatomical endpoint is rooted at M2's pelvis "
            "and remains part of M2's single continuous body. "
        ),
        "",
    )
    rejected_prompt(
        d04_spec,
        d04_entry,
        d04_activity,
        d04_missing_endpoint_owner,
        "secondary lacks anatomical endpoint ownership",
    )

    d01_inserted = deepcopy(d01_activity.model_dump(mode="json"))
    d01_inserted["contact_edges"][0]["state"] = "inserted"
    rejected_activity(
        d01_inserted,
        "clitoral vibrator must remain an external surface contact",
    )
    rejected_mutations += 1

    d05_without_mount = deepcopy(d05_activity.model_dump(mode="json"))
    d05_without_mount["wearable_props"] = []
    rejected_activity(
        d05_without_mount,
        "strap-on activities require exactly one explicit wearable prop",
    )
    rejected_mutations += 1

    d05_disconnected = deepcopy(d05_activity.model_dump(mode="json"))
    d05_disconnected["contact_edges"][0]["source"] = {
        "entity_id": "partner_a",
        "region": "strap_on",
    }
    rejected_activity(
        d05_disconnected,
        "wearable prop must connect through its shaft endpoint",
    )
    rejected_mutations += 1

    d05_self_targeted = deepcopy(d05_activity.model_dump(mode="json"))
    d05_self_targeted["wearable_props"][0]["owner_slot"] = d05_activity.required_slots[
        0
    ]
    rejected_activity(
        d05_self_targeted,
        "wearable prop owner cannot also be its target",
    )
    rejected_mutations += 1

    evaluation_fixture = {
        "evaluations": [
            {
                "scene_id": f"D{index:02d}",
                "geometry_coherence": 8,
                "visual_impact": 8,
                "cast_clarity": 8,
                "contact_clarity": 8,
                "style_integration": 8,
                "strengths": ["coherent"],
                "issues": (
                    ["the pose could be difficult to render"] if index == 3 else []
                ),
                "verdict": "revise" if index == 3 else "pass",
            }
            for index in range(1, 7)
        ]
    }
    speculative_batch = EvaluationBatch.model_validate(evaluation_fixture)
    if evaluation_contract_issues(speculative_batch) != {
        "D03": ["non-passing verdict relies on speculative rendering risk"]
    }:
        raise AssertionError("speculative evaluation was not rejected")
    evaluation_fixture["evaluations"][2]["issues"] = ["the contact source has no owner"]
    deterministic_batch = EvaluationBatch.model_validate(evaluation_fixture)
    if evaluation_contract_issues(deterministic_batch):
        raise AssertionError("deterministic evaluation issue was rejected")

    report = {
        "passed": True,
        "catalogs_validated": len(CAST_KEYS),
        "entries_validated": len(CAST_KEYS) * 256,
        "coded_actor_ids_validated": EXPECTED_CAST_IDS,
        "legacy_personal_names_in_compiled_prompts": 0,
        "compiled_pose_activity_combinations": compiled_combinations,
        "strap_on_activities_validated": strap_on_activities,
        "exact_scene_assertions": [
            "D01",
            "D02",
            "D03",
            "D04",
            "D05",
            "D06",
        ],
        "rejected_mutations": rejected_mutations,
        "rejected_prompt_mutations": 6,
        "evaluation_contract_fixtures": 2,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "validation-report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
