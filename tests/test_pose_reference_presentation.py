from __future__ import annotations

import ast
import importlib.util
import itertools
import sys
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

import t2i_spatial_pipeline.pose_reference_presentation as presentation_module
from t2i_spatial_pipeline.pose_reference_presentation import (
    SUPPORT_PROFILES,
    ReferenceCamera,
    ReferencePresentation,
    ReferenceSubject,
    ReferenceSurfaceRealization,
    SurfaceExtent,
    SurfaceHeight,
    SurfaceOrientation,
    presentation_accepts_camera,
    presentation_supports,
    reference_cameras,
    reference_presentations,
    reference_subjects,
    render_reference_camera,
    render_reference_presentation,
    render_reference_subject,
)
from t2i_spatial_pipeline.pose_reference_types import ReferenceModel, Surface

CAMERAS = reference_cameras()
SUBJECTS = reference_subjects()
PRESENTATIONS = reference_presentations()
SURFACES = get_args(Surface)


@pytest.mark.parametrize(
    ("lens", "perspective", "distance"),
    itertools.product(
        ("normal", "short_telephoto"),
        ("natural", "gentle_compression"),
        ("full_body_clearance", "extended_full_body_clearance"),
    ),
)
def test_camera_accepts_only_coherent_optical_recipes(
    lens: str, perspective: str, distance: str
) -> None:
    payload = CAMERAS[0].model_dump()
    payload.update(lens=lens, perspective=perspective, subject_distance=distance)
    if (lens, perspective, distance) in {
        ("normal", "natural", "full_body_clearance"),
        ("short_telephoto", "gentle_compression", "extended_full_body_clearance"),
    }:
        assert ReferenceCamera.model_validate(payload).lens == lens
    else:
        with pytest.raises(ValidationError, match="must be coherent"):
            ReferenceCamera.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("camera_id", "Front 1"),
        ("coordinate_frame", "anatomical_axes"),
        ("coordinate_frame", "image_frame"),
        ("view", "overhead"),
        ("height", "floor_level"),
        ("framing", "close_up"),
        ("lens", "wide_angle"),
        ("perspective", "extreme"),
        ("subject_distance", 10),
        ("focus", "background"),
        ("depth_of_field", "shallow"),
        ("negative_space", "above"),
        ("foreground", "across_body"),
        ("focal_length_mm", 85),
    ],
)
def test_camera_fields_are_bounded(field: str, value: object) -> None:
    payload = CAMERAS[0].model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        ReferenceCamera.model_validate(payload)


def test_camera_requires_explicit_room_coordinate_frame() -> None:
    payload = CAMERAS[0].model_dump()
    del payload["coordinate_frame"]
    with pytest.raises(ValidationError) as error:
        ReferenceCamera.model_validate(payload)
    assert error.value.errors()[0]["loc"] == ("coordinate_frame",)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("age", [24, 0, -1, 25.5, True, "32"])
def test_subject_rejects_invalid_age(age: object) -> None:
    payload = SUBJECTS[0].model_dump()
    payload["adult_age"] = age
    with pytest.raises(ValidationError):
        ReferenceSubject.model_validate(payload)


def test_subject_accepts_adult_age_boundary_and_requires_clothing() -> None:
    payload = SUBJECTS[0].model_dump()
    payload["adult_age"] = 25
    assert ReferenceSubject.model_validate(payload).adult_age == 25
    payload["coverage"] = "partial"
    with pytest.raises(ValidationError):
        ReferenceSubject.model_validate(payload)


