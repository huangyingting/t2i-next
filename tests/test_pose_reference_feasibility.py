from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from t2i_spatial_pipeline.pose_reference import (
    NeutralPose,
    NeutralPoseLibrary,
    PoseReferenceBatch,
    PoseReferenceScene,
    audit_reference_library,
    pose_accepts_camera,
    presentation_fits_pose,
    render_pose_reference,
    sample_pose_references,
)
from t2i_spatial_pipeline.pose_reference_catalog import build_neutral_pose_library
from t2i_spatial_pipeline.pose_reference_geometry import (
    compile_reference_geometry,
    reference_geometry_report,
    reference_joint_positions,
)
from t2i_spatial_pipeline.pose_reference_presentation import (
    ReferenceCamera,
    ReferencePresentation,
)

LIBRARY = build_neutral_pose_library()
POSES = {pose.pose_id: pose for pose in LIBRARY.poses}
ATELIER = LIBRARY.presentations[0]
SUBJECT = LIBRARY.subjects[0]


@pytest.mark.parametrize("pose_id", tuple(POSES))
def test_load_description_has_one_source_of_truth(pose_id: str) -> None:
    pose = POSES[pose_id]
    camera = next(c for c in LIBRARY.cameras if pose_accepts_camera(pose, c))
    prompt = render_pose_reference(pose, camera, SUBJECT, ATELIER)
    assert "weight_distribution" not in pose.model_dump()
    assert prompt.count(" bears weight") == sum(c.load_bearing for c in pose.supports)
    assert prompt.count(" makes light contact") == sum(
        not c.load_bearing for c in pose.supports
    )
    for contact in pose.supports:
        realization = next(
            s for s in ATELIER.supports if s.surface == contact.surface
        )
        expected = (
            f"{contact.body_part.replace('_', ' ')} on {realization.description}"
            + (" bears weight" if contact.load_bearing else " makes light contact")
        )
        assert prompt.count(expected) == 1
    assert "own anatomical sides" in prompt
    assert "Room front is the fixed scene reference" in prompt
    assert "relative to the head, not toward the lens" in prompt
    assert "Allow natural overlap" in prompt
    assert "Keep both hands, both feet" not in prompt


@pytest.mark.parametrize("pose_id", ["table_supported_both", "crouched_supported_both"])
def test_two_hand_support_keeps_both_loads(pose_id: str) -> None:
    pose = POSES[pose_id]
    assert pose.balance_bias == "unbiased"
    assert {c.body_part for c in pose.supports if c.load_bearing} == {
        "left_foot", "right_foot", "left_hand", "right_hand"
    }


@pytest.mark.parametrize("pose_id", ["table_supported_both", "crouched_supported_both"])
def test_supporting_hands_cannot_silently_become_light_contacts(pose_id: str) -> None:
    payload = POSES[pose_id].model_dump()
    for contact in payload["supports"]:
        if contact["body_part"] == "right_hand":
            contact["load_bearing"] = False
    with pytest.raises(ValidationError, match="hand supports must bear weight"):
        NeutralPose.model_validate(payload)


def test_upright_kneeling_records_knees_and_toe_ends() -> None:
    pose = POSES["kneeling_upright_centered"]
    assert {c.body_part for c in pose.supports} == {
        "left_knee", "right_knee", "left_toes", "right_toes",
    }
    assert all(c.surface == "mat" and c.load_bearing for c in pose.supports)


def test_reference_intro_does_not_override_the_selected_visual_medium() -> None:
    presentation = next(
        p for p in LIBRARY.presentations if p.presentation_id == "rehearsal_stage"
    )
    prompt = render_pose_reference(
        POSES["standing_parallel_relaxed"], LIBRARY.cameras[0], SUBJECT, presentation,
    )
    assert "gouache figure study" in prompt
    assert "photograph" not in prompt


@pytest.mark.parametrize("variant", ["left", "right", "folded"])
def test_lying_rest_supports_head_and_releases_lower_arm(variant: str) -> None:
    pose = POSES[f"side_lying_rest_{variant}"]
    contacts = {c.body_part: c for c in pose.supports}
    lower = "left_hand" if pose.resting_side == "left" else "right_hand"
    assert getattr(pose, lower) == "on_mat_forward"
    assert contacts[lower].surface == "mat"
    assert contacts[lower].load_bearing is False
    assert contacts["head"].surface == "headrest"
    assert contacts["head"].load_bearing is True
    assert pose.legs == "staggered_bent_knees"
    assert pose.head_orientation.yaw == "aligned"
    camera = next(c for c in LIBRARY.cameras if pose_accepts_camera(pose, c))
    prompt = render_pose_reference(pose, camera, SUBJECT, ATELIER)
    assert "not trapped underneath" in prompt
    assert "lower shin slightly forward" in prompt
    assert "headrest fills the gap beneath the head" in prompt


