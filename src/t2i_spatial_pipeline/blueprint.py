from __future__ import annotations

import asyncio
import hashlib
import random
import re
from collections.abc import Sequence
from itertools import combinations, product
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    model_validator,
)

from .config import SpatialProviderSettings, load_spatial_provider_settings
from .layers import (
    PRESENTATION_ROLE_CODES,
    CharacterProfile,
    PresentationPreset,
    RoleStylingPreset,
    SceneLayerInputs,
    SettingPreset,
    StylePreset,
    SupportRealization,
    stable_hash,
)
from .provider import OpenAISpatialModel, generate_with_repair

Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
ShortPhrase = Annotated[str, StringConstraints(min_length=2, max_length=60)]
SUPPORTED_SURFACES = {
    "bed",
    "bed_edge",
    "chair",
    "floor",
    "furniture",
    "sofa",
    "support_sling",
    "wall",
}
PRODUCTION_SUPPORT_SURFACES = SUPPORTED_SURFACES
SupportSurface = Literal[
    "bed",
    "bed_edge",
    "chair",
    "floor",
    "furniture",
    "sofa",
    "support_sling",
    "wall",
]
PROHIBITED_MINOR_PATTERN = (
    r"child|children|minors|minor[-\s]+aged|teens?|teenage|teenaged|teenagers?|schoolgirls?|"
    r"schoolboys?|juveniles?|high\s+school|middle\s+school|primary\s+school"
)
PROHIBITED_MINOR_CONCEPTS = re.compile(
    rf"\b(?:{PROHIBITED_MINOR_PATTERN})\b",
    re.I,
)
FORBIDDEN_CREATIVE_CONCEPTS = re.compile(
    r"\b(?:woman|man|person|people|crowd|attendant|guard|servant|"
    r"anatomy|pose|intercourse|fellatio|cunnilingus|masturbation|"
    r"penis|vagina|vulva|anus|breast|clitoris|camera|lens|framing|viewpoint|"
    r"mirror|statue|mannequin|" + PROHIBITED_MINOR_PATTERN + r")\b",
    re.I,
)
FORBIDDEN_STYLE_CONCEPTS = re.compile(
    r"\b(?:woman|man|person|people|crowd|attendant|guard|servant|"
    r"anatomy|pose|intercourse|fellatio|cunnilingus|masturbation|"
    r"penis|vagina|vulva|anus|breast|clitoris|"
    + PROHIBITED_MINOR_PATTERN
    + r")\b",
    re.I,
)
FORBIDDEN_PRESENTATION_CONCEPTS = re.compile(r"\b(?:mirror|mannequin|statue)\b", re.I)
INCOMPLETE_TEXT_END = re.compile(
    r"(?:\b(?:a|an|the|and|or|but|with|without|over|under|on|in|at|to|"
    r"from|for|of)|[,(;/:-])\s*$",
    re.I,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlueprintSupportRealization(StrictModel):
    support: SupportSurface
    description: str = Field(min_length=3, max_length=80)


class LocationCard(StrictModel):
    location_id: Identifier
    location: str = Field(min_length=8, max_length=100)
    architecture: str = Field(min_length=5, max_length=100)
    materials: list[str] = Field(min_length=2, max_length=5)
    environment_props: list[str] = Field(min_length=1, max_length=5)
    light_sources: list[str] = Field(min_length=1, max_length=3)
    support_realizations: list[BlueprintSupportRealization] = Field(
        min_length=2,
        max_length=9,
    )
    mood_tags: list[Identifier] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def supports_are_known_and_unique(self) -> LocationCard:
        support_ids = [item.support for item in self.support_realizations]
        unknown = set(support_ids).difference(SUPPORTED_SURFACES)
        if unknown:
            raise ValueError(f"location has unknown supports: {sorted(unknown)}")
        ensure_unique("support realizations", support_ids)
        ensure_unique("mood_tags", self.mood_tags)
        return self


class WorldBlueprint(StrictModel):
    family_id: Identifier
    world_genre: Identifier
    era: Identifier
    locations: list[LocationCard] = Field(min_length=6, max_length=12)
    time_options: list[Identifier] = Field(min_length=2, max_length=6)
    weather_options: list[Identifier] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def locations_cover_support_ontology(self) -> WorldBlueprint:
        ensure_unique("location IDs", [item.location_id for item in self.locations])
        ensure_unique("time options", self.time_options)
        ensure_unique("weather options", self.weather_options)
        coverage = {
            support: sum(
                support in {item.support for item in location.support_realizations}
                for location in self.locations
            )
            for support in PRODUCTION_SUPPORT_SURFACES
        }
        insufficient = {
            support: count for support, count in coverage.items() if count < 1
        }
        if insufficient:
            raise ValueError(
                f"world locations have insufficient support coverage: {insufficient}"
            )
        compound_requirements = (
            {"floor", "furniture"},
            {"support_sling", "wall"},
        )
        missing_compounds = [
            sorted(requirement)
            for requirement in compound_requirements
            if not any(
                requirement.issubset(
                    {item.support for item in location.support_realizations}
                )
                for location in self.locations
            )
        ]
        if missing_compounds:
            raise ValueError(
                f"world locations lack compound support coverage: {missing_compounds}"
            )
        return self


class StyleRecipe(StrictModel):
    style_id: Identifier
    medium: str = Field(min_length=5, max_length=60)
    rendering_language: str = Field(min_length=5, max_length=70)
    surface_texture: str = Field(min_length=5, max_length=70)
    contrast: str = Field(min_length=3, max_length=50)
    color_treatment: str = Field(min_length=5, max_length=70)
    lighting_treatment: str = Field(min_length=5, max_length=70)
    atmosphere: str = Field(min_length=5, max_length=70)
    compatible_moods: list[Identifier] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def moods_are_unique(self) -> StyleRecipe:
        ensure_unique("compatible moods", self.compatible_moods)
        return self


class StyleBlueprint(StrictModel):
    recipes: list[StyleRecipe] = Field(min_length=6, max_length=12)

    @model_validator(mode="after")
    def recipes_are_unique(self) -> StyleBlueprint:
        ensure_unique("style IDs", [item.style_id for item in self.recipes])
        return self


def complete_style_mood_coverage(
    style: StyleBlueprint,
    allowed_moods: Sequence[str],
) -> StyleBlueprint:
    mood_lists = [list(recipe.compatible_moods) for recipe in style.recipes]
    used_moods = {mood for moods in mood_lists for mood in moods}
    missing_moods = sorted(set(allowed_moods).difference(used_moods))
    cursor = 0
    for mood in missing_moods:
        for offset in range(len(mood_lists)):
            index = (cursor + offset) % len(mood_lists)
            if len(mood_lists[index]) < 6:
                mood_lists[index].append(mood)
                cursor = (index + 1) % len(mood_lists)
                break
        else:
            raise ValueError(
                "style recipes lack capacity for complete mood coverage"
            )
    return StyleBlueprint(
        recipes=[
            recipe.model_copy(update={"compatible_moods": mood_lists[index]})
            for index, recipe in enumerate(style.recipes)
        ]
    )


class RoleStylingRecipe(StrictModel):
    role: Literal["f1", "f2", "f3", "m1", "m2"]
    coverage_mode: Literal["selective_access", "styled_nude"]
    wardrobe: str = Field(min_length=4, max_length=100)
    footwear_type: Literal[
        "boots",
        "heels",
        "sandals",
        "shoes",
        "slippers",
        "pumps",
        "mules",
        "sneakers",
        "loafers",
        "platforms",
    ]
    footwear_details: str = Field(min_length=3, max_length=60)
    accessories: list[ShortPhrase] = Field(default_factory=list, max_length=2)
    makeup_and_grooming: str = Field(min_length=3, max_length=80)

    @model_validator(mode="after")
    def styling_components_are_unique(self) -> RoleStylingRecipe:
        normalized_wardrobe = self.wardrobe.strip().lower()
        if (
            self.coverage_mode == "selective_access"
            and normalized_wardrobe == "none"
        ):
            raise ValueError("selective-access role styling requires a wardrobe")
        if (
            self.coverage_mode == "styled_nude"
            and normalized_wardrobe != "none"
        ):
            raise ValueError("styled-nude role styling wardrobe must be none")
        ensure_unique("role styling accessories", self.accessories)
        return self


class PresentationRecipe(StrictModel):
    presentation_id: Identifier
    role_styles: list[RoleStylingRecipe] = Field(min_length=1, max_length=5)
    compatible_moods: list[Identifier] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def recipe_is_coherent(self) -> PresentationRecipe:
        roles = [style.role for style in self.role_styles]
        if len(set(roles)) != len(roles):
            raise ValueError("role styles contain duplicate roles")
        wardrobes = [style.wardrobe for style in self.role_styles]
        dressed_wardrobes = [
            wardrobe
            for wardrobe in wardrobes
            if wardrobe.strip().lower() != "none"
        ]
        ensure_unique("presentation role wardrobes", dressed_wardrobes)
        ensure_unique(
            "presentation role footwear",
            [
                f"{style.footwear_details} {style.footwear_type}"
                for style in self.role_styles
            ],
        )
        ensure_unique(
            "presentation role accessory sets",
            ["|".join(style.accessories) for style in self.role_styles],
        )
        ensure_unique("presentation moods", self.compatible_moods)
        return self


class PresentationBlueprint(StrictModel):
    recipes: list[PresentationRecipe] = Field(min_length=1, max_length=20)
    appearance_bias: list[Identifier] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def recipes_are_varied(self) -> PresentationBlueprint:
        ensure_unique(
            "presentation IDs",
            [recipe.presentation_id for recipe in self.recipes],
        )
        ensure_unique(
            "presentation footwear",
            [
                "|".join(
                    f"{style.footwear_details} {style.footwear_type}"
                    for style in recipe.role_styles
                )
                for recipe in self.recipes
            ],
        )
        ensure_unique(
            "presentation recipes",
            [
                "|".join(
                    (
                        *(
                            "|".join(
                                (
                                    style.role,
                                    style.coverage_mode,
                                    style.wardrobe,
                                    style.footwear_type,
                                    style.footwear_details,
                                    *style.accessories,
                                    style.makeup_and_grooming,
                                )
                            )
                            for style in recipe.role_styles
                        ),
                        *recipe.compatible_moods,
                    )
                )
                for recipe in self.recipes
            ],
        )
        ensure_unique("appearance biases", self.appearance_bias)
        validate_output_concepts_with_pattern(
            self,
            "presentation blueprint",
            FORBIDDEN_PRESENTATION_CONCEPTS,
        )
        return self


class CharacterBlueprint(StrictModel):
    profiles: list[CharacterProfile] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def profiles_are_complete_and_distinct(self) -> CharacterBlueprint:
        roles = [profile.role for profile in self.profiles]
        if len(set(roles)) != len(roles):
            raise ValueError("character profiles contain duplicate roles")
        unsupported_roles = set(roles).difference(PRESENTATION_ROLE_CODES)
        if unsupported_roles:
            raise ValueError(
                f"character profiles contain unsupported roles: "
                f"{sorted(unsupported_roles)}"
            )
        ensure_unique(
            "character ages",
            [str(profile.adult_age) for profile in self.profiles],
        )
        ensure_unique(
            "character height-weight designs",
            [
                f"{profile.height_cm}|{profile.weight_kg}"
                for profile in self.profiles
            ],
        )
        ensure_unique(
            "character physical designs",
            [
                "|".join(
                    (
                        profile.body_build,
                        profile.body_proportions,
                        profile.skin_tone,
                        profile.face_features,
                        profile.hair_style,
                        profile.hair_color,
                    )
                )
                for profile in self.profiles
            ],
        )
        ensure_unique(
            "character faces",
            [profile.face_features for profile in self.profiles],
        )
        ensure_unique(
            "character hair designs",
            [
                f"{profile.hair_color} {profile.hair_style}"
                for profile in self.profiles
            ],
        )
        ensure_unique(
            "character intimate designs",
            [profile.intimate_anatomy for profile in self.profiles],
        )
        for profile in self.profiles:
            pattern = (
                r"\b(?:clitoris|clitoral|labia|vulva|vulvar|vagina|vaginal)\b"
                if profile.role.startswith("f")
                else r"\b(?:penis|penile|scrotum|scrotal|testicles|testicular)\b"
            )
            if not re.search(pattern, profile.intimate_anatomy, re.I):
                raise ValueError(
                    f"{profile.role} intimate anatomy is not role-appropriate"
                )
        return self


class CreativeBlueprint(StrictModel):
    characters: CharacterBlueprint
    world: WorldBlueprint
    style: StyleBlueprint
    presentation: PresentationBlueprint

    @model_validator(mode="after")
    def layers_are_safe_and_compatible(self) -> CreativeBlueprint:
        character_roles = {
            profile.role for profile in self.characters.profiles
        }
        mismatched_presentations = [
            recipe.presentation_id
            for recipe in self.presentation.recipes
            if {style.role for style in recipe.role_styles} != character_roles
        ]
        if mismatched_presentations:
            raise ValueError(
                "presentation role styles do not match character profiles: "
                f"{mismatched_presentations}"
            )
        world_moods = {
            mood for location in self.world.locations for mood in location.mood_tags
        }
        incompatible_styles = [
            recipe.style_id
            for recipe in self.style.recipes
            if not world_moods.intersection(recipe.compatible_moods)
        ]
        if incompatible_styles:
            raise ValueError(
                f"styles have no compatible world mood: {incompatible_styles}"
            )
        incompatible_presentations = [
            recipe.presentation_id
            for recipe in self.presentation.recipes
            if not world_moods.intersection(recipe.compatible_moods)
        ]
        if incompatible_presentations:
            raise ValueError(
                "presentations have no compatible world mood: "
                f"{incompatible_presentations}"
            )
        uncovered_locations = [
            location.location_id
            for location in self.world.locations
            if not any(
                set(location.mood_tags).intersection(recipe.compatible_moods)
                for recipe in self.style.recipes
            )
        ]
        if uncovered_locations:
            raise ValueError(
                f"locations have no compatible style: {uncovered_locations}"
            )
        text = " ".join(iter_strings(self.model_dump(mode="json")))
        if not text.isascii():
            raise ValueError("creative blueprint must use ASCII text")
        minor_matches = sorted(
            {
                match.group(0).lower()
                for match in PROHIBITED_MINOR_CONCEPTS.finditer(text)
            }
        )
        if minor_matches:
            raise ValueError(
                f"creative blueprint contains minor concepts: {minor_matches}"
            )
        return self


def non_ascii_paths(value: object, path: str = "") -> list[str]:
    if isinstance(value, str):
        characters = sorted(
            {character for character in value if not character.isascii()}
        )
        if characters:
            codepoints = ",".join(
                f"U+{ord(character):04X}" for character in characters
            )
            return [f"{path or '<root>'} ({codepoints})"]
        return []
    if isinstance(value, dict):
        return [
            issue
            for key, item in value.items()
            for issue in non_ascii_paths(
                item,
                f"{path}.{key}" if path else str(key),
            )
        ]
    if isinstance(value, list):
        return [
            issue
            for index, item in enumerate(value)
            for issue in non_ascii_paths(item, f"{path}.{index}")
        ]
    return []


def validate_output_text(value: BaseModel, label: str) -> None:
    payload = value.model_dump(mode="json")
    non_ascii_issues = non_ascii_paths(payload)
    if non_ascii_issues:
        raise ValueError(
            f"{label} must use ASCII English in every string; replace fields "
            + "; ".join(non_ascii_issues[:12])
        )
    text = " ".join(iter_strings(payload))
    minor_matches = sorted(
        {
            match.group(0).lower()
            for match in PROHIBITED_MINOR_CONCEPTS.finditer(text)
        }
    )
    if minor_matches:
        raise ValueError(f"{label} contains minor concepts: {minor_matches}")
    fragment_issues = [
        path
        for path, field_text in iter_string_paths(payload)
        if " " in field_text
        and (
            INCOMPLETE_TEXT_END.search(field_text)
            or field_text.count("(") != field_text.count(")")
        )
    ]
    if fragment_issues:
        raise ValueError(
            f"{label} contains incomplete phrases at "
            + ", ".join(fragment_issues[:12])
        )


def validate_forbidden_output_concepts(value: BaseModel, label: str) -> None:
    validate_output_concepts_with_pattern(
        value,
        label,
        FORBIDDEN_CREATIVE_CONCEPTS,
    )


def validate_output_concepts_with_pattern(
    value: BaseModel,
    label: str,
    pattern: re.Pattern[str],
) -> None:
    payload = value.model_dump(mode="json")
    issues = []
    for path_value in iter_string_paths(payload):
        path, text = path_value
        matches = sorted(
            {
                match.group(0).lower()
                for match in pattern.finditer(text)
            }
        )
        if matches:
            issues.append(f"{path}: {', '.join(matches)}")
    if issues:
        raise ValueError(
            f"{label} contains forbidden concepts at "
            + "; ".join(issues[:12])
        )


def iter_string_paths(
    value: object,
    path: str = "",
) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path or "<root>", value)]
    if isinstance(value, dict):
        return [
            issue
            for key, item in value.items()
            for issue in iter_string_paths(
                item,
                f"{path}.{key}" if path else str(key),
            )
        ]
    if isinstance(value, list):
        return [
            issue
            for index, item in enumerate(value)
            for issue in iter_string_paths(item, f"{path}.{index}")
        ]
    return []


