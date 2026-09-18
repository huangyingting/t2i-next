"""Bounded, offline recipes for neutral clothed adult figure studies.

Camera choices describe artistic intent, not simulated optics or measured space.
Support descriptions are contact-ready phrases; callers render only the supports
required by a pose, rather than every available object in a presentation.
Support profiles are qualitative scene-design requirements, not measured reach
or biomechanics. Custom presentations may use other bounded profiles; callers
select profiles that fit the pose when constructing the scene.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from .pose_reference_types import (
    CameraHeight,
    CameraView,
    Identifier,
    ReferenceModel,
    Surface,
)


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("reference text must not be blank")
    return value


ReferenceText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=400, pattern=r"^[\x20-\x7e]+$"),
    AfterValidator(_nonblank),
]

SurfaceHeight = Literal[
    "ground",
    "below_standing_knee",
    "seated_knee",
    "standing_hip",
    "standing_shoulder",
    "seated_upper_back",
    "lying_head",
]
SurfaceExtent = Literal[
    "whole_body",
    "seat_and_thighs",
    "upper_back",
    "upper_body",
    "both_palms_and_forearms",
    "whole_foot",
    "head_and_neck",
]
SurfaceOrientation = Literal["horizontal", "vertical"]

SUPPORT_PROFILES: dict[
    Surface, tuple[SurfaceHeight, SurfaceExtent, SurfaceOrientation]
] = {
    "floor": ("ground", "whole_body", "horizontal"),
    "mat": ("ground", "whole_body", "horizontal"),
    "chair_seat": ("seated_knee", "seat_and_thighs", "horizontal"),
    "chair_back": ("seated_upper_back", "upper_back", "vertical"),
    "wall": ("standing_shoulder", "upper_body", "vertical"),
    "table": ("standing_hip", "both_palms_and_forearms", "horizontal"),
    "step": ("below_standing_knee", "whole_foot", "horizontal"),
    "headrest": ("lying_head", "head_and_neck", "horizontal"),
}


class ReferenceCamera(ReferenceModel):
    camera_id: Identifier
    coordinate_frame: Literal["room_axes"]
    view: CameraView
    height: CameraHeight
    framing: Literal["full_body"] = "full_body"
    lens: Literal["normal", "short_telephoto"]
    perspective: Literal["natural", "gentle_compression"]
    subject_distance: Literal["full_body_clearance", "extended_full_body_clearance"]
    focus: Literal["face_and_body", "whole_figure_and_supports"]
    depth_of_field: Literal["moderate", "deep"]
    negative_space: Literal["balanced", "left", "right"]
    foreground: Literal["none", "edge_frame"]

    @model_validator(mode="after")
    def coherent_camera_recipe(self) -> ReferenceCamera:
        triples = {
            ("normal", "natural", "full_body_clearance"),
            (
                "short_telephoto",
                "gentle_compression",
                "extended_full_body_clearance",
            ),
        }
        if (self.lens, self.perspective, self.subject_distance) not in triples:
            raise ValueError("lens, perspective, and subject distance must be coherent")
        return self


class ReferenceSubject(ReferenceModel):
    subject_id: Identifier
    adult_age: int = Field(ge=25, strict=True)
    appearance: ReferenceText
    outfit: ReferenceText
    body_scale: float = Field(ge=0.85, le=1.15, allow_inf_nan=False)
    coverage: Literal["fully_clothed"] = "fully_clothed"


class ReferenceSurfaceRealization(ReferenceModel):
    surface: Surface
    object_id: Identifier
    description: ReferenceText
    height: SurfaceHeight
    extent: SurfaceExtent
    orientation: SurfaceOrientation


class ReferencePresentation(ReferenceModel):
    presentation_id: Identifier
    setting: ReferenceText
    palette: ReferenceText
    lighting: ReferenceText
    finish: ReferenceText
    space: Literal["standard", "extended"]
    supports: tuple[ReferenceSurfaceRealization, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent_support_objects(self) -> ReferencePresentation:
        by_surface = {support.surface: support for support in self.supports}
        if len(by_surface) != len(self.supports):
            raise ValueError("presentation surface mappings must be unique")
        seat, back = by_surface.get("chair_seat"), by_surface.get("chair_back")
        if seat is not None and back is not None and seat.object_id != back.object_id:
            raise ValueError("chair seat and back must belong to the same chair object")
        by_object: dict[str, set[Surface]] = {}
        for support in self.supports:
            by_object.setdefault(support.object_id, set()).add(support.surface)
        for surfaces in by_object.values():
            if len(surfaces) > 1 and surfaces != {"chair_seat", "chair_back"}:
                raise ValueError("unrelated surfaces must not share an object_id")
        if "headrest" in by_surface and "mat" not in by_surface:
            raise ValueError("a headrest requires a mat in the same presentation")
        return self


_CAMERAS = (
    ReferenceCamera(
        camera_id="front_eye",
        coordinate_frame="room_axes",
        view="front",
        height="subject_eye_level",
        lens="normal",
        perspective="natural",
        subject_distance="full_body_clearance",
        focus="face_and_body",
        depth_of_field="moderate",
        negative_space="balanced",
        foreground="none",
    ),
    ReferenceCamera(
        camera_id="left_eye",
        coordinate_frame="room_axes",
        view="left_three_quarter",
        height="subject_eye_level",
        lens="short_telephoto",
        perspective="gentle_compression",
        subject_distance="extended_full_body_clearance",
        focus="face_and_body",
        depth_of_field="moderate",
        negative_space="right",
        foreground="edge_frame",
    ),
    ReferenceCamera(
        camera_id="right_eye",
        coordinate_frame="room_axes",
        view="right_three_quarter",
        height="subject_eye_level",
        lens="short_telephoto",
        perspective="gentle_compression",
        subject_distance="extended_full_body_clearance",
        focus="face_and_body",
        depth_of_field="deep",
        negative_space="left",
        foreground="none",
    ),
    ReferenceCamera(
        camera_id="left_high",
        coordinate_frame="room_axes",
        view="left_three_quarter",
        height="slightly_above_subject",
        lens="normal",
        perspective="natural",
        subject_distance="full_body_clearance",
        focus="whole_figure_and_supports",
        depth_of_field="deep",
        negative_space="right",
        foreground="none",
    ),
    ReferenceCamera(
        camera_id="right_high",
        coordinate_frame="room_axes",
        view="right_three_quarter",
        height="slightly_above_subject",
        lens="normal",
        perspective="natural",
        subject_distance="full_body_clearance",
        focus="whole_figure_and_supports",
        depth_of_field="moderate",
        negative_space="left",
        foreground="edge_frame",
    ),
)

_SUBJECTS = (
    ReferenceSubject(
        subject_id="mara",
        adult_age=32,
        body_scale=0.98,
        appearance=(
            "Mara, a woman with deep brown skin, close-cropped black curls, "
            "dark brown eyes, and a rounded face"
        ),
        outfit=(
            "an opaque ochre long-sleeved cotton shirt, fully covering charcoal "
            "full-length trousers, dark socks, and closed-toe flat leather shoes"
        ),
    ),
    ReferenceSubject(
        subject_id="elias",
        adult_age=46,
        body_scale=1.06,
        appearance=(
            "Elias, a man with olive skin, short salt-and-pepper hair, "
            "hazel eyes, and a neatly trimmed beard"
        ),
        outfit=(
            "an opaque slate-blue long-sleeved twill shirt, fully covering sand "
            "full-length trousers, navy socks, and closed-toe flat canvas shoes"
        ),
    ),
    ReferenceSubject(
        subject_id="june",
        adult_age=58,
        body_scale=1.0,
        appearance=(
            "June, a woman with light freckled skin, a straight silver bob, "
            "gray eyes, and rectangular glasses"
        ),
        outfit=(
            "an opaque forest-green long-sleeved poplin shirt, fully covering "
            "navy full-length trousers, gray socks, and closed-toe flat shoes"
        ),
    ),
    ReferenceSubject(
        subject_id="ren",
        adult_age=27,
        body_scale=0.94,
        appearance=(
            "Ren, a nonbinary adult with medium tan skin, straight black hair "
            "tied back, brown eyes, and prominent straight eyebrows"
        ),
        outfit=(
            "an opaque rust-red long-sleeved linen shirt, fully covering stone "
            "full-length trousers, brown socks, and closed-toe flat lace-up shoes"
        ),
    ),
)


def _support(
    surface: Surface, object_id: str, description: str
) -> ReferenceSurfaceRealization:
    height, extent, orientation = SUPPORT_PROFILES[surface]
    return ReferenceSurfaceRealization(
        surface=surface,
        object_id=object_id,
        description=description,
        height=height,
        extent=extent,
        orientation=orientation,
    )


_PRESENTATIONS = (
    ReferencePresentation(
        presentation_id="daylight_atelier",
        setting="a spacious figure-drawing atelier with tall north-facing windows",
        palette="warm oak, chalk white, muted sage, and soft charcoal",
        lighting=(
            "broad daylight from the visible windows at image-frame left, softened "
            "by linen blinds, with gentle fill from the opposite white wall"
        ),
        finish="a restrained matte portrait photograph with clear fabric texture",
        space="extended",
        supports=(
            _support("floor", "oak_floor", "the dry, level oak floor"),
            _support("mat", "sage_mat", "the flat, non-slip sage exercise mat"),
            _support(
                "headrest", "sage_towel",
                "the folded sage towel resting flat on the mat",
            ),
            _support(
                "chair_seat", "oak_chair",
                "the broad seat of the stable, armless oak chair",
            ),
            _support(
                "chair_back", "oak_chair",
                "the solid back of the same stable, armless oak chair",
            ),
            _support("wall", "plaster_wall", "the solid chalk-white plaster wall"),
            _support(
                "table", "oak_table",
                "the level top of the sturdy, stationary oak table",
            ),
            _support(
                "step", "sage_step",
                "the broad non-slip top of the low, fixed sage step",
            ),
        ),
    ),
    ReferencePresentation(
        presentation_id="window_portrait_room",
        setting="a quiet portrait room beside a broad east-facing window",
        palette="cream plaster, honey-colored beech, and muted blue",
        lighting=(
            "soft morning light through the visible sheer window curtain at "
            "image-frame right, with fill reflected from a cream wall"
        ),
        finish="a softly textured colored-pencil study with distinct contours",
        space="standard",
        supports=(
            _support("floor", "beech_floor", "the dry, level beech floor"),
            _support(
                "chair_seat", "blue_chair",
                "the wide seat of the sturdy, armless blue wooden chair",
            ),
            _support(
                "chair_back", "blue_chair",
                "the solid back of the same sturdy, armless blue wooden chair",
            ),
            _support("wall", "cream_wall", "the solid cream plaster wall"),
        ),
    ),
    ReferencePresentation(
        presentation_id="rehearsal_stage",
        setting="a spacious, level rehearsal stage with an unadorned backdrop",
        palette="warm gray, muted terracotta, and pale ash wood",
        lighting=(
            "a visible diffused stage work light at the upper left image-frame edge "
            "provides a broad key, balanced by soft overhead work lights"
        ),
        finish="a clean gouache figure study with broad, readable shadow shapes",
        space="extended",
        supports=(
            _support("floor", "stage_floor", "the dry, level gray stage floor"),
            _support("mat", "rust_mat", "the flat, non-slip terracotta exercise mat"),
            _support(
                "headrest", "terracotta_towel",
                "the folded terracotta towel resting flat on the mat",
            ),
            _support(
                "table", "ash_table",
                "the level top of the sturdy, stationary ash table",
            ),
            _support(
                "step", "stage_step",
                "the broad non-slip top of the low, fixed stage step",
            ),
        ),
    ),
    ReferencePresentation(
        presentation_id="print_studio",
        setting="an orderly print studio with a clear central posing area",
        palette="off-white, graphite gray, and muted teal",
        lighting=(
            "a visible high frosted window supplies even daylight from image-frame "
            "left, with a shaded ceiling lamp filling the room"
        ),
        finish="a fine-grained editorial portrait with subdued contrast",
        space="standard",
        supports=(
            _support("floor", "studio_floor", "the dry, level matte gray floor"),
            _support("wall", "teal_wall", "the solid muted-teal plaster wall"),
            _support(
                "table", "work_table",
                "the cleared, level top of the heavy, stationary work table",
            ),
        ),
    ),
    ReferencePresentation(
        presentation_id="drawing_classroom",
        setting="a calm drawing classroom with a clear floor and pale walls",
        palette="pale ivory, muted burgundy, and natural birch",
        lighting=(
            "a visible frosted skylight provides broad overhead daylight, "
            "with soft fill reflected from the pale classroom walls"
        ),
        finish="an ink-and-wash study with light color washes and legible hands",
        space="standard",
        supports=(
            _support("floor", "birch_floor", "the dry, level birch floor"),
            _support(
                "mat", "burgundy_mat", "the flat, non-slip burgundy exercise mat"
            ),
            _support(
                "headrest", "burgundy_towel",
                "the folded burgundy towel resting flat on the mat",
            ),
            _support(
                "chair_seat", "birch_chair",
                "the broad seat of the stable, armless birch chair",
            ),
            _support(
                "chair_back", "birch_chair",
                "the solid back of the same stable, armless birch chair",
            ),
            _support(
                "step", "birch_step",
                "the broad non-slip top of the low, fixed birch step",
            ),
        ),
    ),
)


def reference_cameras() -> tuple[ReferenceCamera, ...]:
    return _CAMERAS


def reference_subjects() -> tuple[ReferenceSubject, ...]:
    return _SUBJECTS


def reference_presentations() -> tuple[ReferencePresentation, ...]:
    return _PRESENTATIONS


def presentation_supports(
    presentation: ReferencePresentation, required_surfaces: tuple[Surface, ...]
) -> bool:
    available = {support.surface for support in presentation.supports}
    return set(required_surfaces) <= available


def presentation_accepts_camera(
    presentation: ReferencePresentation, camera: ReferenceCamera
) -> bool:
    return (
        camera.subject_distance != "extended_full_body_clearance"
        or presentation.space == "extended"
    )


def render_reference_camera(camera: ReferenceCamera) -> str:
    view = {
        "front": "room front",
        "left_three_quarter": "room left three-quarter",
        "right_three_quarter": "room right three-quarter",
    }[camera.view]
    height = (
        "at the subject's eye level"
        if camera.height == "subject_eye_level"
        else "slightly above the subject"
    )
    distance = (
        "Allow full-body clearance around the figure."
        if camera.subject_distance == "full_body_clearance"
        else "Stand farther back for extended full-body clearance around the figure."
    )
    focus = (
        "the face and clothed body"
        if camera.focus == "face_and_body"
        else "the whole figure, including facial features, and the needed supports"
    )
    negative_space = (
        "Balance the negative space on the image-frame left and right."
        if camera.negative_space == "balanced"
        else f"Leave more negative space on the image-frame {camera.negative_space}."
    )
    foreground = (
        "Keep the image-frame foreground clear and outside the figure's silhouette."
        if camera.foreground == "none"
        else (
            "Let a subtle room edge frame the outer image-frame border, entirely "
            "outside the figure's silhouette and accessible contact boundaries."
        )
    )
    return (
        f"Frame the whole figure from a {view} view, {height}. "
        f"Use a {camera.lens.replace('_', ' ')} lens with "
        f"{camera.perspective.replace('_', ' ')} perspective. {distance} "
        f"Keep {focus} in focus with {camera.depth_of_field} depth of field. "
        f"{negative_space} {foreground} "
        "Keep the whole figure uncropped and accessible contact boundaries clear. "
        "Naturally occluded undersides remain hidden; do not add extra limbs "
        "to expose them. Keep supports in their pose-required positions; do not "
        "move them to satisfy the camera. Retain the pose's head orientation "
        "and gaze."
    )


def render_reference_subject(subject: ReferenceSubject) -> str:
    return (
        f"A neutral, non-sexual figure study of exactly one adult aged "
        f"{subject.adult_age}, {subject.coverage.replace('_', ' ')}. "
        f"{subject.appearance}, wearing {subject.outfit}. "
        "Keep the opaque everyday clothing fully covering the torso, arms, "
        "and legs, with shoes on both feet."
    )


def render_reference_presentation(presentation: ReferencePresentation) -> str:
    """Render the environment; callers separately resolve required supports."""
    lighting = presentation.lighting[0].upper() + presentation.lighting[1:]
    space = (
        "Leave comfortable space for a clear full-body view."
        if presentation.space == "standard"
        else (
            "Leave generous open space for a clear full-body view and a camera "
            "set farther back."
        )
    )
    return (
        f"Place the figure in {presentation.setting}. "
        f"Surround the figure with {presentation.palette}. {lighting}. "
        f"Render the image as {presentation.finish}. {space} "
        "Preserve light and gentle fill on the face so facial features remain "
        "visible; do not reduce the figure to a full silhouette. "
        "Keep visible hands, feet, and accessible contact boundaries distinct "
        "from the surroundings; naturally occluded undersides remain hidden."
    )
