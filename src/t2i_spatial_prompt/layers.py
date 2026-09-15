from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
]
RoleCode = Annotated[str, StringConstraints(pattern=r"^[fm][1-9][0-9]*$")]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
INTIMATE_REGIONS = {
    "anus",
    "clitoris",
    "penis",
    "vagina",
    "vulva",
}
EXTRA_CAST_HAZARDS = {
    "background_people",
    "humanoid_statues",
    "mirrors_showing_extra_bodies",
    "person_shaped_shadows",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CharacterProfile(StrictModel):
    role: RoleCode
    adult_age: int = Field(ge=21, le=75)
    nationality: str = Field(min_length=2, max_length=40)
    stature: Identifier
    build: Identifier
    skin_tone: Identifier
    face_structure: Identifier
    hair_base: Identifier
    body_detail_profile: Identifier
    pubic_hair_profile: Identifier
    fantasy_body_traits: list[Identifier] = Field(default_factory=list, max_length=4)


class SupportRealization(StrictModel):
    support: Identifier
    description: str = Field(min_length=3, max_length=80)


class SettingPreset(StrictModel):
    setting_id: Identifier
    world_genre: Identifier
    location: str = Field(min_length=8, max_length=120)
    era: Identifier = "contemporary"
    time_of_day: Identifier
    weather: Identifier = "interior_controlled"
    architecture: str = Field(min_length=5, max_length=120)
    materials: list[str] = Field(min_length=2, max_length=5)
    environment_props: list[str] = Field(default_factory=list, max_length=5)
    motivated_light_sources: list[str] = Field(min_length=1, max_length=4)
    support_realizations: list[SupportRealization] = Field(
        min_length=1,
        max_length=9,
    )
    mood_tags: list[Identifier] = Field(min_length=1, max_length=6)
    forbidden_elements: list[Identifier] = Field(
        default_factory=lambda: sorted(EXTRA_CAST_HAZARDS),
        min_length=4,
        max_length=8,
    )

    @model_validator(mode="after")
    def protects_exact_cast(self) -> SettingPreset:
        missing = EXTRA_CAST_HAZARDS.difference(self.forbidden_elements)
        if missing:
            raise ValueError(f"setting omits exact-cast hazards: {sorted(missing)}")
        support_ids = [item.support for item in self.support_realizations]
        if len(support_ids) != len(set(support_ids)):
            raise ValueError("setting contains duplicate support realizations")
        return self


class StylePreset(StrictModel):
    style_id: Identifier
    medium: str = Field(min_length=5, max_length=60)
    rendering_language: str = Field(min_length=5, max_length=80)
    surface_texture: str = Field(min_length=5, max_length=80)
    contrast: str = Field(min_length=3, max_length=60)
    color_treatment: str = Field(min_length=5, max_length=80)
    lighting_treatment: str = Field(min_length=5, max_length=80)
    atmosphere: str = Field(min_length=5, max_length=80)
    compatible_moods: list[Identifier] = Field(min_length=1, max_length=6)


class PresentationPreset(StrictModel):
    presentation_id: Identifier
    wardrobe_theme: str = Field(min_length=5, max_length=100)
    accessory_theme: list[str] = Field(default_factory=list, max_length=4)
    makeup_theme: str = Field(min_length=3, max_length=80)
    appearance_bias: list[Identifier] = Field(default_factory=list, max_length=4)


class SceneLayerInputs(StrictModel):
    setting: SettingPreset
    style: StylePreset
    presentation: PresentationPreset


class RolePresentation(StrictModel):
    role: RoleCode
    wardrobe: str
    wardrobe_state: Identifier
    footwear: str
    accessories: list[str] = Field(default_factory=list, max_length=4)
    makeup: str
    hair_styling: str
    surface_finish: str


class PresentationPlan(StrictModel):
    scene_id: Annotated[str, StringConstraints(pattern=r"^D\d{2}$")]
    spatial_fingerprint: Fingerprint
    setting_id: Identifier
    style_id: Identifier
    presentation_id: Identifier
    roles: list[RolePresentation] = Field(min_length=1, max_length=5)
    motivated_light_source: str
    lighting_direction: Identifier
    lighting_quality: Identifier
    medium: str
    rendering_language: str
    surface_texture: str
    contrast: str
    color_treatment: str
    lighting_treatment: str
    atmosphere: str
    appearance_bias: list[Identifier] = Field(default_factory=list, max_length=4)


class FinalVisibilityPlan(StrictModel):
    required_regions_by_role: dict[RoleCode, list[Identifier]]
    visible_regions_by_role: dict[RoleCode, list[Identifier]]
    emitted_body_details_by_role: dict[RoleCode, list[str]]
    omitted_body_details_by_role: dict[RoleCode, list[Identifier]]


class LayerFingerprints(StrictModel):
    spatial: Fingerprint
    characters: Fingerprint
    setting: Fingerprint
    style: Fingerprint
    presentation: Fingerprint


class TokenMetrics(StrictModel):
    geometry_estimated_tokens: int = Field(ge=1)
    verbose_layer_estimated_tokens: int = Field(ge=1)
    layer_estimated_tokens: int = Field(ge=1)
    compact_saved_tokens: int = Field(ge=0)
    final_estimated_tokens: int = Field(ge=1)


class ResolvedSceneLayers(StrictModel):
    characters: list[CharacterProfile] = Field(min_length=1, max_length=5)
    setting: SettingPreset
    style: StylePreset
    presentation_source: PresentationPreset
    required_environment_supports: list[Identifier] = Field(max_length=4)
    presentation: PresentationPlan
    visibility: FinalVisibilityPlan
    fingerprints: LayerFingerprints
    compact_suffix: str
    token_metrics: TokenMetrics


CHARACTER_PROFILES = {
    "f1": CharacterProfile(
        role="f1",
        adult_age=29,
        nationality="Chinese",
        stature="tall",
        build="athletic_slim",
        skin_tone="warm_light",
        face_structure="oval_defined",
        hair_base="long_black_wavy",
        body_detail_profile="compact_symmetrical_intimate_anatomy",
        pubic_hair_profile="neatly_trimmed",
    ),
    "f2": CharacterProfile(
        role="f2",
        adult_age=30,
        nationality="Chinese",
        stature="medium",
        build="compact_athletic",
        skin_tone="neutral_light",
        face_structure="heart_shaped",
        hair_base="shoulder_length_black",
        body_detail_profile="soft_full_intimate_anatomy",
        pubic_hair_profile="closely_trimmed",
    ),
    "f3": CharacterProfile(
        role="f3",
        adult_age=31,
        nationality="Chinese",
        stature="tall",
        build="soft_curvy",
        skin_tone="warm_medium",
        face_structure="angular_elegant",
        hair_base="long_dark_brown",
        body_detail_profile="defined_natural_intimate_anatomy",
        pubic_hair_profile="natural_groomed",
    ),
    "m1": CharacterProfile(
        role="m1",
        adult_age=32,
        nationality="Chinese",
        stature="tall",
        build="lean_muscular",
        skin_tone="warm_medium",
        face_structure="square_defined",
        hair_base="short_black",
        body_detail_profile="proportional_adult_intimate_anatomy",
        pubic_hair_profile="closely_trimmed",
    ),
    "m2": CharacterProfile(
        role="m2",
        adult_age=30,
        nationality="Chinese",
        stature="medium_tall",
        build="athletic",
        skin_tone="neutral_medium",
        face_structure="oval_masculine",
        hair_base="short_dark_brown",
        body_detail_profile="lean_proportional_intimate_anatomy",
        pubic_hair_profile="natural_groomed",
    ),
}


def stable_hash(value: object) -> str:
    def normalized(item: object) -> object:
        if isinstance(item, BaseModel):
            return normalized(item.model_dump(mode="json"))
        if isinstance(item, dict):
            return {str(key): normalized(entry) for key, entry in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalized(entry) for entry in item]
        return item

    payload = normalized(value)
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / 4)


