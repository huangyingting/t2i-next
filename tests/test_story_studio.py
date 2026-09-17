from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from pathlib import Path

import pytest

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.errors import (
    StoryProviderResponseError,
    StoryProviderTruncatedOutputError,
    StoryRunIncompleteError,
    StoryStructuredOutputError,
)
from t2i_story_pipeline.models import (
    FrameQualityPolicy,
    NarrativeFrameSequence,
    NarrativeThemeBatch,
    StoryQualityPolicy,
    StoryStage,
    ThemeQualityPolicy,
    TokenUsage,
)
from t2i_story_pipeline.provider import (
    ModelResponse,
    StoryProviderSettings,
    TextModelResponse,
)
from t2i_story_pipeline.run_store import (
    LocalStoryRunStore,
    StoryAttemptOutcome,
    StoryRunSettings,
    StoryRunStatus,
)
from t2i_story_pipeline.studio import StoryStudio
from tests.story_factories import (
    make_frame_sequence,
    make_story_request,
    make_theme_batch,
)


class FakeStoryModel:
    def __init__(self, values: Iterable[object]) -> None:
        self._values = iter(values)
        self.stages: list[StoryStage] = []
        self.messages = []
        self.max_output_tokens: list[int] = []

    async def generate(
        self,
        *,
        stage,
        messages,
        response_model,
        max_output_tokens,
    ) -> ModelResponse:
        self.stages.append(stage)
        self.messages.append(messages)
        self.max_output_tokens.append(max_output_tokens)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        return ModelResponse(
            value=value,
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )

    async def generate_text(
        self,
        *,
        stage,
        messages,
        max_output_tokens,
    ) -> TextModelResponse:
        self.stages.append(stage)
        self.messages.append(messages)
        self.max_output_tokens.append(max_output_tokens)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, NarrativeFrameSequence):
            value = "\n".join(f"<FRAME>{frame.prose}</FRAME>" for frame in value.frames)
        if not isinstance(value, str):
            raise TypeError("fake text response must be a string")
        return TextModelResponse(
            text=value,
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )


class RoutedStoryModel(FakeStoryModel):
    def __init__(self) -> None:
        super().__init__([])

    async def generate(self, **kwargs):
        payload = json.loads(kwargs["messages"][1].content)
        self._values = iter(
            [
                make_theme_batch(
                    start=len(payload["existing_themes"]) + 1,
                    count=payload["theme_count"],
                )
            ]
        )
        return await super().generate(**kwargs)

    async def generate_text(self, **kwargs):
        payload = json.loads(kwargs["messages"][1].content)
        sequence = make_frame_sequence(
            frame_count=payload["frames_per_theme"],
            theme_index=int(payload["theme"]["theme_id"][1:]),
        )
        self._values = iter(
            [
                NarrativeFrameSequence(
                    frames=[
                        frame
                        for frame in sequence.frames
                        if frame.frame_id in payload["requested_frame_slots"]
                    ]
                )
            ]
        )
        return await super().generate_text(**kwargs)


def make_studio(
    model: FakeStoryModel,
    directory: Path,
    **setting_changes,
) -> StoryStudio:
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        **setting_changes,
    )
    return StoryStudio(
        model,
        LocalStoryRunStore(
            directory / "runs",
            directory / "prompts",
        ),
        settings,
        resolve_story_rules(make_story_request()),
    )


def test_story_studio_defaults_to_eight_concurrent_frame_sequences() -> None:
    settings = StoryRunSettings(provider=StoryProviderSettings(model="test-model"))

    assert settings.concurrency == 8


@pytest.mark.asyncio
async def test_studio_assigns_ids_and_wraps_batched_text_frames(
    tmp_path,
) -> None:
    source_theme = make_theme_batch().themes[0]
    frame_sequence = make_frame_sequence()
    model = FakeStoryModel(
        [
            NarrativeThemeBatch(
                semantic_name="lost_luggage_reunion",
                themes=[
                    {
                        "title": source_theme.title,
                        "premise": source_theme.premise,
                        "style": source_theme.style,
                    }
                ],
            ),
            frame_sequence,
        ]
    )

    completed = await make_studio(
        model,
        tmp_path,
        concurrency=1,
    ).run(make_story_request())

    result = completed.result
    assert result.themes[0].theme.theme_id == "T001"
    assert [frame.frame_id for frame in result.themes[0].frames] == [
        "F01",
        "F02",
    ]
    assert [frame.prose for frame in result.themes[0].frames] == [
        frame.prose for frame in frame_sequence.frames
    ]
    assert model.stages == [
        StoryStage.THEMES,
        StoryStage.FRAMES,
    ]


