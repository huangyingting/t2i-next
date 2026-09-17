from __future__ import annotations

import asyncio
import json

import pytest

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.errors import (
    StoryProviderHTTPError,
    StoryRunIncompleteError,
)
from t2i_story_pipeline.models import StoryStage
from t2i_story_pipeline.provider import StoryProviderSettings
from t2i_story_pipeline.run_store import LocalStoryRunStore, StoryRunSettings
from t2i_story_pipeline.studio import StoryStudio
from tests.story_factories import make_frame_sequence, make_story_request, make_theme
from tests.test_story_studio import RoutedStoryModel, make_studio


class OverlappingStoryModel(RoutedStoryModel):
    def __init__(self):
        super().__init__()
        self.active = 0
        self.maximum_active = 0
        self.later_theme_started = asyncio.Event()
        self.first_frame_started = asyncio.Event()
        self.overlap_observed = asyncio.Event()

    def start_call(self):
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)

    async def generate(self, **kwargs):
        self.start_call()
        try:
            payload = json.loads(kwargs["messages"][1].content)
            if payload["existing_themes"]:
                self.later_theme_started.set()
                await asyncio.wait_for(self.first_frame_started.wait(), timeout=2)
                assert self.active == 2
                self.overlap_observed.set()
            return await super().generate(**kwargs)
        finally:
            self.active -= 1

    async def generate_text(self, **kwargs):
        self.start_call()
        try:
            await asyncio.wait_for(self.later_theme_started.wait(), timeout=2)
            self.first_frame_started.set()
            await asyncio.wait_for(self.overlap_observed.wait(), timeout=2)
            return await super().generate_text(**kwargs)
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_frames_overlap_later_themes_under_one_global_limit(tmp_path):
    model = OverlappingStoryModel()
    completed = await asyncio.wait_for(
        make_studio(model, tmp_path, concurrency=2, theme_batch_size=2).run(
            make_story_request(theme_count=4, frames_per_theme=1)
        ),
        timeout=5,
    )
    assert model.overlap_observed.is_set()
    assert model.maximum_active == 2
    assert model.active == 0
    assert len(completed.result.themes) == 4
    assert model.stages.count(StoryStage.THEMES) == 2
    assert model.stages.count(StoryStage.FRAMES) == 4


@pytest.mark.asyncio
async def test_resume_overlaps_saved_theme_holes_with_new_themes(tmp_path):
    request = make_story_request(theme_count=3, frames_per_theme=2)
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        concurrency=2,
        theme_batch_size=2,
    )
    rules = resolve_story_rules(request)
    store = LocalStoryRunStore(tmp_path / "runs", tmp_path / "prompts")
    snapshot = store.create(request, settings, rules)
    store.checkpoint_themes(snapshot.run_id, [make_theme()], "lost_luggage_reunion")
    saved_frame = make_frame_sequence().frames[0]
    store.checkpoint_frame(snapshot.run_id, "T001", saved_frame)

    model = OverlappingStoryModel()
    completed = await asyncio.wait_for(
        StoryStudio(model, store, settings, rules).resume(snapshot.run_id), timeout=5
    )
    assert model.overlap_observed.is_set()
    assert model.maximum_active == 2
    assert model.stages.count(StoryStage.THEMES) == 1
    payloads = [
        json.loads(messages[1].content)
        for stage, messages in zip(model.stages, model.messages, strict=True)
        if stage == StoryStage.FRAMES
    ]
    old_theme = next(p for p in payloads if p["theme"]["theme_id"] == "T001")
    assert old_theme["requested_frame_slots"] == ["F02"]
    assert old_theme["accepted_frames"] == [saved_frame.model_dump()]
    assert completed.result.themes[0].frames[0] == saved_frame