class WorldBlueprintOutput(StrictModel):
    world: WorldBlueprint

    @model_validator(mode="after")
    def output_text_is_valid(self) -> WorldBlueprintOutput:
        validate_output_text(self, "world blueprint")
        validate_forbidden_output_concepts(self, "world blueprint")
        return self


class CharacterBlueprintOutput(StrictModel):
    characters: CharacterBlueprint

    @model_validator(mode="after")
    def output_text_is_valid(
        self,
        info: ValidationInfo,
    ) -> CharacterBlueprintOutput:
        validate_output_text(self, "character blueprint")
        expected_roles = set((info.context or {}).get("cast_roles", ()))
        actual_roles = {
            profile.role for profile in self.characters.profiles
        }
        if expected_roles and actual_roles != expected_roles:
            raise ValueError(
                "character profiles must exactly match requested cast roles: "
                f"expected {sorted(expected_roles)}, got {sorted(actual_roles)}"
            )
        return self


class StyleBlueprintOutput(StrictModel):
    style: StyleBlueprint

    @model_validator(mode="after")
    def output_text_is_valid(
        self,
        info: ValidationInfo,
    ) -> StyleBlueprintOutput:
        validate_output_text(self, "style blueprint")
        validate_output_concepts_with_pattern(
            self,
            "style blueprint",
            FORBIDDEN_STYLE_CONCEPTS,
        )
        allowed_moods = set((info.context or {}).get("allowed_mood_tags", ()))
        used_moods = {
            mood
            for recipe in self.style.recipes
            for mood in recipe.compatible_moods
        }
        unknown_moods = used_moods.difference(allowed_moods)
        if allowed_moods and unknown_moods:
            raise ValueError(
                f"style uses unsupported mood tags: {sorted(unknown_moods)}"
            )
        missing_moods = allowed_moods.difference(used_moods)
        require_complete_coverage = (info.context or {}).get(
            "require_complete_mood_coverage",
            True,
        )
        if missing_moods and require_complete_coverage:
            raise ValueError(
                f"style does not cover mood tags: {sorted(missing_moods)}"
            )
        return self


