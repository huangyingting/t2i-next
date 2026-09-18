from __future__ import annotations

import json

from typer.testing import CliRunner

from t2i_story_pipeline.cli import app
from t2i_story_pipeline.diagnostics import run_diagnostics, stage_diagnostics
from t2i_story_pipeline.models import TokenUsage
from t2i_story_pipeline.provider import StoryProviderSettings
from t2i_story_pipeline.run_store import (
    LocalStoryRunStore,
    StoryAttempt,
    StoryRunSettings,
)
from tests.story_factories import make_story_input, make_story_request


def attempt(number, requested, accepted, **fields):
    return StoryAttempt(
        occurred_at=f"2026-01-01T00:00:0{number}+00:00",
        stage="frames",
        operation_id="frames-T001",
        attempt=number,
        max_output_tokens=4096,
        requested_ids=requested,
        accepted_ids=accepted,
        outcome="accepted" if requested == accepted else "rejected",
        issues=[],
        duration_ms=100,
        **fields,
    )


def test_diagnostics_distinguish_slot_retries_and_durable_checkpoints():
    attempts = [
        attempt(
            1,
            ["T001-F01", "T001-F02"],
            ["T001-F01"],
            usage=TokenUsage(prompt_tokens=100, completion_tokens=40, total_tokens=140),
            quality_issues=[
                {
                    "stage": "frames",
                    "theme_id": "T001",
                    "frame_id": "F02",
                    "field": "prose",
                    "check": "prose_length",
                    "message": "Too short.",
                }
            ],
        ),
        attempt(
            2,
            ["T001-F02"],
            ["T001-F02"],
            usage=TokenUsage(prompt_tokens=110, completion_tokens=20, total_tokens=130),
        ),
    ]
    report = stage_diagnostics(attempts, checkpointed_slots=1)
    assert report.calls == 2
    assert report.requested_slots == report.accepted_slots == 2
    assert report.checkpointed_slots == 1
    assert report.first_pass_accepted_slots == 1
    assert report.first_pass_acceptance_rate == 0.5
    assert report.retry_slot_requests == 1
    assert report.quality_issues == {"prose_length": 1}
    assert report.outcomes == {"rejected": 1, "accepted": 1}
    assert report.summed_call_duration_ms == 200
    assert report.reported_total_tokens == 270
    assert report.reported_tokens_per_checkpoint == 270
    assert report.calls_without_reported_tokens == 0
    assert stage_diagnostics(list(reversed(attempts)), 1) == report


def test_diagnostics_do_not_treat_missing_usage_as_measured_zero_cost():
    report = stage_diagnostics([attempt(1, ["T001-F01"], [])], 0)
    assert report.calls_without_reported_tokens == 1
    assert report.reported_tokens_per_checkpoint is None
    empty = stage_diagnostics([], 0)
    assert empty.first_pass_acceptance_rate is None
    assert empty.calls == 0


def test_diagnostics_command_is_read_only_and_needs_no_provider(tmp_path, monkeypatch):
    settings = StoryRunSettings(provider=StoryProviderSettings(model="test-model"))
    resolved = make_story_input(make_story_request(), settings)
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    snapshot = store.create(resolved, settings)
    before = snapshot.manifest.model_dump_json()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = CliRunner().invoke(
        app,
        [
            "diagnostics",
            snapshot.run_id,
            "--runs-dir",
            str(tmp_path / "runs"),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report == run_diagnostics(snapshot, ())
    assert report["stages"]["frames"]["calls"] == 0
    assert store.inspect(snapshot.run_id).manifest.model_dump_json() == before


def test_diagnostics_command_reports_missing_run(tmp_path):
    result = CliRunner().invoke(
        app, ["diagnostics", "20260101T000000Z-missing1", "--runs-dir", str(tmp_path)]
    )
    assert result.exit_code != 0
