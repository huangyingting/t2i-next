from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import t2i_spatial_pipeline.service as spatial_service
from t2i_spatial_pipeline.audit import _audit_character_profiles
from t2i_spatial_pipeline.catalog import (
    CASTS,
    TOPOLOGY_AUDIT_VERSION,
    ActivityTemplate,
    CentralPose,
    ContactEdge,
    ContactEndpoint,
    HandheldProp,
    PoseCatalog,
    PoseEntry,
    pose_activity_issues,
    resolve_central_hand_tasks,
)
from t2i_spatial_pipeline.compiler import (
    PROMPT_AUDIT_VERSION,
    SceneSpec,
    actor_name,
    compile_geometry,
    load_catalog,
    partner_body_chain_clause,
    partner_relationship,
    prompt_issues,
    resolved_central_arm_description,
    resolved_partner_supports,
    support_clause,
)

MULTI_ACTOR_CASTS = tuple(key for key, roles in CASTS.items() if len(roles) > 1)


@pytest.fixture(scope="module", params=MULTI_ACTOR_CASTS)
def catalog(request: pytest.FixtureRequest) -> PoseCatalog:
    return load_catalog(request.param)


def _spec(catalog: PoseCatalog, entry: PoseEntry, activity_id: str) -> SceneSpec:
    return SceneSpec(
        scene_id="contact_audit",
        cast_key=catalog.cast_key,
        family=entry.central_pose.family,
        variant=entry.central_pose.variant,
        activity_id=activity_id,
        viewpoint=entry.central_pose.compatible_camera_views[0],
        shot_scale="full_body",
        setting_id="audit_setting",
    )


def _tool_activity(controller: str) -> ActivityTemplate:
    return ActivityTemplate(
        activity_id="neutral_contact",
        focus_role="f1",
        contact_edges=[
            ContactEdge(
                edge_id="primary",
                source=ContactEndpoint(entity_id="prop_a", region="contact_surface"),
                target=ContactEndpoint(entity_id="f1", region="shoulder"),
                state="external_contact",
                preferred_visibility="visible",
            )
        ],
        handheld_props=[
            HandheldProp(
                prop_id="prop_a",
                controller_role=controller,
                category="surface_tool",
                grip_region="right_hand",
                deployment="external_surface_contact",
                orientation="aligned_to_target_surface",
            )
        ],
    )


def test_partner_posture_matches_declared_supports(catalog: PoseCatalog) -> None:
    activities = {activity.activity_id: activity for activity in catalog.activities}
    for entry in catalog.entries:
        for activity_id in entry.compatible_activity_ids:
            activity = activities[activity_id]
            central = actor_name(activity.focus_role, catalog.cast_key)
            for plan in entry.actor_plans[1:]:
                relationship = partner_relationship(
                    plan, activity, central, entry.central_pose
                )
                supports = resolved_partner_supports(plan, activity, entry.central_pose)
                assert not (
                    relationship.startswith("kneels") and supports == ["both_feet"]
                ), (entry.pose_id, activity_id, plan.role)


def test_partner_body_chain_preserves_the_stated_stance(catalog: PoseCatalog) -> None:
    activities = {activity.activity_id: activity for activity in catalog.activities}
    for entry in catalog.entries:
        for activity_id in entry.compatible_activity_ids:
            activity = activities[activity_id]
            central = actor_name(activity.focus_role, catalog.cast_key)
            for plan in entry.actor_plans[1:]:
                relationship = partner_relationship(
                    plan, activity, central, entry.central_pose
                )
                chain = partner_body_chain_clause(
                    plan, activity, central, catalog.cast_key
                )
                assert not (
                    "all fours" in relationship and "vertically connected" in chain
                ), (entry.pose_id, activity_id, plan.role)


def test_bilateral_lift_does_not_allocate_a_handheld_task(
    catalog: PoseCatalog,
) -> None:
    activities = {activity.activity_id: activity for activity in catalog.activities}
    for entry in catalog.entries:
        if entry.central_pose.primary_surface != "partner_support":
            continue
        occupied_roles = set(catalog.cast_roles[:2])
        for activity_id in entry.compatible_activity_ids:
            activity = activities[activity_id]
            assert not any(
                prop.controller_role in occupied_roles
                for prop in activity.handheld_props
            ), (entry.pose_id, activity_id)