class PresentationBlueprintOutput(StrictModel):
    presentation: PresentationBlueprint

    @model_validator(mode="after")
    def output_text_is_valid(
        self,
        info: ValidationInfo,
    ) -> PresentationBlueprintOutput:
        validate_output_text(self, "presentation blueprint")
        expected_roles = set((info.context or {}).get("cast_roles", ()))
        mismatched_recipes = [
            recipe.presentation_id
            for recipe in self.presentation.recipes
            if {style.role for style in recipe.role_styles} != expected_roles
        ]
        if expected_roles and mismatched_recipes:
            raise ValueError(
                "presentation recipes must exactly match requested cast roles: "
                f"{mismatched_recipes}"
            )
        expected_scene_count = (info.context or {}).get("scene_count")
        if (
            expected_scene_count is not None
            and len(self.presentation.recipes) != expected_scene_count
        ):
            raise ValueError(
                "presentation recipe count must exactly match requested scene count: "
                f"expected {expected_scene_count}, got "
                f"{len(self.presentation.recipes)}"
            )
        allowed_moods = set((info.context or {}).get("allowed_mood_tags", ()))
        used_moods = {
            mood
            for recipe in self.presentation.recipes
            for mood in recipe.compatible_moods
        }
        unknown_moods = used_moods.difference(allowed_moods)
        if allowed_moods and unknown_moods:
            raise ValueError(
                "presentation uses unsupported mood tags: "
                f"{sorted(unknown_moods)}"
            )
        return self


