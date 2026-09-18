"""Independent, fail-closed static scene validation.

Checks fixed-body joint bounds, self/inter-actor/furniture solid intersections,
and declared surface contacts. This is not a dynamics, equilibrium, friction,
strength, comfort, or biological safety assessment. No support declaration can
exempt a hand, forearm, foot, or other collider from collision checking.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter

import numpy as np
from pydantic import ValidationError

from .collision import (
    Collider,
    localized_overlap_proven,
    query_colliders,
    shallow_overlap_proven,
)
from .kinematics import Skeleton, forward_kinematics, matrix
from .models import (
    JOINT_LIMITS,
    Box,
    Face,
    Issue,
    Scene,
    Tolerances,
    ValidationReport,
    Vec3,
)

FACE_AXES: dict[Face, tuple[int, int]] = {
    "right": (0, 1),
    "left": (0, -1),
    "front": (1, 1),
    "back": (1, -1),
    "top": (2, 1),
    "bottom": (2, -1),
}


def face_frame(box: Box, face: Face) -> tuple[Vec3, Vec3]:
    """Return face-center position and outward world normal."""
    axis, sign = FACE_AXES[face]
    rotation = matrix(box.rotation)
    normal = sign * rotation[:, axis]
    center = np.asarray(box.center) + normal * box.size[axis] / 2
    return tuple(float(x) for x in center), tuple(float(x) for x in normal)


def _contact_issues(
    scene: Scene, skeletons: dict[str, Skeleton], tolerances: Tolerances
) -> list[Issue]:
    issues: list[Issue] = []
    objects = {obj.object_id: obj for obj in scene.objects}
    for contact in scene.contacts:
        parts = (contact.actor_id, contact.anchor, contact.object_id, contact.face)
        skeleton = skeletons.get(contact.actor_id)
        if skeleton is None:
            issues.append(
                Issue(
                    code="unknown_actor", parts=parts, details="Unknown contact actor"
                )
            )
            continue
        anchor = skeleton.anchors.get(contact.anchor)
        if anchor is None:
            issues.append(
                Issue(
                    code="unknown_anchor", parts=parts, details="Unknown contact anchor"
                )
            )
            continue
        obj = objects.get(contact.object_id)
        if obj is None:
            issues.append(
                Issue(
                    code="unknown_object", parts=parts, details="Unknown contact object"
                )
            )
            continue
        axis, sign = FACE_AXES[contact.face]
        rotation = matrix(obj.rotation)
        local = rotation.T @ (np.asarray(anchor.position) - np.asarray(obj.center))
        closest = np.clip(local, -np.asarray(obj.size) / 2, np.asarray(obj.size) / 2)
        closest[axis] = sign * obj.size[axis] / 2
        error = float(np.linalg.norm(local - closest))
        if error > tolerances.contact_m:
            issues.append(
                Issue(
                    code="contact_distance",
                    parts=parts,
                    details="Anchor is not on the bounded requested face",
                    error_m=error,
                )
            )
        outward = sign * rotation[:, axis]
        normal_error = math.degrees(
            math.acos(float(np.clip(-np.asarray(anchor.normal) @ outward, -1.0, 1.0)))
        )
        if normal_error > tolerances.normal_degrees:
            issues.append(
                Issue(
                    code="contact_normal",
                    parts=parts,
                    details=(
                        f"Surface normals are not opposing: {normal_error:.6g} degrees"
                    ),
                )
            )
    return issues


def _body_contact_issues(
    scene: Scene, skeletons: dict[str, Skeleton], tolerances: Tolerances
) -> list[Issue]:
    issues: list[Issue] = []
    for contact in scene.body_contacts:
        parts = (
            contact.actor_id,
            contact.anchor,
            contact.target_actor_id,
            contact.target_anchor,
        )
        endpoints = []
        for actor_id, anchor_name in (
            (contact.actor_id, contact.anchor),
            (contact.target_actor_id, contact.target_anchor),
        ):
            skeleton = skeletons.get(actor_id)
            if skeleton is None:
                issues.append(
                    Issue(
                        code="unknown_actor",
                        parts=parts,
                        details=f"Unknown body-contact actor: {actor_id}",
                    )
                )
                continue
            anchor = skeleton.anchors.get(anchor_name)
            if anchor is None:
                issues.append(
                    Issue(
                        code="unknown_anchor",
                        parts=parts,
                        details=(
                            f"Unknown body-contact anchor: {actor_id}/{anchor_name}"
                        ),
                    )
                )
                continue
            endpoints.append(anchor)
        if len(endpoints) != 2:
            continue
        source, target = endpoints
        distance = float(np.linalg.norm(np.subtract(source.position, target.position)))
        if distance > tolerances.contact_m:
            issues.append(
                Issue(
                    code="body_contact_distance",
                    parts=parts,
                    details="Current FK body-surface anchors are not coincident",
                    error_m=distance,
                )
            )
        normal_error = math.degrees(
            math.acos(
                float(
                    np.clip(
                        -np.asarray(source.normal) @ np.asarray(target.normal),
                        -1.0,
                        1.0,
                    )
                )
            )
        )
        if normal_error > tolerances.normal_degrees:
            issues.append(
                Issue(
                    code="body_contact_normal",
                    parts=parts,
                    details=(
                        f"Body-surface normals are not opposing: "
                        f"{normal_error:.6g} degrees"
                    ),
                )
            )
    return issues


def validate_scene(
    scene: Scene, *, tolerances: Tolerances | None = None
) -> ValidationReport:
    """Rebuild every body collider and test all distinct body/body and body/box pairs.

    Invalid models created through unchecked ``model_copy``/``model_construct``
    are revalidated. Dependency/narrowphase failures produce a failed report;
    no cached certificate, caller collision shape, or IK status is trusted.
    """
    try:
        scene = Scene.model_validate(scene.model_dump())
        tolerances = Tolerances.model_validate(
            (tolerances or Tolerances()).model_dump()
        )
    except (ValidationError, TypeError, ValueError, AttributeError) as error:
        return ValidationReport(
            passed=False,
            issues=(Issue(code="invalid_model", parts=(), details=str(error)),),
        )
    issues: list[Issue] = []
    for kind, identifiers in (
        ("actor", [actor.actor_id for actor in scene.actors]),
        ("object", [obj.object_id for obj in scene.objects]),
    ):
        for identifier, count in Counter(identifiers).items():
            if count > 1:
                issues.append(
                    Issue(
                        code="duplicate_id",
                        parts=(kind, identifier),
                        details=f"Duplicate {kind} identifier",
                    )
                )
    if issues:
        return ValidationReport(passed=False, issues=tuple(issues))
    if not scene.actors:
        return ValidationReport(
            passed=False,
            issues=(
                Issue(
                    code="empty_scene", parts=(), details="At least one actor required"
                ),
            ),
        )
    skeletons: dict[str, Skeleton] = {}
    colliders: dict[str, tuple[Collider, ...]] = {}
    try:
        for actor in scene.actors:
            for name, (lower, upper) in JOINT_LIMITS.items():
                angle = getattr(actor.angles, name)
                if not lower <= angle <= upper:
                    issues.append(
                        Issue(
                            code="joint_limit",
                            parts=(actor.actor_id, name),
                            details=(
                                f"{angle:g} degrees is outside [{lower:g}, {upper:g}]"
                            ),
                        )
                    )
            skeletons[actor.actor_id] = skeleton = forward_kinematics(actor)
            colliders[actor.actor_id] = tuple(Collider(s) for s in skeleton.shapes)
        objects = tuple(Collider(obj) for obj in scene.objects)

        def check(
            a: Collider,
            b: Collider,
            code: str,
            parts: tuple[str, ...],
            skeleton: Skeleton | None = None,
        ) -> None:
            a_low, a_high = a.bounds()
            b_low, b_high = b.bounds()
            if np.any(a_low > b_high) or np.any(b_low > a_high):
                return
            result = query_colliders(a, b)
            if not result.colliding or shallow_overlap_proven(
                a, b, tolerances.penetration_m, result
            ):
                return
            regions = ()
            if skeleton is not None:
                pair = frozenset((a.shape.shape_id, b.shape.shape_id))
                regions = tuple(
                    region
                    for region in skeleton.joint_regions
                    if frozenset(region.shapes) == pair
                )
            if regions and localized_overlap_proven(a, b, regions):
                return
            issues.append(
                Issue(
                    code=code,
                    parts=parts,
                    details=(
                        "Solid overlap outside numerical tolerance"
                        + (
                            "; containment in the local joint region was not proven"
                            if regions
                            else ""
                        )
                    ),
                    penetration_m=result.penetration_m,
                )
            )

        for actor in scene.actors:
            for a, b in itertools.combinations(colliders[actor.actor_id], 2):
                check(
                    a,
                    b,
                    "self_collision",
                    (actor.actor_id, a.shape.shape_id, b.shape.shape_id),
                    skeletons[actor.actor_id],
                )
            for body, obj in itertools.product(colliders[actor.actor_id], objects):
                check(
                    body,
                    obj,
                    "object_collision",
                    (actor.actor_id, body.shape.shape_id, obj.shape.shape_id),
                )
        for first, second in itertools.combinations(scene.actors, 2):
            for a, b in itertools.product(
                colliders[first.actor_id], colliders[second.actor_id]
            ):
                check(
                    a,
                    b,
                    "inter_actor_collision",
                    (
                        first.actor_id,
                        a.shape.shape_id,
                        second.actor_id,
                        b.shape.shape_id,
                    ),
                )
        issues.extend(_contact_issues(scene, skeletons, tolerances))
        issues.extend(_body_contact_issues(scene, skeletons, tolerances))
    except (ArithmeticError, RuntimeError, ValueError, TypeError) as error:
        issues.append(Issue(code="geometry_error", parts=(), details=str(error)))
    return ValidationReport(passed=not issues, issues=tuple(issues))
