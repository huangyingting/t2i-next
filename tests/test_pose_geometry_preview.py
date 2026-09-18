from __future__ import annotations

import inspect
import itertools
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from unittest.mock import patch

import numpy as np
import pytest
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation

from t2i_pose_geometry import (
    ActorPose,
    BodyContact,
    BodySpec,
    Box,
    Contact,
    JointAngles,
    Scene,
    ValidationReport,
    forward_kinematics,
    validate_scene,
)
from t2i_pose_geometry.preview import render_scene_svg

_NS = {"s": "http://www.w3.org/2000/svg"}


def _scene() -> Scene:
    return Scene(
        actors=(ActorPose(actor_id="adult"),),
        objects=(Box(object_id="floor", center=(0, 0, -0.1), size=(3, 3, 0.2)),),
        contacts=tuple(
            Contact(actor_id="adult", anchor=f"{side}_sole", object_id="floor")
            for side in ("left", "right")
        ),
    )


def _panels(root: ET.Element) -> list[ET.Element]:
    return root.findall("s:g[@class='view']", _NS)


def _volume(panel: ET.Element, owner: str, shape: str) -> ET.Element:
    return next(
        element
        for element in panel.iter()
        if element.get("class") == "collision-volume"
        and element.get("data-owner") == owner
        and element.get("data-shape") == shape
    )


def _point(panel: ET.Element, position: tuple | np.ndarray) -> tuple[float, float]:
    scale = float(panel.attrib["data-scale"])
    u = "xyz".index(panel.attrib["data-horizontal-axis"])
    v = "xyz".index(panel.attrib["data-vertical-axis"])
    return (
        float(panel.attrib["data-origin-x"]) + position[u] * scale,
        float(panel.attrib["data-origin-y"]) - position[v] * scale,
    )


def _child(parent: ET.Element, tag: str) -> ET.Element:
    child = parent.find(f"s:{tag}", _NS)
    assert child is not None
    return child


def _polygon(group: ET.Element) -> np.ndarray:
    return np.array(
        [
            tuple(map(float, vertex.split(",")))
            for vertex in _child(group, "polygon").attrib["points"].split()
        ]
    )


def _status(root: ET.Element) -> str:
    status = root.find("s:text[@class='validation-status']", _NS)
    assert status is not None
    return status.text or ""


def test_svg_is_parseable_deterministic_and_has_three_labeled_views() -> None:
    scene = _scene()
    original = scene.model_dump_json()
    svg = render_scene_svg(scene)
    root = ET.fromstring(svg)
    assert render_scene_svg(scene) == svg
    assert scene.model_dump_json() == original
    assert root.tag == f"{{{_NS['s']}}}svg"
    assert [panel.attrib["data-view"] for panel in _panels(root)] == [
        "front",
        "side",
        "top",
    ]
    assert len({p.attrib["data-scale"] for p in _panels(root)}) == 1
    text = " ".join(root.itertext())
    assert "Diagnostic proxy geometry" in text
    assert "Not an AI render" in text
    assert "not a medical or safety assessment" in text
    assert _status(root).startswith("PASS")
    assert "No validation issues." in text
    assert float(root.attrib["width"]) <= 1600
    assert float(root.attrib["height"]) <= 1200


def test_each_view_draws_every_actual_volume_joint_and_anchor() -> None:
    scene = _scene()
    skeleton = forward_kinematics(scene.actors[0])
    root = ET.fromstring(render_scene_svg(scene))
    for panel in _panels(root):
        volumes = panel.findall(".//s:g[@class='collision-volume']", _NS)
        assert len(volumes) == len(skeleton.shapes) + len(scene.objects)
        assert {v.get("data-kind") for v in volumes} == {
            "capsule",
            "ellipsoid",
            "box",
        }
        assert len(panel.findall(".//s:circle[@data-joint]", _NS)) == len(
            skeleton.joints
        )
        assert len(panel.findall(".//s:circle[@data-anchor]", _NS)) == len(
            skeleton.anchors
        )
        for marker in panel.findall(".//s:circle[@data-joint]", _NS):
            expected = _point(panel, skeleton.joints[marker.attrib["data-joint"]])
            assert (float(marker.attrib["cx"]), float(marker.attrib["cy"])) == (
                pytest.approx(expected, abs=2e-6)
            )
        assert panel.findall(".//s:g[@class='skeleton']/s:line", _NS)


