"""Independent static humanoid geometry; no pipeline, provider, or network imports.

The model uses synthetic dimensions and bounded geometric joint ranges. Passing
validation proves only the stated static solid/contact constraints, not balance,
dynamics, anatomical fidelity, comfort, or biological safety. IK is a candidate
generator; always independently call ``validate_scene`` before accepting a pose.
"""

from .kinematics import Skeleton, forward_kinematics
from .models import (
    JOINT_LIMITS,
    ActorPose,
    Anchor,
    AnchorTarget,
    BodyContact,
    BodySpec,
    Box,
    Contact,
    Issue,
    JointAngles,
    JointRegion,
    Scene,
    Shape,
    SolveResult,
    TargetError,
    Tolerances,
    ValidationReport,
)
from .solver import ROOT_VARIABLES, VARIABLE_GROUPS, expand_variable_names, solve_actor
from .validation import face_frame, validate_scene

__all__ = [
    "JOINT_LIMITS",
    "ROOT_VARIABLES",
    "VARIABLE_GROUPS",
    "ActorPose",
    "Anchor",
    "AnchorTarget",
    "BodyContact",
    "BodySpec",
    "Box",
    "Contact",
    "Issue",
    "JointAngles",
    "JointRegion",
    "Scene",
    "Shape",
    "Skeleton",
    "SolveResult",
    "TargetError",
    "Tolerances",
    "ValidationReport",
    "expand_variable_names",
    "face_frame",
    "forward_kinematics",
    "solve_actor",
    "validate_scene",
]
