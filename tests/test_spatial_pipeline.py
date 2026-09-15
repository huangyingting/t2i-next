from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import BaseModel, ValidationError

import t2i_spatial_pipeline.audit as spatial_audit
from t2i_spatial_pipeline.audit import run_spatial_audit
from t2i_spatial_pipeline.blueprint import (
    FORBIDDEN_STYLE_CONCEPTS,
    BlueprintSupportRealization,
    CharacterBlueprint,
    CharacterBlueprintOutput,
    LocationCard,
    PresentationBlueprint,
    PresentationBlueprintOutput,
    PresentationRecipe,
    RoleStylingRecipe,
    StyleBlueprint,
    StyleBlueprintOutput,
    StyleRecipe,
    WorldBlueprint,
    complete_style_mood_coverage,
    normalize_presentation_moods,
    normalize_world_mood_vocabulary,
    validate_forbidden_output_concepts,
    validate_output_concepts_with_pattern,
    validate_output_text,
)
from t2i_spatial_pipeline.catalog import CASTS, activity_ids, cast_key_for_counts
from t2i_spatial_pipeline.compiler import (
    SceneSpec,
    compile_geometry,
    distributed_contact_axis_clause,
    load_catalog,
    prompt_issues,
    select_plan,
)
from t2i_spatial_pipeline.config import load_spatial_provider_settings
from t2i_spatial_pipeline.layers import (
    CharacterProfile,
    layer_issues,
    make_scene_layer_inputs,
    resolve_scene_layers,
)
from t2i_spatial_pipeline.provider import normalize_ascii_punctuation
from t2i_spatial_pipeline.safety import (
    SUPPORTED_ACTIVITIES_BY_CAST,
    SUPPORTED_CASTS,
    SUPPORTED_POSE_FAMILIES,
    catalog_support_issues,
    symbolic_validation_metadata,
)
from t2i_spatial_pipeline.service import (
    BULK_BATCH_SIZE,
    build_scene_requests,
    build_spatial_bulk_plan,
    publish_prompt_batch,
)


def character_profiles() -> list[CharacterProfile]:
    return [
        CharacterProfile(
            role="f1",
            adult_age=26,
            nationality="Chinese",
            height_cm=158,
            weight_kg=48,
            body_build="petite and softly toned",
            body_proportions="narrow shoulders and rounded hips",
            skin_tone="warm ivory",
            face_features="heart-shaped face with almond eyes",
            hair_style="long layered waves",
            hair_color="blue-black",
            intimate_anatomy="compact vulva with symmetrical labia",
            pubic_hair="neatly trimmed triangle",
        ),
        CharacterProfile(
            role="f2",
            adult_age=29,
            nationality="Chinese",
            height_cm=166,
            weight_kg=57,
            body_build="athletic and lean",
            body_proportions="broad shoulders and long legs",
            skin_tone="neutral beige",
            face_features="oval face with high cheekbones",
            hair_style="shoulder-length blunt bob",
            hair_color="chestnut brown",
            intimate_anatomy="full vulva with softly defined outer labia",
            pubic_hair="closely groomed strip",
        ),
        CharacterProfile(
            role="f3",
            adult_age=33,
            nationality="Chinese",
            height_cm=173,
            weight_kg=68,
            body_build="softly curvy",
            body_proportions="full bust and broad hips",
            skin_tone="golden tan",
            face_features="angular face with hooded eyes",
            hair_style="waist-length straight hair",
            hair_color="copper red",
            intimate_anatomy="defined vulva with prominent inner labia",
            pubic_hair="natural groomed patch",
        ),
        CharacterProfile(
            role="m1",
            adult_age=31,
            nationality="Chinese",
            height_cm=181,
            weight_kg=79,
            body_build="lean muscular",
            body_proportions="wide shoulders and narrow waist",
            skin_tone="warm bronze",
            face_features="square jaw with deep-set eyes",
            hair_style="short textured crop",
            hair_color="jet black",
            intimate_anatomy="proportional penis with defined scrotum",
            pubic_hair="closely trimmed",
        ),
        CharacterProfile(
            role="m2",
            adult_age=37,
            nationality="Chinese",
            height_cm=188,
            weight_kg=94,
            body_build="heavy muscular",
            body_proportions="thick torso and powerful legs",
            skin_tone="deep olive",
            face_features="long face with straight brows",
            hair_style="slicked-back undercut",
            hair_color="dark brown",
            intimate_anatomy="thick penis with low rounded scrotum",
            pubic_hair="natural short growth",
        ),
    ]