def test_rotated_box_projects_convex_hull_of_all_eight_corners() -> None:
    box = Box(
        object_id="rotated",
        center=(1.2, 0.3, 0.7),
        size=(0.8, 0.3, 0.5),
        rotation=(23, -37, 41),
    )
    scene = Scene(actors=(ActorPose(actor_id="adult"),), objects=(box,))
    root = ET.fromstring(render_scene_svg(scene))
    rotation = Rotation.from_euler("xyz", box.rotation, degrees=True).as_matrix()
    local = np.array(list(itertools.product((-0.5, 0.5), repeat=3))) * box.size
    corners = local @ rotation.T + box.center
    for panel in _panels(root):
        points = np.array([_point(panel, point) for point in corners])
        expected = points[ConvexHull(points).vertices]
        actual = _polygon(_volume(panel, "rotated", "rotated"))
        assert len(actual) == len(expected) == 6
        for vertex in actual:
            assert min(np.linalg.norm(expected - vertex, axis=1)) < 3e-6


def test_rotated_body_capsules_have_exact_projected_axis_and_radius() -> None:
    actor = ActorPose(
        actor_id="adult",
        root_position=(0.4, -0.2, 1.1),
        root_rotation=(21, -17, 33),
        angles=JointAngles(left_elbow_flex=45, left_shoulder_flex=20),
    )
    skeleton = forward_kinematics(actor)
    shape = next(s for s in skeleton.shapes if s.shape_id == "left_forearm")
    rotation = Rotation.from_euler("xyz", shape.rotation, degrees=True).as_matrix()
    axis = rotation[:, 2] * shape.length / 2
    root = ET.fromstring(render_scene_svg(Scene(actors=(actor,))))
    for panel in _panels(root):
        volume = _volume(panel, "adult", "left_forearm")
        line = _child(volume, "line")
        assert line.get("stroke-linecap") == "round"
        assert (float(line.attrib["x1"]), float(line.attrib["y1"])) == pytest.approx(
            _point(panel, np.asarray(shape.center) - axis),
            abs=3e-6,
        )
        assert (float(line.attrib["x2"]), float(line.attrib["y2"])) == pytest.approx(
            _point(panel, np.asarray(shape.center) + axis),
            abs=3e-6,
        )
        assert float(line.attrib["stroke-width"]) == pytest.approx(
            2 * shape.radius * float(panel.attrib["data-scale"]),
            abs=1e-6,
        )


def test_end_on_capsule_is_a_filled_circle_not_an_invisible_zero_length_line() -> None:
    root = ET.fromstring(render_scene_svg(Scene(actors=(ActorPose(actor_id="a"),))))
    top = _panels(root)[2]
    circle = _child(_volume(top, "a", "left_shin"), "circle")
    assert float(circle.attrib["r"]) == pytest.approx(
        BodySpec().shin_radius * float(top.attrib["data-scale"]),
        abs=1e-6,
    )