@pytest.mark.parametrize(
    ("pose_id", "changes", "message"),
    [
        (
            "standing_parallel_relaxed",
            {"pelvis_facing": "left_three_quarter"},
            "untwisted pelvis and chest",
        ),
        (
            "standing_parallel_turn_left",
            {"pelvis_facing": "right_three_quarter"},
            "adjacent pelvis/chest",
        ),
        (
            "standing_parallel_turn_left",
            {"pelvis_facing": "left_three_quarter"},
            "adjacent pelvis/chest",
        ),
        (
            "standing_parallel_relaxed",
            {"head_orientation": {"yaw": "backward", "pitch": "neutral"}},
            "Input should be",
        ),
        (
            "standing_parallel_relaxed",
            {"coordinate_frame": "screen_axes"},
            "Input should be",
        ),
        (
            "standing_parallel_relaxed",
            {"resting_side": "left"},
            "only for lying",
        ),
        (
            "side_lying_rest_left",
            {"resting_side": "right"},
            "declared support surface",
        ),
        (
            "side_lying_rest_left",
            {"head_orientation": {"yaw": "gentle_left", "pitch": "neutral"}},
            "head must stay aligned",
        ),
        (
            "wall_supported_back",
            {"spine": "forward_inclined"},
            "cannot use a back support",
        ),
        (
            "half_kneeling_left",
            {"balance_bias": "left"},
            "standing load-bearing foot",
        ),
    ],
)
def test_rejects_contradictory_reference_frames_and_postures(
    pose_id: str, changes: dict[str, object], message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        NeutralPose.model_validate(POSES[pose_id].model_dump() | changes)


def test_lying_lower_arm_cannot_be_hidden_even_without_a_surface_contact() -> None:
    payload = POSES["side_lying_rest_left"].model_dump()
    payload["left_hand"] = "at_side"
    payload["supports"] = [
        c for c in payload["supports"] if c["body_part"] != "left_hand"
    ]
    with pytest.raises(ValidationError, match="lower hand must rest ahead"):
        NeutralPose.model_validate(payload)


@pytest.mark.parametrize("part", ["head", "left_side"])
def test_lying_requires_body_and_head_loads(part: str) -> None:
    payload = POSES["side_lying_rest_left"].model_dump()
    for contact in payload["supports"]:
        if contact["body_part"] == part:
            contact["load_bearing"] = False
    with pytest.raises(ValidationError, match="required load-bearing contacts"):
        NeutralPose.model_validate(payload)


def test_lying_hand_cannot_replace_body_support() -> None:
    payload = POSES["side_lying_rest_left"].model_dump()
    for contact in payload["supports"]:
        if contact["body_part"] == "left_hand":
            contact["load_bearing"] = True
    with pytest.raises(ValidationError, match="must not replace lying"):
        NeutralPose.model_validate(payload)


@pytest.mark.parametrize("pose_id", ["table_supported_left", "wall_supported_left"])
def test_support_layout_rejects_wrong_side_or_behind_body(pose_id: str) -> None:
    payload = POSES[pose_id].model_dump()
    for placement in payload["support_layout"]:
        if placement["surface"] in {"wall", "table"}:
            placement["position"] = "behind_upper_back"
    with pytest.raises(ValidationError, match="anatomical contact layout"):
        NeutralPose.model_validate(payload)


def test_support_layout_is_complete_unique_and_anatomical() -> None:
    payload = POSES["table_supported_both"].model_dump()
    with pytest.raises(ValidationError, match="anatomical contact layout"):
        NeutralPose.model_validate(
            payload | {"support_layout": payload["support_layout"][:1]}
        )
    with pytest.raises(ValidationError, match="one support placement"):
        NeutralPose.model_validate(
            payload | {"support_layout": payload["support_layout"] * 2}
        )
    payload["support_layout"][0]["coordinate_frame"] = "screen"
    with pytest.raises(ValidationError, match="Input should be"):
        NeutralPose.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("height", "standing_shoulder"),
        ("extent", "whole_foot"),
        ("orientation", "vertical"),
    ],
)
def test_present_but_unsuitable_table_is_rejected_everywhere(
    field: str, value: str,
) -> None:
    payload = ATELIER.model_dump()
    for surface in payload["supports"]:
        if surface["surface"] == "table":
            surface[field] = value
    presentation = ReferencePresentation.model_validate(payload)
    pose = POSES["table_supported_both"]
    assert not presentation_fits_pose(presentation, pose)
    with pytest.raises(ValueError, match="height, extent or orientation"):
        render_pose_reference(pose, LIBRARY.cameras[0], SUBJECT, presentation)
    geometry = compile_reference_geometry(pose, SUBJECT, ATELIER)
    with pytest.raises(ValidationError, match="height, extent or orientation"):
        PoseReferenceScene(
            pose=pose, camera=LIBRARY.cameras[0], subject=SUBJECT,
            presentation=presentation, prompt="A stale but nonempty prompt.",
            geometry=geometry, geometry_report=reference_geometry_report(geometry),
            geometry_joints=reference_joint_positions(geometry),
        )
    library_payload = LIBRARY.model_dump(mode="json")
    library_payload["presentations"][0] = payload
    library = NeutralPoseLibrary.model_validate(library_payload)
    with pytest.raises(ValueError, match="no reference poses fit"):
        sample_pose_references(
            library, seed=1, count=1, family="table_supported",
            presentation_id=ATELIER.presentation_id,
        )
    audit_reference_library(library)