@pytest.mark.parametrize("scale", [0.0, 0.84, 1.16, float("nan"), float("inf")])
def test_subject_body_scale_is_bounded_and_finite(scale: float) -> None:
    payload = SUBJECTS[0].model_dump() | {"body_scale": scale}
    with pytest.raises(ValidationError):
        ReferenceSubject.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "recipe", "field"),
    [
        (ReferenceSubject, SUBJECTS[0], "appearance"),
        (ReferenceSubject, SUBJECTS[0], "outfit"),
        (ReferenceSurfaceRealization, PRESENTATIONS[0].supports[0], "description"),
        (ReferencePresentation, PRESENTATIONS[0], "setting"),
        (ReferencePresentation, PRESENTATIONS[0], "palette"),
        (ReferencePresentation, PRESENTATIONS[0], "lighting"),
        (ReferencePresentation, PRESENTATIONS[0], "finish"),
    ],
)
@pytest.mark.parametrize(
    "text",
    [
        "", "   ", "\t", "a\tb", "a\nb", "ends with newline\n", "a\rb",
        "a\x00b", "a\x1bb", "a\x7fb", "caf\u00e9", "\u00a0", "x" * 401,
    ],
)
def test_recipe_text_is_bounded_nonblank_printable_ascii(
    model: type[ReferenceModel], recipe: ReferenceModel, field: str, text: str
) -> None:
    payload = recipe.model_dump()
    payload[field] = text
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_support_profile_vocabulary_and_curated_geometry_are_exact() -> None:
    assert get_args(SurfaceHeight) == (
        "ground", "below_standing_knee", "seated_knee", "standing_hip",
        "standing_shoulder", "seated_upper_back", "lying_head",
    )
    assert get_args(SurfaceExtent) == (
        "whole_body", "seat_and_thighs", "upper_back", "upper_body",
        "both_palms_and_forearms", "whole_foot", "head_and_neck",
    )
    assert get_args(SurfaceOrientation) == ("horizontal", "vertical")
    assert len(SURFACES) == len(SUPPORT_PROFILES) == 8
    assert set(SURFACES) == set(SUPPORT_PROFILES)
    assert SUPPORT_PROFILES == {
        "floor": ("ground", "whole_body", "horizontal"),
        "mat": ("ground", "whole_body", "horizontal"),
        "chair_seat": ("seated_knee", "seat_and_thighs", "horizontal"),
        "chair_back": ("seated_upper_back", "upper_back", "vertical"),
        "wall": ("standing_shoulder", "upper_body", "vertical"),
        "table": ("standing_hip", "both_palms_and_forearms", "horizontal"),
        "step": ("below_standing_knee", "whole_foot", "horizontal"),
        "headrest": ("lying_head", "head_and_neck", "horizontal"),
    }


@pytest.mark.parametrize("field", ("height", "extent", "orientation"))
def test_surface_geometry_fields_are_required(field: str) -> None:
    payload = PRESENTATIONS[0].supports[0].model_dump()
    del payload[field]
    with pytest.raises(ValidationError) as error:
        ReferenceSurfaceRealization.model_validate(payload)
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("height", "waist_high"),
        ("height", 1.2),
        ("extent", "unbounded"),
        ("extent", 2),
        ("orientation", "inclined"),
        ("orientation", 90),
    ],
)
def test_surface_geometry_rejects_unbounded_values(field: str, value: object) -> None:
    payload = PRESENTATIONS[0].supports[0].model_dump()
    payload[field] = value
    with pytest.raises(ValidationError) as error:
        ReferenceSurfaceRealization.model_validate(payload)
    assert error.value.errors()[0]["loc"] == (field,)
    assert error.value.errors()[0]["type"] == "literal_error"


@pytest.mark.parametrize(
    ("height", "extent", "orientation"),
    itertools.product(
        get_args(SurfaceHeight), get_args(SurfaceExtent), get_args(SurfaceOrientation)
    ),
)
def test_surface_geometry_accepts_all_bounded_profiles(
    height: str, extent: str, orientation: str
) -> None:
    payload = PRESENTATIONS[0].supports[0].model_dump()
    payload.update(height=height, extent=extent, orientation=orientation)
    support = ReferenceSurfaceRealization.model_validate(payload)
    assert (support.height, support.extent, support.orientation) == (
        height, extent, orientation
    )
    assert support == ReferenceSurfaceRealization.model_validate_json(
        support.model_dump_json()
    )


@pytest.mark.parametrize("surface", SURFACES)
def test_custom_presentation_accepts_alternative_bounded_profiles(surface: str) -> None:
    payload = PRESENTATIONS[0].model_dump()
    support = next(item for item in payload["supports"] if item["surface"] == surface)
    for field, values in (
        ("height", get_args(SurfaceHeight)),
        ("extent", get_args(SurfaceExtent)),
        ("orientation", get_args(SurfaceOrientation)),
    ):
        support[field] = next(value for value in values if value != support[field])
    presentation = ReferencePresentation.model_validate(payload)
    actual = next(item for item in presentation.supports if item.surface == surface)
    assert actual.model_dump() == support
    assert (actual.height, actual.extent, actual.orientation) != (
        SUPPORT_PROFILES[surface]
    )
    assert presentation == ReferencePresentation.model_validate_json(
        presentation.model_dump_json()
    )


def test_support_mapping_rejects_duplicate_surfaces() -> None:
    payload = PRESENTATIONS[0].model_dump()
    payload["supports"] += (payload["supports"][0],)
    with pytest.raises(ValidationError, match="surface mappings must be unique"):
        ReferencePresentation.model_validate(payload)