class NormalizedBriefOutput(StrictModel):
    brief: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def output_text_is_valid(self) -> NormalizedBriefOutput:
        validate_output_text(self, "normalized brief")
        return self


class BlueprintInference(StrictModel):
    schema_version: int
    system_prompt_hash: Fingerprint
    brief_hash: Fingerprint
    inference_config_hash: Fingerprint
    creative_seed: int
    model: str
    normalized_brief: str
    structured_rejections: list[list[str]]
    usage: dict[str, int]
    blueprint: CreativeBlueprint


BLUEPRINT_SCHEMA_VERSION = 24
BRIEF_NORMALIZATION_SYSTEM = """
Translate and normalize the user's creative brief into concise semantic ASCII
English. Preserve all setting, era, atmosphere, content, clothing or nudity,
and visual-style requirements without adding people, actions, or restrictions.
Every character must be printable ASCII. Return only schema data.
""".strip()
WORLD_BLUEPRINT_SYSTEM = """
OUTPUT LANGUAGE IS MANDATORY: every string value must be concise printable
ASCII English, regardless of the brief's language.
Infer only the WorldBlueprint from the brief. Produce six to twelve coherent
location cards with concise ASCII English architecture, materials, inanimate
props, practical light sources, and identifier mood tags. Every support record
must pair an allowed support identifier with a physical object or surface in
the location. Across the locations, cover bed, bed_edge, chair, floor,
furniture, sofa, support_sling, and wall at least once. Include one location
that realizes both floor and furniture, and one that realizes both
support_sling and wall.
Never add people, mirrors, humanoid objects, crowds,
attendants, guards, servants, or minor concepts. Return only schema data.
""".strip()
CHARACTER_BLUEPRINT_SYSTEM = """
OUTPUT LANGUAGE IS MANDATORY: every string value must be concise printable
ASCII English, regardless of the brief's language.
Infer only the CharacterBlueprint from the brief and supplied cast_roles. Return
exactly one profile for every supplied role and no other role. Every profile is
an independently designed adult aged at least 21, with a distinct age,
height-weight pair, build and fatness or leanness, proportions, skin tone,
facial structure and features, hair style and color, role-appropriate adult
intimate anatomy, pubic-hair treatment, and coherent fantasy traits. Female
anatomy must name clitoris, labia, vulva, or vagina; male anatomy must name
penis, scrotum, or testicles. Do not copy faces, hair, physical designs, or
intimate designs. Use concise printable ASCII English and return only schema
data.
""".strip()
STYLE_BLUEPRINT_SYSTEM = """
OUTPUT LANGUAGE IS MANDATORY: every string value must be concise printable
ASCII English, regardless of the brief's language.
Infer only the StyleBlueprint from the brief. Produce six to twelve coherent
complete style recipes rather than shuffled adjectives. Every compatible_moods
value must come from the supplied allowed_mood_tags, and every supplied mood tag
must appear in at least one recipe. Treat allowed_mood_tags as a closed enum:
copy its values character-for-character and never derive, combine, or invent
additional mood tags. Keep medium, rendering language, texture,
contrast, color, lighting, and atmosphere mutually coherent. Do not describe
people, anatomy, pose, contact, or camera geometry. Use concise printable ASCII
English and return only schema data.
""".strip()
PRESENTATION_BLUEPRINT_SYSTEM = """
OUTPUT LANGUAGE IS MANDATORY: every string value must be concise printable
ASCII English, regardless of the brief's language.
Infer only the PresentationBlueprint from the brief, supplied cast_roles, and
allowed_mood_tags. Produce exactly scene_count recipes. Every recipe must
contain exactly one role_styles entry for every supplied role and no unused
role. Give each visible person separately designed but scene-coordinated garments,
footwear, zero to two small wearable identity-relevant accessories, and
makeup-and-grooming treatment. Never add handheld novelty props, occupational
equipment, medical equipment, masks, or costume-role accessories unless the brief
explicitly requires them. Accessories must be wearable items selected from
earrings, necklaces, bracelets, rings, watches, hairpins, brooches, cufflinks,
tie clips, or pocket squares; do not use handheld or reflective accessories.
Within a
scene, choose coverage_mode independently for every role according to the brief
and creative composition. A role may use selective_access with named garments
or styled_nude with wardrobe set to literal none. A scene may therefore be fully
nude, fully selectively dressed, or mixed; there is no nudity quota and garments
must not be added merely to create variety. Dressed roles need visibly different
garments, silhouettes, materials, and color accents. All roles, including nude
roles, need distinct footwear, accessory sets, makeup, and grooming; male and
female roles must never receive the same footwear description. Every
compatible_moods value must come from allowed_mood_tags. Match the brief's era,
region, professions, and stable character identities; do not introduce unrelated
costume scenarios. Never use mirrors, mannequins, statues, sentence fragments,
unclosed parentheses, or a footwear_details noun that contradicts footwear_type.
Use actual footwear types from the schema, concise printable ASCII English, and
return only schema data.
""".strip()
BLUEPRINT_SYSTEM_HASH = hashlib.sha256(
    "\n\n".join(
        (
            BRIEF_NORMALIZATION_SYSTEM,
            WORLD_BLUEPRINT_SYSTEM,
            CHARACTER_BLUEPRINT_SYSTEM,
            STYLE_BLUEPRINT_SYSTEM,
            PRESENTATION_BLUEPRINT_SYSTEM,
        )
    ).encode()
).hexdigest()


