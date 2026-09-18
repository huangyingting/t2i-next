"""Static orthographic diagnostics of the model's actual collision proxies.

This is neither an image generator nor an anatomical, medical, or safety
assessment. Rendering rebuilds kinematics and validation without changing a pose.
Only oversized horizontal ground boxes can be cropped by the preview viewport.
"""

from __future__ import annotations

import itertools
import math
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np

from .kinematics import Skeleton, forward_kinematics, matrix
from .models import Box, Scene, Shape, ValidationReport
from .validation import FACE_AXES, validate_scene

_RED = "#c62828"
_INK = "#263238"
_CONTACT = "#9b6500"
_WIDTH = 1272
_PANEL_WIDTH = 400
_PANEL_HEIGHT = 430
_PLOT_WIDTH = 364
_PLOT_HEIGHT = 322
_PALETTE = ("#1565c0", "#008577", "#8e44ad", "#c45c00", "#526d27", "#80514b")
_IMPORTANT_ANCHORS = {
    "seat",
    "back",
    "left_sole",
    "right_sole",
    "left_palm",
    "right_palm",
}


def _xml(value: object) -> str:
    """Replace XML 1.0 forbidden characters before ElementTree escapes markup."""
    return "".join(
        char
        if (
            char in "\t\n\r"
            or "\x20" <= char <= "\ud7ff"
            or "\ue000" <= char <= "\ufffd"
            or "\U00010000" <= char <= "\U0010ffff"
        )
        else "\ufffd"
        for char in str(value)
    )


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("Preview coordinates must be finite")
    return f"{0.0 if abs(value) < 0.0000005 else value:.6f}".rstrip("0").rstrip(".")


def _element(parent: ET.Element, tag: str, **attrs: object) -> ET.Element:
    return ET.SubElement(
        parent,
        tag,
        {
            key.rstrip("_").replace("_", "-"): (
                _number(value) if isinstance(value, float) else _xml(value)
            )
            for key, value in attrs.items()
        },
    )


def _text(parent: ET.Element, x: float, y: float, value: str, **attrs: object) -> None:
    _element(parent, "text", x=x, y=y, **attrs).text = _xml(value)


def _title(parent: ET.Element, value: str) -> None:
    _element(parent, "title").text = _xml(value)


def _short(value: str) -> str:
    return value if len(value) <= 38 else value[:35] + "..."


def _color(index: int) -> str:
    if index < len(_PALETTE):
        return _PALETTE[index]
    return f"hsl({index * 137.508 % 360:.3f},65%,36%)"


def _box_corners(shape: Shape | Box) -> np.ndarray:
    offsets = np.array(list(itertools.product((-0.5, 0.5), repeat=3)))
    return (offsets * np.asarray(shape.size)) @ matrix(shape.rotation).T + shape.center


def _bounds(shape: Shape | Box) -> tuple[np.ndarray, np.ndarray]:
    rotation = matrix(shape.rotation)
    if isinstance(shape, Box) or shape.kind == "box":
        extent = np.abs(rotation) @ (np.asarray(shape.size) / 2)
    elif shape.kind == "capsule":
        extent = np.abs(rotation[:, 2]) * shape.length / 2 + shape.radius
    else:
        extent = np.linalg.norm(rotation * np.asarray(shape.radii), axis=1)
    return np.asarray(shape.center) - extent, np.asarray(shape.center) + extent


def _hull(points: np.ndarray) -> list[tuple[float, float]]:
    """Monotone convex hull, including degenerate orthographic projections."""
    ordered = sorted(set(map(tuple, points.tolist())))
    if len(ordered) <= 2:
        return ordered

    def half(sequence: list[tuple[float, float]]) -> list[tuple[float, float]]:
        result: list[tuple[float, float]] = []
        for point in sequence:
            while len(result) >= 2:
                a, b = result[-2:]
                cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (
                    point[0] - a[0]
                )
                if cross > 0:
                    break
                result.pop()
            result.append(point)
        return result

    return half(ordered)[:-1] + half(ordered[::-1])[:-1]


