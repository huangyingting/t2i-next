from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
]
RoleCode = Annotated[str, StringConstraints(pattern=r"^[fm][1-9][0-9]*$")]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
PRESENTATION_ROLE_CODES = ("f1", "f2", "f3", "m1", "m2")
INTIMATE_REGIONS = {
    "anus",
    "clitoris",
    "penis",
    "vagina",
    "vulva",
}
WARDROBE_ACCESS_REGIONS = INTIMATE_REGIONS | {
    "breast",
    "buttock",
    "pubic_region",
}
RETAINED_COVERAGE_REGIONS = [
    "shoulders",
    "arms",
    "upper_back",
    "abdomen",
    "outer_hips",
    "outer_thighs",
    "lower_legs",
]
FOOTWEAR_PATTERN_TEXT = (
    r"(?i)^.*\b(?:boots?|heels?|sandals?|shoes?|slippers?|pumps?|mules?|"
    r"sneakers?|loafers?|platforms?)\b.*$"
)
FOOTWEAR_PATTERN = re.compile(FOOTWEAR_PATTERN_TEXT)
FootwearDescription = Annotated[
    str,
    StringConstraints(min_length=3, max_length=80, pattern=FOOTWEAR_PATTERN_TEXT),
]
EXTRA_CAST_HAZARDS = {
    "background_people",
    "humanoid_statues",
    "mirrors_showing_extra_bodies",
    "person_shaped_shadows",
}
DEFAULT_ROLE_STYLE_DETAILS = (
    ("f1", "structured silhouette", "ivory-accented", "pearl", "defined eyes"),
    ("f2", "draped silhouette", "burgundy-accented", "silver", "soft contour"),
    (
        "f3",
        "asymmetric silhouette",
        "emerald-accented",
        "crystal",
        "graphic liner",
    ),
    ("m1", "tailored silhouette", "onyx-accented", "steel", "clean contour"),
    ("m2", "layered silhouette", "cobalt-accented", "leather", "matte finish"),
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CharacterProfile(StrictModel):
    role: RoleCode
    adult_age: int = Field(ge=21, le=75)
    nationality: str = Field(min_length=2, max_length=40)
    height_cm: int = Field(ge=140, le=210)
    weight_kg: int = Field(ge=38, le=160)
    body_build: str = Field(min_length=3, max_length=60)
    body_proportions: str = Field(min_length=3, max_length=80)
    skin_tone: str = Field(min_length=3, max_length=50)
    face_features: str = Field(min_length=5, max_length=100)
    hair_style: str = Field(min_length=3, max_length=70)
    hair_color: str = Field(min_length=3, max_length=40)
    intimate_anatomy: str = Field(min_length=5, max_length=100)
    pubic_hair: str = Field(min_length=3, max_length=60)
    fantasy_body_traits: list[str] = Field(default_factory=list, max_length=4)


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


class RoleStylingPreset(StrictModel):
    role: RoleCode
    wardrobe_theme: str = Field(min_length=4, max_length=100)
    footwear_theme: FootwearDescription
    accessory_theme: list[str] = Field(min_length=2, max_length=4)
    makeup_and_grooming_theme: str = Field(min_length=3, max_length=80)


class PresentationPreset(StrictModel):
    presentation_id: Identifier
    coverage_mode: Literal["selective_access", "styled_nude"]
    role_styles: list[RoleStylingPreset] = Field(min_length=1, max_length=5)
    appearance_bias: list[Identifier] = Field(default_factory=list, max_length=4)
    compatible_moods: list[Identifier] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def coverage_has_matching_wardrobe(self) -> PresentationPreset:
        roles = [style.role for style in self.role_styles]
        if len(set(roles)) != len(roles):
            raise ValueError("presentation role styles contain duplicate roles")
        unsupported_roles = set(roles).difference(PRESENTATION_ROLE_CODES)
        if unsupported_roles:
            raise ValueError(
                f"presentation contains unsupported roles: {sorted(unsupported_roles)}"
            )
        wardrobes = [
            style.wardrobe_theme.strip().lower() for style in self.role_styles
        ]
        if self.coverage_mode == "selective_access":
            if "none" in wardrobes:
                raise ValueError(
                    "selective-access presentation requires every role wardrobe"
                )
            if len(set(wardrobes)) != len(wardrobes):
                raise ValueError(
                    "selective-access role wardrobes must be visibly distinct"
                )
        elif set(wardrobes) != {"none"}:
            raise ValueError("styled-nude role wardrobes must all be none")
        footwear = [
            style.footwear_theme.strip().lower() for style in self.role_styles
        ]
        if len(set(footwear)) != len(footwear):
            raise ValueError("role footwear must be visibly distinct")
        if any(
            not FOOTWEAR_PATTERN.search(style.footwear_theme)
            for style in self.role_styles
        ):
            raise ValueError("every role footwear theme must name a footwear type")
        accessory_sets = [
            tuple(item.strip().lower() for item in style.accessory_theme)
            for style in self.role_styles
        ]
        if len(set(accessory_sets)) != len(accessory_sets):
            raise ValueError("role accessory sets must be visibly distinct")
        return self


class SceneLayerInputs(StrictModel):
    setting: SettingPreset
    style: StylePreset
    presentation: PresentationPreset


class RolePresentation(StrictModel):
    role: RoleCode
    wardrobe: str
    wardrobe_state: Identifier
    exposed_regions: list[Identifier] = Field(default_factory=list, max_length=8)
    covered_regions: list[Identifier] = Field(default_factory=list, max_length=10)
    footwear: str
    accessories: list[str] = Field(default_factory=list, max_length=4)
    makeup_and_grooming: str
    hair_styling: str
    surface_finish: str


class RoleExpression(StrictModel):
    role: RoleCode
    intensity: Identifier
    gaze_target: Identifier
    eye_behavior: str
    brow_behavior: str
    mouth_behavior: str
    facial_tension: str
    interaction_response: str


class PresentationPlan(StrictModel):
    scene_id: Annotated[str, StringConstraints(pattern=r"^S\d{2}$")]
    spatial_fingerprint: Fingerprint
    setting_id: Identifier
    style_id: Identifier
    presentation_id: Identifier
    roles: list[RolePresentation] = Field(min_length=1, max_length=5)
    expressions: list[RoleExpression] = Field(min_length=1, max_length=5)
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
    footwear_theme: str = "coordinated dress shoes",
    accessory_theme: tuple[str, ...] = ("minimal jewelry", "slim wrist cuff"),
    makeup_theme: str = "polished editorial makeup",
    appearance_bias: tuple[str, ...] = (),
    coverage_mode: Literal["selective_access", "styled_nude"] = "selective_access",
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
            coverage_mode=coverage_mode,
            role_styles=[
                RoleStylingPreset(
                    role=role,
                    wardrobe_theme=(
                        f"{wardrobe_theme}, {wardrobe_detail}"
                        if coverage_mode == "selective_access"
                        else "none"
                    ),
                    footwear_theme=f"{footwear_detail} {footwear_theme}",
                    accessory_theme=[
                        *accessory_theme,
                        f"{accessory_detail} accent",
                    ][:4],
                    makeup_and_grooming_theme=(
                        f"{makeup_theme}, {grooming_detail}"
                        if role.startswith("f")
                        else (
                            "no makeup with polished masculine grooming, "
                            f"{grooming_detail}"
                        )
                    ),
                )
                for (
                    role,
                    wardrobe_detail,
                    footwear_detail,
                    accessory_detail,
                    grooming_detail,
                ) in DEFAULT_ROLE_STYLE_DETAILS
            ],
            appearance_bias=list(appearance_bias),
            compatible_moods=list(mood_tags),
        ),
    )


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