@pytest.mark.asyncio
async def test_batched_text_retries_only_rejected_frames(
    tmp_path,
) -> None:
    source_theme = make_theme_batch().themes[0]
    frame_sequence = make_frame_sequence()
    model = FakeStoryModel(
        [
            NarrativeThemeBatch(
                semantic_name="lost_luggage_reunion",
                themes=[
                    {
                        "title": source_theme.title,
                        "premise": source_theme.premise,
                        "style": source_theme.style,
                    }
                ],
            ),
            f"<FRAME>{frame_sequence.frames[0].prose}</FRAME>\n"
            "<FRAME>需要重试的第二帧。</FRAME>",
            f"<FRAME>{frame_sequence.frames[1].prose}</FRAME>",
        ]
    )

    completed = await make_studio(
        model,
        tmp_path,
        quality=StoryQualityPolicy(
            frames=FrameQualityPolicy(
                mode="enforce",
                checks=[{"type": "forbidden_text", "values": ["需要重试"]}],
            )
        ),
        concurrency=1,
    ).run(make_story_request())

    assert model.stages == [
        StoryStage.THEMES,
        StoryStage.FRAMES,
        StoryStage.FRAMES,
    ]
    second_frame_payload = json.loads(model.messages[2][1].content)
    assert second_frame_payload["requested_frame_slots"] == ["F02"]
    assert second_frame_payload["accepted_frames"] == [
        frame_sequence.frames[0].model_dump()
    ]
    retry_messages = model.messages[2]
    assert "纯自然语言画面正文" in retry_messages[-1].content
    assert "schema" not in retry_messages[-1].content
    assert all(message.content != "需要重试的第二帧。" for message in retry_messages)
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    frame_attempts = [
        attempt
        for attempt in store.attempts(completed.run_id)
        if attempt.stage == StoryStage.FRAMES
    ]
    assert [(attempt.operation_id, attempt.outcome) for attempt in frame_attempts] == [
        ("frames-T001", StoryAttemptOutcome.REJECTED),
        ("frames-T001", StoryAttemptOutcome.ACCEPTED),
    ]
    assert frame_attempts[0].accepted_ids == ["T001-F01"]
    assert frame_attempts[1].requested_ids == ["T001-F02"]


@pytest.mark.asyncio
async def test_studio_generates_final_story_paragraphs(tmp_path) -> None:
    model = FakeStoryModel(
        [
            make_theme_batch(count=2),
            make_frame_sequence(theme_index=1),
            make_frame_sequence(theme_index=2),
        ]
    )

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request(theme_count=2)
    )
    result = completed.result

    assert [item.theme.theme_id for item in result.themes] == ["T001", "T002"]
    assert len(result.themes[0].frames) == 2
    assert model.stages == [
        StoryStage.THEMES,
        StoryStage.FRAMES,
        StoryStage.FRAMES,
    ]
    assert model.max_output_tokens == [6000, 32768, 32768]
    assert result.usage.total_tokens == 45


@pytest.mark.asyncio
async def test_studio_accepts_prose_without_quality_template(tmp_path) -> None:
    sequence = make_frame_sequence()
    sequence.frames[0].prose = (
        "雨夜电影风格，1930年代北平旧车站，两名三十岁的成年人隔着一只"
        "旧皮箱相望；平视中景让两人的迟疑与站灯下的潮湿反光同时留在画面里。"
    )
    model = FakeStoryModel([make_theme_batch(), sequence])

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request()
    )
    result = completed.result

    assert result.themes[0].frames[0].prose == sequence.frames[0].prose
    assert model.stages == [StoryStage.THEMES, StoryStage.FRAMES]


@pytest.mark.asyncio
async def test_studio_generates_one_hundred_themes_and_six_hundred_frames(
    tmp_path,
) -> None:
    model = RoutedStoryModel()

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request(theme_count=100, frames_per_theme=6)
    )
    result = completed.result

    assert len(result.themes) == 100
    assert sum(len(item.frames) for item in result.themes) == 600
    assert model.stages.count(StoryStage.THEMES) == 10
    assert model.stages.count(StoryStage.FRAMES) == 100
    frame_payloads = [
        json.loads(messages[1].content)
        for stage, messages in zip(model.stages, model.messages, strict=True)
        if stage == StoryStage.FRAMES
    ]
    assert all(
        payload["requested_frame_slots"] == [f"F{index:02d}" for index in range(1, 7)]
        for payload in frame_payloads
    )
    assert (
        sum(len(payload["requested_frame_slots"]) for payload in frame_payloads) == 600
    )
    assert len(model.stages) == 110


