from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from t2i_prompt_pipeline import batch
from t2i_prompt_pipeline.batch import (
    BatchLimits,
    BatchRecovery,
    BatchTask,
    run_batch,
)
from t2i_prompt_pipeline.errors import (
    BatchPausedError,
    ConfigurationError,
    RunIncompleteError,
    RunStoreError,
)
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    FrameMode,
    GenerationStage,
    OutputLanguage,
    ProviderSettings,
    ThemeSimilarityReport,
    ThemeSimilaritySettings,
    ThemeSimilarityState,
)
from t2i_prompt_pipeline.persistence import exclusive_file_lock
from t2i_prompt_pipeline.store import LocalRunStore
from tests.factories import make_rules, make_settings, make_spec
from tests.test_pipeline import FakeAuthor


class ManagedAuthor(FakeAuthor):
    def __init__(self, spec):
        super().__init__(spec)
        self.entries = 0
        self.exits = []
        self.before_generate = None

    async def __aenter__(self):
        self.entries += 1
        return self

    async def __aexit__(self, exception_type, _exception, _traceback):
        self.exits.append(exception_type)

    async def generate(self, **kwargs):
        if self.before_generate is not None:
            await self.before_generate(**kwargs)
        return await super().generate(**kwargs)


@dataclass
class BatchCase:
    config: AppConfig
    tasks: tuple[BatchTask, ...]
    path: Path
    author: ManagedAuthor

    @property
    def store(self):
        return LocalRunStore(
            self.config.runs_directory, self.config.prompts_directory
        )

    @property
    def lock(self):
        return self.path.with_name(f"{self.path.name}.lock")

    def state(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def progress(self):
        return self.state()["tasks"][self.tasks[0].task_id]

    async def run(self, **kwargs):
        kwargs.setdefault("retry_delay_seconds", 0)
        return await run_batch(self.config, self.tasks, self.path, **kwargs)


@pytest.fixture
def case(tmp_path, monkeypatch):
    spec = make_spec()
    config = AppConfig(
        spec=spec,
        provider=ProviderSettings(model="never-use-network"),
        runs_directory=tmp_path / "runs",
        prompts_directory=tmp_path / "prompts",
        run_settings=make_settings(generation_retries=0),
        rules=make_rules(spec),
    )
    value = BatchCase(
        config,
        (BatchTask("first", spec, "First task"),),
        tmp_path / "batch.json",
        ManagedAuthor(spec),
    )
    monkeypatch.setattr(batch, "OpenAICompatibleProvider", lambda _: value.author)
    return value


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 1, 1, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(batch, "datetime", Clock)
    return Clock


def forbid_provider(monkeypatch):
    def unexpected_provider(_config):
        pytest.fail("resumption must not open a provider")

    monkeypatch.setattr(batch, "OpenAICompatibleProvider", unexpected_provider)


async def pause_at_attempt_limit(case, limit=1):
    case.author.fail_frame_themes.add("T01")
    with pytest.raises(BatchPausedError):
        await case.run(
            recovery=BatchRecovery.RETRY,
            limits=BatchLimits(max_task_attempts=limit),
        )


async def test_success_reserves_attempts_and_resume_is_idempotent(
    case, monkeypatch
):
    case.tasks += (BatchTask("second", case.config.spec, "Second task"),)
    observed = set()
    messages = []

    async def inspect_reservation(**_kwargs):
        state = case.state()
        running = [
            (task_id, progress)
            for task_id, progress in state["tasks"].items()
            if progress["status"] == "running"
        ]
        assert len(running) == 1
        task_id, progress = running[0]
        assert progress["attempts"] == 1
        assert len(progress["run_ids"]) == 1
        assert case.store.inspect(progress["run_ids"][0]).completed is None
        observed.add(task_id)
        with pytest.raises(RunStoreError):
            with exclusive_file_lock(case.lock):
                pytest.fail("paid generation ran outside the batch lock")

    case.author.before_generate = inspect_reservation
    result = await case.run(on_progress=messages.append)

    assert result.completed_tasks == 2
    assert result.generated_frames == 2
    assert result.state_file == case.path.resolve()
    assert len(set(result.prompt_files)) == 2
    assert all(Path(path).read_text(encoding="utf-8") for path in result.prompt_files)
    assert observed == {"first", "second"}
    assert messages
    state = case.state()
    assert state["limits"] == {
        "max_task_attempts": 10,
        "max_replacement_runs": 2,
        "max_duration_seconds": 86400,
    }
    assert state["recovery"] == "stop"
    assert all(item["status"] == "completed" for item in state["tasks"].values())
    original_state = case.path.read_bytes()
    original_prompts = {
        path: Path(path).read_bytes() for path in result.prompt_files
    }
    forbid_provider(monkeypatch)

    assert await case.run() == result
    assert case.path.read_bytes() == original_state
    assert {path: Path(path).read_bytes() for path in result.prompt_files} == (
        original_prompts
    )
    with exclusive_file_lock(case.lock):
        pass


async def test_default_stop_pauses_incomplete_then_resumes_same_run(case):
    case.author.fail_frame_themes.add("T01")

    with pytest.raises(BatchPausedError) as caught:
        await case.run()

    progress = case.progress()
    run_id = progress["run_ids"][0]
    assert caught.value.state_file == case.path.resolve()
    assert progress["attempts"] == 1
    assert progress["status"] == "running"
    assert "T01 failed" in progress["last_error"]
    assert case.state()["pause_reason"]
    snapshot = case.store.inspect(run_id)
    assert snapshot.foundation is not None
    assert list(snapshot.themes) == ["T01"]
    assert snapshot.completed is None
    prior_calls = len(case.author.calls)
    case.author.fail_frame_themes.clear()

    result = await case.run()

    assert result.completed_tasks == 1
    assert case.progress()["attempts"] == 2
    assert case.progress()["run_ids"] == [run_id]
    assert case.state()["pause_reason"] is None
    assert all(
        stage == GenerationStage.FRAMES
        for stage, *_ in case.author.calls[prior_calls:]
    )


async def test_retry_attempt_budget_and_explicit_increases_survive_reload(
    case, monkeypatch
):
    await pause_at_attempt_limit(case, limit=2)
    original = case.state()
    run_id = case.progress()["run_ids"][0]
    assert case.progress()["attempts"] == 2

    with monkeypatch.context() as patch:
        forbid_provider(patch)
        for limits in (None, BatchLimits()):
            with pytest.raises(BatchPausedError):
                await case.run(recovery=BatchRecovery.RETRY, limits=limits)
            assert case.progress()["attempts"] == 2

    with pytest.raises(BatchPausedError):
        await case.run(
            recovery=BatchRecovery.RETRY,
            limits=BatchLimits(
                max_task_attempts=3, max_replacement_runs=4,
                max_duration_seconds=100000,
            ),
        )
    assert case.progress()["attempts"] == 3
    assert case.progress()["run_ids"] == [run_id]
    assert case.state()["created_at"] == original["created_at"]
    assert case.state()["limits"] == {
        "max_task_attempts": 3,
        "max_replacement_runs": 4,
        "max_duration_seconds": 100000,
    }

    case.author.fail_frame_themes.clear()
    await case.run(
        recovery=BatchRecovery.RETRY,
        limits=BatchLimits(max_task_attempts=4),
    )
    assert case.progress()["attempts"] == 4
    assert case.progress()["run_ids"] == [run_id]
    assert case.state()["limits"] == {
        "max_task_attempts": 4,
        "max_replacement_runs": 4,
        "max_duration_seconds": 100000,
    }


@pytest.mark.parametrize(
    "limits",
    [
        BatchLimits(max_task_attempts=1),
        BatchLimits(max_replacement_runs=1),
        BatchLimits(max_duration_seconds=60),
    ],
)
async def test_resume_rejects_budget_decreases_without_changing_state(
    case, monkeypatch, limits
):
    await pause_at_attempt_limit(case, limit=2)
    before = case.path.read_bytes()
    forbid_provider(monkeypatch)

    with pytest.raises(ConfigurationError):
        await case.run(recovery=BatchRecovery.RETRY, limits=limits)

    assert case.path.read_bytes() == before


async def test_replacement_cap_retains_all_runs_and_counts_attempts(
    case, monkeypatch
):
    resumed = []

    async def exhaust_similarity(_studio, run_id):
        progress = case.progress()
        assert progress["run_ids"][-1] == run_id
        assert progress["attempts"] == len(resumed) + 1
        resumed.append(run_id)
        case.store.record_theme_similarity(
            run_id,
            ThemeSimilarityReport(
                state=ThemeSimilarityState.EXHAUSTED,
                model="test-embedding",
                scene_threshold=0.86,
                style_threshold=0.815,
                input_count=0,
                pairs=[],
            ),
        )
        raise RunIncompleteError(
            run_id,
            missing_themes=1,
            missing_frames=1,
            causes=("similarity exhausted",),
        )

    monkeypatch.setattr(batch.PromptStudio, "resume", exhaust_similarity)
    with pytest.raises(BatchPausedError):
        await case.run(
            recovery=BatchRecovery.RETRY,
            limits=BatchLimits(max_replacement_runs=1),
        )

    assert len(resumed) == len(set(resumed)) == 2
    assert case.progress()["run_ids"] == resumed
    assert case.progress()["attempts"] == 2
    assert case.progress()["last_error"]
    with monkeypatch.context() as patch:
        forbid_provider(patch)
        with pytest.raises(BatchPausedError):
            await case.run(recovery=BatchRecovery.RETRY)
    assert case.progress()["attempts"] == 2

    with pytest.raises(BatchPausedError):
        await case.run(
            recovery=BatchRecovery.RETRY,
            limits=BatchLimits(max_replacement_runs=2),
        )
    assert len(resumed) == len(set(resumed)) == 3
    assert case.progress()["run_ids"] == resumed
    assert case.progress()["attempts"] == 3
    assert all(
        case.store.inspect(run_id).theme_similarity_report.state
        == ThemeSimilarityState.EXHAUSTED
        for run_id in resumed
    )


async def test_deadline_includes_restart_downtime_and_requires_increase(
    case, clock, monkeypatch
):
    case.author.fail_frame_themes.add("T01")
    with pytest.raises(BatchPausedError):
        await case.run(limits=BatchLimits(max_duration_seconds=10))
    created_at = case.state()["created_at"]
    clock.current += timedelta(seconds=11)
    case.author.fail_frame_themes.clear()

    with monkeypatch.context() as patch:
        forbid_provider(patch)
        with pytest.raises(BatchPausedError):
            await case.run()
    assert case.progress()["attempts"] == 1
    assert case.state()["created_at"] == created_at
    assert case.state()["limits"]["max_duration_seconds"] == 10

    result = await case.run(limits=BatchLimits(max_duration_seconds=20))

    assert result.completed_tasks == 1
    assert case.progress()["attempts"] == 2
    assert case.state()["created_at"] == created_at
    assert case.state()["limits"]["max_duration_seconds"] == 20


async def test_deadline_cancels_in_flight_generation_and_releases_lock(case):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def block(**_kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    case.author.before_generate = block
    with pytest.raises(BatchPausedError):
        await asyncio.wait_for(
            case.run(limits=BatchLimits(max_duration_seconds=1)), timeout=5
        )

    assert started.is_set()
    assert cancelled.is_set()
    assert case.author.exits == [asyncio.CancelledError]
    assert case.progress()["attempts"] == 1
    assert case.state()["pause_reason"]
    assert case.store.inspect(case.progress()["run_ids"][0]).completed is None
    with exclusive_file_lock(case.lock):
        pass


async def test_external_cancellation_consumes_reserved_attempt_and_releases_lock(
    case, monkeypatch
):
    started = asyncio.Event()

    async def block(**_kwargs):
        started.set()
        await asyncio.Event().wait()

    case.author.before_generate = block
    operation = asyncio.create_task(
        case.run(limits=BatchLimits(max_task_attempts=1))
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        assert case.progress()["attempts"] == 1
        with pytest.raises(RunStoreError):
            await case.run()
    finally:
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation

    assert case.author.exits == [asyncio.CancelledError]
    assert case.progress()["attempts"] == 1
    run_ids = case.progress()["run_ids"]
    with exclusive_file_lock(case.lock):
        pass
    with monkeypatch.context() as patch:
        forbid_provider(patch)
        with pytest.raises(BatchPausedError):
            await case.run()

    case.author.before_generate = None
    assert (
        await case.run(limits=BatchLimits(max_task_attempts=2))
    ).completed_tasks == 1
    assert case.progress()["attempts"] == 2
    assert case.progress()["run_ids"] == run_ids


async def test_lock_is_acquired_before_reading_or_creating_state(case, monkeypatch):
    forbid_provider(monkeypatch)
    with exclusive_file_lock(case.lock):
        with pytest.raises(RunStoreError):
            await case.run()
        assert not case.path.exists()
        case.path.write_text("not valid JSON", encoding="utf-8")
        with pytest.raises(RunStoreError):
            await case.run()
        assert case.path.read_text(encoding="utf-8") == "not valid JSON"

    with pytest.raises(ConfigurationError):
        await case.run()


@pytest.mark.parametrize(
    "change",
    [
        "task_id", "spec", "rules", "provider_signature", "output_token_limit",
        "theme_similarity", "runs_directory", "prompts_directory", "recovery",
    ],
)
async def test_state_mismatch_is_rejected_before_provider_or_state_mutation(
    case, monkeypatch, change
):
    await pause_at_attempt_limit(case)
    before = case.path.read_bytes()
    recovery = BatchRecovery.RETRY
    if change == "task_id":
        case.tasks = (BatchTask("different", case.config.spec, "Different"),)
    elif change == "spec":
        case.tasks = (
            BatchTask("first", make_spec(brief="A different brief"), "First"),
        )
    elif change == "rules":
        case.config = case.config.model_copy(
            update={
                "rules": case.config.rules.model_copy(
                    update={"frames": (*case.config.rules.frames, "Another rule")}
                )
            }
        )
    elif change in {"runs_directory", "prompts_directory"}:
        case.config = case.config.model_copy(
            update={change: case.path.parent / "different"}
        )
    elif change == "recovery":
        recovery = BatchRecovery.STOP
    else:
        changes = {
            "provider_signature": "different-provider",
            "output_token_limit": 256,
            "theme_similarity": ThemeSimilaritySettings(model="different-model"),
        }
        case.config = case.config.model_copy(
            update={
                "run_settings": case.config.run_settings.model_copy(
                    update={change: changes[change]}
                )
            }
        )
    forbid_provider(monkeypatch)

    with pytest.raises(ConfigurationError):
        await case.run(recovery=recovery)

    assert case.path.read_bytes() == before


async def test_runtime_tuning_and_labels_do_not_replace_frozen_run_settings(case):
    await pause_at_attempt_limit(case)
    saved_settings = case.state()["settings"]
    case.config = case.config.model_copy(
        update={
            "run_settings": case.config.run_settings.model_copy(
                update={
                    "generation_retries": 2, "max_concurrency": 1,
                    "theme_batch_size": 1, "output_token_limit": 32768,
                }
            )
        }
    )
    case.tasks = (BatchTask("first", case.config.spec, "A new display label"),)
    case.author.fail_frame_themes.clear()

    await case.run(
        recovery=BatchRecovery.RETRY,
        limits=BatchLimits(max_task_attempts=2),
    )

    assert case.state()["settings"] == saved_settings
    run = case.store.inspect(case.progress()["run_ids"][0])
    assert run.settings.model_dump(mode="json") == saved_settings


@pytest.mark.parametrize("stage", ["initial", "run_id", "reservation", "error"])
async def test_state_write_failures_abort_without_retry(case, monkeypatch, stage):
    original_write = batch.write_json
    snapshots = []
    case.author.fail_frame_themes.add("T01")

    def fail_write(path, value):
        if path == case.path:
            progress = value["tasks"]["first"]
            matches = {
                "initial": not progress["run_ids"],
                "run_id": bool(progress["run_ids"]) and progress["attempts"] == 0,
                "reservation": progress["attempts"] == 1,
                "error": progress["last_error"] is not None,
            }
            if matches[stage]:
                snapshots.append(value)
                raise RunStoreError("injected batch write failure")
        original_write(path, value)

    monkeypatch.setattr(batch, "write_json", fail_write)
    with pytest.raises(RunStoreError, match="injected batch write failure"):
        await case.run(recovery=BatchRecovery.RETRY)

    assert len(snapshots) == 1
    if stage == "initial":
        assert not case.path.exists()
        assert case.author.entries == 0
    elif stage == "run_id":
        assert case.progress()["run_ids"] == []
    else:
        assert case.progress()["attempts"] == (1 if stage == "error" else 0)
    if stage != "error":
        assert case.author.calls == []
    with exclusive_file_lock(case.lock):
        pass


async def test_published_run_reconciles_after_batch_commit_failure_and_expiry(
    case, clock, monkeypatch
):
    original_write = batch.write_json

    def fail_completion(path, value):
        if (
            path == case.path
            and value["tasks"]["first"]["status"] == "completed"
        ):
            raise RunStoreError("batch completion commit lost")
        original_write(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(batch, "write_json", fail_completion)
        with pytest.raises(RunStoreError, match="batch completion commit lost"):
            await case.run(
                limits=BatchLimits(max_task_attempts=1, max_duration_seconds=10)
            )
    progress = case.progress()
    assert progress["status"] == "running"
    assert progress["attempts"] == 1
    archived = case.store.inspect(progress["run_ids"][0]).completed
    assert archived is not None
    prompt_before = Path(archived.prompt_file).read_bytes()
    clock.current += timedelta(days=1)
    forbid_provider(monkeypatch)

    result = await case.run()

    assert result.completed_tasks == 1
    assert result.prompt_files == (archived.prompt_file,)
    assert case.progress()["status"] == "completed"
    assert case.progress()["attempts"] == 1
    assert case.progress()["run_ids"] == progress["run_ids"]
    assert Path(archived.prompt_file).read_bytes() == prompt_before
    assert await case.run() == result


@pytest.mark.parametrize("contents", ["", "{", "[]", "null", "{}", '{"format":"old"}'])
async def test_malformed_state_fails_closed(case, monkeypatch, contents):
    case.path.write_text(contents, encoding="utf-8")
    forbid_provider(monkeypatch)

    with pytest.raises(ConfigurationError):
        await case.run()

    assert case.path.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize("ids", [(), ("",), (" \t",), ("same", "same")])
async def test_empty_or_duplicate_tasks_fail_before_creating_state(
    case, monkeypatch, ids
):
    case.tasks = tuple(BatchTask(item, case.config.spec, item) for item in ids)
    forbid_provider(monkeypatch)

    with pytest.raises(ConfigurationError):
        await case.run()

    assert not case.path.exists()
    assert not case.lock.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_level", ContentLevel.HARDCORE),
        ("frame_mode", FrameMode.VARIATIONS),
        ("output_language", OutputLanguage.ENGLISH),
    ],
)
async def test_tasks_must_share_rule_selectors(case, monkeypatch, field, value):
    different = case.config.spec.model_copy(update={field: value})
    case.tasks += (BatchTask("different", different, "Different"),)
    forbid_provider(monkeypatch)

    with pytest.raises(ConfigurationError):
        await case.run()

    assert not case.path.exists()


@pytest.mark.parametrize("delay", [-1, float("nan"), float("inf")])
async def test_invalid_retry_delay_fails_before_creating_state(
    case, monkeypatch, delay
):
    forbid_provider(monkeypatch)

    with pytest.raises(ConfigurationError):
        await case.run(retry_delay_seconds=delay)

    assert not case.path.exists()


@pytest.mark.parametrize(
    "values",
    [
        {"max_task_attempts": 0},
        {"max_task_attempts": -1},
        {"max_task_attempts": 1001},
        {"max_task_attempts": 1.5},
        {"max_replacement_runs": -1},
        {"max_replacement_runs": 101},
        {"max_replacement_runs": 0.5},
        {"max_duration_seconds": 0},
        {"max_duration_seconds": -1},
        {"max_duration_seconds": float("nan")},
        {"max_duration_seconds": float("inf")},
        {"max_duration_seconds": 31536001},
        {"unknown_limit": 1},
    ],
)
def test_invalid_limits_are_rejected(values):
    with pytest.raises(ValidationError):
        BatchLimits(**values)


def test_limits_accept_smallest_and_largest_documented_budgets():
    assert BatchLimits(max_task_attempts=1, max_replacement_runs=0)
    assert BatchLimits(
        max_task_attempts=1000,
        max_replacement_runs=100,
        max_duration_seconds=31536000,
    )