@dataclass(frozen=True)
class _View:
    name: str
    horizontal: int
    vertical: int
    scale: float
    origin_x: float
    origin_y: float

    def point(self, position: np.ndarray | tuple) -> tuple[float, float]:
        return (
            self.origin_x + self.scale * position[self.horizontal],
            self.origin_y - self.scale * position[self.vertical],
        )

    def projection(self) -> np.ndarray:
        projection = np.zeros((2, 3))
        projection[0, self.horizontal] = self.scale
        projection[1, self.vertical] = -self.scale
        return projection


def _volume(
    parent: ET.Element,
    view: _View,
    shape: Shape | Box,
    owner: str,
    color: str,
    errors: list[str],
) -> None:
    kind = "box" if isinstance(shape, Box) else shape.kind
    name = shape.object_id if isinstance(shape, Box) else shape.shape_id
    group = _element(
        parent,
        "g",
        class_="collision-volume",
        data_owner=owner,
        data_shape=name,
        data_kind=kind,
        data_errors=" ".join(errors),
        fill=_RED if errors else color,
        stroke=_RED if errors else color,
        fill_opacity="0.20",
        stroke_width="1.3",
    )
    _title(
        group,
        f"{owner}: {name} ({kind})" + ("; " + "; ".join(errors) if errors else ""),
    )
    cx, cy = view.point(shape.center)
    if kind == "box":
        hull = _hull(np.array([view.point(p) for p in _box_corners(shape)]))
        _element(
            group,
            "polygon",
            points=" ".join(f"{_number(x)},{_number(y)}" for x, y in hull),
        )
    elif kind == "capsule":
        axis = matrix(shape.rotation)[:, 2] * shape.length / 2
        start = view.point(np.asarray(shape.center) - axis)
        end = view.point(np.asarray(shape.center) + axis)
        radius = shape.radius * view.scale
        if math.dist(start, end) < 1e-8:
            _element(group, "circle", cx=cx, cy=cy, r=radius)
        else:
            _element(
                group,
                "line",
                x1=start[0],
                y1=start[1],
                x2=end[0],
                y2=end[1],
                stroke_width=2 * radius,
                stroke_linecap="round",
                stroke_opacity="0.35",
            )
    else:
        projected = view.projection() @ matrix(shape.rotation) * shape.radii
        values, vectors = np.linalg.eigh(projected @ projected.T)
        rx, ry = np.sqrt(np.maximum(values[::-1], 0))
        angle = (
            0.0
            if math.isclose(rx, ry, rel_tol=1e-12)
            else math.degrees(math.atan2(vectors[1, 1], vectors[0, 1]))
        )
        _element(
            group,
            "ellipse",
            cx=cx,
            cy=cy,
            rx=float(rx),
            ry=float(ry),
            transform=f"rotate({_number(angle)} {_number(cx)} {_number(cy)})",
        )
    if errors:
        _text(
            parent,
            cx + 5,
            cy - 5,
            ", ".join(error.split()[0] for error in errors),
            class_="error-label",
            data_owner=owner,
            data_shape=name,
            fill=_RED,
            font_size="10",
            font_weight="bold",
        )


def _joint_parts(name: str) -> tuple[str, ...]:
    if name.startswith("torso_"):
        return ("torso", "neck", "head", "left_clavicle", "right_clavicle")
    if name.startswith("head_"):
        return ("head", "neck")
    side, joint, *_ = name.split("_")
    affected = {
        "hip": ("hip_joint", "thigh", "pelvis"),
        "knee": ("thigh", "knee_joint", "shin"),
        "ankle": ("shin", "ankle_joint", "foot"),
        "shoulder": ("clavicle", "shoulder_joint", "upper_arm"),
        "elbow": ("upper_arm", "elbow_joint", "forearm"),
        "wrist": ("forearm", "wrist_joint", "hand"),
    }
    return tuple(
        part if part == "pelvis" else f"{side}_{part}"
        for part in affected.get(joint, ())
    )