@pytest.mark.asyncio
async def test_studio_supports_smaller_theme_batches(tmp_path) -> None:
    model = RoutedStoryModel()

    completed = await make_studio(
        model,
        tmp_path,
        concurrency=1,
        theme_batch_size=3,
    ).run(make_story_request(theme_count=6))
    result = completed.result

    assert len(result.themes) == 6
    assert model.stages.count(StoryStage.THEMES) == 2


@pytest.mark.asyncio
async def test_studio_assigns_contiguous_theme_ids_across_batches(tmp_path) -> None:
    model = RoutedStoryModel()

    completed = await make_studio(
        model,
        tmp_path,
        concurrency=1,
        generation_retries=0,
        theme_batch_size=5,
    ).run(make_story_request(theme_count=10))
    result = completed.result

    assert [item.theme.theme_id for item in result.themes] == [
        "T001",
        "T002",
        "T003",
        "T004",
        "T005",
        "T006",
        "T007",
        "T008",
        "T009",
        "T010",
    ]
    assert model.stages.count(StoryStage.THEMES) == 2


@pytest.mark.asyncio
async def test_studio_retries_provider_shape_failure_and_counts_usage(
    tmp_path,
) -> None:
    model = FakeStoryModel(
        [
            StoryStructuredOutputError(
                "invalid themes",
                raw_content='{"themes":[]}',
                usage=TokenUsage(total_tokens=30),
                validation_issues=("themes: List should have at least 1 item",),
            ),
            make_theme_batch(),
            make_frame_sequence(),
        ]
    )

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request()
    )
    result = completed.result

    assert model.stages.count(StoryStage.THEMES) == 2
    assert "invalid themes" in model.messages[1][-1].content
    assert result.usage.total_tokens == 60
    attempts = LocalStoryRunStore(tmp_path / "runs").attempts(completed.run_id)
    assert attempts[0].requested_ids == ["T001"]
    assert attempts[0].accepted_ids == []
    assert attempts[0].outcome == StoryAttemptOutcome.REJECTED
    assert attempts[0].issues[-1].startswith("themes:")
    assert attempts[1].accepted_ids == ["T001"]


@pytest.mark.asyncio
async def test_studio_expands_budget_after_truncated_output(tmp_path) -> None:
    model = FakeStoryModel(
        [
            StoryProviderTruncatedOutputError(
                "themes output truncated",
                raw_content='{"themes":[',
                usage=TokenUsage(total_tokens=20),
                validation_issues=("invalid JSON",),
            ),
            make_theme_batch(),
            make_frame_sequence(),
        ]
    )

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request()
    )
    attempts = LocalStoryRunStore(tmp_path / "runs").attempts(completed.run_id)

    assert model.max_output_tokens == [6000, 32768, 32768]
    assert attempts[0].max_output_tokens == 6000
    assert attempts[0].outcome == StoryAttemptOutcome.TRUNCATED
    assert attempts[1].max_output_tokens == 32768


@pytest.mark.asyncio
async def test_studio_preserves_truncation_budget_across_resume(
    tmp_path,
) -> None:
    first_model = FakeStoryModel(
        [
            StoryProviderTruncatedOutputError(
                "themes output truncated",
                raw_content='{"themes":[',
                usage=TokenUsage(total_tokens=20),
                validation_issues=("invalid JSON",),
            ),
            StoryStructuredOutputError(
                "themes still invalid",
                raw_content='{"themes":[]}',
                usage=TokenUsage(total_tokens=30),
                validation_issues=("themes: List should have at least 1 item",),
            ),
        ]
    )
    studio = make_studio(
        first_model,
        tmp_path,
        concurrency=1,
        generation_retries=1,
    )

    with pytest.raises(StoryRunIncompleteError) as failure:
        await studio.run(make_story_request())

    snapshot = LocalStoryRunStore(tmp_path / "runs").inspect(failure.value.run_id)
    resumed_model = FakeStoryModel([make_theme_batch(), make_frame_sequence()])
    completed = await StoryStudio(
        resumed_model,
        LocalStoryRunStore(tmp_path / "runs"),
        snapshot.manifest.settings,
        snapshot.rules,
    ).resume(snapshot.run_id)

    assert completed.result.usage.total_tokens == 80
    assert resumed_model.max_output_tokens == [32768, 32768]
    assert "List should have at least 1 item" in (resumed_model.messages[0][-1].content)


