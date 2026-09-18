from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import t2i_spatial_pipeline.audit as spatial_audit
from t2i_spatial_pipeline.catalog import CASTS, PoseCatalog, PoseEntry, build_catalog
from t2i_spatial_pipeline.cli import app
from t2i_spatial_pipeline.compiler import load_catalog
from t2i_spatial_pipeline.diagnostics import (
    StructuralDiagnostics,
    accumulate_structural_diagnostics,
)
from t2i_spatial_pipeline.service import SceneRequest, build_scene_requests


def _request(entry: PoseEntry, scene_id: str) -> SceneRequest:
    return SceneRequest(
        scene_id=scene_id,
        family=entry.central_pose.family,
        variant=entry.central_pose.variant,
        activity_id=entry.compatible_activity_ids[0],
        viewpoint=entry.central_pose.compatible_camera_views[0],
        shot_scale="full_body",
        cast_key="one_woman",
    )


def _changed_definition(cast_key: str) -> PoseCatalog:
    catalog = build_catalog(cast_key)
    catalog.entries[0].pose_id = "changed_definition_entry"
    return PoseCatalog.model_validate(catalog.model_dump(mode="json"))


@pytest.mark.parametrize("cast_key", tuple(CASTS))
def test_packaged_catalog_matches_current_definition(cast_key: str) -> None:
    assert load_catalog(cast_key) == build_catalog(cast_key)


def test_diagnostics_distinguish_entry_pose_and_macro_structure() -> None:
    catalog = load_catalog("one_woman")
    entries = [
        entry
        for entry in catalog.entries
        if entry.central_pose.family == "supine"
        and entry.central_pose.leg_configuration
        == catalog.entries[0].central_pose.leg_configuration
        and entry.compatible_activity_ids
    ]
    assert len(entries) >= 2
    requests = tuple(
        _request(entry, f"S{index + 1:02d}")
        for index, entry in enumerate(entries[:2])
    )
    original = StructuralDiagnostics()
    report = accumulate_structural_diagnostics(original, catalog, requests)

    assert original.evaluated_scenes == 0
    assert original.coverage == {}
    assert report.evidence == "symbolic_structure_only"
    assert report.visual_validation is False
    assert report.evaluated_batches == 1
    assert report.evaluated_scenes == 2
    assert report.unique_pose_entries == 2
    assert report.unique_pose_structures == 2
    assert report.unique_macro_structures == 1
    assert report.minimum_distinct_macro_structures == 1
    assert report.within_batch_pairs == 1
    assert report.same_macro_structure_pairs == 1
    assert report.exact_selection_repeats == 0
    assert report.coverage["family"] == {"supine": 2}
    assert report.coverage["body_level"] == {"low": 2}
    assert report.coverage["primary_surface"] == {"bed": 2}
    assert report.coverage["shot_scale"] == {"full_body": 2}
    assert set(report.coverage) == {
        "pose_entry",
        "pose_structure",
        "macro_structure",
        "selection",
        "family",
        "body_level",
        "torso_orientation",
        "pelvis_orientation",
        "primary_surface",
        "viewpoint",
        "shot_scale",
    }
    assert all(sum(counts.values()) == 2 for counts in report.coverage.values())

    restored = StructuralDiagnostics.model_validate_json(report.model_dump_json())
    replay = tuple(
        request._replace(scene_id=f"R{index}")
        for index, request in enumerate(requests)
    )
    accumulated = accumulate_structural_diagnostics(restored, catalog, replay)
    assert accumulated.evaluated_batches == 2
    assert accumulated.evaluated_scenes == 4
    assert accumulated.unique_pose_entries == 2
    assert accumulated.unique_pose_structures == 2
    assert accumulated.unique_macro_structures == 1
    assert accumulated.exact_selection_repeats == 2
    assert accumulated.within_batch_pairs == 2
    assert accumulated.same_macro_structure_pairs == 2
    assert all(
        sum(counts.values()) == 4 for counts in accumulated.coverage.values()
    )


def test_camera_change_is_not_counted_as_pose_change() -> None:
    catalog = load_catalog("one_woman")
    entry = catalog.entries[0]
    request = _request(entry, "S01")
    report = accumulate_structural_diagnostics(
        StructuralDiagnostics(),
        catalog,
        (
            request,
            request._replace(
                scene_id="S02",
                viewpoint=entry.central_pose.compatible_camera_views[1],
            ),
        ),
    )
    assert report.unique_pose_entries == 1
    assert report.unique_pose_structures == 1
    assert report.unique_macro_structures == 1
    assert report.exact_selection_repeats == 0
    assert len(report.coverage["viewpoint"]) == 2
    assert len(report.coverage["selection"]) == 2


