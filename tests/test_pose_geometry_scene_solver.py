from __future__ import annotations

import math

import pytest

from t2i_pose_geometry import (
    ActorPose,
    BodyContact,
    BodySpec,
    Box,
    Contact,
    JointAngles,
    Scene,
    SceneSolveResult,
    Tolerances,
    forward_kinematics,
    solve_scene,
    validate_scene,
)


def contact_chain(
    count: int = 3, *, scale: float = 1.0, perturbed: bool = True
) -> Scene:
    actors = tuple(
        ActorPose(
            actor_id=f"adult_{index}",
            body=BodySpec().scaled(scale),
            root_position=(
                index * (0.60 if perturbed else 0.53) * scale,
                0.04 * (-1) ** index if perturbed and index else 0,
                0.895 * scale + (0.02 + index * 0.01 if perturbed else 0),
            ),
            angles=JointAngles(
                torso_yaw=5 * (-1) ** index if perturbed and index else 0
            ),
        )
        for index in range(count)
    )
    return Scene(
        actors=actors,
        objects=(Box(object_id="floor", center=(0, 0, -0.1), size=(4, 4, 0.2)),),
        contacts=tuple(
            Contact(actor_id=actor.actor_id, anchor=f"{side}_sole", object_id="floor")
            for actor in actors
            for side in ("left", "right")
        ),
        body_contacts=tuple(
            BodyContact(
                actor_id=actors[index].actor_id,
                anchor="right_side",
                target_actor_id=actors[index + 1].actor_id,
                target_anchor="left_side",
            )
            for index in range(count - 1)
        ),
    )


def variables(scene: Scene) -> dict[str, tuple[str, ...]]:
    return {
        actor.actor_id: (("root_z",) if index == 0 else ("root_position", "torso_yaw"))
        for index, actor in enumerate(scene.actors)
    }


@pytest.mark.parametrize("count", (2, 3))
@pytest.mark.parametrize("scale", (0.8, 1.0, 1.2))
def test_scene_contacts_converge_together_without_resizing_bodies(
    count: int, scale: float
) -> None:
    scene = contact_chain(count, scale=scale)
    original = scene.model_dump_json()
    result = solve_scene(scene, variables(scene))

    assert result.accepted, result.report
    assert result.converged
    assert result.nfev > 1
    assert len(result.errors) == count * 2 + count - 1
    assert max(error.error_m for error in result.errors) < 1e-6
    assert max(error.normal_error_degrees for error in result.errors) < 1e-5
    assert result.report == validate_scene(result.scene, tolerances=result.tolerances)
    assert scene.model_dump_json() == original
    assert result.scene.objects == scene.objects
    assert result.scene.contacts == scene.contacts
    assert result.scene.body_contacts == scene.body_contacts
    for initial, fitted in zip(scene.actors, result.scene.actors, strict=True):
        assert initial.body == fitted.body
        assert abs(fitted.angles.torso_yaw) < 1e-5
    skeletons = {
        actor.actor_id: forward_kinematics(actor) for actor in result.scene.actors
    }
    for contact in result.scene.body_contacts:
        first = skeletons[contact.actor_id].anchors[contact.anchor]
        second = skeletons[contact.target_actor_id].anchors[contact.target_anchor]
        assert math.dist(first.position, second.position) < 1e-6
    assert SceneSolveResult.model_validate_json(result.model_dump_json()) == result


def test_back_to_back_contact_and_floor_constraints_are_solved_together() -> None:
    scene = contact_chain(2)
    scene = scene.model_copy(
        update={
            "actors": (
                ActorPose(actor_id="adult_0", root_position=(0, 0, 0.92)),
                ActorPose(
                    actor_id="adult_1",
                    root_position=(0.04, -0.28, 0.94),
                    root_rotation=(0, 0, 180),
                ),
            ),
            "body_contacts": (
                BodyContact(
                    actor_id="adult_0",
                    anchor="back",
                    target_actor_id="adult_1",
                    target_anchor="back",
                ),
            ),
        }
    )
    result = solve_scene(scene, {"adult_0": ("root_z",), "adult_1": ("root_position",)})

    assert result.accepted, result.report
    assert result.scene.actors[1].root_position == pytest.approx((0, -0.21, 0.895))
    assert max(error.error_m for error in result.errors) < 1e-6