def test_rotated_ellipsoid_projection_uses_projected_covariance() -> None:
    actor = ActorPose(
        actor_id="adult",
        root_rotation=(23, -19, 37),
        angles=JointAngles(torso_pitch=25, torso_yaw=15),
    )
    torso = next(
        shape for shape in forward_kinematics(actor).shapes if shape.shape_id == "torso"
    )
    rotation = Rotation.from_euler("xyz", torso.rotation, degrees=True).as_matrix()
    root = ET.fromstring(render_scene_svg(Scene(actors=(actor,))))
    for panel in _panels(root):
        u = "xyz".index(panel.attrib["data-horizontal-axis"])
        v = "xyz".index(panel.attrib["data-vertical-axis"])
        projection = np.zeros((2, 3))
        scale = float(panel.attrib["data-scale"])
        projection[0, u], projection[1, v] = scale, -scale
        projected = projection @ rotation * torso.radii
        expected = projected @ projected.T
        ellipse = _child(_volume(panel, "adult", "torso"), "ellipse")
        angle = math.radians(float(ellipse.attrib["transform"][7:].split()[0]))
        transform = np.array(
            [
                [math.cos(angle), -math.sin(angle)],
                [math.sin(angle), math.cos(angle)],
            ]
        )
        radii = np.array([float(ellipse.attrib[key]) for key in ("rx", "ry")])
        assert transform @ np.diag(radii**2) @ transform.T == pytest.approx(
            expected,
            abs=5e-5,
        )
        assert (float(ellipse.attrib["cx"]), float(ellipse.attrib["cy"])) == (
            pytest.approx(_point(panel, torso.center), abs=2e-6)
        )


def test_scaling_changes_all_volume_dimensions_and_actors_have_distinct_colors() -> (
    None
):
    scene = Scene(
        actors=(
            ActorPose(actor_id="small"),
            ActorPose(
                actor_id="large", body=BodySpec().scaled(2), root_position=(3, 0, 1.79)
            ),
        )
    )
    root = ET.fromstring(render_scene_svg(scene))
    for panel in _panels(root)[:2]:
        small = _volume(panel, "small", "left_thigh")
        large = _volume(panel, "large", "left_thigh")
        assert small.attrib["fill"] != large.attrib["fill"]
        assert float(_child(large, "line").attrib["stroke-width"]) == pytest.approx(
            2 * float(_child(small, "line").attrib["stroke-width"]),
            abs=2e-6,
        )
        for key in ("rx", "ry"):
            assert float(
                _child(_volume(panel, "large", "head"), "ellipse").attrib[key]
            ) == pytest.approx(
                2
                * float(_child(_volume(panel, "small", "head"), "ellipse").attrib[key]),
                abs=2e-6,
            )
        assert np.ptp(_polygon(_volume(panel, "large", "left_foot")), axis=0) == (
            pytest.approx(
                2 * np.ptp(_polygon(_volume(panel, "small", "left_foot")), axis=0),
                abs=2e-6,
            )
        )


def test_required_contacts_have_visible_anchors_targets_and_labels_in_each_view() -> (
    None
):
    scene = _scene()
    skeleton = forward_kinematics(scene.actors[0])
    root = ET.fromstring(render_scene_svg(scene))
    for panel in _panels(root):
        markers = panel.findall(".//s:g[@class='contact-marker']", _NS)
        assert len(markers) == 4
        for index, contact in enumerate(scene.contacts, 1):
            pair = [m for m in markers if m.get("data-contact") == f"C{index}"]
            assert {m.attrib["data-role"] for m in pair} == {"anchor", "target"}
            assert any(contact.anchor in "".join(m.itertext()) for m in pair)
            assert any("floor.top" in "".join(m.itertext()) for m in pair)
            for marker in pair:
                circle = _child(marker, "circle")
                assert float(circle.attrib["r"]) >= 4
                assert (float(circle.attrib["cx"]), float(circle.attrib["cy"])) == (
                    pytest.approx(
                        _point(panel, skeleton.anchors[contact.anchor].position),
                        abs=2e-6,
                    )
                )