def test_structure_signatures_ignore_catalog_labels_and_support_order() -> None:
    catalog = load_catalog("one_woman").model_copy(deep=True)
    request = _request(catalog.entries[0], "S01")
    report = accumulate_structural_diagnostics(
        StructuralDiagnostics(), catalog, (request,)
    )
    entry = catalog.entries[0]
    entry.pose_id = "renamed_entry"
    entry.central_pose.support_points.reverse()
    for plan in entry.actor_plans:
        plan.support_points.reverse()
        plan.limb_roles.reverse()
    report = accumulate_structural_diagnostics(report, catalog, (request,))
    assert report.unique_pose_entries == 2
    assert report.unique_pose_structures == 1
    assert report.unique_macro_structures == 1
    assert report.exact_selection_repeats == 1
    assert report.within_batch_pairs == 0


def test_diagnostics_reject_empty_requests() -> None:
    with pytest.raises(ValueError, match="at least one scene"):
        accumulate_structural_diagnostics(
            StructuralDiagnostics(), load_catalog("one_woman"), ()
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"cast_key": "two_women"}, "cast differs"),
        ({"family": "unknown_pose"}, "pose not found"),
    ],
)
def test_diagnostics_reject_requests_outside_catalog(
    changes: dict[str, str], message: str
) -> None:
    catalog = load_catalog("one_woman")
    request = _request(catalog.entries[0], "S01")._replace(**changes)
    with pytest.raises(ValueError, match=message):
        accumulate_structural_diagnostics(
            StructuralDiagnostics(), catalog, (request,)
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"cast_key": "two_women"}, "different cast"),
        ({"family": "unknown_pose"}, "unknown pose"),
    ],
)
def test_audit_rejects_requests_outside_catalog(
    changes: dict[str, str], message: str
) -> None:
    catalog = load_catalog("one_woman")
    request = _request(catalog.entries[0], "S01")._replace(**changes)
    with pytest.raises(ValueError, match=message):
        spatial_audit._audit_requests((request,), catalog, 1, [])