def test_character_blueprint_accepts_only_required_roles_in_any_order() -> None:
    profiles = character_profiles()

    blueprint = CharacterBlueprint(
        profiles=[profiles[3], profiles[0], profiles[4]]
    )

    assert {profile.role for profile in blueprint.profiles} == {
        "f1",
        "m1",
        "m2",
    }


def test_character_blueprint_rejects_reused_age_design() -> None:
    profiles = character_profiles()
    profiles[1] = profiles[1].model_copy(
        update={"adult_age": profiles[0].adult_age}
    )

    with pytest.raises(ValidationError, match="character ages"):
        CharacterBlueprint(profiles=profiles)


def test_character_output_rejects_non_ascii_text_for_structured_repair() -> None:
    profiles = character_profiles()[:1]
    profiles[0] = profiles[0].model_copy(update={"nationality": "中国"})

    with pytest.raises(ValidationError, match=r"U\+4E2D"):
        CharacterBlueprintOutput(
            characters=CharacterBlueprint(profiles=profiles)
        )


def test_character_output_rejects_roles_outside_request_context() -> None:
    profiles = character_profiles()

    with pytest.raises(ValidationError, match="requested cast roles"):
        CharacterBlueprintOutput.model_validate(
            {"characters": {"profiles": [profiles[0], profiles[3], profiles[4]]}},
            context={"cast_roles": ("f1", "m1")},
        )


def test_multi_character_layers_keep_people_and_styling_distinct() -> None:
    profiles = character_profiles()
    inputs = make_scene_layer_inputs(
        "editorial_suite",
        "private editorial suite",
        "warm practical sconces",
        "rich neutral palette",
        "intimate editorial atmosphere",
    )

    layers = resolve_scene_layers(
        scene_id="S01",
        spatial_fingerprint="a" * 64,
        geometry="Geometry.",
        cast_roles=["f1", "m1", "m2"],
        character_profiles=profiles,
        body_level="floor",
        setting=inputs.setting,
        style=inputs.style,
        presentation_source=inputs.presentation,
        required_environment_supports=[],
        required_regions_by_role={"f1": [], "m1": [], "m2": []},
        visible_regions_by_role={"f1": [], "m1": [], "m2": []},
        interaction_partners_by_role={
            "f1": ["m1"],
            "m1": ["f1"],
            "m2": ["f1"],
        },
    )

    presentations = layers.presentation.roles
    assert not layer_issues(layers, ["f1", "m1", "m2"])
    assert len({item.wardrobe for item in presentations}) == 3
    assert len({item.footwear for item in presentations}) == 3
    assert len({tuple(item.accessories) for item in presentations}) == 3
    assert "F1 is 158 cm and 48 kg" in layers.compact_suffix
    assert "M1 is 181 cm and 79 kg" in layers.compact_suffix
    assert "M2 is 188 cm and 94 kg" in layers.compact_suffix


def test_role_coverage_can_mix_nudity_and_clothing_in_one_scene() -> None:
    profiles = character_profiles()
    inputs = make_scene_layer_inputs(
        "mixed_suite",
        "private editorial suite",
        "warm practical sconces",
        "rich neutral palette",
        "intimate editorial atmosphere",
    )
    role_styles = [
        style.model_copy(
            update={
                "coverage_mode": "styled_nude",
                "wardrobe_theme": "none",
            }
        )
        if style.role == "m1"
        else style
        for style in inputs.presentation.role_styles
    ]
    presentation = inputs.presentation.model_copy(
        update={"role_styles": role_styles}
    )

    layers = resolve_scene_layers(
        scene_id="S02",
        spatial_fingerprint="b" * 64,
        geometry="Geometry.",
        cast_roles=["f1", "m1"],
        character_profiles=profiles,
        body_level="floor",
        setting=inputs.setting,
        style=inputs.style,
        presentation_source=presentation,
        required_environment_supports=[],
        required_regions_by_role={"f1": [], "m1": []},
        visible_regions_by_role={"f1": [], "m1": []},
        interaction_partners_by_role={"f1": ["m1"], "m1": ["f1"]},
    )

    states = {
        role.role: role.wardrobe_state for role in layers.presentation.roles
    }
    assert states == {"f1": "fully_dressed", "m1": "styled_nude"}
    assert "F1 remains visibly dressed" in layers.compact_suffix
    assert "M1 is intentionally fully nude" in layers.compact_suffix