def test_pairwise_reachable_contacts_do_not_certify_an_inconsistent_group() -> None:
    scene = contact_chain(3, perturbed=False)
    assert validate_scene(scene).passed
    closing_edge = BodyContact(
        actor_id="adult_0",
        anchor="right_side",
        target_actor_id="adult_2",
        target_anchor="left_side",
    )
    scene = scene.model_copy(
        update={"body_contacts": (*scene.body_contacts, closing_edge)}
    )
    result = solve_scene(scene, variables(scene))

    assert not result.converged
    assert not result.accepted
    assert not result.report.passed
    assert any(
        error.error_m > result.tolerances.contact_m
        or error.normal_error_degrees > result.tolerances.normal_degrees
        for error in result.errors
    )


def test_contact_convergence_cannot_exempt_solid_intersection() -> None:
    scene = contact_chain(2, perturbed=False)
    scene = scene.model_copy(
        update={
            "actors": (
                scene.actors[0],
                scene.actors[1].model_copy(update={"root_position": (0.529, 0, 0.895)}),
            )
        }
    )
    result = solve_scene(scene, {"adult_0": (), "adult_1": ()})

    assert result.converged
    assert result.nfev == 0
    assert not result.accepted
    assert any(issue.code == "inter_actor_collision" for issue in result.report.issues)


def test_uninvolved_third_actor_still_participates_in_collision_checks() -> None:
    scene = contact_chain(2, perturbed=False)
    third = scene.actors[0].model_copy(update={"actor_id": "third"})
    scene = scene.model_copy(update={"actors": (*scene.actors, third)})
    result = solve_scene(scene, {actor.actor_id: () for actor in scene.actors})

    assert result.converged
    assert not result.accepted
    assert any(
        issue.code == "inter_actor_collision" and "third" in issue.parts
        for issue in result.report.issues
    )


def test_furniture_contacts_use_bounded_faces_not_infinite_planes() -> None:
    scene = contact_chain(1, perturbed=False)
    scene = scene.model_copy(
        update={
            "objects": (
                Box(object_id="floor", center=(0, 0, -0.1), size=(0.1, 0.1, 0.2)),
            )
        }
    )
    result = solve_scene(scene, {"adult_0": ("root_position",)})

    assert not result.converged
    assert not result.accepted
    assert any(issue.code == "contact_distance" for issue in result.report.issues)


def test_root_bounds_and_exhausted_search_remain_unverified() -> None:
    scene = contact_chain(2)
    bounded = solve_scene(scene, variables(scene), root_translation_bound_m=0.005)
    exhausted = solve_scene(scene, variables(scene), max_nfev=1)

    for result in (bounded, exhausted):
        assert not result.converged
        assert not result.accepted
    for initial, fitted in zip(scene.actors, bounded.scene.actors, strict=True):
        for before, after in zip(
            initial.root_position, fitted.root_position, strict=True
        ):
            assert abs(after - before) <= 0.005 + 1e-10


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"actor_id": "missing"}, "Unknown contact actor"),
        ({"anchor": "unmodeled_surface"}, "Unknown contact anchor"),
        ({"target_actor_id": "missing"}, "Unknown contact actor"),
        ({"target_anchor": "unmodeled_surface"}, "Unknown contact anchor"),
    ],
)
def test_missing_body_contact_geometry_fails_without_substitution(
    changes: dict[str, str], message: str
) -> None:
    scene = contact_chain(2)
    scene = scene.model_copy(
        update={"body_contacts": (scene.body_contacts[0].model_copy(update=changes),)}
    )
    with pytest.raises(ValueError, match=message):
        solve_scene(scene, variables(scene))