def resolve_role_expressions(
    *,
    scene_id: str,
    cast_roles: list[str],
    focus_role: str,
    activity_id: str,
    interaction_partners_by_role: dict[str, list[str]],
) -> list[RoleExpression]:
    focus_variants = (
        (
            "peak_orgasm",
            "eyes squeezed shut",
            "brows raised and drawn together",
            "mouth open in an involuntary O shape",
            "strong cheek, jaw, and neck tension at release",
        ),
        (
            "intense_release",
            "eyes rolled upward beneath half-lowered lids",
            "inner brows lifted",
            "lips parted on a sharp exhale",
            "visible facial tremor and released jaw",
        ),
        (
            "rising_arousal",
            "heavy-lidded focused eyes",
            "brows softly contracted",
            "lips parted with controlled breathing",
            "building tension through cheeks and jaw",
        ),
        (
            "controlled_focus",
            "steady alert eyes",
            "brows level and intent",
            "mouth slightly open",
            "restrained concentration in the jaw",
        ),
    )
    focus_variant = focus_variants[int(scene_id[1:]) % len(focus_variants)]
    expressions = []
    for role_index, role in enumerate(cast_roles):
        partners = interaction_partners_by_role.get(role, [])
        if not partners and len(cast_roles) > 1:
            partners = [
                cast_roles[(role_index + offset) % len(cast_roles)]
                for offset in range(1, len(cast_roles))
            ]
        gaze_target = partners[0] if partners else "camera"
        if role == focus_role:
            intensity, eyes, brows, mouth, tension = focus_variant
            if intensity == "peak_orgasm":
                gaze_target = "inward"
        else:
            intensity = "responsive_arousal"
            eyes = f"eyes directed toward {gaze_target.upper()}"
            brows = "brows actively responding to the partner"
            mouth = (
                "lips parted with exertion"
                if role_index % 2
                else "mouth set in concentrated breathing"
            )
            tension = "focused cheek and jaw tension"
        response = (
            f"visibly responding to {gaze_target.upper()} during "
            f"{activity_id.replace('_', ' ')}"
            if gaze_target in cast_roles
            else f"visibly responding to {activity_id.replace('_', ' ')}"
        )
        expressions.append(
            RoleExpression(
                role=role,
                intensity=intensity,
                gaze_target=gaze_target,
                eye_behavior=eyes,
                brow_behavior=brows,
                mouth_behavior=mouth,
                facial_tension=tension,
                interaction_response=response,
            )
        )
    return expressions