def _issue_shapes(
    scene: Scene,
    report: ValidationReport,
    skeletons: dict[str, Skeleton],
) -> tuple[dict[tuple[str, str], list[str]], dict[str, list[str]]]:
    bodies: dict[tuple[str, str], list[str]] = {}
    objects: dict[str, list[str]] = {}
    object_contacts = {
        (contact.actor_id, contact.anchor, contact.object_id, contact.face)
        for contact in scene.contacts
    }
    for index, issue in enumerate(report.issues, 1):
        label = f"E{index} {issue.code}"
        parts = issue.parts
        pairs: list[tuple[str, str]] = []
        if issue.code == "self_collision" and len(parts) == 3:
            pairs = [(parts[0], part) for part in parts[1:]]
        elif issue.code == "object_collision" and len(parts) == 3:
            pairs = [(parts[0], parts[1])]
            objects.setdefault(parts[2], []).append(label)
        elif issue.code == "inter_actor_collision" and len(parts) == 4:
            pairs = [(parts[0], parts[1]), (parts[2], parts[3])]
        elif issue.code == "joint_limit" and len(parts) == 2:
            pairs = [(parts[0], part) for part in _joint_parts(parts[1])]
        elif issue.code == "duplicate_id" and len(parts) == 2:
            if parts[0] == "object":
                objects.setdefault(parts[1], []).append(label)
            elif parts[1] in skeletons:
                pairs = [(parts[1], s.shape_id) for s in skeletons[parts[1]].shapes]
        else:
            # Contact issues identify an actor followed by its surface anchor.
            object_contact = parts in object_contacts
            for offset in (0,) if object_contact else (0, 2):
                if len(parts) <= offset + 1 or parts[offset] not in skeletons:
                    continue
                anchor = skeletons[parts[offset]].anchors.get(parts[offset + 1])
                if anchor is not None:
                    pairs.append((parts[offset], anchor.shape_id))
            if object_contact:
                objects.setdefault(parts[2], []).append(label)
        for pair in pairs:
            bodies.setdefault(pair, []).append(label)
    return bodies, objects


def _overlay(parent: ET.Element, view: _View, owner: str, skeleton: Skeleton) -> None:
    bones = [
        ("root", "shoulder_center"),
        ("shoulder_center", "head_base"),
        ("head_base", "head"),
    ]
    for side in ("left", "right"):
        bones.extend(
            [
                ("root", f"{side}_hip"),
                (f"{side}_hip", f"{side}_knee"),
                (f"{side}_knee", f"{side}_ankle"),
                ("shoulder_center", f"{side}_shoulder"),
                (f"{side}_shoulder", f"{side}_elbow"),
                (f"{side}_elbow", f"{side}_wrist"),
            ]
        )
    group = _element(parent, "g", class_="skeleton", data_actor=owner)
    for start, end in bones:
        if start in skeleton.joints and end in skeleton.joints:
            x1, y1 = view.point(skeleton.joints[start])
            x2, y2 = view.point(skeleton.joints[end])
            _element(
                group,
                "line",
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                stroke=_INK,
                stroke_width="0.8",
                stroke_opacity="0.65",
            )
    for name, position in skeleton.joints.items():
        x, y = view.point(position)
        marker = _element(
            group,
            "circle",
            cx=x,
            cy=y,
            r="1.8",
            fill=_INK,
            data_joint=name,
        )
        _title(marker, f"{owner}.{name}")
        if name in {"root", "head"}:
            _text(group, x + 5, y - 5, _short(f"{owner}.{name}"), font_size="9")


def _marker(
    parent: ET.Element,
    view: _View,
    position: tuple | np.ndarray,
    label: str,
    role: str,
    contact: str,
) -> None:
    x, y = view.point(position)
    group = _element(
        parent,
        "g",
        class_="contact-marker",
        data_contact=contact,
        data_role=role,
    )
    _title(group, label)
    _element(
        group,
        "circle",
        cx=x,
        cy=y,
        r="5",
        fill="#fff3cd",
        stroke=_CONTACT,
        stroke_width="1.8",
    )
    _element(
        group,
        "path",
        d=f"M{_number(x - 3)},{_number(y)}h6M{_number(x)},{_number(y - 3)}v6",
        stroke=_CONTACT,
        fill="none",
    )
    _text(
        group,
        x + 7,
        y + (13 if role == "target" else -7),
        _short(label),
        font_size="9",
        fill=_CONTACT,
    )


