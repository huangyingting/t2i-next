from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import NamedTuple

from pydantic import ValidationError

from .blueprint import (
    BLUEPRINT_SCHEMA_VERSION,
    BLUEPRINT_SYSTEM_HASH,
    BlueprintInference,
    blueprint_inference_config_hash,
    infer_creative_blueprint,
    maximum_location_assignment,
    sample_scene_layer_inputs,
    semantic_hash,
)
from .catalog import CASTS, PoseEntry
from .compiler import (
    SceneSpec,
    combine_prompt,
    compile_geometry,
    compile_scene_layers,
    environment_supports,
    load_catalog,
    plan_fingerprint,
    prompt_issues,
    select_plan,
)
from .config import load_spatial_provider_settings
from .layers import PRESENTATION_ROLE_CODES, layer_issues, stable_hash


class SceneRequest(NamedTuple):
    scene_id: str
    family: str
    variant: str
    activity_id: str
    viewpoint: str
    shot_scale: str
    cast_key: str = "one_woman_one_man"


VIEWPOINTS = (
    "front_three_quarter",
    "high_three_quarter",
    "low_three_quarter",
    "overhead_three_quarter",
    "rear_three_quarter",
    "side_three_quarter",
)
SHOT_SCALES = ("medium_close", "medium", "medium_wide", "full_body", "wide")


def _assign_unique_activities(
    families: list[str],
    family_entries: dict[str, list[PoseEntry]],
    *,
    rng: random.Random,
) -> dict[str, tuple[str, PoseEntry]]:
    options: dict[str, list[tuple[str, PoseEntry]]] = {}
    for family in families:
        by_activity: dict[str, list[PoseEntry]] = {}
        for entry in family_entries[family]:
            for activity_id in entry.compatible_activity_ids:
                by_activity.setdefault(activity_id, []).append(entry)
        activity_ids = sorted(by_activity)
        rng.shuffle(activity_ids)
        options[family] = [
            (activity_id, rng.choice(by_activity[activity_id]))
            for activity_id in activity_ids
        ]
    assignment: dict[str, tuple[str, PoseEntry]] = {}
    used_activities: set[str] = set()

    def search(remaining: list[str]) -> bool:
        if not remaining:
            return True
        family = min(
            remaining,
            key=lambda item: sum(
                activity_id not in used_activities
                for activity_id, _ in options[item]
            ),
        )
        next_remaining = [item for item in remaining if item != family]
        for activity_id, entry in options[family]:
            if activity_id in used_activities:
                continue
            assignment[family] = (activity_id, entry)
            used_activities.add(activity_id)
            if search(next_remaining):
                return True
            used_activities.remove(activity_id)
            assignment.pop(family)
        return False

    if not search(list(families)):
        raise ValueError(
            "cannot assign unique activities across selected pose families"
        )
    return assignment


def _assign_camera_views(
    families: list[str],
    family_entries: dict[str, list[PoseEntry]],
) -> dict[str, str]:
    compatible_views = {
        family: set(family_entries[family][0].central_pose.compatible_camera_views)
        for family in families
    }
    eligible_families = {
        viewpoint: [
            family for family in families if viewpoint in compatible_views[family]
        ]
        for viewpoint in VIEWPOINTS
    }
    required_order = sorted(
        VIEWPOINTS,
        key=lambda viewpoint: len(eligible_families[viewpoint]),
    )
    required_assignment: dict[str, str] = {}
    used_families: set[str] = set()

    def cover(index: int) -> bool:
        if index == len(required_order):
            return True
        viewpoint = required_order[index]
        for family in eligible_families[viewpoint]:
            if family in used_families:
                continue
            required_assignment[family] = viewpoint
            used_families.add(family)
            if cover(index + 1):
                return True
            used_families.remove(family)
            required_assignment.pop(family)
        return False

    if not cover(0):
        raise ValueError("selected pose families cannot cover all camera viewpoints")

    assignment = dict(required_assignment)
    view_counts = {
        viewpoint: sum(value == viewpoint for value in assignment.values())
        for viewpoint in VIEWPOINTS
    }
    for index, family in enumerate(families):
        if family in assignment:
            continue
        preference = VIEWPOINTS[index % len(VIEWPOINTS) :] + VIEWPOINTS[
            : index % len(VIEWPOINTS)
        ]
        viewpoint = min(
            (view for view in preference if view in compatible_views[family]),
            key=lambda view: (view_counts[view], preference.index(view)),
        )
        assignment[family] = viewpoint
        view_counts[viewpoint] += 1
    return assignment


