from __future__ import annotations

import json

import pytest

from t2i_story_pipeline.errors import StoryProviderError, StoryRunIncompleteError
from t2i_story_pipeline.inputs import (
    StoryDocument,
    StoryRunConfiguration,
    resolve_story_input,
)
from t2i_story_pipeline.models import (
    NarrativeFrame,
    NarrativeThemeBatch,
    NarrativeThemeResult,
    StoryResult,
    TokenUsage,
)
from t2i_story_pipeline.provider import (
    ModelResponse,
    StoryProviderSettings,
    TextModelResponse,
)
from t2i_story_pipeline.run_store import (
    LocalStoryRunStore,
    StoryAttempt,
    StoryRunSettings,
)
from t2i_story_pipeline.studio import StoryStudio
from tests.test_story_studio import FakeStoryModel
from tests.test_story_theme_memory import draft, theme


def setup_run(tmp_path, *, frames=2, themes=1, batch=1, retries=1):
    resolved = resolve_story_input(
        StoryDocument(description="Adult travelers at a railway station."),
        run_configuration=StoryRunConfiguration(
            generation={"frames_per_theme": frames, "theme_count": themes},
            runtime={
                "concurrency": 1,
                "generation_retries": retries,
                "theme_batch_size": batch,
            },
            validation={
                "themes": {"mode": "off", "checks": []},
                "frames": {
                    "mode": "enforce",
                    "checks": [
                        {"type": "prose_length", "min_chars": 3, "max_chars": 20}
                    ],
                },
            },
        ),
    )
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test"),
        **resolved.runtime.model_dump(),
        quality=resolved.quality,
    )
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    return resolved, settings, store


def batch(*indices):
    return NarrativeThemeBatch(
        semantic_name="station", themes=[draft(theme(index)) for index in indices]
    )


@pytest.mark.asyncio
async def test_all_six_frame_errors_and_prior_prose_reach_retry(tmp_path):
    resolved, settings, store = setup_run(tmp_path, frames=6)
    model = FakeStoryModel(
        [
            batch(1),
            "".join(f"<FRAME>{i}</FRAME>" for i in range(1, 7)),
            "".join(f"<FRAME>Scene {i}</FRAME>" for i in range(1, 7)),
        ]
    )
    completed = await StoryStudio(model, store, settings).run(resolved)
    retry = model.messages[-1]
    for i in range(1, 7):
        assert f"T001-F{i:02d}" in retry[-1].content
        assert f'"frame_id": "F{i:02d}"' in retry[-2].content
    attempts = [a for a in store.attempts(completed.run_id) if a.stage == "frames"]
    assert len(attempts[0].rejected_frames) == 6
    assert len(completed.result.themes[0].frames) == 6


@pytest.mark.asyncio
async def test_rejected_prose_survives_resume_without_regenerating_accepted_frame(
    tmp_path,
):
    resolved, settings, store = setup_run(tmp_path, retries=0)
    first = FakeStoryModel([batch(1), "<FRAME>Scene one</FRAME><FRAME>x</FRAME>"])
    with pytest.raises(StoryRunIncompleteError) as failure:
        await StoryStudio(first, store, settings).run(resolved)
    run_id = failure.value.run_id
    saved = store.inspect(run_id)
    assert [f.frame_id for f in saved.frames["T001"].frames] == ["F01"]
    resumed = FakeStoryModel(["<FRAME>Scene two</FRAME>"])
    reopened = LocalStoryRunStore(tmp_path / "runs")
    result = await StoryStudio(resumed, reopened, settings).resume(run_id)
    payload = json.loads(resumed.messages[0][1].content)
    assert payload["requested_frame_slots"] == ["F02"]
    evidence = resumed.messages[0][-2].content
    assert '"frame_id": "F02"' in evidence and '"prose": "x"' in evidence
    assert '"frame_id": "F01"' not in evidence
    assert result.result.themes[0].frames[0].prose == "Scene one"


def test_retry_prose_is_bounded_without_silently_hiding_truncation():
    messages = StoryStudio._retry_messages(
        [],
        ("T001-F01 too long",),
        expects_plain_text=True,
        rejected_frames=(NarrativeFrame(frame_id="F01", prose="x" * 3000),),
    )
    assert '"truncated": true' in messages[0].content
    assert "x" * 2000 in messages[0].content
    assert "x" * 2001 not in messages[0].content