def test_support_mapping_rejects_mismatched_chair_objects() -> None:
    payload = PRESENTATIONS[0].model_dump()
    for support in payload["supports"]:
        if support["surface"] == "chair_back":
            support["object_id"] = "other_chair"
    with pytest.raises(ValidationError, match="same chair object"):
        ReferencePresentation.model_validate(payload)


@pytest.mark.parametrize(("first", "second"), itertools.combinations(SURFACES, 2))
def test_only_chair_surfaces_may_share_an_object(first: str, second: str) -> None:
    payload = PRESENTATIONS[0].model_dump()
    payload["supports"] = [
        {**support, "object_id": "shared"}
        for support in payload["supports"]
        if support["surface"] in (first, second)
    ]
    if {first, second} == {"chair_seat", "chair_back"}:
        assert len(ReferencePresentation.model_validate(payload).supports) == 2
    else:
        with pytest.raises(ValidationError, match="unrelated surfaces"):
            ReferencePresentation.model_validate(payload)


def test_chair_pair_cannot_share_its_object_with_another_surface() -> None:
    payload = PRESENTATIONS[0].model_dump()
    for support in payload["supports"]:
        if support["surface"] == "floor":
            support["object_id"] = "oak_chair"
    with pytest.raises(ValidationError, match="unrelated surfaces"):
        ReferencePresentation.model_validate(payload)


@pytest.mark.parametrize("surface", ("chair_seat", "chair_back"))
def test_single_chair_surface_is_allowed(surface: str) -> None:
    payload = PRESENTATIONS[0].model_dump()
    payload["supports"] = [
        item for item in payload["supports"] if item["surface"] == surface
    ]
    assert len(ReferencePresentation.model_validate(payload).supports) == 1


def test_headrest_requires_mat_in_same_presentation() -> None:
    payload = PRESENTATIONS[0].model_dump()
    payload["supports"] = [
        support for support in payload["supports"] if support["surface"] != "mat"
    ]
    with pytest.raises(ValidationError, match="headrest requires a mat"):
        ReferencePresentation.model_validate(payload)


@pytest.mark.parametrize("surfaces", [("mat",), ("mat", "headrest")])
def test_mat_can_stand_alone_or_pair_with_headrest(surfaces: tuple[str, ...]) -> None:
    payload = PRESENTATIONS[0].model_dump()
    payload["supports"] = [
        support for support in payload["supports"] if support["surface"] in surfaces
    ]
    presentation = ReferencePresentation.model_validate(payload)
    assert {support.surface for support in presentation.supports} == set(surfaces)


def test_presentation_requires_at_least_one_surface() -> None:
    payload = PRESENTATIONS[0].model_dump()
    payload["supports"] = []
    with pytest.raises(ValidationError):
        ReferencePresentation.model_validate(payload)


@pytest.mark.parametrize(
    "recipe", (
        *CAMERAS, *SUBJECTS, *PRESENTATIONS,
        *(
            support
            for presentation in PRESENTATIONS
            for support in presentation.supports
        ),
    )
)
def test_recipes_are_frozen_forbid_extras_and_roundtrip(
    recipe: ReferenceModel,
) -> None:
    model = type(recipe)
    assert isinstance(recipe, ReferenceModel)
    assert recipe == model.model_validate_json(recipe.model_dump_json())
    first_field = next(iter(model.model_fields))
    with pytest.raises(ValidationError, match="frozen"):
        setattr(recipe, first_field, getattr(recipe, first_field))
    with pytest.raises(ValidationError, match="Extra inputs"):
        model.model_validate({**recipe.model_dump(), "activity_id": "not_used"})


def test_curated_camera_ids_keep_existing_views_and_heights() -> None:
    assert len(CAMERAS) == 5
    assert {
        camera.camera_id: (camera.view, camera.height) for camera in CAMERAS
    } == {
        "front_eye": ("front", "subject_eye_level"),
        "left_eye": ("left_three_quarter", "subject_eye_level"),
        "right_eye": ("right_three_quarter", "subject_eye_level"),
        "left_high": ("left_three_quarter", "slightly_above_subject"),
        "right_high": ("right_three_quarter", "slightly_above_subject"),
    }
    for field, expected in {
        "coordinate_frame": {"room_axes"},
        "lens": {"normal", "short_telephoto"},
        "perspective": {"natural", "gentle_compression"},
        "subject_distance": {"full_body_clearance", "extended_full_body_clearance"},
        "focus": {"face_and_body", "whole_figure_and_supports"},
        "depth_of_field": {"moderate", "deep"},
        "negative_space": {"balanced", "left", "right"},
        "foreground": {"none", "edge_frame"},
    }.items():
        assert {getattr(camera, field) for camera in CAMERAS} == expected