def test_missing_furniture_and_duplicate_ids_fail_before_solving() -> None:
    scene = contact_chain(2)
    with pytest.raises(ValueError, match="Unknown contact object"):
        solve_scene(scene.model_copy(update={"objects": ()}), variables(scene))
    with pytest.raises(ValueError, match="IDs must be unique"):
        solve_scene(
            scene.model_copy(update={"actors": (*scene.actors, scene.actors[0])}),
            variables(scene),
        )
    with pytest.raises(ValueError, match="IDs must be unique"):
        solve_scene(
            scene.model_copy(update={"objects": (*scene.objects, scene.objects[0])}),
            variables(scene),
        )


def test_every_actor_requires_explicit_variables_or_a_fixed_declaration() -> None:
    scene = contact_chain(2)
    with pytest.raises(ValueError, match="explicitly name every scene actor"):
        solve_scene(scene, {"adult_0": ("root_position",)})
    with pytest.raises(ValueError, match="explicitly name every scene actor"):
        solve_scene(scene, {**variables(scene), "invented_actor": ()})
    with pytest.raises(ValueError, match="Unknown IK variables"):
        solve_scene(scene, {"adult_0": ("invented_joint",), "adult_1": ()})
    with pytest.raises(ValueError, match="Duplicate IK variable"):
        solve_scene(scene, {"adult_0": ("root_position", "root_x"), "adult_1": ()})


def test_unconstrained_movable_actor_is_not_silently_accepted() -> None:
    scene = contact_chain(2)
    third = ActorPose(actor_id="third", root_position=(2, 0, 0.895))
    scene = scene.model_copy(update={"actors": (*scene.actors, third)})
    with pytest.raises(ValueError, match="Movable actor has no contact"):
        solve_scene(scene, variables(scene))
    with pytest.raises(ValueError, match="At least one scene contact"):
        solve_scene(Scene(actors=scene.actors), variables(scene))
    with pytest.raises(ValueError, match="At least one actor"):
        solve_scene(Scene(actors=()), {})


@pytest.mark.parametrize("budget", (0, 2001, True, 1.5))
def test_invalid_scene_solver_budget_is_rejected(budget: int) -> None:
    scene = contact_chain(2)
    with pytest.raises(ValueError, match="max_nfev"):
        solve_scene(scene, variables(scene), max_nfev=budget)


@pytest.mark.parametrize("bound", (0, 11, math.inf, math.nan))
def test_invalid_scene_translation_bound_is_rejected(bound: float) -> None:
    scene = contact_chain(2)
    with pytest.raises(ValueError, match="root_translation_bound_m"):
        solve_scene(scene, variables(scene), root_translation_bound_m=bound)


def test_scene_validation_uses_the_requested_numerical_tolerances() -> None:
    scene = contact_chain(2, perturbed=False)
    tolerances = Tolerances(contact_m=0.001, normal_degrees=2)
    result = solve_scene(scene, {"adult_0": (), "adult_1": ()}, tolerances=tolerances)

    assert result.accepted
    assert result.tolerances == tolerances
    assert result.report == validate_scene(result.scene, tolerances=tolerances)


def test_rotated_furniture_uses_world_normals_during_scene_fitting() -> None:
    scene = contact_chain(1, perturbed=False)
    floor = scene.objects[0].model_copy(update={"rotation": (0, 7, 0)})
    scene = scene.model_copy(update={"objects": (floor,)})
    result = solve_scene(scene, {"adult_0": ("root_position", "root_rotation")})

    assert result.accepted, result.report
    assert max(error.error_m for error in result.errors) < 1e-6
    assert max(error.normal_error_degrees for error in result.errors) < 1e-5
    assert result.scene.objects == (floor,)
