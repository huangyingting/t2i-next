from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import BaseModel, ValidationError

import t2i_spatial_pipeline.audit as spatial_audit
from t2i_spatial_pipeline.audit import run_spatial_audit
from t2i_spatial_pipeline.blueprint import (
    FORBIDDEN_STYLE_CONCEPTS,
    CharacterBlueprint,
    CharacterBlueprintOutput,
    PresentationBlueprint,
    PresentationBlueprintOutput,
    PresentationRecipe,
    RoleStylingRecipe,
    validate_forbidden_output_concepts,
    validate_output_concepts_with_pattern,
)
from t2i_spatial_pipeline.catalog import CASTS, cast_key_for_counts
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
from t2i_spatial_pipeline.service import (
    build_scene_requests,
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
        "\u201cquoted\u201d\u2014text\u2026"
    ) == '"quoted"-text...'


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


@pytest.mark.parametrize("cast_key", CASTS)
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
    assert {request.viewpoint for request in requests} == {
        "front_three_quarter",
        "high_three_quarter",
        "low_three_quarter",
        "overhead_three_quarter",
        "rear_three_quarter",
        "side_three_quarter",
    }
    assert len({request.shot_scale for request in requests}) == 5


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


@pytest.mark.parametrize("count", [0, 21])
def test_scene_request_count_must_fit_catalog_capacity(count: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 20"):
        build_scene_requests("one_woman_one_man", seed=42, count=count)


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