def test_contact_errors_render_failure_gap_and_only_involved_shapes_in_red() -> None:
    scene = _scene()
    scene = scene.model_copy(
        update={
            "actors": (ActorPose(actor_id="adult", root_position=(0, 0, 1.045)),),
        }
    )
    root = ET.fromstring(render_scene_svg(scene))
    assert _status(root).startswith("FAIL")
    assert "contact_distance" in "".join(root.itertext())
    front = _panels(root)[0]
    for name in ("left_foot", "right_foot"):
        foot = _volume(front, "adult", name)
        assert foot.attrib["fill"] == "#c62828"
        assert "contact_distance" in foot.attrib["data-errors"]
    assert _volume(front, "floor", "floor").attrib["fill"] == "#c62828"
    assert _volume(front, "adult", "head").attrib["fill"] != "#c62828"
    for gap in front.findall(".//s:line[@class='contact-gap']", _NS):
        assert abs(float(gap.attrib["y1"]) - float(gap.attrib["y2"])) > 1


def test_collisions_and_joint_constraints_are_reported_and_highlighted() -> None:
    actor = ActorPose(
        actor_id="adult",
        angles=JointAngles(left_shoulder_abduction=-30, right_knee_flex=-1),
    )
    scene = Scene(actors=(actor,))
    root = ET.fromstring(render_scene_svg(scene))
    report = validate_scene(scene)
    assert {"self_collision", "joint_limit"} <= {i.code for i in report.issues}
    assert _status(root).startswith("FAIL")
    for issue in report.issues:
        assert issue.code in "".join(root.itertext())
    for panel in _panels(root):
        for name in ("torso", "left_upper_arm", "right_shin", "right_knee_joint"):
            assert _volume(panel, "adult", name).attrib["fill"] == "#c62828"
        labels = panel.findall(".//s:text[@class='error-label']", _NS)
        assert labels and all(label.text.startswith("E") for label in labels)


def test_object_collision_labels_the_body_and_box() -> None:
    actor = ActorPose(actor_id="adult")
    head = next(
        shape for shape in forward_kinematics(actor).shapes if shape.shape_id == "head"
    )
    scene = Scene(
        actors=(actor,),
        objects=(Box(object_id="obstacle", center=head.center, size=(0.1, 0.1, 0.1)),),
    )
    root = ET.fromstring(render_scene_svg(scene))
    assert _status(root).startswith("FAIL")
    for panel in _panels(root):
        for owner, name in (("adult", "head"), ("obstacle", "obstacle")):
            volume = _volume(panel, owner, name)
            assert volume.attrib["fill"] == "#c62828"
            assert "object_collision" in volume.attrib["data-errors"]


def test_inter_actor_collision_highlights_only_the_involved_actor_pair() -> None:
    scene = Scene(
        actors=(
            ActorPose(actor_id="first"),
            ActorPose(actor_id="second"),
            ActorPose(actor_id="unrelated", root_position=(2, 0, 0.895)),
        )
    )
    root = ET.fromstring(render_scene_svg(scene))
    assert _status(root).startswith("FAIL")
    for panel in _panels(root):
        for owner in ("first", "second"):
            head = _volume(panel, owner, "head")
            assert head.attrib["fill"] == "#c62828"
            assert "inter_actor_collision" in head.attrib["data-errors"]
        assert _volume(panel, "unrelated", "head").attrib["fill"] != "#c62828"


def test_required_contact_target_uses_rotated_bounded_face_not_its_center() -> None:
    actor = ActorPose(actor_id="adult")
    box = Box(
        object_id="target",
        center=(1, 0.7, 1),
        size=(0.4, 0.2, 0.6),
        rotation=(21, -33, 46),
    )
    scene = Scene(
        actors=(actor,),
        objects=(box,),
        contacts=(
            Contact(
                actor_id="adult",
                anchor="left_palm",
                object_id="target",
                face="front",
            ),
        ),
    )
    position = forward_kinematics(actor).anchors["left_palm"].position
    rotation = Rotation.from_euler("xyz", box.rotation, degrees=True).as_matrix()
    half = np.asarray(box.size) / 2
    target = np.clip(rotation.T @ (np.asarray(position) - box.center), -half, half)
    target[1] = half[1]
    expected = rotation @ target + box.center
    root = ET.fromstring(render_scene_svg(scene))
    assert _status(root).startswith("FAIL")
    for panel in _panels(root):
        marker = panel.find(".//s:g[@data-role='target']/s:circle", _NS)
        assert marker is not None
        assert (float(marker.attrib["cx"]), float(marker.attrib["cy"])) == (
            pytest.approx(_point(panel, expected), abs=2e-6)
        )