def test_provider_normalizes_typographic_punctuation_to_ascii() -> None:
    assert normalize_ascii_punctuation(
        "\u201cquoted\u201d\u2014caf\u00e9\u2026"
    ) == '"quoted"-cafe...'
    assert normalize_ascii_punctuation("\u4e2d\u6587") == "\u4e2d\u6587"


def test_forbidden_output_concepts_report_their_field_path() -> None:
    class Output(BaseModel):
        material: str

    with pytest.raises(ValueError, match="material: mirror"):
        validate_forbidden_output_concepts(
            Output(material="polished mirror panels"),
            "world blueprint",
        )


def test_style_material_can_use_mirror_as_an_adjective() -> None:
    class Output(BaseModel):
        material: str

    validate_output_concepts_with_pattern(
        Output(material="mirror-polished obsidian"),
        "style blueprint",
        FORBIDDEN_STYLE_CONCEPTS,
    )


def test_world_material_can_use_structural_framing() -> None:
    class Output(BaseModel):
        material: str

    validate_forbidden_output_concepts(
        Output(material="blackened steel framing"),
        "world blueprint",
    )


def test_world_requires_sling_and_wall_in_one_location() -> None:
    def location(
        index: int,
        supports: tuple[str, ...],
    ) -> LocationCard:
        return LocationCard(
            location_id=f"location_{index}",
            location=f"Audit location number {index}",
            architecture="Plain enclosed audit room",
            materials=["wood", "stone"],
            environment_props=["table"],
            light_sources=["ceiling lamp"],
            support_realizations=[
                BlueprintSupportRealization(
                    support=support,
                    description=(
                        "adult body-support sling"
                        if support == "support_sling"
                        else f"physical {support.replace('_', ' ')}"
                    ),
                )
                for support in supports
            ],
            mood_tags=["neutral"],
        )

    with pytest.raises(
        ValidationError,
        match=r"support_sling.*wall",
    ):
        WorldBlueprint(
            family_id="audit_world",
            world_genre="audit_genre",
            era="1930s",
            locations=[
                location(1, ("bed", "bed_edge")),
                location(2, ("chair", "floor", "furniture")),
                location(3, ("sofa", "bed")),
                location(4, ("support_sling", "chair")),
                location(5, ("wall", "floor")),
                location(6, ("sofa", "furniture")),
            ],
            time_options=["day", "night"],
            weather_options=["clear"],
        )


def test_support_sling_must_be_body_bearing() -> None:
    with pytest.raises(ValidationError, match="adult body-support"):
        BlueprintSupportRealization(
            support="support_sling",
            description="canvas sling holding damp paper rolls",
        )


@pytest.mark.parametrize(
    "cast_key",
    CASTS,
)
def test_twenty_scene_requests_are_unique_and_diverse(cast_key: str) -> None:
    requests = build_scene_requests(cast_key, seed=42, count=20)

    assert len(requests) == 20
    assert len({request.scene_id for request in requests}) == 20
    assert len(
        {
            (request.family, request.variant)
            for request in requests
        }
    ) == 20
    assert len({request.activity_id for request in requests}) >= 8
    assert len({request.family for request in requests}) == 20
    assert all(
        not catalog_support_issues(
            request.cast_key,
            request.family,
            request.activity_id,
        )
        for request in requests
    )
    assert {request.viewpoint for request in requests} == {
        "front_three_quarter",
        "high_three_quarter",
        "low_three_quarter",
        "overhead_three_quarter",
        "rear_three_quarter",
        "side_three_quarter",
    }
    assert len({request.shot_scale for request in requests}) == 5


@pytest.mark.parametrize("cast_key", ("one_woman_two_men", "three_women"))
def test_group_casts_remain_available(cast_key: str) -> None:
    requests = build_scene_requests(cast_key, seed=42, count=20)

    assert len(requests) == 20
    assert {request.cast_key for request in requests} == {cast_key}


def test_symbolic_validation_metadata_requires_render_review() -> None:
    metadata = symbolic_validation_metadata()

    assert metadata == {
        "validation_status": "symbolic_only",
        "visual_validation": False,
        "requires_render_review": True,
        "production_policy": "full_catalog_symbolic_only",
        "safety_policy_version": 2,
    }