def _contacts(
    parent: ET.Element,
    view: _View,
    scene: Scene,
    skeletons: dict[str, Skeleton],
) -> None:
    objects = {obj.object_id: obj for obj in scene.objects}
    for index, contact in enumerate(scene.contacts, 1):
        skeleton = skeletons.get(contact.actor_id)
        anchor = skeleton.anchors.get(contact.anchor) if skeleton else None
        if anchor is None:
            continue
        label = f"C{index} {contact.actor_id}.{contact.anchor}"
        obj = objects.get(contact.object_id)
        if obj is not None:
            rotation = matrix(obj.rotation)
            half = np.asarray(obj.size) / 2
            local = rotation.T @ (np.asarray(anchor.position) - obj.center)
            target = np.clip(local, -half, half)
            axis, sign = FACE_AXES[contact.face]
            target[axis] = sign * half[axis]
            target = rotation @ target + obj.center
            x1, y1 = view.point(anchor.position)
            x2, y2 = view.point(target)
            _element(
                parent,
                "line",
                class_="contact-gap",
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                stroke=_CONTACT,
                stroke_dasharray="3 3",
            )
            _marker(
                parent,
                view,
                target,
                f"C{index} {contact.object_id}.{contact.face}",
                "target",
                f"C{index}",
            )
        _marker(parent, view, anchor.position, label, "anchor", f"C{index}")
    for index, contact in enumerate(scene.body_contacts, 1):
        endpoints = []
        for owner, name, role in (
            (contact.actor_id, contact.anchor, "anchor"),
            (contact.target_actor_id, contact.target_anchor, "target"),
        ):
            skeleton = skeletons.get(owner)
            anchor = skeleton.anchors.get(name) if skeleton else None
            if anchor is not None:
                endpoints.append(anchor.position)
                _marker(
                    parent,
                    view,
                    anchor.position,
                    f"B{index} {owner}.{name}",
                    role,
                    f"B{index}",
                )
        if len(endpoints) == 2:
            x1, y1 = view.point(endpoints[0])
            x2, y2 = view.point(endpoints[1])
            _element(
                parent,
                "line",
                class_="body-contact-gap",
                data_contact=f"B{index}",
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                stroke=_CONTACT,
                stroke_dasharray="3 3",
            )


def _viewport(
    scene: Scene,
    skeletons: list[Skeleton],
) -> tuple[np.ndarray, np.ndarray, bool]:
    body_bounds = [_bounds(shape) for skel in skeletons for shape in skel.shapes]
    if body_bounds:
        low = np.min([b[0] for b in body_bounds], axis=0)
        high = np.max([b[1] for b in body_bounds], axis=0)
    else:
        low, high = np.array([-0.5, -0.5, 0.0]), np.array([0.5, 0.5, 2.0])
    bounds = [(low, high)]
    span = max(float(np.max(high - low)), 0.1)
    clipped = False
    for obj in scene.objects:
        obj_low, obj_high = _bounds(obj)
        upright = abs(matrix(obj.rotation)[2, 2]) > 1 - 1e-10
        if (
            body_bounds
            and upright
            and obj.center[2] <= low[2]
            and obj.size[2] <= span
            and max(obj.size[:2]) > 4 * span
        ):
            # Crop only the viewport contribution, never the model or drawn solid.
            obj_low[:2] = np.maximum(obj_low[:2], low[:2] - span / 2)
            obj_high[:2] = np.minimum(obj_high[:2], high[:2] + span / 2)
            clipped = True
        bounds.append((obj_low, obj_high))
    return (
        np.min([b[0] for b in bounds], axis=0),
        np.max([b[1] for b in bounds], axis=0),
        clipped,
    )