@pytest.mark.asyncio
async def test_studio_records_all_structured_output_issues(tmp_path) -> None:
    validation_issues = tuple(f"themes.{index}: Field required" for index in range(40))
    model = FakeStoryModel(
        [
            StoryStructuredOutputError(
                "invalid theme batch",
                raw_content='{"themes":[]}',
                usage=TokenUsage(total_tokens=25),
                validation_issues=validation_issues,
            ),
            make_theme_batch(),
            make_frame_sequence(),
        ]
    )

    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request()
    )
    attempts = LocalStoryRunStore(tmp_path / "runs").attempts(completed.run_id)

    assert len(attempts[0].issues) == 41
    assert attempts[0].issues[-1] == validation_issues[-1]


@pytest.mark.asyncio
async def test_studio_normalizes_frame_ids_by_response_order(tmp_path) -> None:
    sequence = make_frame_sequence()
    sequence.frames[1].frame_id = "F03"
    model = FakeStoryModel([make_theme_batch(), sequence])

    completed = await make_studio(
        model,
        tmp_path,
        concurrency=1,
        generation_retries=0,
    ).run(make_story_request())
    result = completed.result

    assert [frame.frame_id for frame in result.themes[0].frames] == [
        "F01",
        "F02",
    ]


@pytest.mark.asyncio
async def test_studio_does_not_branch_on_story_description_phrases(tmp_path) -> None:
    theme_batch = make_theme_batch()
    theme_batch.themes[0].premise = "An em dash — remains valid model output."
    sequence = make_frame_sequence()
    sequence.frames[
        1
    ].prose = "At Beijing station in autumn, the same wet platform remains visible."
    request = make_story_request().model_copy(
        update={
            "story": (
                "When the requested language is English, use only ASCII code "
                "points U+0020 through U+007E. "
                "Write the opening as a complete first presentation of the "
                "setting with no backward pointer or reference to another Frame."
            )
        }
    )
    model = FakeStoryModel([theme_batch, sequence])

    completed = await make_studio(model, tmp_path, concurrency=1).run(request)
    attempts = LocalStoryRunStore(tmp_path / "runs").attempts(completed.run_id)

    assert completed.result.themes[0].theme.premise == theme_batch.themes[0].premise
    assert completed.result.themes[0].frames[1].prose == sequence.frames[1].prose
    assert model.stages == [StoryStage.THEMES, StoryStage.FRAMES]
    assert all(attempt.outcome == StoryAttemptOutcome.ACCEPTED for attempt in attempts)


@pytest.mark.asyncio
async def test_studio_resumes_only_missing_frame_sequences(tmp_path) -> None:
    first_model = FakeStoryModel(
        [
            make_theme_batch(count=2),
            make_frame_sequence(theme_index=1),
            StoryProviderResponseError("temporary frame failure"),
        ]
    )
    studio = make_studio(
        first_model,
        tmp_path,
        concurrency=1,
        generation_retries=0,
    )

    with pytest.raises(StoryRunIncompleteError) as failure:
        await studio.run(make_story_request(theme_count=2))

    snapshot = LocalStoryRunStore(tmp_path / "runs").inspect(failure.value.run_id)
    assert [theme.theme_id for theme in snapshot.themes] == ["T001", "T002"]
    assert set(snapshot.frames) == {"T001"}

    resumed_model = FakeStoryModel([make_frame_sequence(theme_index=2)])
    resumed = await StoryStudio(
        resumed_model,
        LocalStoryRunStore(tmp_path / "runs"),
        snapshot.manifest.settings,
        snapshot.rules,
    ).resume(snapshot.run_id)

    assert len(resumed.result.themes) == 2
    assert resumed_model.stages == [StoryStage.FRAMES]
    assert "temporary frame failure" in resumed_model.messages[0][-1].content
    assert resumed.result.usage.total_tokens == 45


@pytest.mark.asyncio
async def test_studio_completed_resume_is_idempotent(tmp_path) -> None:
    model = FakeStoryModel([make_theme_batch(), make_frame_sequence()])
    completed = await make_studio(model, tmp_path, concurrency=1).run(
        make_story_request()
    )
    resumed_model = FakeStoryModel([])

    resumed = await StoryStudio(
        resumed_model,
        LocalStoryRunStore(tmp_path / "runs"),
        StoryRunSettings(provider=StoryProviderSettings(model="different-model")),
        resolve_story_rules(make_story_request()),
    ).resume(completed.run_id)

    assert resumed == completed
    assert resumed_model.stages == []


