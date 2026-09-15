from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from pathlib import Path
from typing import Annotated

from catalog_generator import PoseCatalog, PoseEntry
from catalog_scene_demo import (
    DemoSpec,
    combine_prompt,
    compile_geometry,
    compile_scene_layers,
    load_catalog,
    plan_fingerprint,
    prompt_issues,
    select_plan,
)
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from run import _generate_with_repair
from scene_layers import SettingPreset, layer_issues, make_setting_preset

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.provider import OpenAIStoryModel

ROOT = Path(__file__).resolve().parent
TestId = Annotated[str, StringConstraints(pattern=r"^D\d{2}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromptEvaluation(StrictModel):
    scene_id: TestId
    geometry_coherence: int = Field(ge=1, le=10)
    cast_clarity: int = Field(ge=1, le=10)
    pose_distinctiveness: int = Field(ge=1, le=10)
    support_clarity: int = Field(ge=1, le=10)
    visual_impact: int = Field(ge=1, le=10)
    issues: list[str] = Field(max_length=4)
    verdict: Annotated[str, StringConstraints(pattern=r"^(pass|revise|reject)$")]

    @model_validator(mode="after")
    def verdict_matches_issues(self) -> PromptEvaluation:
        if self.verdict == "pass" and self.issues:
            raise ValueError("passing evaluations cannot contain issues")
        if self.verdict != "pass" and not self.issues:
            raise ValueError("non-passing evaluations require issues")
        return self


class DiversityEvaluation(StrictModel):
    evaluations: list[PromptEvaluation] = Field(min_length=12, max_length=12)
    pose_diversity: int = Field(ge=1, le=10)
    support_diversity: int = Field(ge=1, le=10)
    composition_diversity: int = Field(ge=1, le=10)
    duplicate_pairs: list[str] = Field(max_length=12)
    coverage_gaps: list[str] = Field(max_length=12)
    issues: list[str] = Field(max_length=12)
    verdict: Annotated[str, StringConstraints(pattern=r"^(pass|revise)$")]

    @model_validator(mode="after")
    def result_is_consistent(self) -> DiversityEvaluation:
        defects = (
            any(item.verdict != "pass" for item in self.evaluations)
            or bool(self.duplicate_pairs)
            or bool(self.issues)
        )
        if self.verdict == "pass" and defects:
            raise ValueError("passing diversity evaluation contains defects")
        if self.verdict != "pass" and not defects:
            raise ValueError("revised diversity evaluation has no defect")
        return self


EVALUATION_SYSTEM = """
Evaluate the twelve supplied image prompts in their supplied order. For every prompt,
check exact cast count, one continuous body per coded role, anatomical pose
coherence, contact projection, support credibility, limb-task conflicts, pose
distinctiveness, and visual impact. Then assess diversity across the complete
batch. Scores use 1 for unusable and 10 for excellent; use the full scale and
make every score consistent with its verdict. A defect must be a deterministic
contradiction present in the prompt,
not speculation about model rendering. Do not penalize an intentionally
occluded local contact. Treat different pose families, support surfaces, body
levels, camera viewpoints, and silhouettes as meaningful diversity. Report
duplicate_pairs only for materially equivalent poses, not merely a shared
activity or cast. Use pass with an empty issues array for a clean scene. The
overall verdict is pass only when every scene passes and no duplicate pair or
material batch issue exists. Return only schema data.
""".strip()


def test_setting(
    location: str,
    lighting: str,
    palette: str,
    atmosphere: str,
    *,
    world_genre: str = "contemporary",
    wardrobe_theme: str = "editorial evening wear",
    accessory_theme: tuple[str, ...] = ("minimal jewelry",),
    makeup_theme: str = "polished editorial makeup",
    materials: tuple[str, ...] = ("textured fabric", "finished wood"),
    environment_props: tuple[str, ...] = (),
    time_of_day: str = "night",
    weather: str = "interior_controlled",
    appearance_bias: tuple[str, ...] = (),
) -> SettingPreset:
    setting_id = "test_" + re.sub(r"[^a-z0-9]+", "_", location.lower()).strip("_")
    return make_setting_preset(
        setting_id,
        location,
        lighting,
        palette,
        atmosphere,
        world_genre=world_genre,
        time_of_day=time_of_day,
        weather=weather,
        materials=materials,
        environment_props=environment_props,
        wardrobe_theme=wardrobe_theme,
        accessory_theme=accessory_theme,
        makeup_theme=makeup_theme,
        appearance_bias=appearance_bias,
    )


TESTS = (
    (
        DemoSpec(
            "D07",
            "one_woman",
            "supine",
            "knees_bent_wide_hands_on_thighs",
            "vibrator_clitoral",
            "high_three_quarter",
            "medium",
            "",
        ),
        test_setting(
            "rain-lit contemporary apartment",
            "cool window light with restrained cyan reflections",
            "slate blue, ivory and muted cyan",
            "quiet editorial tension",
        ),
    ),
    (
        DemoSpec(
            "D08",
            "one_woman_one_man",
            "prone",
            "legs_wide_hands_grip_edge",
            "anal_rear_entry",
            "rear_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "minimal dark timber bedroom",
            "warm directional light from a shaded bedside source",
            "walnut, amber and charcoal",
            "controlled cinematic intimacy",
        ),
    ),
    (
        DemoSpec(
            "D09",
            "two_women",
            "side_lying_left",
            "top_leg_raised_upper_hand_hip",
            "strap_on_vaginal_side_lying",
            "side_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "soft linen studio bedroom",
            "broad diffused morning light with a pale rim",
            "cream, sand and dusty rose",
            "calm sculptural warmth",
        ),
    ),
    (
        DemoSpec(
            "D10",
            "one_woman_one_man",
            "all_fours",
            "knees_wide_hands_wide",
            "vaginal_rear_entry",
            "overhead_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "geometric hotel bedroom",
            "focused overhead light with softened falloff",
            "deep green, brass and neutral linen",
            "precise dramatic stillness",
        ),
    ),
    (
        DemoSpec(
            "D11",
            "three_women",
            "kneeling_upright",
            "frog_kneel_arms_overhead",
            "kneeling_group",
            "front_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "open loft with polished concrete",
            "large frontal softbox balanced by narrow edge lights",
            "graphite, silver and warm ochre",
            "bold ensemble portraiture",
        ),
    ),
    (
        DemoSpec(
            "D12",
            "one_woman_two_men",
            "kneeling_forward",
            "one_knee_forward_forearms_parallel",
            "dual_oral_on_woman",
            "low_three_quarter",
            "medium",
            "",
        ),
        test_setting(
            "velvet-lined private suite",
            "low side light with a narrow golden highlight",
            "burgundy, black and antique gold",
            "dense theatrical focus",
        ),
    ),
    (
        DemoSpec(
            "D13",
            "two_women",
            "seated_upright",
            "legs_extended_hands_behind",
            "tribadism",
            "high_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "modern lounge with a sculptural chair",
            "clean skylight with a soft reflected fill",
            "stone, ivory and muted teal",
            "balanced contemporary elegance",
        ),
    ),
    (
        DemoSpec(
            "D14",
            "one_woman_two_men",
            "seated_reclined",
            "one_leg_raised_elbows_support",
            "seated_group",
            "front_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "low modular sofa in a luxury loft",
            "triangular key lights with controlled shadow separation",
            "black, ivory and copper",
            "graphic ensemble energy",
        ),
    ),
    (
        DemoSpec(
            "D15",
            "one_woman",
            "seated_edge",
            "one_leg_extended_one_arm_reaching",
            "bed_edge_masturbation",
            "side_three_quarter",
            "medium",
            "",
        ),
        test_setting(
            "compact bedroom with a low platform bed",
            "late afternoon window stripe with gentle ambient fill",
            "honey wood, white and muted blue",
            "observational editorial calm",
        ),
    ),
    (
        DemoSpec(
            "D16",
            "one_woman_one_man",
            "standing_wall_supported",
            "one_leg_raised_one_hand_wall",
            "vaginal_standing",
            "rear_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "narrow architectural corridor",
            "hard side light tracing the wall geometry",
            "concrete gray, rust and deep navy",
            "tense architectural drama",
        ),
    ),
    (
        DemoSpec(
            "D17",
            "three_women",
            "deep_squat",
            "feet_wide_arms_forward",
            "central_manual_both_partners",
            "low_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "minimal stage with a matte floor",
            "low frontal key light and two symmetric rim lights",
            "black, crimson and warm white",
            "high-impact graphic symmetry",
        ),
    ),
    (
        DemoSpec(
            "D18",
            "one_woman_one_man",
            "lifted_supported",
            "legs_wrapped_arms_shoulders",
            "vaginal_lifted",
            "low_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "spacious modern corridor",
            "hard directional sidelight with deep controlled shadows",
            "deep burgundy, ochre and slate",
            "dynamic cinematic intensity",
        ),
    ),
)

ROUND_TWO_TESTS = (
    (
        DemoSpec(
            "D19",
            "one_woman_one_man",
            "side_lying_right",
            "fetal_tuck_arms_folded",
            "anal_side_lying",
            "front_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "rain-soaked roadside motel at midnight",
            "red vacancy neon through wet glass and one bedside lamp",
            "deep red, cyan, tobacco brown and cream",
            "nocturnal neo-noir tension",
            wardrobe_theme="creased nightlife clothing arranged for the scene",
            accessory_theme=("chrome jewelry",),
            makeup_theme="slightly smudged late-night makeup",
            materials=("aged wallpaper", "vinyl", "wet glass"),
            environment_props=("red vacancy sign", "rumpled bed"),
            weather="rain",
        ),
    ),
    (
        DemoSpec(
            "D20",
            "one_woman",
            "standing_upright",
            "staggered_stance_hands_wall",
            "standing_wall_masturbation",
            "side_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "tall concrete studio wall",
            "narrow side beam with a soft reflected fill",
            "concrete, amber and matte black",
            "graphic solitary tension",
        ),
    ),
    (
        DemoSpec(
            "D21",
            "one_woman_one_man",
            "standing_bent",
            "feet_wide_hands_furniture",
            "vaginal_rear_entry",
            "rear_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "double-height luxury hotel suite after midnight",
            "warm brass practicals balanced by cool city window light",
            "emerald velvet, brass, ivory and midnight blue",
            "opulent cinematic depth",
            wardrobe_theme="luxury evening wear arranged for the scene",
            accessory_theme=("fine gold jewelry",),
            makeup_theme="precise evening makeup",
            materials=("emerald velvet", "polished brass", "ivory linen"),
            environment_props=("city window", "dark wood console"),
            appearance_bias=("statuesque", "polished"),
        ),
    ),
    (
        DemoSpec(
            "D22",
            "two_women",
            "bridge_elevated",
            "one_leg_extended_hands_hips",
            "strap_on_vaginal_face_to_face",
            "high_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "minimal platform bed with pale fabric",
            "broad overhead diffusion and a gentle warm edge",
            "ivory, blush and light oak",
            "sculptural floating calm",
        ),
    ),
    (
        DemoSpec(
            "D23",
            "three_women",
            "supine",
            "legs_vertical_arms_overhead",
            "double_toy_vaginal_anal",
            "high_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "obsidian throne chamber in a demon sovereign palace",
            "crimson braziers and molten floor fissures",
            "obsidian, crimson and antique gold",
            "commanding infernal symmetry",
            world_genre="dark_fantasy",
            wardrobe_theme="dark fantasy regalia arranged for the scene",
            accessory_theme=("horned crown", "black metal arm cuffs"),
            makeup_theme="ritual smoky eyes and dark wine lips",
            materials=("obsidian", "black iron", "crimson velvet"),
            environment_props=("empty throne", "braziers", "ritual sigil"),
            appearance_bias=("statuesque", "commanding", "supernatural_eyes"),
        ),
    ),
    (
        DemoSpec(
            "D24",
            "one_woman",
            "seated_upright",
            "knees_wide_one_hand_chair",
            "chair_masturbation",
            "low_three_quarter",
            "medium",
            "",
        ),
        test_setting(
            "sculptural chair beside a low window",
            "low morning light passing through sheer curtains",
            "sand, cream and pale blue",
            "tactile natural quiet",
        ),
    ),
    (
        DemoSpec(
            "D25",
            "one_woman_two_men",
            "all_fours",
            "one_knee_forward_one_hand_headboard",
            "anal_plus_manual",
            "overhead_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "structured hotel bed with a dark headboard",
            "angled key light and separated background practicals",
            "charcoal, bronze and white",
            "layered ensemble drama",
        ),
    ),
    (
        DemoSpec(
            "D26",
            "two_women",
            "kneeling_upright",
            "one_foot_planted_hands_behind",
            "wrist_bondage_oral",
            "front_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "minimal amber performance space",
            "frontal soft light with narrow sculptural shadows",
            "amber, umber and cream",
            "controlled ritual elegance",
        ),
    ),
    (
        DemoSpec(
            "D27",
            "one_woman_one_man",
            "seated_edge",
            "ankles_crossed_one_arm_reaching",
            "mutual_masturbation",
            "high_three_quarter",
            "medium",
            "",
        ),
        test_setting(
            "modern reading room with one sculptural chair",
            "clean skylight and warm reflected floor light",
            "forest green, oak and ivory",
            "composed contemporary intimacy",
        ),
    ),
    (
        DemoSpec(
            "D28",
            "one_woman",
            "seated_reclined",
            "legs_extended_hands_behind",
            "blindfolded_manual",
            "front_three_quarter",
            "medium_wide",
            "",
        ),
        test_setting(
            "low sofa in a quiet monochrome loft",
            "soft frontal key with a dim practical glow",
            "graphite, pearl and muted violet",
            "restrained sensory atmosphere",
        ),
    ),
    (
        DemoSpec(
            "D29",
            "three_women",
            "standing_wall_supported",
            "feet_wide_arms_overhead",
            "wall_supported_group",
            "side_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "long plaster wall in an open gallery",
            "raking side light with two distant pools of illumination",
            "chalk white, rust and deep gray",
            "architectural ensemble rhythm",
        ),
    ),
    (
        DemoSpec(
            "D30",
            "two_women",
            "lifted_supported",
            "thighs_supported_one_arm_partner",
            "strap_on_vaginal_lifted",
            "low_three_quarter",
            "full_body",
            "",
        ),
        test_setting(
            "spacious corridor with dark polished panels",
            "hard diagonal light and a subtle floor reflection",
            "burgundy, slate and warm brass",
            "dynamic cinematic suspension",
        ),
    ),
)


def reference_subset(catalog: PoseCatalog) -> list[PoseEntry]:
    variant_indexes = (0, 1, 4, 5, 10, 11, 14, 15)
    subset = []
    for family in dict.fromkeys(entry.central_pose.family for entry in catalog.entries):
        family_entries = [
            entry for entry in catalog.entries if entry.central_pose.family == family
        ]
        subset.extend(family_entries[index] for index in variant_indexes)
    return subset


def reference_metrics(entries: list[PoseEntry]) -> dict[str, object]:
    return {
        "poses": len(entries),
        "unique_signatures": len({entry.signature for entry in entries}),
        "pose_families": len({entry.central_pose.family for entry in entries}),
        "poses_per_family": dict(
            sorted(Counter(entry.central_pose.family for entry in entries).items())
        ),
        "body_levels": sorted({entry.central_pose.body_level for entry in entries}),
        "primary_surfaces": sorted(
            {entry.central_pose.primary_surface for entry in entries}
        ),
        "leg_configurations": len(
            {entry.central_pose.leg_configuration for entry in entries}
        ),
        "arm_configurations": len(
            {entry.central_pose.arm_configuration for entry in entries}
        ),
        "camera_viewpoints": sorted(
            {
                camera
                for entry in entries
                for camera in entry.central_pose.compatible_camera_views
            }
        ),
        "support_topologies": len(
            {tuple(entry.central_pose.support_points) for entry in entries}
        ),
    }


def evaluation_contract_issues(
    evaluation: DiversityEvaluation,
    expected_ids: list[str],
) -> list[str]:
    issues = []
    actual_ids = [item.scene_id for item in evaluation.evaluations]
    if actual_ids != expected_ids:
        issues.append(
            f"evaluation IDs changed: expected {expected_ids}, got {actual_ids}"
        )
    speculative = re.compile(
        r"\b(?:may|might|could|potential|possibly|likely|unlikely|"
        r"challenge|risk|difficult to render)\b",
        re.I,
    )
    for item in evaluation.evaluations:
        scores = (
            item.geometry_coherence,
            item.cast_clarity,
            item.pose_distinctiveness,
            item.support_clarity,
            item.visual_impact,
        )
        if item.verdict == "pass" and min(scores) < 7:
            issues.append(f"{item.scene_id} pass verdict has a score below 7")
        if item.verdict != "pass" and speculative.search(" ".join(item.issues)):
            issues.append(f"{item.scene_id} relies on speculative rendering risk")
    diversity_scores = (
        evaluation.pose_diversity,
        evaluation.support_diversity,
        evaluation.composition_diversity,
    )
    if evaluation.verdict == "pass" and min(diversity_scores) < 8:
        issues.append("batch pass verdict has a diversity score below 8")
    if evaluation.verdict != "pass" and speculative.search(" ".join(evaluation.issues)):
        issues.append("batch verdict relies on speculative rendering risk")
    return issues


async def evaluate_prompts(
    prompts: list[str],
    selections: list[dict[str, object]],
) -> dict[str, object]:
    settings = load_story_provider_settings()
    payload: dict[str, object] = {
        "tests": [
            {
                "scene_id": selection["scene_id"],
                "prompt": prompt,
            }
            for selection, prompt in zip(selections, prompts, strict=True)
        ]
    }
    responses = []
    rejections: list[list[str]] = []
    contract_issues: list[str] = []
    async with OpenAIStoryModel(settings) as model:
        for _ in range(3):
            response, structured_rejections = await _generate_with_repair(
                model,
                system=EVALUATION_SYSTEM,
                payload=payload,
                response_model=DiversityEvaluation,
                max_output_tokens=min(12000, settings.output_token_limit),
            )
            responses.append(response)
            rejections.extend(structured_rejections)
            evaluation = DiversityEvaluation.model_validate(response.value)
            contract_issues = evaluation_contract_issues(
                evaluation,
                [str(selection["scene_id"]) for selection in selections],
            )
            if not contract_issues:
                break
            payload = {
                **payload,
                "previous_evaluation": evaluation.model_dump(mode="json"),
                "contract_issues": contract_issues,
                "repair_requirement": (
                    "Re-evaluate the complete batch. Make every numeric score "
                    "consistent with its verdict. For a low-scoring item, either "
                    "state the deterministic defect and use revise/reject or "
                    "raise the score when no material defect exists. Remove "
                    "conclusions based only on speculative rendering risk."
                ),
            }
    return {
        "model": settings.model,
        "attempts": len(responses),
        "contract_issues": contract_issues,
        "structured_rejections": rejections,
        "usage_by_attempt": [
            response.usage.model_dump(mode="json") for response in responses
        ],
        **evaluation.model_dump(mode="json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and evaluate twelve stratified catalog prompts."
    )
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--batch", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    tests = TESTS if args.batch == 1 else ROUND_TWO_TESTS
    output = (
        ROOT / "diversity-12-output"
        if args.batch == 1
        else ROOT / "diversity-12-round2-output"
    )
    prompts = []
    selections = []
    resolved_layers = []
    issues: dict[str, list[str]] = {}
    for spec, setting in tests:
        catalog = load_catalog(spec.cast_key)
        entry, activity = select_plan(catalog, spec)
        fingerprint = plan_fingerprint(spec, entry, activity)
        geometry = compile_geometry(spec, entry, activity)
        layers = compile_scene_layers(
            spec,
            entry,
            activity,
            fingerprint,
            geometry,
            setting,
        )
        prompt = combine_prompt(geometry, layers)
        prompt_problems = [
            *layer_issues(layers, list(catalog.cast_roles)),
            *prompt_issues(spec, entry, activity, prompt),
        ]
        if prompt_problems:
            issues[spec.scene_id] = prompt_problems
        prompts.append(prompt)
        resolved_layers.append(layers)
        selections.append(
            {
                "scene_id": spec.scene_id,
                "cast_key": spec.cast_key,
                "pose_id": entry.pose_id,
                "pose_family": entry.central_pose.family,
                "pose_variant": entry.central_pose.variant,
                "body_level": entry.central_pose.body_level,
                "primary_surface": entry.central_pose.primary_surface,
                "support_points": entry.central_pose.support_points,
                "activity_id": activity.activity_id,
                "camera_viewpoint": spec.viewpoint,
                "shot_scale": spec.shot_scale,
                "plan_fingerprint": fingerprint,
                "character_fingerprint": layers.fingerprints.characters,
                "setting_id": layers.setting.setting_id,
                "setting_fingerprint": layers.fingerprints.setting,
                "presentation_fingerprint": layers.fingerprints.presentation,
                "estimated_tokens": layers.token_metrics.final_estimated_tokens,
            }
        )

    reference = reference_subset(load_catalog("one_woman_one_man"))
    reference_report = reference_metrics(reference)
    sample_report = {
        "prompts": len(prompts),
        "unique_pose_signatures": len(
            {selection["plan_fingerprint"] for selection in selections}
        ),
        "pose_families": len({selection["pose_family"] for selection in selections}),
        "cast_configurations": len({selection["cast_key"] for selection in selections}),
        "activities": len({selection["activity_id"] for selection in selections}),
        "body_levels": len({selection["body_level"] for selection in selections}),
        "primary_surfaces": len(
            {selection["primary_surface"] for selection in selections}
        ),
        "camera_viewpoints": len(
            {selection["camera_viewpoint"] for selection in selections}
        ),
        "shot_scales": len({selection["shot_scale"] for selection in selections}),
        "settings": len({selection["setting_id"] for selection in selections}),
    }
    thresholds = {
        "prompts": 12,
        "unique_pose_signatures": 12,
        "pose_families": 12,
        "cast_configurations": 5,
        "activities": 12,
        "body_levels": 3,
        "primary_surfaces": 7,
        "camera_viewpoints": 6,
        "shot_scales": 3,
        "settings": 12,
    }
    threshold_failures = {
        field: {"actual": sample_report[field], "required": minimum}
        for field, minimum in thresholds.items()
        if sample_report[field] < minimum
    }
    reference_valid = (
        reference_report["poses"] == 128
        and reference_report["unique_signatures"] == 128
        and reference_report["pose_families"] == 16
        and set(reference_report["poses_per_family"].values()) == {8}
    )
    report = {
        "passed": not issues and not threshold_failures and reference_valid,
        "batch": args.batch,
        "catalog_entries_per_cast": 256,
        "reference_128": reference_report,
        "sample_12": sample_report,
        "thresholds": thresholds,
        "threshold_failures": threshold_failures,
        "prompt_issues": issues,
        "token_metrics": {
            "estimated_total": sum(
                layers.token_metrics.final_estimated_tokens
                for layers in resolved_layers
            ),
            "estimated_average": round(
                sum(
                    layers.token_metrics.final_estimated_tokens
                    for layers in resolved_layers
                )
                / len(resolved_layers),
                2,
            ),
            "maximum_layer_tokens": max(
                layers.token_metrics.layer_estimated_tokens
                for layers in resolved_layers
            ),
            "verbose_layer_estimated_total": sum(
                layers.token_metrics.verbose_layer_estimated_tokens
                for layers in resolved_layers
            ),
            "compact_saved_total": sum(
                layers.token_metrics.compact_saved_tokens for layers in resolved_layers
            ),
            "layer_budget_tokens": min(
                layers.token_metrics.layer_budget_tokens for layers in resolved_layers
            ),
            "style_generation_calls": 0,
            "evaluation_payload": "scene_id_and_prompt_only",
        },
    }
    if args.evaluate:
        evaluation = asyncio.run(evaluate_prompts(prompts, selections))
        report["deepseek_evaluation"] = evaluation
        report["passed"] = (
            report["passed"]
            and not evaluation["contract_issues"]
            and evaluation["verdict"] == "pass"
        )
    output.mkdir(parents=True, exist_ok=True)
    (output / "prompts.txt").write_text(
        "\n".join(prompts) + "\n",
        encoding="utf-8",
    )
    (output / "selections.json").write_text(
        json.dumps(selections, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "layers.json").write_text(
        json.dumps(
            [layers.model_dump(mode="json") for layers in resolved_layers],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