def ensure_unique(label: str, values: list[str]) -> None:
    normalized = [value.strip().lower() for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} contains duplicate values")


def iter_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            text
            for key, item in value.items()
            for text in (*iter_strings(key), *iter_strings(item))
        ]
    if isinstance(value, list):
        return [text for item in value for text in iter_strings(item)]
    return []


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized[:80] or "creative"


def compact_phrase(value: str, max_words: int) -> str:
    natural = value.replace("_", " ")
    return " ".join(natural.split()[:max_words]).rstrip(",;:")


def clean_phrase(value: str) -> str:
    return " ".join(value.replace("_", " ").split()).strip(" ,;:")


def presentation_footwear_phrase(recipe: RoleStylingRecipe) -> str:
    details = clean_phrase(recipe.footwear_details)
    if re.search(
        r"\b(?:boots?|heels?|sandals?|shoes?|slippers?|pumps?|mules?|"
        r"sneakers?|loafers?|platforms?)\b",
        details,
        re.I,
    ):
        return details
    footwear_root = recipe.footwear_type.rstrip("s")
    if re.search(rf"\b{re.escape(footwear_root)}s?\b", details, re.I):
        return details
    return f"{details} {recipe.footwear_type}"


def blueprint_inference_config_hash(settings: SpatialProviderSettings) -> str:
    payload = {
        "base_url": settings.base_url.rstrip("/"),
        "model": settings.model,
        "thinking_mode": (
            settings.thinking_mode.value if settings.thinking_mode is not None else None
        ),
        "reasoning_effort": (
            settings.reasoning_effort.value
            if settings.reasoning_effort is not None
            else None
        ),
        "temperature": settings.temperature,
        "max_output_tokens": min(32768, settings.output_token_limit),
    }
    return stable_hash(payload)