class CancellableStoryModel:
    def __init__(self) -> None:
        self.started_frames = 0
        self.cancelled_frames = 0
        self.all_frames_started = asyncio.Event()
        self.release_frames = asyncio.Event()

    async def generate(
        self,
        *,
        stage,
        messages,
        response_model,
        max_output_tokens,
    ) -> ModelResponse:
        if stage == StoryStage.THEMES:
            return ModelResponse(
                value=make_theme_batch(
                    count=json.loads(messages[1].content)["theme_count"]
                ),
                usage=TokenUsage(total_tokens=10),
            )
        raise AssertionError("structured generation is only used for themes")

    async def generate_text(
        self, *, stage, messages, max_output_tokens
    ) -> TextModelResponse:
        self.started_frames += 1
        if self.started_frames == 2:
            self.all_frames_started.set()
        try:
            await self.release_frames.wait()
        except asyncio.CancelledError:
            self.cancelled_frames += 1
            raise
        raise AssertionError("frame generation should be cancelled")


@pytest.mark.asyncio
@pytest.mark.parametrize("theme_count", [2, 10])
async def test_cancelling_story_run_cleans_up_frame_tasks(
    tmp_path, theme_count
) -> None:
    model = CancellableStoryModel()
    store = LocalStoryRunStore(
        tmp_path / "runs",
        tmp_path / "prompts",
    )
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        concurrency=2,
    )
    task = asyncio.create_task(
        StoryStudio(
            model,
            store,
            settings,
            resolve_story_rules(make_story_request()),
        ).run(make_story_request(theme_count=theme_count))
    )
    await asyncio.wait_for(model.all_frames_started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    summary = store.list_runs().runs[0]
    snapshot = store.inspect(summary.run_id)
    assert model.cancelled_frames == 2
    assert snapshot.manifest.status == StoryRunStatus.RUNNING
    assert len(snapshot.themes) == theme_count
    assert snapshot.frames == {}
    with store.lock(snapshot.run_id):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["off", "report"])
async def test_optional_quality_never_retries_in_off_or_report_mode(tmp_path, mode):
    model = FakeStoryModel([make_theme_batch(), make_frame_sequence()])
    policy = StoryQualityPolicy(
        frames=FrameQualityPolicy(
            mode=mode, checks=[{"type": "required_text", "values": ["MISSING ANCHOR"]}]
        )
    )
    completed = await make_studio(model, tmp_path, quality=policy).run(
        make_story_request()
    )
    assert len(model.stages) == 2
    assert completed.result.quality.status == (
        "skipped" if mode == "off" else "warnings"
    )
    expected_count = 0 if mode == "off" else 2
    assert len(completed.result.quality.issues) == expected_count
    store = LocalStoryRunStore(tmp_path / "runs")
    attempt = store.attempts(completed.run_id)[-1]
    assert attempt.outcome == StoryAttemptOutcome.ACCEPTED
    assert attempt.issues == []
    assert len(attempt.quality_issues) == expected_count
    assert store.inspect(completed.run_id).completed.result.quality == (
        completed.result.quality
    )
    assert "MISSING ANCHOR" not in model.messages[1][1].content
    assert "quality" not in json.loads(model.messages[1][1].content)


@pytest.mark.asyncio
async def test_enforced_quality_retries_with_evidence_and_saves_clean_report(tmp_path):
    bad_sequence = make_frame_sequence()
    good_sequence = make_frame_sequence()
    for frame in good_sequence.frames:
        frame.prose += " 银色站钟。"
    model = FakeStoryModel([make_theme_batch(), bad_sequence, good_sequence])
    policy = StoryQualityPolicy(
        frames=FrameQualityPolicy(
            mode="enforce", checks=[{"type": "required_text", "values": ["银色站钟"]}]
        )
    )
    completed = await make_studio(model, tmp_path, quality=policy).run(
        make_story_request()
    )
    assert len(model.stages) == 3
    assert "银色站钟" in model.messages[2][-1].content
    assert "T001-F01" in model.messages[2][-1].content
    assert completed.result.quality.status == "passed"
    assert completed.result.quality.issues == []
    attempts = LocalStoryRunStore(tmp_path / "runs").attempts(completed.run_id)
    assert attempts[1].outcome == StoryAttemptOutcome.REJECTED
    assert len(attempts[1].quality_issues) == 2
    assert attempts[2].quality_issues == []