@pytest.mark.parametrize(
    ("controller", "conflicts"), [("f1", True), ("m1", True), ("m2", False)]
)
def test_lift_tool_conflict_is_local_to_the_occupied_roles(
    controller: str, conflicts: bool
) -> None:
    catalog = load_catalog("one_woman_two_men")
    pose = next(
        entry.central_pose
        for entry in catalog.entries
        if entry.central_pose.family == "lifted_supported"
        and entry.central_pose.variant == "legs_wrapped_arms_shoulders"
    )
    issues = pose_activity_issues(_tool_activity(controller), pose, catalog.cast_roles)

    assert ("lift support conflicts with handheld prop control" in issues) == conflicts
    if not conflicts:
        assert issues == []


def test_prompt_audit_rejects_kneeling_with_standing_support(
    catalog: PoseCatalog,
) -> None:
    activities = {activity.activity_id: activity for activity in catalog.activities}
    entry, activity, prop = next(
        (entry, activities[activity_id], prop)
        for entry in catalog.entries
        if entry.central_pose.family == "standing_upright"
        for activity_id in entry.compatible_activity_ids
        for prop in activities[activity_id].handheld_props
        if prop.controller_role != activities[activity_id].focus_role
    )
    profiles = _audit_character_profiles(catalog)
    spec = _spec(catalog, entry, activity.activity_id)
    prompt = compile_geometry(spec, entry, activity, profiles)
    name = actor_name(prop.controller_role, catalog.cast_key)
    standing = f"{name} stands beside"
    assert standing in prompt
    assert prompt_issues(spec, entry, activity, prompt, profiles) == []

    changed = prompt.replace(standing, f"{name} kneels beside", 1)
    assert f"{name} has a kneeling stance with standing-only supports" in (
        prompt_issues(spec, entry, activity, changed, profiles)
    )


def test_prompt_audit_rechecks_contact_task_compatibility() -> None:
    catalog = load_catalog("one_woman_two_men")
    entry = next(
        entry
        for entry in catalog.entries
        if entry.central_pose.family == "lifted_supported"
        and entry.central_pose.variant == "legs_wrapped_arms_shoulders"
    )
    activity = _tool_activity("m1")
    profiles = _audit_character_profiles(catalog)
    spec = _spec(catalog, entry, activity.activity_id)
    prompt = compile_geometry(spec, entry, activity, profiles)

    assert "lift support conflicts with handheld prop control" in prompt_issues(
        spec, entry, activity, prompt, profiles
    )


@pytest.mark.parametrize("cast_key", tuple(CASTS))
def test_vertically_raised_leg_is_excluded_from_planted_support(cast_key: str) -> None:
    catalog = load_catalog(cast_key)
    entries = [
        entry
        for entry in catalog.entries
        if entry.central_pose.leg_configuration == "one_leg_vertical"
    ]
    assert entries
    for entry in entries:
        assert "both_feet" not in entry.central_pose.support_points
        assert "planted_foot" in entry.central_pose.support_points
        assert entry.actor_plans[0].support_points == entry.central_pose.support_points


def test_raised_foot_cannot_be_reintroduced_as_a_planted_support() -> None:
    pose = next(
        entry.central_pose
        for entry in load_catalog("two_women").entries
        if entry.central_pose.leg_configuration == "one_leg_vertical"
    )
    with pytest.raises(ValidationError, match="vertically raised leg"):
        CentralPose.model_validate(
            pose.model_dump()
            | {"support_points": ["shoulders", "upper_back", "both_feet"]}
        )


def _hand_contact(region: str = "hand") -> ActivityTemplate:
    return ActivityTemplate(
        activity_id="neutral_contact",
        focus_role="f1",
        contact_edges=[
            ContactEdge(
                edge_id="primary",
                source=ContactEndpoint(entity_id="f1", region=region),
                target=ContactEndpoint(entity_id="f2", region="shoulder"),
                state="external_contact",
                preferred_visibility="visible",
            )
        ],
    )