def make_setting_preset(
    setting_id: str,
    location: str,
    lighting: str,
    *,
    world_genre: str = "contemporary",
    era: str = "contemporary",
    time_of_day: str = "night",
    weather: str = "interior_controlled",
    architecture: str | None = None,
    materials: tuple[str, ...] = ("textured fabric", "finished wood"),
    environment_props: tuple[str, ...] = (),
    support_realizations: tuple[tuple[str, str], ...] = (
        ("floor", "finished floor"),
        ("wall", "structural wall"),
    ),
    mood_tags: tuple[str, ...] = ("editorial",),
) -> SettingPreset:
    return SettingPreset(
        setting_id=setting_id,
        world_genre=world_genre,
        era=era,
        location=location,
        time_of_day=time_of_day,
        weather=weather,
        architecture=architecture or location,
        materials=list(materials),
        environment_props=list(environment_props),
        motivated_light_sources=[lighting],
        support_realizations=[
            SupportRealization(support=support, description=description)
            for support, description in support_realizations
        ],
        mood_tags=list(mood_tags),
    )


def make_scene_layer_inputs(
    setting_id: str,
    location: str,
    lighting: str,
    color_treatment: str,
    atmosphere: str,
    *,
    world_genre: str = "contemporary",
    era: str = "contemporary",
    time_of_day: str = "night",
    weather: str = "interior_controlled",
    architecture: str | None = None,
    materials: tuple[str, ...] = ("textured fabric", "finished wood"),
    environment_props: tuple[str, ...] = (),
    support_realizations: tuple[tuple[str, str], ...] = (
        ("floor", "finished floor"),
        ("wall", "structural wall"),
    ),
    mood_tags: tuple[str, ...] = ("editorial",),
    wardrobe_theme: str = "editorial evening wear",
    accessory_theme: tuple[str, ...] = ("minimal jewelry",),
    makeup_theme: str = "polished editorial makeup",
    appearance_bias: tuple[str, ...] = (),
    medium: str = "cinematic photography",
    rendering_language: str = "editorial realism",
    surface_texture: str = "tactile natural surfaces",
    contrast: str = "controlled contrast",
    lighting_treatment: str = "clean subject separation",
) -> SceneLayerInputs:
    return SceneLayerInputs(
        setting=make_setting_preset(
            setting_id,
            location,
            lighting,
            world_genre=world_genre,
            era=era,
            time_of_day=time_of_day,
            weather=weather,
            architecture=architecture,
            materials=materials,
            environment_props=environment_props,
            support_realizations=support_realizations,
            mood_tags=mood_tags,
        ),
        style=StylePreset(
            style_id=f"{setting_id}_style",
            medium=medium,
            rendering_language=rendering_language,
            surface_texture=surface_texture,
            contrast=contrast,
            color_treatment=color_treatment,
            lighting_treatment=lighting_treatment,
            atmosphere=atmosphere,
            compatible_moods=list(mood_tags),
        ),
        presentation=PresentationPreset(
            presentation_id=f"{setting_id}_presentation",
            wardrobe_theme=wardrobe_theme,
            accessory_theme=list(accessory_theme),
            makeup_theme=makeup_theme,
            appearance_bias=list(appearance_bias),
        ),
    )