def resolve_scene_layers(
    *,
    scene_id: str,
    spatial_fingerprint: str,
    geometry: str,
    cast_roles: list[str],
    character_profiles: list[CharacterProfile],
    body_level: str,
    setting: SettingPreset,
    style: StylePreset,
    presentation_source: PresentationPreset,
    required_environment_supports: list[str],
    required_regions_by_role: dict[str, list[str]],
    visible_regions_by_role: dict[str, list[str]],
    activity_id: str = "unspecified_activity",
    focus_role: str | None = None,
    interaction_partners_by_role: dict[str, list[str]] | None = None,
) -> ResolvedSceneLayers:
    profile_by_role = {profile.role: profile for profile in character_profiles}
    missing_profiles = set(cast_roles).difference(profile_by_role)
    if missing_profiles:
        raise ValueError(
            f"character blueprint lacks roles: {sorted(missing_profiles)}"
        )
    characters = [profile_by_role[role] for role in cast_roles]
    expressions = resolve_role_expressions(
        scene_id=scene_id,
        cast_roles=cast_roles,
        focus_role=focus_role or cast_roles[0],
        activity_id=activity_id,
        interaction_partners_by_role=interaction_partners_by_role or {},
    )
    role_presentations = []
    role_style_map = {
        role_style.role: role_style
        for role_style in presentation_source.role_styles
    }
    for profile in characters:
        required = set(required_regions_by_role.get(profile.role, []))
        styled_nude = presentation_source.coverage_mode == "styled_nude"
        role_style = role_style_map[profile.role]
        exposed_regions = (
            ["whole_body"]
            if styled_nude
            else sorted(required.intersection(WARDROBE_ACCESS_REGIONS))
        )
        wardrobe_state = (
            "styled_nude"
            if styled_nude
            else "localized_exposure"
            if exposed_regions
            else "fully_dressed"
        )
        wardrobe = "no garments" if styled_nude else role_style.wardrobe_theme
        role_presentations.append(
            RolePresentation(
                role=profile.role,
                wardrobe=wardrobe,
                wardrobe_state=wardrobe_state,
                exposed_regions=exposed_regions,
                covered_regions=[] if styled_nude else RETAINED_COVERAGE_REGIONS,
                footwear=role_style.footwear_theme,
                accessories=list(role_style.accessory_theme),
                makeup_and_grooming=role_style.makeup_and_grooming_theme,
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
        expressions=expressions,
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
                profile.intimate_anatomy,
                profile.pubic_hair,
            ]
            omitted[profile.role] = []
        else:
            emitted[profile.role] = []
            omitted[profile.role] = [
                "intimate_anatomy",
                "pubic_hair",
            ]
    visibility = FinalVisibilityPlan(
        required_regions_by_role=required_regions_by_role,
        visible_regions_by_role=visible_regions_by_role,
        emitted_body_details_by_role=emitted,
        omitted_body_details_by_role=omitted,
    )
    character_phrases = [
        (
            f"{profile.role.upper()} is {profile.height_cm} cm and "
            f"{profile.weight_kg} kg, with {profile.body_build}, "
            f"{profile.body_proportions}, {profile.skin_tone} skin, "
            f"{profile.face_features}, and {profile.hair_color} "
            f"{profile.hair_style} hair"
        )
        for profile in characters
    ]
    wardrobe_phrases = []
    for role in role_presentations:
        styling_extras = (
            f"wearing {role.footwear} with {', '.join(role.accessories)}; "
            f"{role.makeup_and_grooming}"
        )
        if role.wardrobe_state == "styled_nude":
            wardrobe_phrases.append(
                f"{role.role.upper()} is intentionally fully nude for this scene, "
                f"but remains styled by {styling_extras}"
            )
            continue
        exposed_region_phrase = ", ".join(
            region.replace("_", " ") for region in role.exposed_regions
        )
        exposure = (
            f"only {exposed_region_phrase} locally exposed for contact"
            if role.exposed_regions
            else "no body region exposed by the wardrobe"
        )
        coverage = ", ".join(
            region.replace("_", " ") for region in role.covered_regions
        )
        wardrobe_phrases.append(
            f"{role.role.upper()} remains visibly dressed in {role.wardrobe}, "
            f"{exposure}; retained garments cover {coverage}; "
            f"all unlisted body regions remain clothed; {styling_extras}"
        )
    visible_detail_phrases = [
        f"{role.upper()} {', '.join(details)}"
        for role, details in emitted.items()
        if details
    ]
    expression_phrases = [
        (
            f"{expression.role.upper()} shows "
            f"{expression.intensity.replace('_', ' ')}: "
            f"{expression.eye_behavior}, {expression.brow_behavior}, "
            f"{expression.mouth_behavior}, {expression.facial_tension}; "
            f"{expression.interaction_response}"
        )
        for expression in expressions
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
            f"Wardrobe: {'; '.join(wardrobe_phrases)}"
        ),
        f"Expression: {'; '.join(expression_phrases)}",
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
            (
                "Every pelvis connects to exactly two legs; no limb is duplicated, "
                "fused, detached or assigned to two bodies"
            ),
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
    expression_roles = [item.role for item in layers.presentation.expressions]
    if (
        roles != cast_roles
        or presentation_roles != cast_roles
        or expression_roles != cast_roles
    ):
        issues.append("layer roles changed exact cast or order")
    if len(cast_roles) > 1 and not any(
        expression.gaze_target in cast_roles
        and expression.gaze_target != expression.role
        for expression in layers.presentation.expressions
    ):
        issues.append("multi-actor expressions lack interpersonal interaction")
    if len(cast_roles) > 1:
        role_presentations = layers.presentation.roles
        if layers.presentation_source.coverage_mode == "selective_access" and len(
            {item.wardrobe.strip().lower() for item in role_presentations}
        ) != len(role_presentations):
            issues.append("multi-actor wardrobes are not role-distinct")
        if len(
            {item.footwear.strip().lower() for item in role_presentations}
        ) != len(role_presentations):
            issues.append("multi-actor footwear is not role-distinct")
        styling_signatures = {
            (
                tuple(accessory.strip().lower() for accessory in item.accessories),
                item.makeup_and_grooming.strip().lower(),
            )
            for item in role_presentations
        }
        if len(styling_signatures) != len(role_presentations):
            issues.append(
                "multi-actor accessories, makeup, and grooming are not role-distinct"
            )
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
        required_exposure = set(required).intersection(WARDROBE_ACCESS_REGIONS)
        actual_exposure = set(presentation.exposed_regions)
        styled_nude = presentation.wardrobe_state == "styled_nude"
        if not styled_nude and required_exposure != actual_exposure:
            issues.append(f"{role} wardrobe blocks a required contact")
        expected_state = (
            "styled_nude"
            if layers.presentation_source.coverage_mode == "styled_nude"
            else "localized_exposure"
            if required_exposure
            else "fully_dressed"
        )
        if presentation.wardrobe_state != expected_state:
            issues.append(f"{role} wardrobe state contradicts its exposure ledger")
        if actual_exposure.intersection(presentation.covered_regions):
            issues.append(f"{role} wardrobe exposes and covers the same region")
    for role, emitted in layers.visibility.emitted_body_details_by_role.items():
        visible = set(layers.visibility.visible_regions_by_role.get(role, []))
        if emitted and not visible.intersection(INTIMATE_REGIONS):
            issues.append(f"{role} emits invisible body details")
    forbidden_words = re.compile(
        r"\b(?:crowd|onlookers|attendants|guards|servants)\b",
        re.I,
    )
    setting_text = " ".join(
        (
            layers.setting.location,
            layers.setting.architecture,
            *layers.setting.materials,
            *layers.setting.environment_props,
            *layers.setting.motivated_light_sources,
        )
    )
    if forbidden_words.search(setting_text):
        issues.append("setting introduces unplanned background people")
    return issues