def test_curated_subjects_have_distinct_clothed_adult_identities() -> None:
    assert len(SUBJECTS) == 4
    assert len({subject.subject_id for subject in SUBJECTS}) == 4
    assert len({subject.appearance for subject in SUBJECTS}) == 4
    assert len({subject.outfit for subject in SUBJECTS}) == 4
    for subject in SUBJECTS:
        assert subject.adult_age >= 25
        assert subject.coverage == "fully_clothed"
        for feature in ("skin", "eyes"):
            assert feature in subject.appearance
        for garment in (
            "opaque", "long-sleeved", "shirt", "fully covering", "full-length",
            "trousers", "socks", "closed-toe", "shoes",
        ):
            assert garment in subject.outfit


def test_curated_presentations_cover_every_support_and_camera_combination() -> None:
    assert len(PRESENTATIONS) == 5
    assert {p.presentation_id: len(p.supports) for p in PRESENTATIONS} == {
        "daylight_atelier": 8,
        "window_portrait_room": 4,
        "rehearsal_stage": 5,
        "print_studio": 3,
        "drawing_classroom": 6,
    }
    assert len({item.presentation_id for item in PRESENTATIONS}) == len(PRESENTATIONS)
    assert len({frozenset(s.surface for s in p.supports) for p in PRESENTATIONS}) >= 4
    assert {p.space for p in PRESENTATIONS} == {"standard", "extended"}
    universal = [
        p for p in PRESENTATIONS
        if p.space == "extended" and presentation_supports(p, SURFACES)
    ]
    assert universal
    for camera in CAMERAS:
        assert any(presentation_accepts_camera(p, camera) for p in universal)
    for presentation in PRESENTATIONS:
        assert "visible" in presentation.lighting
        for support in presentation.supports:
            assert support.description.startswith("the ")
            assert support.object_id
            assert (support.height, support.extent, support.orientation) == (
                SUPPORT_PROFILES[support.surface]
            )


def test_mat_presentations_have_distinct_contact_ready_towel_headrests() -> None:
    towels = {}
    for presentation in PRESENTATIONS:
        by_surface = {support.surface: support for support in presentation.supports}
        assert ("headrest" in by_surface) is ("mat" in by_surface)
        if "headrest" in by_surface:
            headrest = by_surface["headrest"]
            towels[presentation.presentation_id] = (
                headrest.object_id, headrest.description
            )
            assert headrest.object_id != by_surface["mat"].object_id
    assert towels == {
        "daylight_atelier": (
            "sage_towel",
            "the folded sage towel resting flat on the mat",
        ),
        "rehearsal_stage": (
            "terracotta_towel",
            "the folded terracotta towel resting flat on the mat",
        ),
        "drawing_classroom": (
            "burgundy_towel",
            "the folded burgundy towel resting flat on the mat",
        ),
    }
    assert len({object_id for object_id, _ in towels.values()}) == len(towels)


@pytest.mark.parametrize("presentation", PRESENTATIONS)
def test_presentation_supports_matches_surface_subsets(
    presentation: ReferencePresentation,
) -> None:
    available = {support.surface for support in presentation.supports}
    for count in range(len(SURFACES) + 1):
        for required in itertools.combinations(SURFACES, count):
            assert presentation_supports(presentation, required) is (
                set(required) <= available
            )
    surface = presentation.supports[0].surface
    assert presentation_supports(presentation, (surface, surface))


@pytest.mark.parametrize(("presentation", "camera"), itertools.product(
    PRESENTATIONS, CAMERAS
))
def test_camera_space_compatibility(
    presentation: ReferencePresentation, camera: ReferenceCamera
) -> None:
    expected = (
        camera.subject_distance == "full_body_clearance"
        or presentation.space == "extended"
    )
    assert presentation_accepts_camera(presentation, camera) is expected


