from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .catalog import (
    CASTS,
    TOPOLOGY_AUDIT_VERSION,
    PoseCatalog,
    pose_activity_issues,
)
from .compiler import (
    CATALOGS,
    PROMPT_AUDIT_VERSION,
    SceneSpec,
    compile_geometry,
    load_catalog,
    prompt_issues,
)
from .layers import CharacterProfile
from .safety import SAFETY_POLICY_VERSION, SUPPORTED_CASTS
from .service import ASSIGNMENT_ALGORITHM_VERSION, SceneRequest, build_scene_requests

AUDIT_SCHEMA_VERSION = "1.2"
ProgressCallback = Callable[[str], None]


class AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuditParameters(AuditModel):
    cast_keys: list[str]
    start_seed: int
    seed_count: int = Field(ge=1)
    scene_count: int = Field(ge=1, le=20)
    assignment_algorithm_version: int
    safety_policy_version: int
    topology_audit_version: int
    prompt_audit_version: int


class CastAuditProgress(AuditModel):
    catalog_hash: str
    retained_combinations: int = 0
    enabled_entries: int = 0
    completed_seeds: int = Field(default=0, ge=0)
    compiled_prompts: int = Field(default=0, ge=0)
    minimum_distinct_activities: int | None = None
    complete: bool = False


class SpatialAuditProgress(AuditModel):
    schema_version: Literal["1.2"] = AUDIT_SCHEMA_VERSION
    fingerprint: str
    parameters: AuditParameters
    casts: dict[str, CastAuditProgress]
    last_error: str | None = None
    complete: bool = False


def _catalog_hash(cast_key: str) -> str:
    return hashlib.sha256(
        (CATALOGS / f"{cast_key}.json").read_bytes()
    ).hexdigest()


