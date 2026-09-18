"""Convex-solid collision queries backed by FCL, with conservative joint proofs.

Contact points are diagnostics, never a certificate that all overlap is shallow.
Numerical touching is certified by exact support-function interval separation.
Joint allowances use a bounded subdivision of a *covering* box of the actual
intersection: each cell must be wholly inside an allowed sphere, or proven
disjoint from at least one actual solid. Unresolved cells fail closed. No limb
pair is globally exempted, and subdivision never reduces body radii.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import fcl
import numpy as np

from .kinematics import matrix, vector
from .models import Box, JointRegion, Shape, Vec3


@dataclass(frozen=True)
class ContactPoint:
    position: Vec3
    normal: Vec3
    penetration_m: float


@dataclass(frozen=True)
class PairResult:
    colliding: bool
    distance_m: float
    penetration_m: float | None
    contacts: tuple[ContactPoint, ...]


def box_shape(box: Box) -> Shape:
    return Shape(
        shape_id=box.object_id,
        kind="box",
        center=box.center,
        size=box.size,
        rotation=box.rotation,
    )


class Collider:
    """One in-memory FCL object and its exact convex support function."""

    def __init__(self, shape: Shape | Box):
        self.shape = box_shape(shape) if isinstance(shape, Box) else shape
        self.center = np.asarray(self.shape.center)
        self.rotation = matrix(self.shape.rotation)
        if self.shape.kind == "capsule":
            geometry = fcl.Capsule(self.shape.radius, self.shape.length)
        elif self.shape.kind == "ellipsoid":
            geometry = fcl.Ellipsoid(*self.shape.radii)
        else:
            geometry = fcl.Box(*self.shape.size)
        self.object = fcl.CollisionObject(
            geometry, fcl.Transform(self.rotation, self.center)
        )

    def extent(self, normal: np.ndarray) -> float:
        local = self.rotation.T @ normal
        if self.shape.kind == "capsule":
            return float(
                self.shape.radius * np.linalg.norm(normal)
                + self.shape.length / 2 * abs(local[2])
            )
        if self.shape.kind == "ellipsoid":
            return float(np.linalg.norm(np.asarray(self.shape.radii) * local))
        return float(np.abs(local) @ (np.asarray(self.shape.size) / 2))

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        extents = np.array([self.extent(axis) for axis in np.eye(3)])
        return self.center - extents, self.center + extents


def _intersects(a: fcl.CollisionObject, b: fcl.CollisionObject) -> bool:
    result = fcl.CollisionResult()
    count = fcl.collide(a, b, fcl.CollisionRequest(), result)
    return bool(count or result.is_collision)


def query_colliders(a: Collider, b: Collider) -> PairResult:
    result = fcl.CollisionResult()
    count = fcl.collide(
        a.object,
        b.object,
        fcl.CollisionRequest(num_max_contacts=64, enable_contact=True),
        result,
    )
    colliding = bool(count or result.is_collision)
    contacts = tuple(
        ContactPoint(
            position=vector(contact.pos),
            normal=vector(contact.normal),
            penetration_m=float(contact.penetration_depth),
        )
        for contact in result.contacts
    )
    if any(
        not all(math.isfinite(value) for value in (*c.position, *c.normal))
        or not math.isfinite(c.penetration_m)
        for c in contacts
    ):
        raise ArithmeticError("FCL produced a non-finite contact")
    if colliding:
        return PairResult(
            True,
            0.0,
            max((max(0.0, c.penetration_m) for c in contacts), default=None),
            contacts,
        )
    distance = float(
        fcl.distance(a.object, b.object, fcl.DistanceRequest(), fcl.DistanceResult())
    )
    if not math.isfinite(distance):
        raise ArithmeticError("FCL produced an invalid separation distance")
    if distance < 0:
        # Unsigned FCL distance may report its overlap sentinel at tangency
        # even when collide() reports separation. Resolve conservatively;
        # support functions still independently certify harmless touching.
        return PairResult(True, 0.0, None, ())
    return PairResult(False, distance, 0.0, ())


def query_pair(a: Shape | Box, b: Shape | Box) -> PairResult:
    """Exact convex collision boolean and unsigned separation, in meters."""
    return query_colliders(Collider(a), Collider(b))


def shallow_overlap_proven(
    a: Collider, b: Collider, tolerance: float, result: PairResult
) -> bool:
    """Certify a separating translation of at most ``tolerance`` meters.

    Contact normals merely propose directions; an independent whole-solid
    support-function test proves the bound even if FCL omitted other contacts.
    """
    if not result.colliding:
        return True
    candidates = [
        *a.rotation.T,
        *b.rotation.T,
        b.center - a.center,
        *(np.asarray(contact.normal) for contact in result.contacts),
    ]
    candidates.extend(
        np.cross(first, second) for first in a.rotation.T for second in b.rotation.T
    )
    for candidate in candidates:
        length = float(np.linalg.norm(candidate))
        if length <= 1e-12:
            continue
        normal = candidate / length
        separation = abs(float((b.center - a.center) @ normal)) - (
            a.extent(normal) + b.extent(normal)
        )
        if separation >= -tolerance:
            return True
    return False


def _contained(collider: Collider, region: JointRegion) -> bool:
    offset = collider.center - np.asarray(region.center)
    if collider.shape.kind == "capsule":
        half_line = collider.rotation[:, 2] * collider.shape.length / 2
        farthest = max(
            np.linalg.norm(offset - half_line), np.linalg.norm(offset + half_line)
        )
        bound = farthest + collider.shape.radius
    elif collider.shape.kind == "ellipsoid":
        bound = np.linalg.norm(offset) + max(collider.shape.radii)
    else:
        half_size = np.asarray(collider.shape.size) / 2
        bound = max(
            np.linalg.norm(offset + collider.rotation @ (half_size * signs))
            for signs in itertools.product((-1, 1), repeat=3)
        )
    return bool(bound <= region.radius - 1e-10)


def localized_overlap_proven(
    a: Collider,
    b: Collider,
    regions: tuple[JointRegion, ...],
    *,
    max_depth: int = 14,
    max_cells: int = 4096,
) -> bool:
    """Prove all common volume is inside the specified local joint spheres.

    This is deliberately conservative: exceeding the subdivision budget rejects
    the pose. The allowed regions must already be derived from trusted FK and
    scoped to this exact pair; callers must not supply artist-authored regions.
    """
    if not regions:
        return False
    if any(_contained(a, region) or _contained(b, region) for region in regions):
        return True
    a_low, a_high = a.bounds()
    b_low, b_high = b.bounds()
    low, high = np.maximum(a_low, b_low), np.minimum(a_high, b_high)
    if np.any(low > high):
        return True
    # Outward padding preserves the covering property under floating point.
    stack = [(low - 1e-10, high + 1e-10, 0)]
    visited = 0
    while stack:
        low, high, depth = stack.pop()
        visited += 1
        if visited > max_cells:
            return False
        center = (low + high) / 2
        half_size = (high - low) / 2
        if any(
            np.linalg.norm(np.abs(center - region.center) + half_size)
            <= region.radius - 1e-10
            for region in regions
        ):
            continue
        cell = fcl.CollisionObject(
            fcl.Box(*(high - low)), fcl.Transform(np.eye(3), center)
        )
        if not _intersects(cell, a.object) or not _intersects(cell, b.object):
            continue
        if depth >= max_depth:
            return False
        axis = int(np.argmax(high - low))
        first_high, second_low = high.copy(), low.copy()
        first_high[axis] = second_low[axis] = center[axis]
        stack.append((low, first_high, depth + 1))
        stack.append((second_low, high, depth + 1))
    return True