def test_audit_rejects_packaged_drift_even_when_catalog_is_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    load_catalog("one_woman")
    (tmp_path / "one_woman.json").write_text(
        _changed_definition("one_woman").model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(spatial_audit, "CATALOGS", tmp_path)
    progress_path = tmp_path / "audit-progress.json"
    with pytest.raises(ValueError, match="packaged catalog differs"):
        spatial_audit.run_spatial_audit(
            progress_path, seed_count=1, cast_keys=("one_woman",)
        )
    checkpoint = json.loads(progress_path.read_text(encoding="utf-8"))
    cast = checkpoint["casts"]["one_woman"]
    assert cast["catalog_matches_definition"] is False
    assert cast["completed_seeds"] == 0
    assert cast["structural_diagnostics"]["evaluated_scenes"] == 0
    assert "packaged catalog differs" in checkpoint["last_error"]
    assert checkpoint["complete"] is False


def test_audit_checkpoint_binds_generated_definition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    progress_path = tmp_path / "audit-progress.json"
    spatial_audit.run_spatial_audit(
        progress_path, seed_count=1, scene_count=1, cast_keys=("one_woman",)
    )
    monkeypatch.setattr(spatial_audit, "build_catalog", _changed_definition)
    with pytest.raises(ValueError, match="use --restart"):
        spatial_audit.run_spatial_audit(
            progress_path, seed_count=1, scene_count=1, cast_keys=("one_woman",)
        )
    with pytest.raises(ValueError, match="packaged catalog differs"):
        spatial_audit.run_spatial_audit(
            progress_path,
            seed_count=1,
            scene_count=1,
            cast_keys=("one_woman",),
            restart=True,
        )


def test_audit_rejects_stale_in_memory_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(spatial_audit, "load_catalog", _changed_definition)
    with pytest.raises(ValueError, match="cached catalog differs"):
        spatial_audit.run_spatial_audit(
            tmp_path / "audit-progress.json",
            seed_count=1,
            scene_count=1,
            cast_keys=("one_woman",),
        )


def test_audit_does_not_checkpoint_non_reproducible_seed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0

    def non_reproducible_requests(
        cast_key: str, *, seed: int, count: int
    ) -> tuple[SceneRequest, ...]:
        nonlocal calls
        calls += 1
        requests = build_scene_requests(cast_key, seed=seed, count=count)
        if calls % 2 == 0:
            return (requests[0]._replace(shot_scale="wide"), *requests[1:])
        return requests

    monkeypatch.setattr(
        spatial_audit, "build_scene_requests", non_reproducible_requests
    )
    progress_path = tmp_path / "audit-progress.json"
    with pytest.raises(ValueError, match="not reproducible"):
        spatial_audit.run_spatial_audit(
            progress_path, seed_count=1, scene_count=1, cast_keys=("one_woman",)
        )
    checkpoint = json.loads(progress_path.read_text(encoding="utf-8"))
    cast = checkpoint["casts"]["one_woman"]
    assert cast["catalog_matches_definition"] is True
    assert cast["completed_seeds"] == 0
    assert cast["compiled_prompts"] == 0
    assert cast["reproducibility_checks"] == 0
    assert cast["structural_diagnostics"]["evaluated_batches"] == 0
    assert "not reproducible" in checkpoint["last_error"]


def test_audit_rejects_old_schema_without_migration(tmp_path: Path) -> None:
    progress_path = tmp_path / "audit-progress.json"
    progress_path.write_text('{"schema_version":"1.2"}', encoding="utf-8")
    with pytest.raises(ValueError, match="incompatible schema.*use --restart"):
        spatial_audit.run_spatial_audit(
            progress_path, seed_count=1, scene_count=1, cast_keys=("one_woman",)
        )
    report = spatial_audit.run_spatial_audit(
        progress_path,
        seed_count=1,
        scene_count=1,
        cast_keys=("one_woman",),
        restart=True,
    )
    assert report.schema_version == "1.3"
    assert report.complete
    assert report.casts["one_woman"].structural_diagnostics.within_batch_pairs == 0


def test_audit_cli_reports_catalog_mismatch_as_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(spatial_audit, "build_catalog", _changed_definition)
    result = CliRunner().invoke(
        app,
        ["audit", "--seed-count", "1", "--count", "1", "--runs-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "packaged catalog differs" in result.output


_ISOLATED_AUDIT_SCRIPT = """
import contextlib
import hashlib
import importlib
import importlib.abc
import io
import json
import runpy
import socket
import sys
from pathlib import Path

blocked = {"t2i_story_pipeline", "t2i_prompt_pipeline", "t2i_film_style_pipeline"}
attempted_imports = []

class RejectOtherPipelines(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            attempted_imports.append(fullname)
            raise AssertionError("cross-pipeline dependency: " + fullname)
        return None

def reject_external_access(*args, **kwargs):
    raise AssertionError("offline audit accessed a provider or network")

sys.meta_path.insert(0, RejectOtherPipelines())
socket.socket.connect = reject_external_access
socket.create_connection = reject_external_access

import t2i_spatial_pipeline
from t2i_spatial_pipeline import blueprint, config, service
from t2i_spatial_pipeline.catalog import CASTS

for module in (blueprint, config, service):
    module.load_spatial_provider_settings = reject_external_access
for path in sorted(Path(t2i_spatial_pipeline.__file__).parent.glob("*.py")):
    if path.stem not in {"__main__", "__init__"}:
        importlib.import_module("t2i_spatial_pipeline." + path.stem)

samples = [
    [
        list(request)
        for request in service.build_scene_requests(cast, seed=seed, count=count)
    ]
    for cast in CASTS
    for seed in (0, 7)
    for count in (1, 6, 20)
]
digest = hashlib.sha256(json.dumps(samples, sort_keys=True).encode()).hexdigest()
directory = sys.argv[1]
sys.argv = [
    "t2i-spatial", "audit", "--seed-count", "1", "--count", "20",
    "--runs-dir", directory,
]
output = io.StringIO()
with contextlib.redirect_stdout(output):
    try:
        runpy.run_module("t2i_spatial_pipeline", run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise AssertionError(output.getvalue()) from exc
assert not attempted_imports, attempted_imports
assert not any(name.split(".")[0] in blocked for name in sys.modules)
print(digest)
"""


def test_standalone_module_is_offline_and_hash_seed_independent(tmp_path: Path) -> None:
    digests = []
    reports = []
    for hash_seed in ("1", "987654"):
        directory = tmp_path / hash_seed
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OPENAI_", "COPILOT_"))
        }
        environment["PYTHONHASHSEED"] = hash_seed
        result = subprocess.run(
            [sys.executable, "-c", _ISOLATED_AUDIT_SCRIPT, str(directory)],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        digests.append(result.stdout.strip())
        report = spatial_audit.SpatialAuditProgress.model_validate_json(
            (directory / "audit-progress.json").read_text(encoding="utf-8")
        )
        assert report.complete
        assert set(report.casts) == set(CASTS)
        for cast in report.casts.values():
            assert cast.catalog_matches_definition
            assert cast.completed_seeds == cast.reproducibility_checks == 1
            assert cast.compiled_prompts == 20
            diagnostics = cast.structural_diagnostics
            assert diagnostics.evaluated_scenes == 20
            assert diagnostics.evaluated_batches == 1
            assert diagnostics.within_batch_pairs == 190
            assert diagnostics.unique_pose_entries == 20
            assert diagnostics.visual_validation is False
            assert all(
                sum(counts.values()) == 20
                for counts in diagnostics.coverage.values()
            )
        reports.append(report)
    assert len(digests[0]) == 64
    assert digests[0] == digests[1]
    assert reports[0] == reports[1]
