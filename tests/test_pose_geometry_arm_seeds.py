from __future__ import annotations

import numpy as np
import pytest

from t2i_pose_geometry.arm_seeds import arm_seed_candidates
from t2i_pose_geometry.kinematics import forward_kinematics
from t2i_pose_geometry.models import (
    JOINT_LIMITS,
    ActorPose,
    AnchorTarget,
    BodySpec,
    JointAngles,
)


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("scale", [0.94, 1.0, 1.06])
def test_two_bone_seeds_preserve_lengths_and_meet_actual_surface_target(
    side: str, scale: float,
) -> None:
    opposite = "right" if side == "left" else "left"
    actor = ActorPose(
        actor_id="person", body=BodySpec().scaled(scale),
        root_position=(0.2, -0.1, 0.895 * scale),
        root_rotation=(0, 0, 30),
        angles=JointAngles.model_validate({
            f"{opposite}_shoulder_flex": 15,
            f"{opposite}_elbow_flex": 50,
        }),
    )
    before = actor.model_dump_json()
    site = forward_kinematics(actor).anchors[f"{opposite}_forearm"]
    target = AnchorTarget(
        anchor=f"{side}_palm", position=site.position,
        normal=(-site.normal[0], -site.normal[1], -site.normal[2]),
    )
    candidates = arm_seed_candidates(actor, side, target)
    assert candidates
    assert candidates == arm_seed_candidates(actor, side, target)
    assert actor.model_dump_json() == before
    for candidate in candidates:
        assert candidate.body == actor.body
        assert candidate.root_position == actor.root_position
        assert candidate.root_rotation == actor.root_rotation
        skeleton = forward_kinematics(candidate)
        palm = skeleton.anchors[target.anchor]
        np.testing.assert_allclose(palm.position, target.position, atol=1e-7)
        np.testing.assert_allclose(palm.normal, target.normal, atol=1e-7)
        for start, end, length in (
            ("shoulder", "elbow", actor.body.upper_arm_length),
            ("elbow", "wrist", actor.body.forearm_length),
        ):
            delta = np.subtract(
                skeleton.joints[f"{side}_{start}"], skeleton.joints[f"{side}_{end}"]
            )
            assert np.linalg.norm(delta) == pytest.approx(length, abs=1e-9)
        assert all(
            low <= getattr(candidate.angles, name) <= high
            for name, (low, high) in JOINT_LIMITS.items()
        )


def test_seed_limit_is_enforced_and_unreachable_target_yields_no_seed() -> None:
    actor = ActorPose(actor_id="person")
    target = AnchorTarget(
        anchor="left_palm", position=(-0.2, 10.0, 1.0), normal=(0, 0, -1)
    )
    assert arm_seed_candidates(actor, "left", target) == ()
    with pytest.raises(ValueError, match="selected side"):
        arm_seed_candidates(actor, "right", target)
    with pytest.raises(ValueError, match="max_candidates"):
        arm_seed_candidates(actor, "left", target, max_candidates=0)