@pytest.mark.parametrize(
    ("family", "arms", "free_hand"),
    [
        ("side_lying_left", "upper_arm_overhead", "left_hand"),
        ("side_lying_right", "upper_arm_overhead", "right_hand"),
        ("side_lying_left", "upper_hand_hip", "left_hand"),
        ("side_lying_right", "upper_hand_hip", "right_hand"),
        ("side_lying_left", "lower_arm_forward", "right_hand"),
        ("side_lying_right", "lower_arm_forward", "left_hand"),
        ("side_lying_open", "upper_arm_overhead", "left_hand"),
    ],
)
def test_side_lying_contact_uses_the_anatomically_unreserved_hand(
    family: str, arms: str, free_hand: str
) -> None:
    pose = next(
        entry.central_pose
        for entry in load_catalog("two_women").entries
        if entry.central_pose.family == family
        and entry.central_pose.arm_configuration == arms
    )
    activity = _hand_contact()
    resolved = resolve_central_hand_tasks(activity, pose)

    assert resolved.issues == ()
    assert resolved.contact_hands == {0: free_hand}
    assert f"the {free_hand.replace('_', ' ')} performs" in (
        resolved_central_arm_description(pose, activity, "two_women")
    )


def test_explicit_hand_and_tool_grip_cannot_override_a_reserved_pose_hand() -> None:
    poses = {
        side: next(
            entry.central_pose
            for entry in load_catalog("two_women").entries
            if entry.central_pose.family == f"side_lying_{side}"
            and entry.central_pose.arm_configuration == "upper_arm_overhead"
        )
        for side in ("left", "right")
    }
    for activity in (_hand_contact("right_hand"), _tool_activity("f1")):
        issues = pose_activity_issues(activity, poses["left"], ["f1", "f2"])
        assert "central contact requires the hand reserved by the pose" in issues
        with pytest.raises(ValueError, match="hand reserved by the pose"):
            resolved_central_arm_description(poses["left"], activity, "two_women")
        assert pose_activity_issues(activity, poses["right"], ["f1", "f2"]) == []


def test_generic_hand_assignment_reserves_later_explicit_hands_first() -> None:
    pose = next(
        entry.central_pose
        for entry in load_catalog("two_women").entries
        if entry.central_pose.family == "supine"
        and entry.central_pose.arm_configuration == "arms_beside"
    )
    generic = _hand_contact().contact_edges[0]
    explicit = ContactEdge(
        edge_id="secondary",
        source=ContactEndpoint(entity_id="f1", region="right_hand"),
        target=ContactEndpoint(entity_id="f2", region="forearm"),
        state="external_contact",
        preferred_visibility="visible",
    )
    activity = ActivityTemplate(
        activity_id="neutral_contact",
        focus_role="f1",
        contact_edges=[generic, explicit],
    )
    resolved = resolve_central_hand_tasks(activity, pose)

    assert resolved.issues == ()
    assert resolved.contact_hands == {0: "left_hand", 1: "right_hand"}


@pytest.mark.parametrize("cast_key", ("one_woman_one_man", "two_women"))
def test_prompt_audit_rejects_swapping_contact_back_to_an_overhead_hand(
    cast_key: str,
) -> None:
    catalog = load_catalog(cast_key)
    activities = {activity.activity_id: activity for activity in catalog.activities}
    entry, activity = next(
        (entry, activities[activity_id])
        for entry in catalog.entries
        if entry.central_pose.family == "side_lying_left"
        and entry.central_pose.arm_configuration == "upper_arm_overhead"
        for activity_id in entry.compatible_activity_ids
        if any(
            edge.source.entity_id == "f1" and edge.source.region == "hand"
            for edge in activities[activity_id].contact_edges
        )
    )
    profiles = _audit_character_profiles(catalog)
    spec = _spec(catalog, entry, activity.activity_id)
    prompt = compile_geometry(spec, entry, activity, profiles)
    assert prompt_issues(spec, entry, activity, prompt, profiles) == []
    changed = prompt.replace(
        "the left hand performs the assigned contact",
        "the right hand performs the assigned contact",
        1,
    )
    assert changed != prompt
    assert "central contact-hand allocation changed" in prompt_issues(
        spec, entry, activity, changed, profiles
    )