def test_safety_policy_exposes_every_catalog_category() -> None:
    assert SUPPORTED_CASTS == frozenset(CASTS)
    assert len(SUPPORTED_POSE_FAMILIES) == 24
    assert all(
        SUPPORTED_ACTIVITIES_BY_CAST[cast_key]
        == frozenset(activity_ids(cast_key))
        and len(SUPPORTED_ACTIVITIES_BY_CAST[cast_key]) == 32
        for cast_key in CASTS
    )
    assert catalog_support_issues(
        "one_woman_one_man",
        "lifted_supported",
        "mutual_oral",
    ) == []
    assert catalog_support_issues(
        "unsupported_cast",
        "supine",
        "manual_clitoral",
    ) == ["cast is not present in the spatial catalog"]
    for cast_key in CASTS:
        catalog = load_catalog(cast_key)
        reachable = {
            activity_id
            for entry in catalog.entries
            for activity_id in entry.compatible_activity_ids
        }
        assert reachable == set(activity_ids(cast_key))


def test_spatial_audit_resumes_from_atomic_seed_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    progress_path = tmp_path / "audit-progress.json"
    original_build = spatial_audit.build_scene_requests
    interrupted_calls = 0

    def interrupt_second_seed(*args, **kwargs):
        nonlocal interrupted_calls
        interrupted_calls += 1
        if interrupted_calls == 2:
            raise RuntimeError("simulated interruption")
        return original_build(*args, **kwargs)

    monkeypatch.setattr(
        spatial_audit,
        "build_scene_requests",
        interrupt_second_seed,
    )
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_spatial_audit(
            progress_path,
            seed_count=3,
            cast_keys=("one_woman",),
        )

    checkpoint = json.loads(progress_path.read_text(encoding="utf-8"))
    assert checkpoint["casts"]["one_woman"]["completed_seeds"] == 1
    assert "simulated interruption" in checkpoint["last_error"]

    resumed_calls = 0

    def count_resumed_seeds(*args, **kwargs):
        nonlocal resumed_calls
        resumed_calls += 1
        return original_build(*args, **kwargs)

    monkeypatch.setattr(
        spatial_audit,
        "build_scene_requests",
        count_resumed_seeds,
    )
    progress = run_spatial_audit(
        progress_path,
        seed_count=3,
        cast_keys=("one_woman",),
    )

    assert progress.complete is True
    assert progress.casts["one_woman"].completed_seeds == 3
    assert progress.last_error is None
    assert resumed_calls == 2


def test_spatial_audit_rejects_checkpoint_for_different_options(tmp_path) -> None:
    progress_path = tmp_path / "audit-progress.json"
    run_spatial_audit(
        progress_path,
        seed_count=1,
        cast_keys=("one_woman",),
    )

    with pytest.raises(ValueError, match="use --restart"):
        run_spatial_audit(
            progress_path,
            seed_count=2,
            cast_keys=("one_woman",),
        )


def test_prompt_audit_matches_the_exact_secondary_contact_sentence() -> None:
    catalog = load_catalog("one_woman")
    spec = SceneSpec(
        scene_id="S01",
        cast_key="one_woman",
        family="sling_reclined",
        variant="knees_wide_arms_outward",
        activity_id="dual_manual",
        viewpoint="high_three_quarter",
        shot_scale="full_body",
        setting_id="audit_setting",
    )
    entry, activity = select_plan(catalog, spec)
    profiles = character_profiles()
    prompt = compile_geometry(spec, entry, activity, profiles)

    assert prompt_issues(spec, entry, activity, prompt, profiles) == []


def test_handheld_prop_keeps_anatomical_endpoint_ownership() -> None:
    catalog = load_catalog("one_woman_one_man")
    spec = SceneSpec(
        scene_id="S01",
        cast_key="one_woman_one_man",
        family="side_lying_open",
        variant="scissor_split_lower_arm_forward",
        activity_id="dual_toy",
        viewpoint="side_three_quarter",
        shot_scale="medium_wide",
        setting_id="audit_setting",
    )
    entry, activity = select_plan(catalog, spec)
    profiles = character_profiles()
    prompt = compile_geometry(spec, entry, activity, profiles)

    assert (
        "The secondary anatomical endpoint is rooted at M1's pelvis"
        in prompt
    )
    assert prompt_issues(spec, entry, activity, prompt, profiles) == []