@pytest.mark.asyncio
async def test_quality_enforcement_exhaustion_does_not_publish(tmp_path):
    model = FakeStoryModel([make_theme_batch(), make_frame_sequence()])
    policy = StoryQualityPolicy(
        frames=FrameQualityPolicy(
            mode="enforce", checks=[{"type": "required_text", "values": ["absent"]}]
        )
    )
    with pytest.raises(StoryRunIncompleteError):
        await make_studio(model, tmp_path, quality=policy, generation_retries=0).run(
            make_story_request()
        )
    store = LocalStoryRunStore(tmp_path / "runs")
    run_id = store.list_runs().runs[0].run_id
    snapshot = store.inspect(run_id)
    assert snapshot.manifest.status == StoryRunStatus.FAILED
    assert snapshot.manifest.settings.quality == policy
    assert snapshot.frames == {}
    assert not list((tmp_path / "prompts").rglob("*.txt"))


@pytest.mark.asyncio
async def test_quality_off_keeps_text_batch_contract_and_retry(tmp_path):
    model = FakeStoryModel(
        [
            make_theme_batch(),
            "<FRAME>only one of two requested slots</FRAME>",
            make_frame_sequence(),
        ]
    )
    completed = await make_studio(
        model,
        tmp_path,
        quality=StoryQualityPolicy(frames=FrameQualityPolicy(mode="off")),
    ).run(make_story_request())
    assert len(model.stages) == 3
    assert completed.result.quality.status == "skipped"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["themes", "frames"])
async def test_quality_report_tampering_is_a_storage_error(tmp_path, stage):
    from t2i_story_pipeline.errors import StoryStorageError

    completed = await make_studio(
        FakeStoryModel([make_theme_batch(), make_frame_sequence()]), tmp_path
    ).run(make_story_request())
    payload = json.loads(completed.result_file.read_text(encoding="utf-8"))
    payload["quality"][stage]["status"] = "passed"
    completed.result_file.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StoryStorageError, match="质量报告"):
        LocalStoryRunStore(tmp_path / "runs").inspect(completed.run_id)


@pytest.mark.asyncio
async def test_partial_frames_survive_restart_and_only_missing_slots_are_requested(
    tmp_path,
):
    sequence = make_frame_sequence(frame_count=3)
    text = (
        f"<FRAME>{sequence.frames[0].prose}</FRAME>"
        "<FRAME>bad\nmultiline</FRAME>"
        f"<FRAME>{sequence.frames[2].prose}</FRAME>"
    )
    first = FakeStoryModel([make_theme_batch(), text])
    with pytest.raises(StoryRunIncompleteError) as failure:
        await make_studio(first, tmp_path, generation_retries=0).run(
            make_story_request(frames_per_theme=3)
        )
    run_id = failure.value.run_id
    assert failure.value.missing_frames == 1
    store = LocalStoryRunStore(tmp_path / "runs")
    before = store.inspect(run_id)
    assert [frame.frame_id for frame in before.frames["T001"].frames] == ["F01", "F03"]
    first_path = tmp_path / "runs" / run_id / "frames" / "T001" / "F01.json"
    checkpoint_bytes = first_path.read_bytes()
    assert not first_path.with_name("F02.json").exists()
    assert not list((tmp_path / "prompts").rglob("*.txt"))
    last_attempt = store.attempts(run_id)[-1]
    assert last_attempt.requested_ids == ["T001-F01", "T001-F02", "T001-F03"]
    assert last_attempt.accepted_ids == ["T001-F01", "T001-F03"]
    assert last_attempt.outcome == StoryAttemptOutcome.REJECTED

    resumed_model = FakeStoryModel([f"<FRAME>{sequence.frames[1].prose}</FRAME>"])
    result = await make_studio(resumed_model, tmp_path, generation_retries=0).resume(
        run_id
    )
    assert resumed_model.stages == [StoryStage.FRAMES]
    payload = json.loads(resumed_model.messages[0][1].content)
    assert payload["requested_frame_slots"] == ["F02"]
    assert [item["frame_id"] for item in payload["accepted_frames"]] == ["F01", "F03"]
    assert result.result.themes[0].frames == sequence.frames
    assert first_path.read_bytes() == checkpoint_bytes
    assert result.result.usage.total_tokens == 45
    assert store.attempts(run_id)[-1].attempt == 2