async def infer_creative_blueprint(
    brief: str,
    creative_seed: int,
    cast_roles: tuple[str, ...],
    scene_count: int,
) -> BlueprintInference:
    if not brief.strip():
        raise ValueError("creative brief cannot be empty")
    if (
        not cast_roles
        or len(set(cast_roles)) != len(cast_roles)
        or set(cast_roles).difference(PRESENTATION_ROLE_CODES)
    ):
        raise ValueError(f"invalid creative blueprint cast roles: {cast_roles}")
    if not 1 <= scene_count <= 20:
        raise ValueError("creative blueprint scene count must be between 1 and 20")
    settings = load_spatial_provider_settings()
    brief_hash = hashlib.sha256(brief.strip().encode()).hexdigest()
    async with OpenAISpatialModel(settings) as model:
        normalization_response, normalization_rejections = (
            await generate_with_repair(
                model,
                system=BRIEF_NORMALIZATION_SYSTEM,
                payload={
                    "brief": brief.strip(),
                    "creative_seed": creative_seed,
                    "output_language": "ASCII English only",
                },
                response_model=NormalizedBriefOutput,
                max_output_tokens=min(2000, settings.output_token_limit),
            )
        )
        normalized_brief = NormalizedBriefOutput.model_validate(
            normalization_response.value
        ).brief
        world_response, world_rejections = await generate_with_repair(
            model,
            system=WORLD_BLUEPRINT_SYSTEM,
            payload={
                "brief": normalized_brief,
                "creative_seed": creative_seed,
                "output_language": "ASCII English only",
            },
            response_model=WorldBlueprintOutput,
            max_output_tokens=min(12000, settings.output_token_limit),
        )
        world = WorldBlueprintOutput.model_validate(world_response.value).world
        allowed_mood_tags = sorted(
            {
                mood
                for location in world.locations
                for mood in location.mood_tags
            }
        )
        (
            (character_response, character_rejections),
            (style_response, style_rejections),
            (presentation_response, presentation_rejections),
        ) = await asyncio.gather(
            generate_with_repair(
                model,
                system=CHARACTER_BLUEPRINT_SYSTEM,
                payload={
                    "brief": normalized_brief,
                    "creative_seed": creative_seed,
                    "cast_roles": list(cast_roles),
                    "output_language": "ASCII English only",
                },
                response_model=CharacterBlueprintOutput,
                max_output_tokens=min(8000, settings.output_token_limit),
                validation_context={"cast_roles": cast_roles},
            ),
            generate_with_repair(
                model,
                system=STYLE_BLUEPRINT_SYSTEM,
                payload={
                    "brief": normalized_brief,
                    "creative_seed": creative_seed,
                    "allowed_mood_tags": allowed_mood_tags,
                    "output_language": "ASCII English only",
                },
                response_model=StyleBlueprintOutput,
                max_output_tokens=min(8000, settings.output_token_limit),
                validation_context={
                    "allowed_mood_tags": allowed_mood_tags,
                    "require_complete_mood_coverage": False,
                },
            ),
            generate_with_repair(
                model,
                system=PRESENTATION_BLUEPRINT_SYSTEM,
                payload={
                    "brief": normalized_brief,
                    "creative_seed": creative_seed,
                    "cast_roles": list(cast_roles),
                    "scene_count": scene_count,
                    "allowed_mood_tags": allowed_mood_tags,
                    "output_language": "ASCII English only",
                },
                response_model=PresentationBlueprintOutput,
                max_output_tokens=min(20000, settings.output_token_limit),
                validation_context={
                    "cast_roles": cast_roles,
                    "scene_count": scene_count,
                    "allowed_mood_tags": allowed_mood_tags,
                },
            ),
        )
    style = complete_style_mood_coverage(
        StyleBlueprintOutput.model_validate(
            style_response.value,
            context={
                "allowed_mood_tags": allowed_mood_tags,
                "require_complete_mood_coverage": False,
            },
        ).style,
        allowed_mood_tags,
    )
    StyleBlueprintOutput.model_validate(
        {"style": style.model_dump(mode="json")},
        context={"allowed_mood_tags": allowed_mood_tags},
    )
    blueprint = CreativeBlueprint(
        characters=CharacterBlueprintOutput.model_validate(
            character_response.value
        ).characters,
        world=world,
        style=style,
        presentation=PresentationBlueprintOutput.model_validate(
            presentation_response.value
        ).presentation,
    )
    generated_roles = {
        profile.role for profile in blueprint.characters.profiles
    }
    if generated_roles != set(cast_roles):
        raise ValueError(
            "creative blueprint changed requested cast roles: "
            f"expected {sorted(cast_roles)}, got {sorted(generated_roles)}"
        )
    return BlueprintInference(
        schema_version=BLUEPRINT_SCHEMA_VERSION,
        system_prompt_hash=BLUEPRINT_SYSTEM_HASH,
        brief_hash=brief_hash,
        inference_config_hash=blueprint_inference_config_hash(settings),
        creative_seed=creative_seed,
        model=settings.model,
        normalized_brief=normalized_brief,
        structured_rejections=[
            *normalization_rejections,
            *world_rejections,
            *character_rejections,
            *style_rejections,
            *presentation_rejections,
        ],
        usage={
            key: sum(
                response.usage.model_dump(mode="json")[key]
                for response in (
                    normalization_response,
                    world_response,
                    character_response,
                    style_response,
                    presentation_response,
                )
            )
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
            )
        },
        blueprint=blueprint,
    )