SCENE_LAYER_PRESETS = {
    item.setting.setting_id: item
    for item in (
        make_scene_layer_inputs(
            "rainy_neon_apartment",
            "rain-darkened high-rise apartment",
            "magenta and cyan neon through wet glass",
            "slate, magenta and cyan",
            "electric nocturnal tension",
            weather="rain",
            materials=("wet glass", "brushed steel", "dark linen"),
            environment_props=("rain-streaked window", "low platform bed"),
            support_realizations=(
                ("bed", "low platform bed"),
                ("bed_edge", "firm platform bed edge"),
                ("floor", "finished apartment floor"),
                ("wall", "structural apartment wall"),
            ),
            mood_tags=("electric", "nocturnal"),
            wardrobe_theme="sleek black nightlife tailoring",
            accessory_theme=("silver ear cuffs",),
            makeup_theme="smoky eyes with a glossy finish",
        ),
        make_scene_layer_inputs(
            "amber_restraint_studio",
            "minimal amber performance studio",
            "shielded amber ceiling source",
            "amber, umber and cream",
            "controlled sculptural ritual",
            materials=("matte plaster", "pale timber", "padded leather"),
            environment_props=("low platform",),
            support_realizations=(
                ("floor", "pale timber floor"),
                ("wall", "matte plaster wall"),
                ("furniture", "padded performance platform"),
                ("sofa", "firm padded studio sofa"),
            ),
            mood_tags=("controlled", "sculptural"),
            wardrobe_theme="minimalist performance styling",
        ),
        make_scene_layer_inputs(
            "burgundy_modern_corridor",
            "spacious modern corridor",
            "hard architectural side light",
            "burgundy, ochre and slate",
            "dynamic cinematic intensity",
            materials=("polished stone", "dark timber", "brushed brass"),
            support_realizations=(
                ("floor", "polished stone floor"),
                ("wall", "structural corridor wall"),
            ),
            mood_tags=("dynamic", "cinematic"),
            wardrobe_theme="structured evening tailoring",
        ),
        make_scene_layer_inputs(
            "midnight_luxury_hotel",
            "double-height luxury hotel suite at midnight",
            "warm brass practicals and cool city window light",
            "dark emerald, brass and ivory",
            "opulent after-hours drama",
            materials=("emerald velvet", "polished brass", "ivory linen"),
            environment_props=("city window", "upholstered headboard"),
            support_realizations=(
                ("bed", "upholstered hotel bed"),
                ("bed_edge", "firm upholstered bed edge"),
                ("floor", "polished suite floor"),
                ("wall", "structural suite wall"),
                ("sofa", "deep hotel sofa"),
            ),
            mood_tags=("opulent", "dramatic"),
            wardrobe_theme="luxury evening wear arranged for the scene",
            accessory_theme=("fine gold jewelry", "gemstone choker"),
            makeup_theme="precise evening makeup",
            appearance_bias=("statuesque", "polished"),
        ),
        make_scene_layer_inputs(
            "soft_morning_bedroom",
            "quiet bedroom in early morning",
            "broad window light with a warm rim",
            "pale linen, cream and soft gold",
            "quiet editorial warmth",
            time_of_day="morning",
            materials=("washed linen", "light oak", "sheer fabric"),
            environment_props=("low bed", "sheer curtains"),
            support_realizations=(
                ("bed", "low linen bed"),
                ("bed_edge", "firm low bed edge"),
                ("floor", "light oak floor"),
                ("wall", "structural bedroom wall"),
            ),
            mood_tags=("quiet", "warm"),
            wardrobe_theme="soft silk sleepwear",
            makeup_theme="natural luminous makeup",
        ),
        make_scene_layer_inputs(
            "demon_sovereign_palace",
            "obsidian throne chamber of a demon sovereign",
            "crimson braziers and molten floor fissures",
            "obsidian, crimson and antique gold",
            "commanding infernal grandeur",
            world_genre="dark_fantasy",
            era="fantasy",
            materials=("obsidian", "black iron", "crimson velvet"),
            environment_props=("empty throne", "braziers", "ritual sigil"),
            support_realizations=(
                ("floor", "level obsidian floor"),
                ("wall", "load-bearing obsidian wall"),
                ("sofa", "firm crimson ceremonial divan"),
                ("furniture", "solid black iron altar"),
            ),
            mood_tags=("commanding", "infernal", "regal"),
            wardrobe_theme="dark fantasy regalia arranged for the scene",
            accessory_theme=("horned crown", "black metal arm cuffs"),
            makeup_theme="ritual smoky eyes and dark wine lips",
            appearance_bias=("statuesque", "commanding", "supernatural_eyes"),
            medium="dark fantasy cinematic photography",
            rendering_language="high detail infernal realism",
            surface_texture="polished obsidian and tactile velvet",
            contrast="hard luminous contrast",
            lighting_treatment="ritual fire with restrained bloom",
        ),
    )
}