@pytest.mark.asyncio
async def test_malformed_batch_retries_whole_batch_with_bounded_attempts(tmp_path):
    model = FakeStoryModel(
        [make_theme_batch(), "<FRAME>only one</FRAME>", make_frame_sequence()]
    )
    completed = await make_studio(model, tmp_path).run(make_story_request())
    attempts = LocalStoryRunStore(tmp_path / "runs").attempts(completed.run_id)
    assert len(model.stages) == 3
    assert attempts[1].accepted_ids == []
    assert attempts[1].requested_ids == attempts[2].requested_ids
    assert "expected=2, actual=1" in attempts[1].issues[0]


@pytest.mark.asyncio
async def test_frame_truncation_budget_is_frozen_across_resume(tmp_path):
    model = FakeStoryModel(
        [
            make_theme_batch(),
            StoryProviderTruncatedOutputError(
                "truncated frame batch",
                raw_content="<FRAME>partial",
                usage=TokenUsage(total_tokens=100),
                validation_issues=(),
            ),
        ]
    )
    with pytest.raises(StoryRunIncompleteError) as failure:
        await make_studio(
            model, tmp_path, frame_output_tokens=512, generation_retries=0
        ).run(make_story_request())
    assert model.max_output_tokens[-1] == 512
    second = FakeStoryModel([make_frame_sequence()])
    completed = await make_studio(
        second, tmp_path, frame_output_tokens=512, generation_retries=0
    ).resume(failure.value.run_id)
    assert second.max_output_tokens == [32768]
    assert completed.result.usage.total_tokens == 130


@pytest.mark.asyncio
async def test_interrupted_frame_writes_preserve_usage_and_only_committed_frames(
    tmp_path, monkeypatch
):
    from t2i_story_pipeline.errors import StoryStorageError

    original_checkpoint = LocalStoryRunStore.checkpoint_frame

    def fail_second_write(self, run_id, theme_id, frame):
        if frame.frame_id == "F02":
            raise StoryStorageError("simulated disk failure")
        return original_checkpoint(self, run_id, theme_id, frame)

    monkeypatch.setattr(LocalStoryRunStore, "checkpoint_frame", fail_second_write)
    with pytest.raises(StoryRunIncompleteError):
        await make_studio(
            FakeStoryModel([make_theme_batch(), make_frame_sequence()]), tmp_path
        ).run(make_story_request())
    store = LocalStoryRunStore(tmp_path / "runs")
    run_id = store.list_runs().runs[0].run_id
    assert store.total_usage(run_id).total_tokens == 30
    frames = store.inspect(run_id).frames["T001"].frames
    assert [frame.frame_id for frame in frames] == ["F01"]
    monkeypatch.setattr(LocalStoryRunStore, "checkpoint_frame", original_checkpoint)
    prose = make_frame_sequence().frames[1].prose
    model = FakeStoryModel([f"<FRAME>{prose}</FRAME>"])
    completed = await make_studio(model, tmp_path).resume(run_id)
    assert completed.result.usage.total_tokens == 45
    assert json.loads(model.messages[0][1].content)["requested_frame_slots"] == ["F02"]


@pytest.mark.asyncio
async def test_partial_progress_never_resets_the_retry_budget(tmp_path):
    model = FakeStoryModel(
        [
            make_theme_batch(),
            "<FRAME>first</FRAME><FRAME></FRAME><FRAME></FRAME>",
            "<FRAME>second</FRAME><FRAME></FRAME>",
        ]
    )
    with pytest.raises(StoryRunIncompleteError) as failure:
        await make_studio(model, tmp_path, generation_retries=1).run(
            make_story_request(frames_per_theme=3)
        )
    assert failure.value.missing_frames == 1
    assert len(model.stages) == 3
    store = LocalStoryRunStore(tmp_path / "runs")
    frames = store.inspect(failure.value.run_id).frames["T001"].frames
    assert [frame.frame_id for frame in frames] == ["F01", "F02"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["off", "report"])
async def test_theme_quality_off_and_report_do_not_retry(tmp_path, mode):
    policy = StoryQualityPolicy(
        themes=ThemeQualityPolicy(
            mode=mode,
            checks=[
                {"type": "required_text", "field": "premise", "values": ["missing"]}
            ],
        )
    )
    model = FakeStoryModel([make_theme_batch(), make_frame_sequence()])
    completed = await make_studio(model, tmp_path, quality=policy).run(
        make_story_request()
    )
    assert len(model.stages) == 2
    report = completed.result.quality
    assert report.themes.status == ("skipped" if mode == "off" else "warnings")
    assert report.frames.status == "skipped"
    attempt = LocalStoryRunStore(tmp_path / "runs").attempts(completed.run_id)[0]
    assert attempt.outcome == StoryAttemptOutcome.ACCEPTED
    assert len(attempt.quality_issues) == (0 if mode == "off" else 1)
    assert "missing" not in model.messages[0][1].content