@pytest.mark.parametrize("gap", [0.0, 0.04])
def test_body_contacts_show_both_actual_anchors_and_constraint_errors(
    gap: float,
) -> None:
    scene = Scene(
        actors=(
            ActorPose(actor_id="first"),
            ActorPose(
                actor_id="second",
                root_position=(0, -0.21 - gap, 0.895),
                root_rotation=(0, 0, 180),
            ),
        ),
        body_contacts=(
            BodyContact(
                actor_id="first",
                anchor="back",
                target_actor_id="second",
                target_anchor="back",
            ),
        ),
    )
    root = ET.fromstring(render_scene_svg(scene))
    assert _status(root).startswith("FAIL" if gap else "PASS")
    skeletons = {actor.actor_id: forward_kinematics(actor) for actor in scene.actors}
    for panel in _panels(root):
        markers = panel.findall(".//s:g[@class='contact-marker']", _NS)
        assert len(markers) == 2
        assert {marker.get("data-contact") for marker in markers} == {"B1"}
        for marker in markers:
            owner = "first" if marker.get("data-role") == "anchor" else "second"
            assert f"{owner}.back" in "".join(marker.itertext())
            circle = _child(marker, "circle")
            assert (float(circle.attrib["cx"]), float(circle.attrib["cy"])) == (
                pytest.approx(
                    _point(panel, skeletons[owner].anchors["back"].position),
                    abs=2e-6,
                )
            )
            torso = _volume(panel, owner, "torso")
            assert (torso.attrib["fill"] == "#c62828") == bool(gap)
            if gap:
                assert "body_contact_distance" in torso.attrib["data-errors"]
        if gap and panel.attrib["data-view"] != "front":
            line = panel.find(".//s:line[@class='body-contact-gap']", _NS)
            assert line is not None
            assert (
                math.dist(
                    (float(line.attrib["x1"]), float(line.attrib["y1"])),
                    (float(line.attrib["x2"]), float(line.attrib["y2"])),
                )
                > 1
            )


def test_contact_object_and_actor_may_share_identifier_without_losing_error_color() -> (
    None
):
    scene = Scene(
        actors=(ActorPose(actor_id="adult"),),
        objects=(Box(object_id="adult", center=(0, 0, -0.2), size=(3, 3, 0.2)),),
        contacts=(Contact(actor_id="adult", anchor="left_sole", object_id="adult"),),
    )
    root = ET.fromstring(render_scene_svg(scene))
    assert _status(root).startswith("FAIL")
    for panel in _panels(root):
        assert _volume(panel, "adult", "adult").attrib["fill"] == "#c62828"
        assert _volume(panel, "adult", "left_foot").attrib["fill"] == "#c62828"
        assert _volume(panel, "adult", "head").attrib["fill"] != "#c62828"


def test_validation_is_recomputed_and_cannot_be_replaced_with_forged_pass() -> None:
    scene = Scene(
        actors=(ActorPose(actor_id="adult", angles=JointAngles(left_knee_flex=-1)),)
    )
    with patch(
        "t2i_pose_geometry.preview.validate_scene",
        wraps=validate_scene,
    ) as validator:
        root = ET.fromstring(render_scene_svg(scene))
    validator.assert_called_once_with(scene)
    assert _status(root).startswith("FAIL")
    assert list(inspect.signature(render_scene_svg).parameters) == ["scene"]
    with pytest.raises(TypeError):
        render_scene_svg(scene, report=ValidationReport(passed=True))