def _audit_fingerprint(
    parameters: AuditParameters,
    catalog_hashes: dict[str, str],
) -> str:
    payload = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "parameters": parameters.model_dump(mode="json"),
        "catalog_hashes": catalog_hashes,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_progress(path: Path, progress: SpatialAuditProgress) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(progress.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _load_or_create_progress(
    path: Path,
    parameters: AuditParameters,
    catalog_hashes: dict[str, str],
    *,
    restart: bool,
) -> SpatialAuditProgress:
    fingerprint = _audit_fingerprint(parameters, catalog_hashes)
    if path.exists() and not restart:
        progress = SpatialAuditProgress.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if progress.fingerprint != fingerprint:
            raise ValueError(
                f"audit checkpoint does not match current catalogs or options: "
                f"{path}; use --restart to replace it"
            )
        return progress
    progress = SpatialAuditProgress(
        fingerprint=fingerprint,
        parameters=parameters,
        casts={
            cast_key: CastAuditProgress(catalog_hash=catalog_hashes[cast_key])
            for cast_key in parameters.cast_keys
        },
    )
    _write_progress(path, progress)
    return progress


def _audit_catalog(catalog: PoseCatalog) -> tuple[int, int]:
    activities = {
        activity.activity_id: activity for activity in catalog.activities
    }
    retained_combinations = 0
    enabled_entries = 0
    for entry in catalog.entries:
        if entry.compatible_activity_ids:
            enabled_entries += 1
        for activity_id in entry.compatible_activity_ids:
            issues = pose_activity_issues(
                activities[activity_id],
                entry.central_pose,
                catalog.cast_roles,
            )
            if issues:
                raise ValueError(
                    f"{catalog.cast_key}:{entry.pose_id}:{activity_id}: {issues}"
                )
            retained_combinations += 1
    return retained_combinations, enabled_entries


def _audit_character_profiles(catalog: PoseCatalog) -> list[CharacterProfile]:
    profiles = []
    for index, role in enumerate(catalog.cast_roles):
        female = role.startswith("f")
        profiles.append(
            CharacterProfile(
                role=role,
                adult_age=30 + index,
                nationality="Chinese",
                height_cm=165 + index * 4,
                weight_kg=55 + index * 6,
                body_build=f"audit build {index + 1}",
                body_proportions=f"audit proportions {index + 1}",
                skin_tone=f"audit skin tone {index + 1}",
                face_features=f"audit facial features {index + 1}",
                hair_style=f"audit hairstyle {index + 1}",
                hair_color=f"audit hair color {index + 1}",
                intimate_anatomy=(
                    f"audit vulva anatomy {index + 1}"
                    if female
                    else f"audit penis anatomy {index + 1}"
                ),
                pubic_hair=f"audit grooming {index + 1}",
            )
        )
    return profiles


def _audit_requests(
    requests: tuple[SceneRequest, ...],
    catalog: PoseCatalog,
    scene_count: int,
    character_profiles: list[CharacterProfile],
) -> int:
    if len(requests) != scene_count:
        raise ValueError(
            f"{catalog.cast_key} returned {len(requests)} of {scene_count} scenes"
        )
    if len({request.scene_id for request in requests}) != scene_count:
        raise ValueError(f"{catalog.cast_key} returned duplicate scene IDs")
    pose_keys = {
        (request.family, request.variant) for request in requests
    }
    if len(pose_keys) != scene_count:
        raise ValueError(f"{catalog.cast_key} returned duplicate poses")

    entries = {
        (entry.central_pose.family, entry.central_pose.variant): entry
        for entry in catalog.entries
    }
    activities = {
        activity.activity_id: activity for activity in catalog.activities
    }
    for request in requests:
        entry = entries[(request.family, request.variant)]
        if request.activity_id not in entry.compatible_activity_ids:
            raise ValueError(
                f"{catalog.cast_key}:{request.scene_id} selected an incompatible "
                "pose and activity"
            )
        issues = pose_activity_issues(
            activities[request.activity_id],
            entry.central_pose,
            catalog.cast_roles,
        )
        if issues:
            raise ValueError(
                f"{catalog.cast_key}:{request.scene_id} has topology issues: {issues}"
            )
        if request.viewpoint not in entry.central_pose.compatible_camera_views:
            raise ValueError(
                f"{catalog.cast_key}:{request.scene_id} selected an incompatible "
                "camera"
            )
        spec = SceneSpec(
            scene_id=request.scene_id,
            cast_key=request.cast_key,
            family=request.family,
            variant=request.variant,
            activity_id=request.activity_id,
            viewpoint=request.viewpoint,
            shot_scale=request.shot_scale,
            setting_id="audit_setting",
        )
        prompt = compile_geometry(
            spec,
            entry,
            activities[request.activity_id],
            character_profiles,
        )
        issues = prompt_issues(
            spec,
            entry,
            activities[request.activity_id],
            prompt,
            character_profiles,
        )
        if issues:
            raise ValueError(
                f"{catalog.cast_key}:{request.scene_id} compiled prompt issues: "
                f"{issues}"
            )
    return len({request.activity_id for request in requests})


def run_spatial_audit(
    progress_path: Path,
    *,
    start_seed: int = 0,
    seed_count: int = 100,
    scene_count: int = 20,
    cast_keys: Sequence[str] = tuple(sorted(SUPPORTED_CASTS)),
    restart: bool = False,
    on_progress: ProgressCallback | None = None,
) -> SpatialAuditProgress:
    selected_casts = list(cast_keys)
    if not selected_casts or len(selected_casts) != len(set(selected_casts)):
        raise ValueError("audit cast list must contain unique cast keys")
    unknown_casts = set(selected_casts).difference(CASTS)
    if unknown_casts:
        raise ValueError(f"unknown audit cast configurations: {sorted(unknown_casts)}")
    parameters = AuditParameters(
        cast_keys=selected_casts,
        start_seed=start_seed,
        seed_count=seed_count,
        scene_count=scene_count,
        assignment_algorithm_version=ASSIGNMENT_ALGORITHM_VERSION,
        safety_policy_version=SAFETY_POLICY_VERSION,
        topology_audit_version=TOPOLOGY_AUDIT_VERSION,
        prompt_audit_version=PROMPT_AUDIT_VERSION,
    )
    catalog_hashes = {
        cast_key: _catalog_hash(cast_key) for cast_key in selected_casts
    }
    progress = _load_or_create_progress(
        progress_path,
        parameters,
        catalog_hashes,
        restart=restart,
    )
    if progress.complete:
        if on_progress is not None:
            on_progress(f"audit already complete: {progress_path}")
        return progress

    for cast_key in selected_casts:
        cast_progress = progress.casts[cast_key]
        if cast_progress.complete:
            continue
        try:
            catalog = load_catalog(cast_key)
            character_profiles = _audit_character_profiles(catalog)
            if cast_progress.retained_combinations == 0:
                (
                    cast_progress.retained_combinations,
                    cast_progress.enabled_entries,
                ) = _audit_catalog(catalog)
                _write_progress(progress_path, progress)
            for offset in range(cast_progress.completed_seeds, seed_count):
                seed = start_seed + offset
                requests = build_scene_requests(
                    cast_key,
                    seed=seed,
                    count=scene_count,
                )
                distinct_activities = _audit_requests(
                    requests,
                    catalog,
                    scene_count,
                    character_profiles,
                )
                current_minimum = cast_progress.minimum_distinct_activities
                cast_progress.minimum_distinct_activities = (
                    distinct_activities
                    if current_minimum is None
                    else min(current_minimum, distinct_activities)
                )
                cast_progress.completed_seeds = offset + 1
                cast_progress.compiled_prompts += len(requests)
                progress.last_error = None
                _write_progress(progress_path, progress)
                if on_progress is not None and (
                    offset == 0
                    or (offset + 1) % 10 == 0
                    or offset + 1 == seed_count
                ):
                    on_progress(
                        f"{cast_key}: {offset + 1}/{seed_count} seeds audited"
                    )
            cast_progress.complete = True
            _write_progress(progress_path, progress)
        except Exception as exc:
            progress.last_error = (
                f"{cast_key} seed "
                f"{start_seed + cast_progress.completed_seeds}: {exc}"
            )
            _write_progress(progress_path, progress)
            raise

    progress.complete = all(
        cast_progress.complete for cast_progress in progress.casts.values()
    )
    _write_progress(progress_path, progress)
    return progress