def test_same_camera_id_cannot_bypass_lying_view_validation() -> None:
    pose = POSES["side_lying_rest_left"]
    original = next(c for c in LIBRARY.cameras if pose_accepts_camera(pose, c))
    camera = ReferenceCamera.model_validate(
        original.model_dump() | {"height": "subject_eye_level"}
    )
    assert not pose_accepts_camera(pose, camera)
    with pytest.raises(ValueError, match="incompatible"):
        render_pose_reference(pose, camera, SUBJECT, ATELIER)
    payload = LIBRARY.model_dump()
    payload["cameras"] = [
        camera.model_dump() if c["camera_id"] == camera.camera_id else c
        for c in payload["cameras"]
    ]
    with pytest.raises(ValidationError, match="incompatible camera view"):
        NeutralPoseLibrary.model_validate(payload)


@pytest.mark.parametrize("side", ["left", "right"])
def test_camera_does_not_force_outward_turned_head_back_to_lens(side: str) -> None:
    pose = NeutralPose.model_validate(
        POSES[f"standing_parallel_turn_{side}"].model_dump()
        | {"head_orientation": {"yaw": f"gentle_{side}", "pitch": "neutral"}}
    )
    opposite = "right" if side == "left" else "left"
    camera = next(c for c in LIBRARY.cameras if c.camera_id == f"{opposite}_eye")
    assert not pose_accepts_camera(pose, camera)
    with pytest.raises(ValueError, match="incompatible"):
        render_pose_reference(pose, camera, SUBJECT, ATELIER)
    same_side = next(c for c in LIBRARY.cameras if c.camera_id == f"{side}_eye")
    assert pose_accepts_camera(pose, same_side)


def test_reports_do_not_claim_physical_or_visual_validation() -> None:
    audit = audit_reference_library(LIBRARY)
    batch = sample_pose_references(LIBRARY, seed=42, count=48)
    assert batch.schema_version == audit.schema_version == "4.0"
    assert LIBRARY.schema_version == "4.0"
    assert batch.renderer_version == 4
    assert batch.selection_algorithm == "geometry_gated_family_maximin_v4"
    assert batch.report.geometry_checked_scenes == 48
    assert batch.geometry_rejections == ()
    for record in (LIBRARY, audit, audit.pose_report, batch.report):
        assert record.physical_validation is False
        assert record.visual_validation is False
        assert record.requires_render_review is True
    expected = Counter(
        c.body_part for p in LIBRARY.poses for c in p.supports if c.load_bearing
    )
    assert audit.pose_report.load_bearing_contact_counts == dict(expected)
    assert sum(audit.pose_report.balance_bias_counts.values()) == 48
    assert batch == PoseReferenceBatch.model_validate_json(batch.model_dump_json())


@pytest.mark.parametrize("version", ["1.0", "2.0", "3.0"])
def test_superseded_batches_are_rejected_without_migration(version: str) -> None:
    payload = sample_pose_references(LIBRARY, seed=1, count=1).model_dump()
    payload["schema_version"] = version
    with pytest.raises(ValidationError, match="4.0"):
        PoseReferenceBatch.model_validate(payload)
