from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from t2i_spatial_prompt.blueprint import (
    FORBIDDEN_STYLE_CONCEPTS,
    CharacterBlueprint,
    CharacterBlueprintOutput,
    validate_forbidden_output_concepts,
    validate_output_concepts_with_pattern,
)
from t2i_spatial_prompt.layers import (
    CharacterProfile,
    layer_issues,
    make_scene_layer_inputs,
    resolve_scene_layers,
)
from t2i_spatial_prompt.provider import normalize_ascii_punctuation


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
