from __future__ import annotations

import hashlib
import random
import re
from itertools import combinations, product
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from run import _generate_with_repair
from scene_layers import (
    PresentationPreset,
    SceneLayerInputs,
    SettingPreset,
    StylePreset,
    SupportRealization,
    stable_hash,
)

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.provider import OpenAIStoryModel

Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
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
FORBIDDEN_CREATIVE_CONCEPTS = re.compile(
    r"\b(?:woman|man|person|people|crowd|attendant|guard|servant|body|"
    r"anatomy|pose|contact|intercourse|fellatio|cunnilingus|masturbation|"
    r"penis|vagina|vulva|anus|breast|clitoris|camera|lens|framing|viewpoint|"
    r"mirror|statue|mannequin)\b",
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
            for support in SUPPORTED_SURFACES
        }
        insufficient = {
            support: count for support, count in coverage.items() if count < 1
        }
        if insufficient:
            raise ValueError(
                f"world locations have insufficient support coverage: {insufficient}"
            )
        compound_requirements = ({"floor", "furniture"},)
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


class PresentationBlueprint(StrictModel):
    wardrobe_options: list[str] = Field(min_length=4, max_length=10)
    accessory_options: list[str] = Field(min_length=3, max_length=10)
    makeup_options: list[str] = Field(min_length=4, max_length=10)
    appearance_bias: list[Identifier] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def options_are_unique(self) -> PresentationBlueprint:
        ensure_unique("wardrobe options", self.wardrobe_options)
        ensure_unique("accessory options", self.accessory_options)
        ensure_unique("makeup options", self.makeup_options)
        ensure_unique("appearance biases", self.appearance_bias)
        return self


class CreativeBlueprint(StrictModel):
    world: WorldBlueprint
    style: StyleBlueprint
    presentation: PresentationBlueprint

    @model_validator(mode="after")
    def layers_are_safe_and_compatible(self) -> CreativeBlueprint:
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
        matches = sorted(
            {
                match.group(0).lower()
                for match in FORBIDDEN_CREATIVE_CONCEPTS.finditer(text)
            }
        )
        if matches:
            raise ValueError(
                f"creative blueprint contains forbidden concepts: {matches}"
            )
        return self


class BlueprintInference(StrictModel):
    schema_version: int
    system_prompt_hash: Fingerprint
    brief_hash: Fingerprint
    creative_seed: int
    model: str
    structured_rejections: list[list[str]]
    usage: dict[str, int]
    blueprint: CreativeBlueprint


BLUEPRINT_SYSTEM = """
Convert the user brief into one compact CreativeBlueprint with three independent
parts. WorldBlueprint contains coherent location cards with architecture,
materials, inanimate props, motivated practical light sources, mood tags, and
support realization records. Every support record must pair an allowed
identifier with a concise physical object or surface description that exists
in the location or its props. Across the location cards, each allowed support
identifier bed, bed_edge, chair, floor, furniture, sofa, support_sling, and wall
must appear at least once. Use only those exact support identifiers and never
invent a support name. At least one location card must physically realize both
floor and furniture. StyleBlueprint
contains coherent complete style recipes,
not independently shuffled style adjectives. Each recipe controls medium,
rendering language, surface texture, contrast, color treatment, lighting
treatment, atmosphere, and compatible mood tags. PresentationBlueprint contains
wardrobe, accessory, makeup, and soft appearance-bias option pools.

Do not decide cast count, people, roles, names, age, bodies, anatomy, activity,
pose, contact, actor support, screen position, lens, camera placement, viewpoint,
or framing. Do not include mirrors, humanoid statues, crowds, attendants,
guards, servants, or person-shaped objects. Keep every prose field to roughly
two to seven words, use concise ASCII English, and make mood tags match between
each location and at least one style recipe. Use the supplied creative seed as
a diversity nonce. Return only schema data.
""".strip()
BLUEPRINT_SCHEMA_VERSION = 4
BLUEPRINT_SYSTEM_HASH = hashlib.sha256(BLUEPRINT_SYSTEM.encode()).hexdigest()


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