def semantic_hash(value: BaseModel, identity_field: str) -> str:
    payload = value.model_dump(mode="json")
    payload.pop(identity_field)
    return stable_hash(payload)


def unused_setting_variant(
    blueprint: CreativeBlueprint,
    location: LocationCard,
    *,
    setting_id: str,
    used_fingerprints: set[str],
    rng: random.Random,
) -> tuple[SettingPreset, str] | None:
    material_variants = list(
        combinations(
            location.materials,
            min(3, len(location.materials)),
        )
    )
    prop_variants = [
        variant
        for size in range(1, min(2, len(location.environment_props)) + 1)
        for variant in combinations(location.environment_props, size)
    ]
    setting_variants = list(
        product(
            blueprint.world.time_options,
            blueprint.world.weather_options,
            location.light_sources,
            material_variants,
            prop_variants,
        )
    )
    rng.shuffle(setting_variants)
    for time_of_day, weather, light, materials, props in setting_variants:
        setting = SettingPreset(
            setting_id=setting_id,
            world_genre=blueprint.world.world_genre,
            location=compact_phrase(location.location, 10),
            era=blueprint.world.era,
            time_of_day=time_of_day,
            weather=weather,
            architecture=compact_phrase(location.architecture, 8),
            materials=[compact_phrase(value, 4) for value in materials],
            environment_props=[compact_phrase(value, 5) for value in props],
            motivated_light_sources=[compact_phrase(light, 9)],
            support_realizations=[
                SupportRealization(
                    support=item.support,
                    description=compact_phrase(item.description, 6),
                )
                for item in location.support_realizations
            ],
            mood_tags=list(location.mood_tags),
        )
        fingerprint = semantic_hash(setting, "setting_id")
        if fingerprint not in used_fingerprints:
            return setting, fingerprint
    return None


def maximum_location_assignment(
    blueprint: CreativeBlueprint,
    required_supports: list[set[str]],
) -> dict[int, str]:
    compatibility = {
        location.location_id: [
            scene_index
            for scene_index, requirement in enumerate(required_supports)
            if requirement.issubset(
                {realization.support for realization in location.support_realizations}
            )
        ]
        for location in blueprint.world.locations
    }
    scene_matches: dict[int, str] = {}

    def assign(location_id: str, visited_scenes: set[int]) -> bool:
        for scene_index in compatibility[location_id]:
            if scene_index in visited_scenes:
                continue
            visited_scenes.add(scene_index)
            previous_location = scene_matches.get(scene_index)
            if previous_location is None or assign(
                previous_location,
                visited_scenes,
            ):
                scene_matches[scene_index] = location_id
                return True
        return False

    for location_id in compatibility:
        assign(location_id, set())
    return scene_matches