def required_region_map(
    roles: list[str],
    contacts: list[tuple[str, str, str]],
) -> dict[str, list[str]]:
    result = {role: set() for role in roles}
    for source_role, target_role, target_region in contacts:
        if source_role in result:
            result[source_role].add("active_limb")
        if target_role in result:
            result[target_role].add(target_region)
    return {role: sorted(regions) for role, regions in result.items()}


def resolve_scene_layers(
    *,
    scene_id: str,
    spatial_fingerprint: str,
    geometry: str,
    cast_roles: list[str],
    body_level: str,
    setting: SettingPreset,
    style: StylePreset,
    presentation_source: PresentationPreset,
    required_environment_supports: list[str],
    required_regions_by_role: dict[str, list[str]],
    visible_regions_by_role: dict[str, list[str]],
) -> ResolvedSceneLayers:
    characters = [CHARACTER_PROFILES[role] for role in cast_roles]
    role_presentations = []
    for profile in characters:
        required = set(required_regions_by_role.get(profile.role, []))
        intimate_required = bool(required.intersection(INTIMATE_REGIONS))
        wardrobe_state = (
            "clear_of_required_contacts" if intimate_required else "scene_appropriate"
        )
        wardrobe = presentation_source.wardrobe_theme
        if intimate_required:
            wardrobe = f"{wardrobe}, displaced only where contact requires"
        role_presentations.append(
            RolePresentation(
                role=profile.role,
                wardrobe=wardrobe,
                wardrobe_state=wardrobe_state,
                footwear=(
                    "setting-matched footwear"
                    if body_level == "high"
                    else "footwear omitted for stable support"
                ),
                accessories=(
                    presentation_source.accessory_theme
                    if profile.role == cast_roles[0]
                    else []
                ),
                makeup=(
                    presentation_source.makeup_theme
                    if profile.role.startswith("f")
                    else "subtle polished grooming"
                ),
                hair_styling="setting-coherent styling of the locked base hair",
                surface_finish="lighting-responsive natural skin finish",
            )
        )
    presentation = PresentationPlan(
        scene_id=scene_id,
        spatial_fingerprint=spatial_fingerprint,
        setting_id=setting.setting_id,
        style_id=style.style_id,
        presentation_id=presentation_source.presentation_id,
        roles=role_presentations,
        motivated_light_source=setting.motivated_light_sources[0],
        lighting_direction="geometry_preserving",
        lighting_quality="subject_separating",
        medium=style.medium,
        rendering_language=style.rendering_language,
        surface_texture=style.surface_texture,
        contrast=style.contrast,
        color_treatment=style.color_treatment,
        lighting_treatment=style.lighting_treatment,
        atmosphere=style.atmosphere,
        appearance_bias=list(presentation_source.appearance_bias),
    )
    emitted: dict[str, list[str]] = {}
    omitted: dict[str, list[str]] = {}
    for profile in characters:
        visible = set(visible_regions_by_role.get(profile.role, []))
        if visible.intersection(INTIMATE_REGIONS):
            emitted[profile.role] = [
                profile.body_detail_profile.replace("_", " "),
                profile.pubic_hair_profile.replace("_", " "),
            ]
            omitted[profile.role] = []
        else:
            emitted[profile.role] = []
            omitted[profile.role] = [
                "body_detail_profile",
                "pubic_hair_profile",
            ]
    visibility = FinalVisibilityPlan(
        required_regions_by_role=required_regions_by_role,
        visible_regions_by_role=visible_regions_by_role,
        emitted_body_details_by_role=emitted,
        omitted_body_details_by_role=omitted,
    )
    character_phrases = [
        (
            f"{profile.role.upper()} {profile.stature.replace('_', '-')} "
            f"{profile.build.replace('_', '-')}, "
            f"{profile.hair_base.replace('_', '-')} hair, "
            f"{profile.face_structure.replace('_', '-')} face"
        )
        for profile in characters
    ]
    contact_clearance_roles = [
        role.role.upper()
        for role in role_presentations
        if role.wardrobe_state == "clear_of_required_contacts"
    ]
    accessory_phrases = [
        f"{role.role.upper()} {', '.join(role.accessories)}"
        for role in role_presentations
        if role.accessories
    ]
    visible_detail_phrases = [
        f"{role.upper()} {', '.join(details)}"
        for role, details in emitted.items()
        if details
    ]
    setting_props = (
        f"; {', '.join(setting.environment_props)}" if setting.environment_props else ""
    )
    time_phrase = ""
    natural_time = setting.time_of_day.replace("_", " ")
    if natural_time not in setting.location.lower():
        time_phrase = f", {natural_time}"
    suffix_parts = [
        (
            f"World: {setting.location}{time_phrase}; "
            f"{'/'.join(setting.materials)}"
            f"{setting_props}"
        ),
        f"Look: {'; '.join(character_phrases)}",
        (
            f"Wardrobe: {presentation_source.wardrobe_theme}; clear "
            f"{', '.join(contact_clearance_roles)}; women "
            f"{presentation_source.makeup_theme}; "
            f"{'; '.join(accessory_phrases)}"
            if contact_clearance_roles
            else (
                f"Wardrobe: {presentation_source.wardrobe_theme}; women "
                f"{presentation_source.makeup_theme}; "
                f"{'; '.join(accessory_phrases)}"
            )
        ),
    ]
    if visible_detail_phrases:
        suffix_parts.append(f"Visible detail: {'; '.join(visible_detail_phrases)}")
    if presentation.appearance_bias:
        suffix_parts.append(
            "Presence: "
            + ", ".join(
                value.replace("_", " ") for value in presentation.appearance_bias
            )
        )
    support_map = {
        item.support: item.description for item in setting.support_realizations
    }
    required_support_phrases = [
        support_map[support] for support in required_environment_supports
    ]
    if required_support_phrases:
        suffix_parts.append(f"Supports: {', '.join(required_support_phrases)}")
    suffix_parts.extend(
        (
            f"Light: {presentation.motivated_light_source}",
            (
                f"Style: {presentation.medium}; {presentation.rendering_language}; "
                f"{presentation.surface_texture}; {presentation.contrast}; "
                f"{presentation.color_treatment}; "
                f"{presentation.lighting_treatment}; {presentation.atmosphere}"
            ),
            "No extra figures, statues, human shadows or reflections",
        )
    )
    compact_suffix = ". ".join(suffix_parts) + "."
    layer_tokens = estimate_tokens(compact_suffix)
    if not compact_suffix.isascii():
        raise ValueError("resolved scene layers must compile to ASCII")
    fingerprints = LayerFingerprints(
        spatial=spatial_fingerprint,
        characters=stable_hash(characters),
        setting=stable_hash(setting),
        style=stable_hash(style),
        presentation=stable_hash(
            {
                "source": presentation_source,
                "roles": role_presentations,
                "appearance_bias": presentation.appearance_bias,
            }
        ),
    )
    geometry_tokens = estimate_tokens(geometry)
    verbose_layer_tokens = estimate_tokens(
        json.dumps(
            {
                "characters": [
                    profile.model_dump(mode="json") for profile in characters
                ],
                "setting": setting.model_dump(mode="json"),
                "style": style.model_dump(mode="json"),
                "presentation_source": presentation_source.model_dump(mode="json"),
                "presentation": presentation.model_dump(mode="json"),
                "visibility": visibility.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return ResolvedSceneLayers(
        characters=characters,
        setting=setting,
        style=style,
        presentation_source=presentation_source,
        required_environment_supports=required_environment_supports,
        presentation=presentation,
        visibility=visibility,
        fingerprints=fingerprints,
        compact_suffix=compact_suffix,
        token_metrics=TokenMetrics(
            geometry_estimated_tokens=geometry_tokens,
            verbose_layer_estimated_tokens=verbose_layer_tokens,
            layer_estimated_tokens=layer_tokens,
            compact_saved_tokens=verbose_layer_tokens - layer_tokens,
            final_estimated_tokens=geometry_tokens + layer_tokens,
        ),
    )


def layer_issues(
    layers: ResolvedSceneLayers,
    cast_roles: list[str],
) -> list[str]:
    issues: list[str] = []
    roles = [profile.role for profile in layers.characters]
    presentation_roles = [item.role for item in layers.presentation.roles]
    if roles != cast_roles or presentation_roles != cast_roles:
        issues.append("layer roles changed exact cast or order")
    if layers.presentation.spatial_fingerprint != layers.fingerprints.spatial:
        issues.append("presentation changed spatial fingerprint")
    if (
        layers.presentation.motivated_light_source
        not in layers.setting.motivated_light_sources
    ):
        issues.append("lighting source is not motivated by setting")
    realized_supports = {item.support for item in layers.setting.support_realizations}
    missing_supports = set(layers.required_environment_supports).difference(
        realized_supports
    )
    if missing_supports:
        issues.append(f"setting lacks required supports: {sorted(missing_supports)}")
    if not set(layers.setting.mood_tags).intersection(layers.style.compatible_moods):
        issues.append("style is incompatible with setting mood")
    for role, required in layers.visibility.required_regions_by_role.items():
        presentation = next(
            item for item in layers.presentation.roles if item.role == role
        )
        if set(required).intersection(INTIMATE_REGIONS) and (
            presentation.wardrobe_state != "clear_of_required_contacts"
        ):
            issues.append(f"{role} wardrobe blocks a required contact")
    for role, emitted in layers.visibility.emitted_body_details_by_role.items():
        visible = set(layers.visibility.visible_regions_by_role.get(role, []))
        if emitted and not visible.intersection(INTIMATE_REGIONS):
            issues.append(f"{role} emits invisible body details")
    forbidden_words = re.compile(
        r"\b(?:crowd|onlookers|attendants|guards|servants)\b",
        re.I,
    )
    if forbidden_words.search(layers.compact_suffix):
        issues.append("setting introduces unplanned background people")
    return issues