def test_xml_escapes_malicious_identifiers_and_replaces_forbidden_characters() -> None:
    hostile = 'a"><script>alert("x")</script>&\x00\ufffe'
    scene = Scene(
        actors=(ActorPose(actor_id=hostile),),
        contacts=(Contact(actor_id=hostile, anchor="<unknown>&", object_id='"evil"'),),
    )
    svg = render_scene_svg(scene)
    root = ET.fromstring(svg)
    assert not root.findall(".//s:script", _NS)
    assert _status(root).startswith("FAIL")
    assert 'a"><script>alert("x")</script>&\ufffd\ufffd' in "".join(root.itertext())
    assert "&lt;script&gt;" in svg
    assert "unknown_anchor" in "".join(root.itertext())
    ids = [e.attrib["id"] for e in root.iter() if "id" in e.attrib]
    assert len(ids) == len(set(ids))
    assert all("<" not in identifier and "\x00" not in identifier for identifier in ids)


def test_unchecked_nonfinite_models_render_failure_without_nonfinite_geometry() -> None:
    scene = Scene(actors=(ActorPose(actor_id="adult"),)).model_copy(
        update={
            "actors": (
                ActorPose(actor_id="adult").model_copy(
                    update={"root_position": (math.nan, 0, 1)},
                ),
            ),
        }
    )
    root = ET.fromstring(render_scene_svg(scene))
    assert _status(root).startswith("FAIL")
    assert "invalid_model" in "".join(root.itertext())
    assert len(_panels(root)) == 3
    assert not root.findall(".//s:g[@class='collision-volume']", _NS)


def test_large_ground_is_viewport_clipped_without_changing_coordinates() -> None:
    scene = _scene().model_copy(
        update={
            "objects": (
                Box(object_id="floor", center=(0, 0, -0.1), size=(10000, 10000, 0.2)),
            ),
        }
    )
    original = scene.model_dump_json()
    root = ET.fromstring(render_scene_svg(scene))
    assert scene.model_dump_json() == original
    assert "Large ground boxes clipped (preview only)" in "".join(root.itertext())
    assert _status(root).startswith("PASS")
    assert len(root.findall(".//s:clipPath", _NS)) == 3
    front = _panels(root)[0]
    assert float(front.attrib["data-scale"]) > 25
    polygon = _polygon(_volume(front, "floor", "floor"))
    assert np.ptp(polygon[:, 0]) == pytest.approx(
        10000 * float(front.attrib["data-scale"]),
        abs=0.006,
    )
    assert np.max(polygon[:, 0]) > float(root.attrib["width"])


def test_empty_scene_is_a_failed_diagnostic_not_a_success_claim() -> None:
    root = ET.fromstring(render_scene_svg(Scene(actors=())))
    assert len(_panels(root)) == 3
    assert _status(root).startswith("FAIL")
    assert "empty_scene" in "".join(root.itertext())


def test_rendering_has_no_pipeline_imports_network_scripts_or_external_resources() -> (
    None
):
    source = """
import importlib.abc
import socket
import sys
import xml.etree.ElementTree as ET

class BlockPipelines(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith((
            "t2i_spatial_pipeline", "t2i_prompt_pipeline", "t2i_story_pipeline",
            "t2i_model_provider", "t2i_film_style_pipeline", "httpx", "copilot",
        )):
            raise AssertionError("Unexpected pipeline/network import: " + fullname)

def blocked(*args, **kwargs):
    raise AssertionError("Network access attempted")

sys.meta_path.insert(0, BlockPipelines())
socket.create_connection = blocked
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
from t2i_pose_geometry.models import ActorPose, Scene
from t2i_pose_geometry.preview import render_scene_svg
root = ET.fromstring(render_scene_svg(Scene(actors=(ActorPose(actor_id="a"),))))
for element in root.iter():
    assert element.tag.rsplit("}", 1)[-1] not in {
        "script", "image", "foreignObject", "use", "iframe", "a",
    }
    for key, value in element.attrib.items():
        assert not key.lower().startswith("on")
        assert "href" not in key
        if "url(" in value:
            assert value.startswith("url(#clip-")
print("independent-static-svg")
"""
    result = subprocess.run(
        [sys.executable, "-c", source],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "independent-static-svg"