async def infer_creative_blueprint(
    brief: str,
    creative_seed: int,
) -> BlueprintInference:
    if not brief.strip():
        raise ValueError("creative brief cannot be empty")
    settings = load_story_provider_settings()
    brief_hash = hashlib.sha256(brief.strip().encode()).hexdigest()
    async with OpenAIStoryModel(settings) as model:
        response, rejections = await _generate_with_repair(
            model,
            system=BLUEPRINT_SYSTEM,
            payload={
                "brief": brief.strip(),
                "creative_seed": creative_seed,
            },
            response_model=CreativeBlueprint,
            max_output_tokens=min(10000, settings.output_token_limit),
        )
    blueprint = CreativeBlueprint.model_validate(response.value)
    return BlueprintInference(
        schema_version=BLUEPRINT_SCHEMA_VERSION,
        system_prompt_hash=BLUEPRINT_SYSTEM_HASH,
        brief_hash=brief_hash,
        creative_seed=creative_seed,
        model=settings.model,
        structured_rejections=rejections,
        usage=response.usage.model_dump(mode="json"),
        blueprint=blueprint,
    )


def semantic_hash(value: BaseModel, identity_field: str) -> str:
    payload = value.model_dump(mode="json")
    payload.pop(identity_field)
    return stable_hash(payload)


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
    accessory_pairs = list(combinations(blueprint.presentation.accessory_options, 2))
    presentation_variants = list(
        product(
            blueprint.presentation.wardrobe_options,
            blueprint.presentation.makeup_options,
            accessory_pairs,
        )
    )
    rng.shuffle(presentation_variants)
    if len(presentation_variants) < count:
        raise ValueError("presentation blueprint cannot produce enough unique variants")
    location_usage: dict[str, int] = {}
    style_usage: dict[str, int] = {}
    pair_usage: dict[tuple[str, str], int] = {}
    used_setting_fingerprints: set[str] = set()
    used_presentation_fingerprints: set[str] = set()
    selected_by_index: dict[int, SceneLayerInputs] = {}
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
        candidates: list[tuple[float, LocationCard, StyleRecipe]] = []
        for location in blueprint.world.locations:
            if not required.issubset(
                {item.support for item in location.support_realizations}
            ):
                continue
            for recipe in blueprint.style.recipes:
                if not set(location.mood_tags).intersection(recipe.compatible_moods):
                    continue
                pair = (location.location_id, recipe.style_id)
                score = (
                    (100 if location_usage.get(location.location_id, 0) == 0 else 0)
                    + (80 if style_usage.get(recipe.style_id, 0) == 0 else 0)
                    + (40 if pair_usage.get(pair, 0) == 0 else 0)
                    - location_usage.get(location.location_id, 0) * 12
                    - style_usage.get(recipe.style_id, 0) * 9
                    - pair_usage.get(pair, 0) * 20
                    + rng.random()
                )
                candidates.append((score, location, recipe))
        if not candidates:
            raise ValueError(
                f"no compatible world/style candidate for supports {sorted(required)}"
            )
        _, location, recipe = max(candidates, key=lambda item: item[0])
        pair = (location.location_id, recipe.style_id)
        location_usage[location.location_id] = (
            location_usage.get(location.location_id, 0) + 1
        )
        style_usage[recipe.style_id] = style_usage.get(recipe.style_id, 0) + 1
        pair_usage[pair] = pair_usage.get(pair, 0) + 1

        setting_id = (
            f"{blueprint.world.family_id}_{index + 1:02d}_"
            f"{slug(location.location_id)[:28].rstrip('_')}"
        )
        presentation_id = f"{blueprint.world.family_id}_{index + 1:02d}_presentation"
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
        setting = None
        for time_of_day, weather, light, materials, props in setting_variants:
            candidate_setting = SettingPreset(
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
            candidate_fingerprint = semantic_hash(
                candidate_setting,
                "setting_id",
            )
            if candidate_fingerprint not in used_setting_fingerprints:
                setting = candidate_setting
                used_setting_fingerprints.add(candidate_fingerprint)
                break
        if setting is None:
            raise ValueError(
                f"location {location.location_id} exhausted unique setting variants"
            )

        wardrobe, makeup, accessory_pair = presentation_variants[index]
        presentation = PresentationPreset(
            presentation_id=presentation_id,
            wardrobe_theme=compact_phrase(wardrobe, 8),
            accessory_theme=[compact_phrase(value, 4) for value in accessory_pair],
            makeup_theme=compact_phrase(makeup, 7),
            appearance_bias=list(blueprint.presentation.appearance_bias),
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