def build_scene_requests(
    cast_key: str,
    *,
    seed: int,
    count: int = 12,
) -> tuple[SceneRequest, ...]:
    if count != 12:
        raise ValueError("the released creative blueprint requires exactly 12 scenes")
    catalog = load_catalog(cast_key)
    rng = random.Random(seed)
    families = sorted({entry.central_pose.family for entry in catalog.entries})
    rng.shuffle(families)
    selected_families = families[:count]
    family_entries = {
        family: [
            entry
            for entry in catalog.entries
            if entry.central_pose.family == family
        ]
        for family in selected_families
    }
    activity_assignment = _assign_unique_activities(
        selected_families,
        family_entries,
        rng=rng,
    )
    camera_assignment = _assign_camera_views(selected_families, family_entries)
    requests = []
    for index, family in enumerate(selected_families):
        chosen_activity, chosen_entry = activity_assignment[family]
        requests.append(
            SceneRequest(
                scene_id=f"S{index + 1:02d}",
                family=family,
                variant=chosen_entry.central_pose.variant,
                activity_id=chosen_activity,
                viewpoint=camera_assignment[family],
                shot_scale=SHOT_SCALES[index % len(SHOT_SCALES)],
                cast_key=cast_key,
            )
        )
    return tuple(requests)


def blueprint_cache_path(
    brief: str,
    seed: int,
    output: Path,
    cast_roles: tuple[str, ...],
) -> Path:
    settings = load_spatial_provider_settings()
    identity = json.dumps(
        {
            "brief_hash": hashlib.sha256(brief.strip().encode()).hexdigest(),
            "creative_seed": seed,
            "cast_roles": cast_roles,
            "inference_config_hash": blueprint_inference_config_hash(settings),
            "schema_version": BLUEPRINT_SCHEMA_VERSION,
            "system_prompt_hash": BLUEPRINT_SYSTEM_HASH,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        output
        / "blueprint-cache"
        / (f"{hashlib.sha256(identity.encode()).hexdigest()}.json")
    )


def cached_inference(
    brief: str,
    seed: int,
    output: Path,
    cast_roles: tuple[str, ...],
) -> BlueprintInference | None:
    path = blueprint_cache_path(brief, seed, output, cast_roles)
    if not path.exists():
        return None
    try:
        inference = BlueprintInference.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError:
        return None
    expected_hash = hashlib.sha256(brief.strip().encode()).hexdigest()
    settings = load_spatial_provider_settings()
    if (
        inference.brief_hash != expected_hash
        or inference.creative_seed != seed
        or inference.model != settings.model
        or inference.inference_config_hash != blueprint_inference_config_hash(settings)
        or inference.schema_version != BLUEPRINT_SCHEMA_VERSION
        or inference.system_prompt_hash != BLUEPRINT_SYSTEM_HASH
        or {
            profile.role for profile in inference.blueprint.characters.profiles
        }
        != set(cast_roles)
    ):
        return None
    return inference


async def generate_spatial_batch(
    brief: str,
    seed: int,
    *,
    refresh_blueprint: bool,
    scene_requests: tuple[SceneRequest, ...],
    output: Path,
) -> dict[str, object]:
    if not scene_requests:
        raise ValueError("spatial batch requires at least one scene request")
    unknown_casts = {
        request.cast_key
        for request in scene_requests
        if request.cast_key not in CASTS
    }
    if unknown_casts:
        raise ValueError(f"unknown cast configurations: {sorted(unknown_casts)}")
    cast_roles = tuple(
        role
        for role in PRESENTATION_ROLE_CODES
        if any(role in CASTS[request.cast_key] for request in scene_requests)
    )
    inference = (
        None
        if refresh_blueprint
        else cached_inference(brief, seed, output, cast_roles)
    )
    blueprint_cache_hit = inference is not None
    if inference is None:
        inference = await infer_creative_blueprint(brief, seed, cast_roles)
    output.mkdir(parents=True, exist_ok=True)
    (output / "blueprint-cache").mkdir(parents=True, exist_ok=True)
    cache_path = blueprint_cache_path(brief, seed, output, cast_roles)
    cache_path.write_text(
        inference.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "blueprint.json").write_text(
        inference.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    spatial_plans = []
    support_requirements = []
    for request in scene_requests:
        catalog = load_catalog(request.cast_key)
        spec = SceneSpec(
            request.scene_id,
            request.cast_key,
            request.family,
            request.variant,
            request.activity_id,
            request.viewpoint,
            request.shot_scale,
            "",
        )
        entry, activity = select_plan(catalog, spec)
        spatial_plans.append((request, spec, entry, activity, catalog))
        support_requirements.append(set(environment_supports(entry)))
    scene_inputs = sample_scene_layer_inputs(
        inference.blueprint,
        required_supports=support_requirements,
        seed=seed,
    )
    assignable_world_locations = len(
        maximum_location_assignment(
            inference.blueprint,
            support_requirements,
        )
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
    character_profiles = inference.blueprint.characters.profiles
    for (_, base_spec, entry, activity, catalog), layer_inputs in zip(
        spatial_plans,
        scene_inputs,
        strict=True,
    ):
        spec = base_spec._replace(setting_id=layer_inputs.setting.setting_id)
        fingerprint = plan_fingerprint(spec, entry, activity)
        geometry = compile_geometry(
            spec,
            entry,
            activity,
            character_profiles,
        )
        layers = compile_scene_layers(
            spec,
            entry,
            activity,
            fingerprint,
            geometry,
            layer_inputs.setting,
            layer_inputs.style,
            layer_inputs.presentation,
            character_profiles,
        )
        prompt = combine_prompt(geometry, layers)
        current_issues = [
            *layer_issues(layers, list(catalog.cast_roles)),
            *prompt_issues(
                spec,
                entry,
                activity,
                prompt,
                character_profiles,
            ),
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
                "coverage_mode": layer_inputs.presentation.coverage_mode,
                "role_wardrobes": {
                    role_style.role: role_style.wardrobe_theme
                    for role_style in layer_inputs.presentation.role_styles
                    if role_style.role in catalog.cast_roles
                },
                "role_footwear": {
                    role_style.role: role_style.footwear_theme
                    for role_style in layer_inputs.presentation.role_styles
                    if role_style.role in catalog.cast_roles
                },
                "role_accessories": {
                    role_style.role: role_style.accessory_theme
                    for role_style in layer_inputs.presentation.role_styles
                    if role_style.role in catalog.cast_roles
                },
                "expression_intensities": [
                    expression.intensity
                    for expression in layers.presentation.expressions
                ],
                "expression_gaze_targets": [
                    expression.gaze_target
                    for expression in layers.presentation.expressions
                ],
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
        "character_profiles": len(character_profiles),
        "character_ages": len(
            {profile.adult_age for profile in character_profiles}
        ),
        "character_height_weight_designs": len(
            {
                (profile.height_cm, profile.weight_kg)
                for profile in character_profiles
            }
        ),
        "character_faces": len(
            {profile.face_features for profile in character_profiles}
        ),
        "character_hair_designs": len(
            {
                (profile.hair_style, profile.hair_color)
                for profile in character_profiles
            }
        ),
        "character_intimate_designs": len(
            {profile.intimate_anatomy for profile in character_profiles}
        ),
        "cast_configurations": len({selection["cast_key"] for selection in selections}),
        "cast_distribution": {
            cast_key: sum(selection["cast_key"] == cast_key for selection in selections)
            for cast_key in sorted(
                {str(selection["cast_key"]) for selection in selections}
            )
        },
        "pose_families": len({selection["pose_family"] for selection in selections}),
        "activities": len({selection["activity_id"] for selection in selections}),
        "settings": len(
            {selection["setting_semantic_fingerprint"] for selection in selections}
        ),
        "world_locations": len(
            {selection["world_location"] for selection in selections}
        ),
        "assignable_world_locations": assignable_world_locations,
        "styles": len({selection["style_id"] for selection in selections}),
        "presentations": len(
            {selection["presentation_semantic_fingerprint"] for selection in selections}
        ),
        "camera_viewpoints": len(
            {selection["camera_viewpoint"] for selection in selections}
        ),
        "shot_scales": len({selection["shot_scale"] for selection in selections}),
        "shot_scale_distribution": {
            shot_scale: sum(
                selection["shot_scale"] == shot_scale for selection in selections
            )
            for shot_scale in sorted(
                {str(selection["shot_scale"]) for selection in selections}
            )
        },
        "styled_nude_scenes": sum(
            selection["coverage_mode"] == "styled_nude" for selection in selections
        ),
        "selective_access_scenes": sum(
            selection["coverage_mode"] == "selective_access" for selection in selections
        ),
        "wardrobe_styles": len(
            {
                wardrobe
                for selection in selections
                for wardrobe in selection["role_wardrobes"].values()
                if wardrobe != "none"
            }
        ),
        "footwear_styles": len(
            {
                footwear
                for selection in selections
                for footwear in selection["role_footwear"].values()
            }
        ),
        "accessory_styles": len(
            {
                accessory
                for selection in selections
                for accessories in selection["role_accessories"].values()
                for accessory in accessories
            }
        ),
        "presentation_mood_matches": sum(
            bool(
                set(layers.setting.mood_tags).intersection(
                    layers.presentation_source.compatible_moods
                )
            )
            for layers in resolved_layers
        ),
        "expression_intensities": len(
            {
                intensity
                for selection in selections
                for intensity in selection["expression_intensities"]
            }
        ),
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
        "scenes": len(scene_requests),
        "character_profiles": len(cast_roles),
        "character_ages": len(cast_roles),
        "character_height_weight_designs": len(cast_roles),
        "character_faces": len(cast_roles),
        "character_hair_designs": len(cast_roles),
        "character_intimate_designs": len(cast_roles),
        "cast_configurations": len({spec.cast_key for spec in scene_requests}),
        "pose_families": len({spec.family for spec in scene_requests}),
        "activities": len({spec.activity_id for spec in scene_requests}),
        "settings": len(scene_requests),
        "world_locations": min(6, assignable_world_locations),
        "styles": min(6, len(scene_requests)),
        "presentations": len(scene_requests),
        "camera_viewpoints": min(
            6,
            len({spec.viewpoint for spec in scene_requests}),
        ),
        "shot_scales": min(
            5,
            len({spec.shot_scale for spec in scene_requests}),
        ),
    }
    threshold_failures = {
        field: {"actual": metrics[field], "required": minimum}
        for field, minimum in thresholds.items()
        if metrics[field] < minimum
    }
    presentation_policy_issues = []
    if not 1 <= metrics["styled_nude_scenes"] <= max(1, len(prompts) // 4):
        presentation_policy_issues.append(
            "styled-nude scenes must remain between one and one quarter of the batch"
        )
    if any(
        len(accessories) < 2
        for selection in selections
        for accessories in selection["role_accessories"].values()
    ):
        presentation_policy_issues.append(
            "every role presentation must retain at least two accessories"
        )
    report: dict[str, object] = {
        "passed": not issues
        and not threshold_failures
        and not presentation_policy_issues,
        "creative_brief": brief,
        "creative_seed": seed,
        "blueprint_fingerprint": stable_hash(inference.blueprint),
        "blueprint_cache_key": cache_path.stem,
        "sampler_validation": sampler_validation,
        "metrics": metrics,
        "thresholds": thresholds,
        "threshold_failures": threshold_failures,
        "presentation_policy_issues": presentation_policy_issues,
        "prompt_issues": issues,
    }
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
    return report