def test_prompt_audit_rejects_restoring_two_feet_support_for_a_raised_leg(
    catalog: PoseCatalog,
) -> None:
    entry = next(
        entry
        for entry in catalog.entries
        if entry.central_pose.leg_configuration == "one_leg_vertical"
        and entry.compatible_activity_ids
    )
    activity = next(
        activity
        for activity in catalog.activities
        if activity.activity_id == entry.compatible_activity_ids[0]
    )
    profiles = _audit_character_profiles(catalog)
    spec = _spec(catalog, entry, activity.activity_id)
    prompt = compile_geometry(spec, entry, activity, profiles)
    assert prompt_issues(spec, entry, activity, prompt, profiles) == []
    expected = support_clause(entry)
    changed = prompt.replace(expected, expected.replace("planted foot", "both feet"), 1)

    assert changed != prompt
    assert "central support allocation changed" in prompt_issues(
        spec, entry, activity, changed, profiles
    )


@pytest.mark.parametrize(
    "stale_field",
    (
        "schema_version",
        "topology_audit_version",
        "prompt_audit_version",
        "missing_rules",
    ),
)
async def test_bulk_rejects_stale_contact_audit_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stale_field: str
) -> None:
    identity: dict[str, object] = {
        "schema_version": spatial_service.BULK_SCHEMA_VERSION,
        "topology_audit_version": TOPOLOGY_AUDIT_VERSION,
        "prompt_audit_version": PROMPT_AUDIT_VERSION,
        "brief": "Neutral adult figure study",
        "base_seed": 42,
        "count_per_cast": 1,
        "batch_size": spatial_service.BULK_BATCH_SIZE,
        "cast_keys": ["one_woman_one_man"],
        "completed_batches": [],
        "categories": {},
        "complete": False,
    }
    if stale_field == "missing_rules":
        del identity["topology_audit_version"]
        del identity["prompt_audit_version"]
    else:
        identity[stale_field] = 0
    checkpoint = tmp_path / "bulk-report.json"
    original = json.dumps(identity)
    checkpoint.write_text(original, encoding="utf-8")

    async def reject_generation(*args, **kwargs):
        raise AssertionError("stale checkpoints must fail before generation")

    monkeypatch.setattr(spatial_service, "generate_spatial_batch", reject_generation)
    with pytest.raises(ValueError, match="use a new runs directory"):
        await spatial_service.generate_spatial_bulk(
            "Neutral adult figure study",
            42,
            count_per_cast=1,
            refresh_blueprints=False,
            runs_directory=tmp_path,
            prompts_directory=tmp_path / "prompts",
            cast_keys=("one_woman_one_man",),
        )
    assert checkpoint.read_text(encoding="utf-8") == original


async def test_bulk_resumes_with_current_contact_audit_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def generate_neutral_batch(
        brief: str, seed: int, *, runs_directory: Path, **kwargs
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        runs_directory.mkdir(parents=True, exist_ok=True)
        (runs_directory / "prompts.txt").write_text(
            "Two clothed adults stand side by side.\n", encoding="utf-8"
        )
        report = {"passed": True, "spatial_seed": seed}
        (runs_directory / "report.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        return report

    monkeypatch.setattr(
        spatial_service, "generate_spatial_batch", generate_neutral_batch
    )
    runs = tmp_path / "runs"
    for _ in range(2):
        report = await spatial_service.generate_spatial_bulk(
            "Neutral adult figure study",
            42,
            count_per_cast=1,
            refresh_blueprints=False,
            runs_directory=runs,
            prompts_directory=tmp_path / "prompts",
            cast_keys=("one_woman_one_man",),
        )
        assert report["complete"] is True
        assert report["total_records"] == 1
        assert report["topology_audit_version"] == TOPOLOGY_AUDIT_VERSION
        assert report["prompt_audit_version"] == PROMPT_AUDIT_VERSION
    assert calls == 1