def test_frame_retry_uses_one_latest_attempt_despite_backward_clock():
    older = StoryAttempt(
        occurred_at="2026-01-02T00:00:00+00:00",
        stage="frames",
        operation_id="frames-T001",
        requested_ids=["T001-F01"],
        attempt=1,
        max_output_tokens=4096,
        outcome="rejected",
        accepted_ids=[],
        issues=["old failure"],
        duration_ms=10,
        rejected_frames=[NarrativeFrame(frame_id="F01", prose="Old view")],
    )
    newer = older.model_copy(
        update={
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "attempt": 2,
            "issues": ["current failure"],
            "rejected_frames": [NarrativeFrame(frame_id="F01", prose="New view")],
        }
    )
    recent = StoryStudio._recent_frame_attempt((newer, older), "frames-T001")
    assert recent is newer
    assert recent.issues == ["current failure"]
    assert recent.rejected_frames[0].prose == "New view"
    accepted = newer.model_copy(
        update={
            "attempt": 3,
            "issues": [],
            "rejected_frames": [],
            "outcome": "accepted",
            "accepted_ids": ["T001-F01"],
        }
    )
    assert (
        StoryStudio._recent_frame_attempt((newer, older, accepted), "frames-T001")
        is accepted
    )
    assert StoryStudio._recent_frame_attempt((older,), "frames-T002") is None


@pytest.mark.asyncio
async def test_identical_frames_keep_first_and_retry_only_duplicate(tmp_path):
    resolved, settings, store = setup_run(tmp_path)
    model = FakeStoryModel(
        [
            batch(1),
            "<FRAME>Scene one</FRAME><FRAME>Scene one</FRAME>",
            "<FRAME>Scene two</FRAME>",
        ]
    )
    completed = await StoryStudio(model, store, settings).run(resolved)
    payload = json.loads(model.messages[-1][1].content)
    assert payload["requested_frame_slots"] == ["F02"]
    assert "重复" in model.messages[-1][-1].content
    assert completed.result.themes[0].frames[0].prose == "Scene one"
    with pytest.raises(ValueError, match="重复"):
        NarrativeThemeResult(
            theme=theme(),
            frames=[
                NarrativeFrame(frame_id="F01", prose="Scene one"),
                NarrativeFrame(frame_id="F02", prose="SCENE  one"),
            ],
        )


@pytest.mark.asyncio
async def test_theme_batch_duplicates_are_rejected_before_checkpoint(tmp_path):
    resolved, settings, store = setup_run(tmp_path, frames=1, themes=2, batch=2)
    model = FakeStoryModel(
        [
            batch(1, 1),
            batch(1, 2),
            "<FRAME>First view</FRAME>",
            "<FRAME>Second view</FRAME>",
        ]
    )
    completed = await StoryStudio(model, store, settings).run(resolved)
    attempts = [a for a in store.attempts(completed.run_id) if a.stage == "themes"]
    assert len(attempts) == 2
    assert attempts[0].accepted_ids == []
    assert "T002 repeats T001" in attempts[0].issues[0]
    assert "T002 repeats T001" in model.messages[1][-1].content
    publication = completed.result.model_dump(mode="json")
    publication["themes"][1]["theme"]["diversity"] = publication["themes"][0]["theme"][
        "diversity"
    ]
    with pytest.raises(ValueError, match="T002 repeats T001"):
        StoryResult.model_validate(publication)


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
async def test_theme_duplicate_checks_reach_beyond_recent_full_history(
    tmp_path, resume
):
    class HistoryModel:
        def __init__(self, stop_before_fourth=False):
            self.stop_before_fourth = stop_before_fourth
            self.repeated = False
            self.last_messages = []

        async def generate(self, **kwargs):
            messages = kwargs["messages"]
            payload = json.loads(messages[1].content)
            index = len(payload["existing_themes"]) + 1
            self.last_messages = messages
            if index == 4 and self.stop_before_fourth:
                raise StoryProviderError("Stop before fourth Theme")
            if index == 4 and not self.repeated:
                self.repeated = True
                index = 1
            return ModelResponse(value=batch(index), usage=TokenUsage())

        async def generate_text(self, **kwargs):
            payload = json.loads(kwargs["messages"][1].content)
            return TextModelResponse(
                text=f"<FRAME>View {payload['theme']['theme_id']}</FRAME>",
                usage=TokenUsage(),
            )

    resolved, settings, store = setup_run(tmp_path, frames=1, themes=4, batch=1)
    model = HistoryModel()
    if resume:
        interrupted = HistoryModel(stop_before_fourth=True)
        with pytest.raises(StoryRunIncompleteError) as failure:
            await StoryStudio(interrupted, store, settings).run(resolved)
        assert len(store.inspect(failure.value.run_id).themes) == 3
        reopened = LocalStoryRunStore(tmp_path / "runs")
        completed = await StoryStudio(model, reopened, settings).resume(
            failure.value.run_id
        )
    else:
        completed = await StoryStudio(model, store, settings).run(resolved)
    payload = json.loads(model.last_messages[1].content)
    assert [value["theme_id"] for value in payload["existing_themes"]] == [
        "T001",
        "T002",
        "T003",
    ]
    assert [value["theme_id"] for value in payload["recent_themes"]] == ["T002", "T003"]
    assert "T004 repeats T001" in model.last_messages[-1].content
    assert len(completed.result.themes) == 4