def test_mutual_oral_compiles_one_continuous_reciprocal_body_axis() -> None:
    catalog = load_catalog("one_woman_one_man")
    spec = SceneSpec(
        scene_id="S01",
        cast_key="one_woman_one_man",
        family="side_lying_right",
        variant="fetal_tuck_arms_folded",
        activity_id="mutual_oral",
        viewpoint="side_three_quarter",
        shot_scale="medium_wide",
        setting_id="audit_setting",
    )
    entry, activity = select_plan(catalog, spec)
    profiles = character_profiles()
    prompt = compile_geometry(spec, entry, activity, profiles)
    body_axis = distributed_contact_axis_clause(
        entry,
        activity,
        spec.cast_key,
    )

    assert body_axis is not None
    assert body_axis in prompt
    assert prompt_issues(spec, entry, activity, prompt, profiles) == []


@pytest.mark.parametrize(
    ("family", "variant", "activity_id", "expected_chain"),
    [
        (
            "side_lying_right",
            "top_leg_bent_lower_arm_forward",
            "edging_manual",
            "F1 lies on her right side",
        ),
        (
            "side_lying_open",
            "top_leg_raised_upper_arm_overhead",
            "vaginal_face_to_face",
            "M1, the man, forms one continuous body at the penetration axis",
        ),
        (
            "supine",
            "knees_to_chest_hands_on_thighs",
            "cunnilingus",
            "M1, the man, lowers the head attached through the neck",
        ),
        (
            "supine_hips_raised",
            "knees_high_wide_arms_overhead",
            "wrist_bondage_oral",
            "M1, the man, forms one continuous recipient body",
        ),
    ],
)
def test_image_regression_scenes_lock_continuous_body_chains(
    family: str,
    variant: str,
    activity_id: str,
    expected_chain: str,
) -> None:
    catalog = load_catalog("one_woman_one_man")
    spec = SceneSpec(
        scene_id="S01",
        cast_key="one_woman_one_man",
        family=family,
        variant=variant,
        activity_id=activity_id,
        viewpoint="high_three_quarter",
        shot_scale="medium",
        setting_id="audit_setting",
    )
    entry, activity = select_plan(catalog, spec)
    profiles = character_profiles()
    prompt = compile_geometry(spec, entry, activity, profiles)

    assert expected_chain in prompt
    assert {
        "headless",
        "duplicate",
        "detached",
        "extra body",
        "partial body",
    }.isdisjoint(prompt.lower().split())
    assert prompt_issues(spec, entry, activity, prompt, profiles) == []


def test_world_mood_vocabulary_is_normalized_to_twelve_tags() -> None:
    support_sets = (
        ("bed", "bed_edge"),
        ("chair", "floor", "furniture"),
        ("sofa", "bed"),
        ("support_sling", "wall"),
        ("floor", "furniture"),
        ("sofa", "chair"),
    )
    locations = []
    for index, supports in enumerate(support_sets):
        locations.append(
            LocationCard(
                location_id=f"location_{index}",
                location=f"Audit location number {index}",
                architecture="Plain enclosed audit room",
                materials=["wood", "stone"],
                environment_props=["table"],
                light_sources=["ceiling lamp"],
                support_realizations=[
                    BlueprintSupportRealization(
                        support=support,
                        description=(
                            "adult body-support sling"
                            if support == "support_sling"
                            else f"physical {support.replace('_', ' ')}"
                        ),
                    )
                    for support in supports
                ],
                mood_tags=[
                    f"primary_{index}",
                    f"secondary_{index}",
                    f"tertiary_{index}",
                ],
            )
        )
    world = WorldBlueprint.model_validate(
        {
            "family_id": "audit_world",
            "world_genre": "audit_genre",
            "era": "current",
            "locations": [
                location.model_dump(mode="json") for location in locations
            ],
            "time_options": ["day", "night"],
            "weather_options": ["clear"],
        },
        context={"normalize_mood_vocabulary": True},
    )

    normalized = normalize_world_mood_vocabulary(world)

    WorldBlueprint.model_validate(normalized.model_dump(mode="json"))
    assert len(
        {
            mood
            for location in normalized.locations
            for mood in location.mood_tags
        }
    ) == 12
    assert all(location.mood_tags for location in normalized.locations)