@pytest.mark.asyncio
async def test_theme_enforcement_retries_before_any_frame_generation(tmp_path):
    policy = StoryQualityPolicy(
        themes=ThemeQualityPolicy(
            mode="enforce",
            checks=[
                {
                    "type": "required_text",
                    "field": "premise",
                    "values": ["station clock"],
                }
            ],
        )
    )
    good = make_theme_batch()
    good.themes[0].premise += " A station clock."
    model = FakeStoryModel([make_theme_batch(), good, make_frame_sequence()])
    completed = await make_studio(model, tmp_path, quality=policy).run(
        make_story_request()
    )
    assert model.stages == [StoryStage.THEMES, StoryStage.THEMES, StoryStage.FRAMES]
    assert "T001.premise" in model.messages[1][-1].content
    assert "station clock" in model.messages[1][-1].content
    assert completed.result.themes[0].theme.premise == good.themes[0].premise
    assert completed.result.quality.themes.status == "passed"
    assert completed.result.quality.issues == []
    store = LocalStoryRunStore(tmp_path / "runs")
    first, second, _ = store.attempts(completed.run_id)
    assert first.accepted_ids == []
    assert first.quality_issues[0].stage == StoryStage.THEMES
    assert first.quality_issues[0].frame_id is None
    assert second.accepted_ids == ["T001"]
    assert store.inspect(completed.run_id).completed.result.quality == (
        completed.result.quality
    )


@pytest.mark.asyncio
async def test_theme_quality_exhaustion_keeps_frames_unstarted(tmp_path):
    policy = StoryQualityPolicy(
        themes=ThemeQualityPolicy(
            mode="enforce",
            checks=[{"type": "required_text", "field": "style", "values": ["missing"]}],
        )
    )
    model = FakeStoryModel([make_theme_batch()])
    with pytest.raises(StoryRunIncompleteError) as failure:
        await make_studio(
            model,
            tmp_path,
            quality=policy,
            generation_retries=0,
        ).run(make_story_request())
    assert model.stages == [StoryStage.THEMES]
    assert failure.value.missing_themes == 1
    assert failure.value.missing_frames == 2
    snapshot = LocalStoryRunStore(tmp_path / "runs").inspect(failure.value.run_id)
    assert snapshot.themes == ()
    assert snapshot.frames == {}
    assert snapshot.completed is None


@pytest.mark.asyncio
async def test_configured_budgets_are_capped_without_changing_frozen_settings(tmp_path):
    request = make_story_request()
    model = FakeStoryModel([make_theme_batch(), make_frame_sequence()])
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model", output_token_limit=4096),
        theme_output_tokens=12000,
        frame_output_tokens=20000,
    )
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    completed = await StoryStudio(
        model,
        store,
        settings,
        resolve_story_rules(request),
    ).run(request)
    assert model.max_output_tokens == [4096, 4096]
    assert [
        attempt.max_output_tokens for attempt in store.attempts(completed.run_id)
    ] == [4096, 4096]
    assert store.inspect(completed.run_id).manifest.settings == settings


@pytest.mark.asyncio
async def test_theme_enforcement_rejects_the_batch_before_checkpointing(tmp_path):
    policy = StoryQualityPolicy(
        themes=ThemeQualityPolicy(
            mode="enforce",
            checks=[{"type": "required_text", "field": "title", "values": ["clock"]}],
        )
    )
    bad = make_theme_batch(count=2)
    bad.themes[0].title += " clock"
    good = bad.model_copy(deep=True)
    good.themes[1].title += " clock"
    model = FakeStoryModel(
        [
            bad,
            good,
            make_frame_sequence(theme_index=1),
            make_frame_sequence(theme_index=2),
        ]
    )
    completed = await make_studio(model, tmp_path, quality=policy, concurrency=1).run(
        make_story_request(theme_count=2)
    )
    attempts = LocalStoryRunStore(tmp_path / "runs").attempts(completed.run_id)
    assert attempts[0].accepted_ids == []
    assert attempts[0].quality_issues[0].theme_id == "T002"
    assert attempts[1].accepted_ids == ["T001", "T002"]
    assert model.stages[:2] == [StoryStage.THEMES, StoryStage.THEMES]
    assert [item.theme.title for item in completed.result.themes] == [
        theme.title for theme in good.themes
    ]