@pytest.mark.parametrize("camera", CAMERAS)
def test_camera_renderer_preserves_all_fields_and_pose_readability(
    camera: ReferenceCamera,
) -> None:
    text = render_reference_camera(camera)
    assert text.isascii() and "\n" not in text
    view = {
        "front": "room front",
        "left_three_quarter": "room left three-quarter",
        "right_three_quarter": "room right three-quarter",
    }[camera.view]
    height = {
        "subject_eye_level": "at the subject's eye level",
        "slightly_above_subject": "slightly above the subject",
    }[camera.height]
    optics = {
        "normal": (
            "Use a normal lens with natural perspective. "
            "Allow full-body clearance around the figure."
        ),
        "short_telephoto": (
            "Use a short telephoto lens with gentle compression perspective. "
            "Stand farther back for extended full-body clearance around the figure."
        ),
    }[camera.lens]
    focus = {
        "face_and_body": "the face and clothed body",
        "whole_figure_and_supports": (
            "the whole figure, including facial features, and the needed supports"
        ),
    }[camera.focus]
    negative_space = {
        "balanced": "Balance the negative space on the image-frame left and right.",
        "left": "Leave more negative space on the image-frame left.",
        "right": "Leave more negative space on the image-frame right.",
    }[camera.negative_space]
    foreground = {
        "none": (
            "Keep the image-frame foreground clear and outside the figure's silhouette."
        ),
        "edge_frame": (
            "Let a subtle room edge frame the outer image-frame border, entirely "
            "outside the figure's silhouette and accessible contact boundaries."
        ),
    }[camera.foreground]
    assert text == (
        f"Frame the whole figure from a {view} view, {height}. {optics} "
        f"Keep {focus} in focus with {camera.depth_of_field} depth of field. "
        f"{negative_space} {foreground} "
        "Keep the whole figure uncropped and accessible contact boundaries clear. "
        "Naturally occluded undersides remain hidden; do not add extra limbs "
        "to expose them. Keep supports in their pose-required positions; do not "
        "move them to satisfy the camera. Retain the pose's head orientation and gaze."
    )
    assert "toward the camera" not in text
    assert not any(character.isdigit() for character in text)


@pytest.mark.parametrize("subject", SUBJECTS)
def test_subject_renderer_preserves_age_identity_outfit_and_coverage(
    subject: ReferenceSubject,
) -> None:
    text = render_reference_subject(subject)
    assert text.isascii() and "\n" not in text
    for phrase in (
        f"exactly one adult aged {subject.adult_age}",
        subject.appearance, subject.outfit, subject.coverage.replace("_", " "),
        "opaque everyday clothing", "torso, arms, and legs",
        "shoes on both feet", "neutral, non-sexual figure study",
    ):
        assert phrase in text


@pytest.mark.parametrize("presentation", PRESENTATIONS)
def test_presentation_renderer_preserves_recipe_without_unused_supports(
    presentation: ReferencePresentation,
) -> None:
    text = render_reference_presentation(presentation)
    assert text.isascii() and "\n" not in text
    lighting = presentation.lighting[0].upper() + presentation.lighting[1:]
    space = {
        "standard": "Leave comfortable space for a clear full-body view.",
        "extended": (
            "Leave generous open space for a clear full-body view "
            "and a camera set farther back."
        ),
    }[presentation.space]
    assert text == (
        f"Place the figure in {presentation.setting}. "
        f"Surround the figure with {presentation.palette}. {lighting}. "
        f"Render the image as {presentation.finish}. {space} "
        "Preserve light and gentle fill on the face so facial features remain "
        "visible; do not reduce the figure to a full silhouette. "
        "Keep visible hands, feet, and accessible contact boundaries distinct "
        "from the surroundings; naturally occluded undersides remain hidden."
    )
    for support in presentation.supports:
        assert support.description not in text


@pytest.mark.parametrize(
    ("recipe", "renderer", "identifier"),
    [
        *(
            (camera, render_reference_camera, "camera_id")
            for camera in CAMERAS
        ),
        *(
            (subject, render_reference_subject, "subject_id")
            for subject in SUBJECTS
        ),
        *(
            (presentation, render_reference_presentation, "presentation_id")
            for presentation in PRESENTATIONS
        ),
    ],
)
def test_renderers_ignore_identifiers_and_omit_internal_metadata(
    recipe, renderer, identifier
) -> None:
    text = renderer(recipe)
    payload = recipe.model_dump()
    payload[identifier] = "internal_catalog_identifier"
    renamed_text = renderer(type(recipe).model_validate(payload))
    assert renamed_text == text
    assert "internal_catalog_identifier" not in text
    assert ":" not in text
    assert "_" not in text
    for internal in (
        "camera recipe", "subject_id", "presentation_id", "object_id", "schema",
        "simulation", "qualitative", "validation", "symbolic", "workflow",
    ):
        assert internal not in text.lower()


def test_recipe_accessors_are_deterministic_tuples() -> None:
    for accessor in (
        reference_cameras, reference_subjects, reference_presentations
    ):
        assert isinstance(accessor(), tuple)
        assert accessor() == accessor()


def test_module_uses_only_standard_library_pydantic_and_shared_types() -> None:
    source = Path(presentation_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level == 1 and node.module == "pose_reference_types"
                continue
            names = [node.module or ""]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            assert root in sys.stdlib_module_names or root == "pydantic"
    assert importlib.util.find_spec("t2i_spatial_pipeline.pose_reference_types")
