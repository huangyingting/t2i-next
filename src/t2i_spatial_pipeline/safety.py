from __future__ import annotations

from typing import Final

from .catalog import CASTS, POSE_FAMILIES, activity_ids

SAFETY_POLICY_VERSION: Final = 2
VALIDATION_STATUS: Final = "symbolic_only"
PRODUCTION_POLICY: Final = "full_catalog_symbolic_only"

SUPPORTED_CASTS: Final = frozenset(CASTS)
SUPPORTED_POSE_FAMILIES: Final = frozenset(POSE_FAMILIES)
SUPPORTED_ACTIVITIES_BY_CAST: Final = {
    cast_key: frozenset(activity_ids(cast_key)) for cast_key in CASTS
}


def catalog_support_issues(
    cast_key: str,
    pose_family: str,
    activity_id: str,
) -> list[str]:
    if cast_key not in SUPPORTED_CASTS:
        return ["cast is not present in the spatial catalog"]
    issues = []
    if pose_family not in SUPPORTED_POSE_FAMILIES:
        issues.append("pose family is not present in the spatial catalog")
    if activity_id not in SUPPORTED_ACTIVITIES_BY_CAST[cast_key]:
        issues.append("activity is not present in the cast catalog")
    return issues


def symbolic_validation_metadata() -> dict[str, str | bool | int]:
    return {
        "validation_status": VALIDATION_STATUS,
        "visual_validation": False,
        "requires_render_review": True,
        "production_policy": PRODUCTION_POLICY,
        "safety_policy_version": SAFETY_POLICY_VERSION,
    }
