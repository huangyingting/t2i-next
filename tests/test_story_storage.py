from __future__ import annotations

import json

import pytest

from t2i_story_pipeline.errors import StoryStorageError
from t2i_story_pipeline.models import StoryStage, TokenUsage
from t2i_story_pipeline.provider import StoryProviderSettings
from t2i_story_pipeline.run_store import (
    LocalStoryRunStore,
    StoryAttempt,
    StoryAttemptOutcome,
    StoryRunSettings,
    StoryRunStatus,
)
from t2i_story_pipeline.storage import publish_story
from tests.story_factories import (
    make_frame_sequence,
    make_story_request,
    make_story_result,
    make_theme_batch,
)


def test_publish_story_writes_json_and_one_prompt_file(tmp_path) -> None:
    result = make_story_result()

    published = publish_story(result, tmp_path)

    assert published.json_file.exists()
    assert published.prompt_file.exists()
    assert len(published.prompt_file.read_text().splitlines()) == 2
    assert published.prompt_file.read_text().splitlines()[0].startswith(
        "1930年代北平电影风格"
    )
    assert '"run_id": "abcdef123456"' in published.json_file.read_text(
        encoding="utf-8"
    )
    payload = json.loads(published.json_file.read_text(encoding="utf-8"))
    assert payload["request"]["content_level"] == "aesthetic"
    assert "quality_feedback" not in payload
    assert list(tmp_path.glob("*")) == [
        published.json_file,
        published.prompt_file,
    ]


def test_publish_story_writes_six_hundred_ordered_prompts(tmp_path) -> None:
    result = make_story_result(theme_count=100, frames_per_theme=6)

    published = publish_story(result, tmp_path)

    lines = published.prompt_file.read_text().splitlines()
    assert len(lines) == 600
    assert "第1站台" in lines[0]
    assert "第100站台" in lines[-1]


def test_story_run_store_persists_checkpoints_attempts_and_completion(
    tmp_path,
) -> None:
    request = make_story_request()
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        concurrency=1,
    )
    store = LocalStoryRunStore(
        tmp_path / "runs",
        tmp_path / "prompts",
    )
    snapshot = store.create(request, settings)
    themes = make_theme_batch().themes
    frames = make_frame_sequence()

    store.checkpoint_themes(snapshot.run_id, themes)
    store.checkpoint_frames(snapshot.run_id, "T001", frames)
    store.record_attempt(
        snapshot.run_id,
        StoryAttempt(
            occurred_at=store.now(),
            stage=StoryStage.THEMES,
            operation_id="themes-T001-T001",
            attempt=1,
            max_output_tokens=6000,
            outcome=StoryAttemptOutcome.ACCEPTED,
            usage=TokenUsage(total_tokens=10),
        ),
    )
    store.record_attempt(
        snapshot.run_id,
        StoryAttempt(
            occurred_at=store.now(),
            stage=StoryStage.FRAMES,
            operation_id="frames-T001",
            attempt=1,
            max_output_tokens=32768,
            outcome=StoryAttemptOutcome.ACCEPTED,
            usage=TokenUsage(total_tokens=20),
        ),
    )
    result = make_story_result().model_copy(
        update={
            "run_id": snapshot.run_id,
            "request": request,
            "usage": TokenUsage(total_tokens=30),
        }
    )

    completed = store.complete(snapshot.run_id, result)
    restored = LocalStoryRunStore(tmp_path / "runs").inspect(snapshot.run_id)
    listing = store.list_runs()

    assert restored.completed == completed
    assert restored.manifest.status == StoryRunStatus.COMPLETED
    assert completed.result_file.is_file()
    assert completed.published.prompt_file.is_file()
    assert len(tuple((tmp_path / "runs" / snapshot.run_id / "attempts").iterdir())) == 2
    assert [item.run_id for item in listing.runs] == [snapshot.run_id]
    assert listing.runs[0].status == StoryRunStatus.COMPLETED

    (
        tmp_path / "runs" / snapshot.run_id / "themes" / "T001.json"
    ).write_text(
        make_theme_batch(start=2).themes[0].model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(StoryStorageError, match="文件名与内容不匹配"):
        store.inspect(snapshot.run_id)


def test_story_run_store_rejects_corrupt_checkpoint(tmp_path) -> None:
    store = LocalStoryRunStore(
        tmp_path / "runs",
        tmp_path / "prompts",
    )
    snapshot = store.create(
        make_story_request(),
        StoryRunSettings(
            provider=StoryProviderSettings(model="test-model")
        ),
    )
    theme_path = (
        tmp_path
        / "runs"
        / snapshot.run_id
        / "themes"
        / "T001.json"
    )
    theme_path.write_text(
        make_theme_batch(start=2).themes[0].model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(StoryStorageError, match="文件名与内容不匹配"):
        store.inspect(snapshot.run_id)