def test_pair_catalog_uses_only_explicit_mutual_manual_names() -> None:
    catalog = load_catalog("one_woman_one_man")
    activity_ids = {activity.activity_id for activity in catalog.activities}

    assert {
        "mutual_manual_side_by_side",
        "mutual_manual_face_to_face",
        "mutual_manual_seated",
    }.issubset(activity_ids)
    assert {
        "mirror_mutual",
        "shower_mutual",
        "chair_mutual",
    }.isdisjoint(activity_ids)


def test_pair_self_stimulation_keeps_contact_paths_separate() -> None:
    catalog = load_catalog("one_woman_one_man")
    spec = SceneSpec(
        scene_id="S01",
        cast_key="one_woman_one_man",
        family="sling_reclined",
        variant="legs_in_v_arms_beside",
        activity_id="mutual_manual_face_to_face",
        viewpoint="overhead_three_quarter",
        shot_scale="full_body",
        setting_id="audit_setting",
    )
    entry, activity = select_plan(catalog, spec)
    profiles = character_profiles()
    prompt = compile_geometry(spec, entry, activity, profiles)

    assert "separate self-directed contact paths" in prompt
    assert "F1's hand stays on F1's clitoral area" in prompt
    assert "M1's hand stays on M1's penis" in prompt
    assert "mutual manual stimulation" not in prompt
    assert prompt_issues(spec, entry, activity, prompt, profiles) == []