def _report_lines(report: ValidationReport) -> list[str]:
    lines = []
    for index, issue in enumerate(report.issues, 1):
        message = f"E{index} {issue.code}: {' / '.join(issue.parts)}; {issue.details}"
        if issue.error_m is not None:
            message += f"; distance error={issue.error_m:.6g} m"
        if issue.penetration_m is not None:
            message += f"; penetration={issue.penetration_m:.6g} m"
        lines.extend(textwrap.wrap(_xml(message), width=164) or [""])
    return lines


def render_scene_svg(scene: Scene) -> str:
    """Revalidate ``scene`` and render actual proxy volumes in three fixed panels.

    Front is x/z, side is y/z, and top is x/y, using one isotropic pixels-per-meter
    scale. Required contacts show surface-anchor and bounded-face target markers,
    or both actor anchors for body contacts.
    The returned self-contained SVG has no scripts, resources, or supplied report.
    """
    report = validate_scene(scene)
    try:
        scene = Scene.model_validate(scene.model_dump())
    except (ValueError, TypeError, AttributeError):
        # Unchecked model_construct/model_copy inputs must not become SVG numbers.
        scene = Scene(actors=())
    skeleton_list = [forward_kinematics(actor) for actor in scene.actors]
    skeletons = {
        actor.actor_id: skeleton
        for actor, skeleton in zip(scene.actors, skeleton_list, strict=True)
    }
    body_errors, object_errors = _issue_shapes(scene, report, skeletons)
    low, high, clipped = _viewport(scene, skeleton_list)
    span = np.maximum(high - low, 0.1)
    center = low + span / 2
    scale = (
        min(
            _PLOT_WIDTH / max(span[0], span[1]),
            _PLOT_HEIGHT / max(span[2], span[1]),
        )
        * 0.86
    )
    legend_rows = max(1, math.ceil((len(scene.actors) + 1) / 4))
    panels_y = 116 + legend_rows * 18
    report_y = panels_y + _PANEL_HEIGHT + 30
    lines = _report_lines(report)
    height = report_y + 46 + len(lines) * 16
    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(_WIDTH),
            "height": str(height),
            "viewBox": f"0 0 {_WIDTH} {height}",
            "role": "img",
            "aria-labelledby": "preview-title preview-description",
            "font-family": "monospace",
            "font-size": "12",
            "fill": _INK,
        },
    )
    _element(root, "title", id="preview-title").text = "Diagnostic proxy geometry"
    _element(root, "desc", id="preview-description").text = (
        "Front, side, and top orthographic collision volumes with skeletal overlays. "
        "Not an AI render; not a medical or safety assessment. "
        "Validation is recomputed from the unchanged scene."
    )
    _element(root, "rect", width=_WIDTH, height=height, fill="#ffffff")
    _text(root, 20, 28, "Diagnostic proxy geometry", font_size="20", font_weight="bold")
    _text(root, 20, 49, "Not an AI render; not a medical or safety assessment.")
    _text(
        root,
        20,
        71,
        f"{'PASS' if report.passed else 'FAIL'} — recomputed static geometry "
        f"validation; {len(report.issues)} issue(s).",
        fill="#176b3a" if report.passed else _RED,
        font_weight="bold",
        class_="validation-status",
    )
    for index, actor in enumerate(scene.actors):
        x, y = 20 + (index % 4) * 310, 95 + (index // 4) * 18
        _element(root, "rect", x=x, y=y - 10, width=10, height=10, fill=_color(index))
        _text(root, x + 16, y, _short(actor.actor_id), fill=_color(index))
    index = len(scene.actors)
    _text(
        root,
        20 + (index % 4) * 310,
        95 + (index // 4) * 18,
        "Gray: objects; red: errors",
        font_size="11",
    )
    _text(
        root,
        20,
        panels_y - 12,
        "Meters; shared scale. Amber: required contacts. "
        + (
            "Large ground boxes clipped (preview only); geometry unchanged."
            if clipped
            else "Panel clipping is preview-only; geometry unchanged."
        ),
        font_size="11",
    )
    defs = _element(root, "defs")
    for index, (name, horizontal, vertical, direction) in enumerate(
        (
            ("front", 0, 2, "from +y"),
            ("side", 1, 2, "from -x"),
            ("top", 0, 1, "from +z"),
        )
    ):
        x = 20 + index * (_PANEL_WIDTH + 16)
        plot_x, plot_y = x + 18, panels_y + 52
        view = _View(
            name,
            horizontal,
            vertical,
            float(scale),
            float(plot_x + _PLOT_WIDTH / 2 - scale * center[horizontal]),
            float(plot_y + _PLOT_HEIGHT / 2 + scale * center[vertical]),
        )
        panel = _element(
            root,
            "g",
            class_="view",
            data_view=name,
            data_scale=view.scale,
            data_origin_x=view.origin_x,
            data_origin_y=view.origin_y,
            data_horizontal_axis="xyz"[horizontal],
            data_vertical_axis="xyz"[vertical],
        )
        _element(
            panel,
            "rect",
            x=x,
            y=panels_y,
            width=_PANEL_WIDTH,
            height=_PANEL_HEIGHT,
            rx="6",
            fill="#fafbfc",
            stroke="#c9d3db",
        )
        _text(
            panel,
            x + 14,
            panels_y + 23,
            f"{name.title()} — {direction}",
            font_size="15",
            font_weight="bold",
        )
        _text(
            panel,
            x + 14,
            panels_y + 41,
            f"+{'xyz'[horizontal]} right / +{'xyz'[vertical]} up",
            font_size="11",
        )
        clip = _element(defs, "clipPath", id=f"clip-{index}")
        _element(
            clip, "rect", x=plot_x, y=plot_y, width=_PLOT_WIDTH, height=_PLOT_HEIGHT
        )
        drawing = _element(panel, "g", clip_path=f"url(#clip-{index})")
        for obj in scene.objects:
            _volume(
                drawing,
                view,
                obj,
                obj.object_id,
                "#687582",
                object_errors.get(obj.object_id, []),
            )
        for actor_index, (actor, skeleton) in enumerate(
            zip(scene.actors, skeleton_list, strict=True)
        ):
            for shape in skeleton.shapes:
                _volume(
                    drawing,
                    view,
                    shape,
                    actor.actor_id,
                    _color(actor_index),
                    body_errors.get((actor.actor_id, shape.shape_id), []),
                )
        for actor, skeleton in zip(scene.actors, skeleton_list, strict=True):
            _overlay(drawing, view, actor.actor_id, skeleton)
            for name, anchor in skeleton.anchors.items():
                ax, ay = view.point(anchor.position)
                errors = body_errors.get((actor.actor_id, anchor.shape_id), [])
                color = _RED if errors else _INK
                marker = _element(
                    drawing,
                    "circle",
                    cx=ax,
                    cy=ay,
                    r="2.3",
                    fill="#fff",
                    stroke=color,
                    data_anchor=name,
                    data_actor=actor.actor_id,
                )
                _title(marker, f"{actor.actor_id}.{name}")
                if name in _IMPORTANT_ANCHORS:
                    _text(
                        drawing,
                        ax + 4,
                        ay + 10,
                        _short(f"{actor.actor_id}.{name}"),
                        fill=color,
                        font_size="9",
                    )
        _contacts(drawing, view, scene, skeletons)
        _text(
            panel,
            x + 14,
            panels_y + 397,
            f"{scale:.3f} px/m; +{'xyz'[horizontal]} range "
            f"[{low[horizontal]:.3g}, {high[horizontal]:.3g}] m",
            font_size="10",
        )
        _text(
            panel,
            x + 14,
            panels_y + 414,
            "Solid proxies + joints; no pose correction",
            font_size="10",
        )
    _text(
        root,
        20,
        report_y,
        "Validation issues" if lines else "No validation issues.",
        font_weight="bold",
        fill=_RED if lines else _INK,
    )
    for index, line in enumerate(lines):
        _text(root, 20, report_y + 22 + index * 16, line, fill=_RED, font_size="12")
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)
