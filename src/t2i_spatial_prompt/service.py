from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import NamedTuple

from catalog_diversity_12 import evaluate_prompts
from catalog_scene_demo import (
    DemoSpec,
    combine_prompt,
    compile_geometry,
    compile_scene_layers,
    environment_supports,
    load_catalog,
    plan_fingerprint,
    prompt_issues,
    select_plan,
)
from pydantic import ValidationError
from scene_layers import layer_issues, stable_hash
from setting_blueprint import (
    BLUEPRINT_SCHEMA_VERSION,
    BLUEPRINT_SYSTEM_HASH,
    BlueprintInference,
    infer_creative_blueprint,
    sample_scene_layer_inputs,
    semantic_hash,
)

from t2i_story_pipeline.config import load_story_provider_settings

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "demon-hardcore-12-output"
CACHE = OUTPUT / "blueprint-cache"
DEFAULT_BRIEF = (
    "A powerful female demon sovereign and one adult male consort in a vast "
    "dark-fantasy infernal palace. Build varied palace sub-locations with "
    "obsidian, black iron, crimson velvet, ritual fire, supernatural lighting, "
    "regal demon wardrobe, horned crown motifs, and intense cinematic mood."
)


class PoseSpec(NamedTuple):
    scene_id: str
    family: str
    variant: str
    activity_id: str
    viewpoint: str
    shot_scale: str


POSE_SPECS = (
    PoseSpec(
        "D31",
        "supine",
        "knees_bent_wide_arms_outward",
        "vaginal_face_to_face",
        "high_three_quarter",
        "medium_wide",
    ),
    PoseSpec(
        "D32",
        "all_fours",
        "knees_wide_hands_straight",
        "vaginal_rear_entry",
        "overhead_three_quarter",
        "full_body",
    ),
    PoseSpec(
        "D33",
        "side_lying_left",
        "top_leg_raised_upper_hand_hip",
        "vaginal_side_lying",
        "side_three_quarter",
        "medium_wide",
    ),
    PoseSpec(
        "D34",
        "seated_reclined",
        "one_leg_raised_elbows_support",
        "vaginal_seated",
        "front_three_quarter",
        "medium",
    ),
    PoseSpec(
        "D35",
        "standing_wall_supported",
        "one_leg_raised_one_hand_wall",
        "vaginal_standing",
        "rear_three_quarter",
        "full_body",
    ),
    PoseSpec(
        "D36",
        "lifted_supported",
        "legs_wrapped_arms_shoulders",
        "vaginal_lifted",
        "low_three_quarter",
        "full_body",
    ),
    PoseSpec(
        "D37",
        "prone",
        "legs_wide_hands_grip_edge",
        "anal_rear_entry",
        "rear_three_quarter",
        "medium_wide",
    ),
    PoseSpec(
        "D38",
        "side_lying_right",
        "fetal_tuck_arms_folded",
        "anal_side_lying",
        "front_three_quarter",
        "medium_wide",
    ),
    PoseSpec(
        "D39",
        "kneeling_upright",
        "one_foot_planted_hands_behind",
        "fellatio",
        "front_three_quarter",
        "full_body",
    ),
    PoseSpec(
        "D40",
        "seated_edge",
        "one_leg_extended_one_arm_reaching",
        "manual_penile",
        "high_three_quarter",
        "medium",
    ),
    PoseSpec(
        "D41",
        "deep_squat",
        "feet_wide_arms_forward",
        "ankle_bondage_penetration",
        "low_three_quarter",
        "full_body",
    ),
    PoseSpec(
        "D42",
        "standing_bent",
        "feet_wide_hands_furniture",
        "impact_over_furniture",
        "side_three_quarter",
        "full_body",
    ),
)