def sample_scene_layer_inputs(
    blueprint: CreativeBlueprint,
    *,
    required_supports: list[set[str]],
    seed: int,
) -> list[SceneLayerInputs]:
    if not required_supports:
        raise ValueError("at least one scene support requirement is needed")
    unknown = set().union(*required_supports).difference(SUPPORTED_SURFACES)
    if unknown:
        raise ValueError(f"scene requires unknown supports: {sorted(unknown)}")

    rng = random.Random(seed)
    count = len(required_supports)
    if len(blueprint.presentation.recipes) < count:
        raise ValueError("presentation blueprint cannot cover every scene uniquely")
    recipe_order = list(blueprint.presentation.recipes)
    rng.shuffle(recipe_order)
    matched_presentations = {
        scene_index: recipe_order[scene_index] for scene_index in range(count)
    }
    location_usage: dict[str, int] = {}
    style_usage: dict[str, int] = {}
    pair_usage: dict[tuple[str, str], int] = {}
    used_setting_fingerprints: set[str] = set()
    used_presentation_fingerprints: set[str] = set()
    selected_by_index: dict[int, SceneLayerInputs] = {}
    reserved_locations = maximum_location_assignment(
        blueprint,
        required_supports,
    )
    scene_order = sorted(
        range(count),
        key=lambda index: (
            sum(
                required_supports[index].issubset(
                    {item.support for item in location.support_realizations}
                )
                for location in blueprint.world.locations
            ),
            index,
        ),
    )

    for index in scene_order:
        required = required_supports[index]
        assigned_presentation = matched_presentations[index]
        candidates: list[
            tuple[float, LocationCard, StyleRecipe, PresentationRecipe]
        ] = []
        for location in blueprint.world.locations:
            if not required.issubset(
                {item.support for item in location.support_realizations}
            ):
                continue
            for recipe in blueprint.style.recipes:
                if not set(location.mood_tags).intersection(recipe.compatible_moods):
                    continue
                pair = (location.location_id, recipe.style_id)
                presentation_mood_match = bool(
                    set(location.mood_tags).intersection(
                        assigned_presentation.compatible_moods
                    )
                )
                score = (
                    (
                        1000
                        if reserved_locations.get(index) == location.location_id
                        else 0
                    )
                    + (100 if location_usage.get(location.location_id, 0) == 0 else 0)
                    + (80 if style_usage.get(recipe.style_id, 0) == 0 else 0)
                    + (40 if pair_usage.get(pair, 0) == 0 else 0)
                    + (60 if presentation_mood_match else 0)
                    - location_usage.get(location.location_id, 0) * 12
                    - style_usage.get(recipe.style_id, 0) * 9
                    - pair_usage.get(pair, 0) * 20
                    + rng.random()
                )
                candidates.append((score, location, recipe, assigned_presentation))
        if not candidates:
            raise ValueError(
                f"no compatible world/style candidate for supports {sorted(required)}"
            )
        setting_id_prefix = f"{blueprint.world.family_id}_{index + 1:02d}"
        setting = None
        setting_fingerprint = ""
        location = None
        recipe = None
        presentation_recipe = None
        for (
            _,
            candidate_location,
            candidate_recipe,
            candidate_presentation,
        ) in sorted(
            candidates,
            key=lambda item: item[0],
            reverse=True,
        ):
            setting_id = (
                f"{setting_id_prefix}_"
                f"{slug(candidate_location.location_id)[:28].rstrip('_')}"
            )
            variant = unused_setting_variant(
                blueprint,
                candidate_location,
                setting_id=setting_id,
                used_fingerprints=used_setting_fingerprints,
                rng=rng,
            )
            if variant is not None:
                setting, setting_fingerprint = variant
                location = candidate_location
                recipe = candidate_recipe
                presentation_recipe = candidate_presentation
                break
        if (
            setting is None
            or location is None
            or recipe is None
            or presentation_recipe is None
        ):
            raise ValueError(
                f"all compatible locations exhausted for supports {sorted(required)}"
            )
        used_setting_fingerprints.add(setting_fingerprint)
        pair = (location.location_id, recipe.style_id)
        location_usage[location.location_id] = (
            location_usage.get(location.location_id, 0) + 1
        )
        style_usage[recipe.style_id] = style_usage.get(recipe.style_id, 0) + 1
        pair_usage[pair] = pair_usage.get(pair, 0) + 1

        presentation_id = (
            f"{blueprint.world.family_id}_{index + 1:02d}_"
            f"{presentation_recipe.presentation_id}"
        )
        presentation = PresentationPreset(
            presentation_id=presentation_id,
            role_styles=[
                RoleStylingPreset(
                    role=role_style.role,
                    coverage_mode=role_style.coverage_mode,
                    wardrobe_theme=clean_phrase(role_style.wardrobe),
                    footwear_theme=presentation_footwear_phrase(role_style),
                    accessory_theme=[
                        clean_phrase(value)
                        for value in role_style.accessories
                    ],
                    makeup_and_grooming_theme=clean_phrase(
                        role_style.makeup_and_grooming
                    ),
                )
                for role_style in presentation_recipe.role_styles
            ],
            appearance_bias=list(blueprint.presentation.appearance_bias),
            compatible_moods=list(presentation_recipe.compatible_moods),
        )
        presentation_fingerprint = semantic_hash(
            presentation,
            "presentation_id",
        )
        if presentation_fingerprint in used_presentation_fingerprints:
            raise ValueError("presentation sampler produced a semantic duplicate")
        used_presentation_fingerprints.add(presentation_fingerprint)

        selected_by_index[index] = SceneLayerInputs(
            setting=setting,
            style=StylePreset(
                style_id=recipe.style_id,
                medium=compact_phrase(recipe.medium, 5),
                rendering_language=compact_phrase(
                    recipe.rendering_language,
                    6,
                ),
                surface_texture=compact_phrase(recipe.surface_texture, 6),
                contrast=compact_phrase(recipe.contrast, 4),
                color_treatment=compact_phrase(recipe.color_treatment, 7),
                lighting_treatment=compact_phrase(
                    recipe.lighting_treatment,
                    6,
                ),
                atmosphere=compact_phrase(recipe.atmosphere, 6),
                compatible_moods=list(recipe.compatible_moods),
            ),
            presentation=presentation,
        )

    selected = [selected_by_index[index] for index in range(count)]
    semantic_fingerprints = []
    for item in selected:
        payload = item.model_dump(mode="json")
        payload["setting"].pop("setting_id")
        payload["presentation"].pop("presentation_id")
        semantic_fingerprints.append(stable_hash(payload))
    if len(set(semantic_fingerprints)) != count:
        raise ValueError("sampled scene layer inputs are not semantically unique")
    return selected
