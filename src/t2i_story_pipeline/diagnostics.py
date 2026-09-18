"""Read-only generation diagnostics from durable attempts and checkpoints."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from t2i_story_pipeline.models import StoryStage
from t2i_story_pipeline.run_store import (
    StoryAttempt,
    StoryAttemptOutcome,
    StoryRunSnapshot,
)


@dataclass(frozen=True)
class StageDiagnostics:
    calls: int
    requested_slots: int
    accepted_slots: int
    checkpointed_slots: int
    first_pass_accepted_slots: int
    first_pass_acceptance_rate: float | None
    retry_slot_requests: int
    outcomes: dict[str, int]
    quality_issues: dict[str, int]
    summed_call_duration_ms: int
    reported_prompt_tokens: int
    reported_completion_tokens: int
    reported_total_tokens: int
    calls_without_reported_tokens: int
    reported_tokens_per_checkpoint: float | None


def stage_diagnostics(
    attempts: Sequence[StoryAttempt], checkpointed_slots: int
) -> StageDiagnostics:
    seen: set[str] = set()
    accepted: set[str] = set()
    first_pass_accepted: set[str] = set()
    for attempt in sorted(attempts, key=lambda item: (item.attempt, item.operation_id)):
        first_pass_accepted.update(set(attempt.accepted_ids) - seen)
        seen.update(attempt.requested_ids)
        accepted.update(attempt.accepted_ids)
    total_tokens = sum(attempt.usage.total_tokens for attempt in attempts)
    return StageDiagnostics(
        calls=len(attempts),
        requested_slots=len(seen),
        accepted_slots=len(accepted),
        checkpointed_slots=checkpointed_slots,
        first_pass_accepted_slots=len(first_pass_accepted),
        first_pass_acceptance_rate=(
            len(first_pass_accepted) / len(seen) if seen else None
        ),
        retry_slot_requests=sum(len(attempt.requested_ids) for attempt in attempts)
        - len(seen),
        outcomes=dict(Counter(attempt.outcome.value for attempt in attempts)),
        quality_issues=dict(
            Counter(
                issue.check for attempt in attempts for issue in attempt.quality_issues
            )
        ),
        summed_call_duration_ms=sum(attempt.duration_ms for attempt in attempts),
        reported_prompt_tokens=sum(attempt.usage.prompt_tokens for attempt in attempts),
        reported_completion_tokens=sum(
            attempt.usage.completion_tokens for attempt in attempts
        ),
        reported_total_tokens=total_tokens,
        calls_without_reported_tokens=sum(
            not any(
                (
                    attempt.usage.prompt_tokens,
                    attempt.usage.completion_tokens,
                    attempt.usage.total_tokens,
                )
            )
            for attempt in attempts
        ),
        reported_tokens_per_checkpoint=(
            total_tokens / checkpointed_slots if checkpointed_slots else None
        ),
    )


def run_diagnostics(
    snapshot: StoryRunSnapshot, attempts: Sequence[StoryAttempt]
) -> dict[str, object]:
    checkpoints = {
        StoryStage.THEMES: len(snapshot.themes),
        StoryStage.FRAMES: sum(
            len(sequence.frames) for sequence in snapshot.frames.values()
        ),
    }
    stages = {
        stage.value: asdict(
            stage_diagnostics(
                [attempt for attempt in attempts if attempt.stage == stage],
                checkpoints[stage],
            )
        )
        for stage in StoryStage
    }
    return {
        "run_id": snapshot.run_id,
        "status": snapshot.manifest.status.value,
        "stages": stages,
        "notes": [
            "Token totals contain only recorded provider usage, not a price estimate.",
            "Calls without reported tokens are not assumed to be free.",
            "Durations sum generation calls; concurrent calls overlap in wall time.",
            "Accepted slots and durable checkpoints can differ after interruption.",
            "Transport retries inside a generation call are not separately recorded.",
        ],
        "truncated_calls": sum(
            attempt.outcome == StoryAttemptOutcome.TRUNCATED for attempt in attempts
        ),
    }