def blueprint_cache_path(
    brief: str,
    seed: int,
) -> Path:
    model = load_story_provider_settings().model
    identity = json.dumps(
        {
            "brief_hash": hashlib.sha256(brief.strip().encode()).hexdigest(),
            "creative_seed": seed,
            "model": model,
            "schema_version": BLUEPRINT_SCHEMA_VERSION,
            "system_prompt_hash": BLUEPRINT_SYSTEM_HASH,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return CACHE / f"{hashlib.sha256(identity.encode()).hexdigest()}.json"


def cached_inference(
    brief: str,
    seed: int,
) -> BlueprintInference | None:
    path = blueprint_cache_path(brief, seed)
    if not path.exists():
        return None
    try:
        inference = BlueprintInference.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError:
        return None
    expected_hash = hashlib.sha256(brief.strip().encode()).hexdigest()
    expected_model = load_story_provider_settings().model
    if (
        inference.brief_hash != expected_hash
        or inference.creative_seed != seed
        or inference.model != expected_model
        or inference.schema_version != BLUEPRINT_SCHEMA_VERSION
        or inference.system_prompt_hash != BLUEPRINT_SYSTEM_HASH
    ):
        return None
    return inference


async def run(
    brief: str,
    seed: int,
    *,
    evaluate: bool,
    refresh_blueprint: bool,
) -> dict[str, object]:
    inference = None if refresh_blueprint else cached_inference(brief, seed)
    blueprint_cache_hit = inference is not None
    if inference is None:
        inference = await infer_creative_blueprint(brief, seed)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = blueprint_cache_path(brief, seed)
    cache_path.write_text(
        inference.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "blueprint.json").write_text(
        inference.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    catalog = load_catalog("one_woman_one_man")
    spatial_plans = []
    support_requirements = []
    for pose_spec in POSE_SPECS:
        spec = DemoSpec(
            pose_spec.scene_id,
            "one_woman_one_man",
            pose_spec.family,
            pose_spec.variant,
            pose_spec.activity_id,
            pose_spec.viewpoint,
            pose_spec.shot_scale,
            "",
        )
        entry, activity = select_plan(catalog, spec)
        spatial_plans.append((pose_spec, spec, entry, activity))
        support_requirements.append(set(environment_supports(entry)))
    scene_inputs = sample_scene_layer_inputs(
        inference.blueprint,
        required_supports=support_requirements,
        seed=seed,
    )
    repeated_inputs = sample_scene_layer_inputs(
        inference.blueprint,
        required_supports=support_requirements,
        seed=seed,
    )
    alternate_inputs = sample_scene_layer_inputs(
        inference.blueprint,
        required_supports=support_requirements,
        seed=seed + 1,
    )
    sampled_fingerprints = [stable_hash(item) for item in scene_inputs]
    sampler_validation = {
        "same_seed_reproducible": sampled_fingerprints
        == [stable_hash(item) for item in repeated_inputs],
        "different_seed_changes_output": sampled_fingerprints
        != [stable_hash(item) for item in alternate_inputs],
        "semantic_combinations_unique": len(set(sampled_fingerprints))
        == len(scene_inputs),
    }
    if not all(sampler_validation.values()):
        raise AssertionError(
            f"creative sampler validation failed: {sampler_validation}"
        )
    prompts = []
    selections = []
    resolved_layers = []
    issues: dict[str, list[str]] = {}
    for (_, base_spec, entry, activity), layer_inputs in zip(
        spatial_plans,
        scene_inputs,
        strict=True,
    ):
        spec = base_spec._replace(setting_id=layer_inputs.setting.setting_id)
        fingerprint = plan_fingerprint(spec, entry, activity)
        geometry = compile_geometry(spec, entry, activity)
        layers = compile_scene_layers(
            spec,
            entry,
            activity,
            fingerprint,
            geometry,
            layer_inputs.setting,
            layer_inputs.style,
            layer_inputs.presentation,
        )
        prompt = combine_prompt(geometry, layers)
        current_issues = [
            *layer_issues(layers, list(catalog.cast_roles)),
            *prompt_issues(spec, entry, activity, prompt),
        ]
        if current_issues:
            issues[spec.scene_id] = current_issues
        prompts.append(prompt)
        resolved_layers.append(layers)
        selections.append(
            {
                "scene_id": spec.scene_id,
                "cast_key": spec.cast_key,
                "pose_id": entry.pose_id,
                "pose_family": entry.central_pose.family,
                "pose_variant": entry.central_pose.variant,
                "activity_id": activity.activity_id,
                "camera_viewpoint": spec.viewpoint,
                "shot_scale": spec.shot_scale,
                "setting_id": layer_inputs.setting.setting_id,
                "world_location": layer_inputs.setting.location,
                "style_id": layer_inputs.style.style_id,
                "presentation_id": layer_inputs.presentation.presentation_id,
                "spatial_fingerprint": fingerprint,
                "character_fingerprint": layers.fingerprints.characters,
                "setting_fingerprint": layers.fingerprints.setting,
                "setting_semantic_fingerprint": semantic_hash(
                    layer_inputs.setting,
                    "setting_id",
                ),
                "style_fingerprint": layers.fingerprints.style,
                "presentation_fingerprint": layers.fingerprints.presentation,
                "presentation_semantic_fingerprint": semantic_hash(
                    layer_inputs.presentation,
                    "presentation_id",
                ),
                "estimated_tokens": layers.token_metrics.final_estimated_tokens,
            }
        )
    metrics = {
        "scenes": len(prompts),
        "cast": "one_woman_one_man",
        "pose_families": len({selection["pose_family"] for selection in selections}),
        "activities": len({selection["activity_id"] for selection in selections}),
        "settings": len(
            {selection["setting_semantic_fingerprint"] for selection in selections}
        ),
        "world_locations": len(
            {selection["world_location"] for selection in selections}
        ),
        "styles": len({selection["style_id"] for selection in selections}),
        "presentations": len(
            {selection["presentation_semantic_fingerprint"] for selection in selections}
        ),
        "camera_viewpoints": len(
            {selection["camera_viewpoint"] for selection in selections}
        ),
        "shot_scales": len({selection["shot_scale"] for selection in selections}),
        "estimated_total_tokens": sum(
            layers.token_metrics.final_estimated_tokens for layers in resolved_layers
        ),
        "maximum_layer_tokens": max(
            layers.token_metrics.layer_estimated_tokens for layers in resolved_layers
        ),
        "compact_saved_tokens": sum(
            layers.token_metrics.compact_saved_tokens for layers in resolved_layers
        ),
        "blueprint_cache_hit": blueprint_cache_hit,
        "blueprint_prompt_tokens": (
            0 if blueprint_cache_hit else inference.usage["prompt_tokens"]
        ),
        "blueprint_completion_tokens": (
            0 if blueprint_cache_hit else inference.usage["completion_tokens"]
        ),
    }
    thresholds = {
        "scenes": 12,
        "pose_families": 12,
        "activities": 12,
        "settings": 12,
        "world_locations": 6,
        "styles": 6,
        "presentations": 12,
        "camera_viewpoints": 6,
        "shot_scales": 3,
    }
    threshold_failures = {
        field: {"actual": metrics[field], "required": minimum}
        for field, minimum in thresholds.items()
        if metrics[field] < minimum
    }
    report: dict[str, object] = {
        "passed": not issues and not threshold_failures,
        "creative_brief": brief,
        "creative_seed": seed,
        "blueprint_fingerprint": stable_hash(inference.blueprint),
        "blueprint_cache_key": cache_path.stem,
        "sampler_validation": sampler_validation,
        "metrics": metrics,
        "thresholds": thresholds,
        "threshold_failures": threshold_failures,
        "prompt_issues": issues,
    }
    if evaluate:
        evaluation = await evaluate_prompts(prompts, selections)
        report["deepseek_evaluation"] = evaluation
        report["passed"] = (
            report["passed"]
            and not evaluation["contract_issues"]
            and evaluation["verdict"] == "pass"
        )
    (OUTPUT / "prompts.txt").write_text(
        "\n".join(prompts) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "selections.json").write_text(
        json.dumps(selections, ensure_ascii=False, indent=2) + "\n",
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
    (OUTPUT / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Infer a creative blueprint from user input, solve twelve compatible "
            "world/style/presentation combinations, and compile one-woman/one-man "
            "demon-palace scenes."
        )
    )
    parser.add_argument("--creative-brief", default=DEFAULT_BRIEF)
    parser.add_argument("--creative-seed", type=int, default=42)
    parser.add_argument("--refresh-blueprint", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(
        run(
            args.creative_brief,
            args.creative_seed,
            evaluate=args.evaluate,
            refresh_blueprint=args.refresh_blueprint,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