@pytest.mark.asyncio
async def test_theme_failure_drains_saved_work_and_resume_only_fills_gaps(tmp_path):
    class FailingLaterThemes(RoutedStoryModel):
        async def generate(self, **kwargs):
            if json.loads(kwargs["messages"][1].content)["existing_themes"]:
                raise StoryProviderHTTPError(503, "unavailable")
            return await super().generate(**kwargs)

    request = make_story_request(theme_count=4, frames_per_theme=1)
    with pytest.raises(StoryRunIncompleteError) as failure:
        await asyncio.wait_for(
            make_studio(
                FailingLaterThemes(),
                tmp_path,
                concurrency=2,
                theme_batch_size=2,
                generation_retries=0,
            ).run(request),
            timeout=5,
        )
    assert failure.value.missing_themes == 2
    assert failure.value.missing_frames == 2
    store = LocalStoryRunStore(tmp_path / "runs")
    snapshot = store.inspect(failure.value.run_id)
    assert set(snapshot.frames) == {"T001", "T002"}
    assert snapshot.completed is None
    model = RoutedStoryModel()
    completed = await make_studio(
        model,
        tmp_path,
        concurrency=2,
        theme_batch_size=2,
        generation_retries=0,
    ).resume(snapshot.run_id)
    assert model.stages.count(StoryStage.THEMES) == 1
    assert model.stages.count(StoryStage.FRAMES) == 2
    assert completed.result.themes[0].frames == snapshot.frames["T001"].frames


@pytest.mark.asyncio
async def test_unexpected_producer_failure_cancels_workers_and_releases_lock(tmp_path):
    class BrokenProducer(RoutedStoryModel):
        def __init__(self):
            super().__init__()
            self.frame_started = asyncio.Event()
            self.frame_cancelled = asyncio.Event()

        async def generate(self, **kwargs):
            if json.loads(kwargs["messages"][1].content)["existing_themes"]:
                await self.frame_started.wait()
                raise ValueError("unexpected model bug")
            return await super().generate(**kwargs)

        async def generate_text(self, **kwargs):
            self.frame_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.frame_cancelled.set()

    model = BrokenProducer()
    with pytest.raises(ValueError, match="unexpected model bug"):
        await asyncio.wait_for(
            make_studio(model, tmp_path, concurrency=2, theme_batch_size=1).run(
                make_story_request(theme_count=2, frames_per_theme=1)
            ),
            timeout=5,
        )
    assert model.frame_cancelled.is_set()
    store = LocalStoryRunStore(tmp_path / "runs")
    run_id = store.list_runs().runs[0].run_id
    with store.lock(run_id):
        pass


@pytest.mark.asyncio
async def test_cancellation_stops_in_flight_theme_and_frame_calls(tmp_path):
    class CancellablePipeline(RoutedStoryModel):
        def __init__(self):
            super().__init__()
            self.started = set()
            self.cancelled = set()
            self.both_started = asyncio.Event()
            self.call_tasks = set()

        async def wait_for_cancellation(self, stage):
            self.started.add(stage)
            self.call_tasks.add(asyncio.current_task())
            if len(self.started) == 2:
                self.both_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.add(stage)
                raise

        async def generate(self, **kwargs):
            if json.loads(kwargs["messages"][1].content)["existing_themes"]:
                await self.wait_for_cancellation(StoryStage.THEMES)
            return await super().generate(**kwargs)

        async def generate_text(self, **kwargs):
            await self.wait_for_cancellation(StoryStage.FRAMES)
            raise AssertionError("cancelled call returned")

    model = CancellablePipeline()
    task = asyncio.create_task(
        make_studio(model, tmp_path, concurrency=2, theme_batch_size=1).run(
            make_story_request(theme_count=2, frames_per_theme=1)
        )
    )
    try:
        await asyncio.wait_for(model.both_started.wait(), timeout=2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
    assert model.cancelled == {StoryStage.THEMES, StoryStage.FRAMES}
    assert all(task is not None and task.done() for task in model.call_tasks)
    store = LocalStoryRunStore(tmp_path / "runs")
    run_id = store.list_runs().runs[0].run_id
    assert len(store.inspect(run_id).themes) == 1
    with store.lock(run_id):
        pass