@pytest.mark.parametrize("count", [0, 21])
def test_scene_request_count_must_fit_catalog_capacity(count: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 20"):
        build_scene_requests("one_woman_one_man", seed=42, count=count)


def test_bulk_plan_covers_five_categories_with_shared_blueprints() -> None:
    plan = build_spatial_bulk_plan(12345, 600)

    assert BULK_BATCH_SIZE == 20
    assert len(plan) == 150
    assert len({batch.spatial_seed for batch in plan}) == 150
    assert len({batch.blueprint_seed for batch in plan}) == 5
    for cast_key in CASTS:
        cast_batches = [batch for batch in plan if batch.cast_key == cast_key]
        assert len(cast_batches) == 30
        assert sum(batch.scene_count for batch in cast_batches) == 600
        assert len({batch.blueprint_seed for batch in cast_batches}) == 1


def test_bulk_plan_supports_a_partial_final_batch() -> None:
    plan = build_spatial_bulk_plan(
        12345,
        21,
        cast_keys=("one_woman",),
    )

    assert [batch.scene_count for batch in plan] == [20, 1]


@pytest.mark.parametrize(
    ("female_count", "male_count", "cast_key"),
    [
        (1, 0, "one_woman"),
        (1, 1, "one_woman_one_man"),
        (1, 2, "one_woman_two_men"),
        (2, 0, "two_women"),
        (3, 0, "three_women"),
    ],
)
def test_cast_key_is_resolved_from_people_counts(
    female_count: int,
    male_count: int,
    cast_key: str,
) -> None:
    assert cast_key_for_counts(female_count, male_count) == cast_key


def test_unsupported_people_counts_are_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported spatial cast counts"):
        cast_key_for_counts(2, 1)


def test_presentation_output_requires_requested_scene_count() -> None:
    role_style = RoleStylingRecipe(
        role="f1",
        coverage_mode="selective_access",
        wardrobe="silk evening dress",
        footwear_type="heels",
        footwear_details="black lacquered",
        accessories=["jade earrings", "silver bracelet"],
        makeup_and_grooming="precise period makeup",
    )
    presentation = PresentationBlueprint(
        recipes=[
            PresentationRecipe(
                presentation_id="look_one",
                role_styles=[role_style],
                compatible_moods=["restrained"],
            )
        ]
    )

    with pytest.raises(ValidationError, match="requested scene count"):
        PresentationBlueprintOutput.model_validate(
            {"presentation": presentation.model_dump()},
            context={
                "cast_roles": ("f1",),
                "scene_count": 2,
                "allowed_mood_tags": ("restrained",),
            },
        )


def test_style_output_must_cover_every_world_mood() -> None:
    recipes = [
        StyleRecipe(
            style_id=f"style_{index}",
            medium="period photography",
            rendering_language="documentary realism",
            surface_texture="fine film grain",
            contrast="moderate",
            color_treatment="neutral monochrome",
            lighting_treatment="soft practical light",
            atmosphere="restrained observation",
            compatible_moods=["neutral"],
        )
        for index in range(6)
    ]

    with pytest.raises(ValidationError, match="does not cover mood tags"):
        StyleBlueprintOutput.model_validate(
            {"style": StyleBlueprint(recipes=recipes).model_dump()},
            context={"allowed_mood_tags": ("neutral", "tense")},
        )


def test_missing_style_moods_can_be_completed_locally() -> None:
    recipes = [
        StyleRecipe(
            style_id=f"style_{index}",
            medium="period photography",
            rendering_language="documentary realism",
            surface_texture="fine film grain",
            contrast="moderate",
            color_treatment="neutral monochrome",
            lighting_treatment="soft practical light",
            atmosphere="restrained observation",
            compatible_moods=["neutral"],
        )
        for index in range(6)
    ]

    style = complete_style_mood_coverage(
        StyleBlueprint(recipes=recipes),
        ("neutral", "tense"),
    )

    StyleBlueprintOutput.model_validate(
        {"style": style.model_dump()},
        context={"allowed_mood_tags": ("neutral", "tense")},
    )
    assert {
        mood
        for recipe in style.recipes
        for mood in recipe.compatible_moods
    } == {"neutral", "tense"}


def test_presentation_moods_are_normalized_to_world_enum() -> None:
    presentation = PresentationBlueprint(
        recipes=[
            PresentationRecipe(
                presentation_id="presentation_1",
                role_styles=[
                    RoleStylingRecipe(
                        role="f1",
                        coverage_mode="styled_nude",
                        wardrobe="none",
                        footwear_type="heels",
                        footwear_details="black leather",
                        accessories=[],
                        makeup_and_grooming="restrained period styling",
                    )
                ],
                compatible_moods=["invented"],
            )
        ]
    )

    normalized = normalize_presentation_moods(
        presentation,
        ("opulent", "tense"),
    )

    PresentationBlueprintOutput.model_validate(
        {"presentation": normalized.model_dump()},
        context={
            "cast_roles": ("f1",),
            "scene_count": 1,
            "allowed_mood_tags": ("opulent", "tense"),
        },
    )
    assert normalized.recipes[0].compatible_moods == ["opulent"]


def test_minor_as_tonal_adjective_is_not_treated_as_an_age_concept() -> None:
    class TextValue(BaseModel):
        value: str

    validate_output_text(
        TextValue(value="minor tonal variation"),
        "style blueprint",
    )
    with pytest.raises(ValueError, match="minor concepts"):
        validate_output_text(
            TextValue(value="minors in the scene"),
            "style blueprint",
        )


def clear_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for suffix in (
        "BASE_URL",
        "API_KEY_ENV",
        "AUTH_MODE",
        "MODEL",
        "THINKING_MODE",
        "REASONING_EFFORT",
        "TEMPERATURE",
        "OUTPUT_TOKEN_LIMIT",
        "TIMEOUT_SECONDS",
        "TRANSPORT_RETRIES",
    ):
        monkeypatch.delenv(f"OPENAI_{suffix}", raising=False)


def test_spatial_settings_reuse_shared_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    clear_provider_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://shared.example/v1")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.6")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "high")

    settings = load_spatial_provider_settings()

    assert settings.model == "shared-model"
    assert settings.base_url == "https://shared.example/v1"
    assert settings.temperature == 0.6
    assert settings.reasoning_effort == "high"
    assert settings.thinking_mode is None


def test_spatial_prompts_publish_with_story_directory_convention(
    tmp_path,
) -> None:
    first = publish_prompt_batch(
        ["first prompt", "second prompt"],
        semantic_name="republican_social_satire",
        cast_key="one_woman_one_man",
        prompts_directory=tmp_path / "prompts",
        published_on=date(2026, 9, 15),
    )
    second = publish_prompt_batch(
        ["third prompt"],
        semantic_name="republican_social_satire",
        cast_key="one_woman_one_man",
        prompts_directory=tmp_path / "prompts",
        published_on=date(2026, 9, 15),
    )

    assert first == (
        tmp_path
        / "prompts"
        / "2026-09-15"
        / "hardcore"
        / "republican_social_satire_hardcore_1_woman_1_man_0001.txt"
    )
    assert second.name.endswith("_0002.txt")
    assert first.read_text(encoding="utf-8") == (
        "first prompt\nsecond prompt\n"
    )
