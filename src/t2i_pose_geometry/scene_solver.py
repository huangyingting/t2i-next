"""Joint scene contact fitting followed by independent solid validation.

Every actor is rebuilt from the same candidate vector on each iteration.
Furniture, dimensions and contact identities never move to accommodate a fit.
Collision avoidance is not an optimization objective: colliding candidates are
rejected by the independent validator even when all contact residuals converge.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np
from scipy.optimize import least_squares

from .kinematics import Skeleton, forward_kinematics, matrix
from .models import Scene, SceneContactError, SceneSolveResult, Tolerances
from .solver import _ActorParameters, _validate_solver_options
from .validation import FACE_AXES, validate_scene


def _validate_constraints(scene: Scene, skeletons: dict[str, Skeleton]) -> None:
    objects = {obj.object_id for obj in scene.objects}

    def require_anchor(actor_id: str, name: str) -> None:
        if actor_id not in skeletons:
            raise ValueError(f"Unknown contact actor: {actor_id}")
        if name not in skeletons[actor_id].anchors:
            raise ValueError(f"Unknown contact anchor: {actor_id}/{name}")

    for contact in scene.contacts:
        require_anchor(contact.actor_id, contact.anchor)
        if contact.object_id not in objects:
            raise ValueError(f"Unknown contact object: {contact.object_id}")
    for contact in scene.body_contacts:
        require_anchor(contact.actor_id, contact.anchor)
        require_anchor(contact.target_actor_id, contact.target_anchor)


def _contact_vectors(
    scene: Scene, skeletons: dict[str, Skeleton]
) -> list[tuple[np.ndarray, np.ndarray]]:
    vectors = []
    objects = {obj.object_id: obj for obj in scene.objects}
    for contact in scene.contacts:
        anchor = skeletons[contact.actor_id].anchors[contact.anchor]
        obj = objects[contact.object_id]
        rotation = matrix(obj.rotation)
        local = rotation.T @ (np.asarray(anchor.position) - obj.center)
        half = np.asarray(obj.size) / 2
        nearest = np.clip(local, -half, half)
        axis, sign = FACE_AXES[contact.face]
        nearest[axis] = sign * half[axis]
        vectors.append(
            (local - nearest, np.asarray(anchor.normal) + sign * rotation[:, axis])
        )
    for contact in scene.body_contacts:
        first = skeletons[contact.actor_id].anchors[contact.anchor]
        second = skeletons[contact.target_actor_id].anchors[contact.target_anchor]
        vectors.append(
            (
                np.subtract(first.position, second.position),
                np.add(first.normal, second.normal),
            )
        )
    return vectors


def solve_scene(
    scene: Scene,
    variables_by_actor: Mapping[str, tuple[str, ...]],
    max_nfev: int = 200,
    *,
    tolerances: Tolerances | None = None,
    root_translation_bound_m: float = 2.0,
) -> SceneSolveResult:
    """Fit every declared contact simultaneously and revalidate the whole scene.

    Supply selectors for every actor explicitly; an empty tuple fixes an actor.
    Selectors and bounds match ``solve_actor``. At least one contact is required.
    Unsupported endpoints, duplicate IDs, unconstrained movable actors and
    invalid solver options raise rather than dropping constraints. A failed
    numerical search does not prove that no feasible pose exists.
    """
    scene = Scene.model_validate(scene.model_dump())
    tolerances = Tolerances.model_validate((tolerances or Tolerances()).model_dump())
    _validate_solver_options(max_nfev, root_translation_bound_m)
    if not scene.actors:
        raise ValueError("At least one actor is required")
    actor_ids = [actor.actor_id for actor in scene.actors]
    object_ids = [obj.object_id for obj in scene.objects]
    if len(set(actor_ids)) != len(actor_ids) or len(set(object_ids)) != len(object_ids):
        raise ValueError("Scene actor and object IDs must be unique within their kind")
    if not isinstance(variables_by_actor, Mapping) or set(variables_by_actor) != set(
        actor_ids
    ):
        raise ValueError("IK variables must explicitly name every scene actor")
    if not scene.contacts and not scene.body_contacts:
        raise ValueError("At least one scene contact is required")
    skeletons = {
        actor.actor_id: forward_kinematics(actor, include_shapes=False)
        for actor in scene.actors
    }
    _validate_constraints(scene, skeletons)
    constrained = {contact.actor_id for contact in scene.contacts}
    constrained.update(contact.actor_id for contact in scene.body_contacts)
    constrained.update(contact.target_actor_id for contact in scene.body_contacts)
    parameters = []
    for actor in scene.actors:
        packed = _ActorParameters(
            actor, variables_by_actor[actor.actor_id], root_translation_bound_m
        )
        if packed.names and actor.actor_id not in constrained:
            raise ValueError(
                f"Movable actor has no contact constraints: {actor.actor_id}"
            )
        parameters.append(packed)
    initial = np.asarray([value for actor in parameters for value in actor.initial])
    lower = np.asarray([value for actor in parameters for value in actor.lower])
    upper = np.asarray([value for actor in parameters for value in actor.upper])

    def candidate(values: np.ndarray) -> Scene:
        actors = []
        offset = 0
        for actor in parameters:
            end = offset + len(actor.names)
            actors.append(actor.candidate(values[offset:end]))
            offset = end
        return Scene(
            actors=tuple(actors),
            objects=scene.objects,
            contacts=scene.contacts,
            body_contacts=scene.body_contacts,
        )

    def vectors_for(current: Scene) -> list[tuple[np.ndarray, np.ndarray]]:
        return _contact_vectors(
            current,
            {
                actor.actor_id: forward_kinematics(actor, include_shapes=False)
                for actor in current.actors
            },
        )

    normal_scale = 2 * math.sin(math.radians(tolerances.normal_degrees) / 2)

    def residual(values: np.ndarray) -> np.ndarray:
        return np.concatenate(
            [
                np.concatenate((distance / tolerances.contact_m, normal / normal_scale))
                for distance, normal in vectors_for(candidate(values))
            ]
        )

    if initial.size:
        fit = least_squares(
            residual,
            initial,
            bounds=(lower, upper),
            max_nfev=max_nfev,
            x_scale="jac",
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
        )
        fitted = candidate(fit.x)
        nfev, message = int(fit.nfev), str(fit.message)
    else:
        fitted, nfev, message = scene, 0, "No variables requested"
    errors = []
    for index, (distance, normal) in enumerate(vectors_for(fitted)):
        kind: Literal["object_contact", "body_contact"]
        if index < len(scene.contacts):
            contact = scene.contacts[index]
            kind, local_index = "object_contact", index
            parts = (contact.actor_id, contact.anchor, contact.object_id, contact.face)
        else:
            local_index = index - len(scene.contacts)
            body_contact = scene.body_contacts[local_index]
            kind = "body_contact"
            parts = (
                body_contact.actor_id,
                body_contact.anchor,
                body_contact.target_actor_id,
                body_contact.target_anchor,
            )
        errors.append(
            SceneContactError(
                kind=kind,
                index=local_index,
                parts=parts,
                error_m=float(np.linalg.norm(distance)),
                normal_error_degrees=math.degrees(
                    2 * math.asin(float(np.clip(np.linalg.norm(normal) / 2, 0, 1)))
                ),
            )
        )
    return SceneSolveResult(
        scene=fitted,
        tolerances=tolerances,
        converged=all(
            error.error_m <= tolerances.contact_m
            and error.normal_error_degrees <= tolerances.normal_degrees
            for error in errors
        ),
        errors=tuple(errors),
        report=validate_scene(fitted, tolerances=tolerances),
        message=message,
        nfev=nfev,
    )
