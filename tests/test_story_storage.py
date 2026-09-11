from __future__ import annotations

import pytest

from t2i_story_pipeline import persistence, run_store
from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.errors import StoryStorageError
from t2i_story_pipeline.models import ContentLevel, StoryStage, TokenUsage
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


@pytest.mark.parametrize(
    ("female_count", "male_count", "expected"),
    (
        (1, 1, "one_woman_one_man"),
        (2, 0, "two_women"),
        (3, 0, "three_women"),
        (2, 1, "two_women_one_man"),
        (1, 2, "one_woman_two_men"),
    ),
)
def test_story_prompt_cast_slug_uses_existing_naming_convention(
    female_count,
    male_count,
    expected,
) -> None:
    request = make_story_request(
        female_count=female_count,
        male_count=male_count,
    )

    assert run_store._cast_slug(request) == expected


@pytest.mark.parametrize(
    ("female_count", "male_count", "expected"),
    (
        (1, 0, "3-view_hardcore_1_woman_0_men"),
        (1, 1, "3-view_hardcore_1_woman_1_man"),
        (2, 1, "3-view_hardcore_2_women_1_man"),
        (None, None, "3-view_hardcore_unspecified_women_unspecified_men"),
    ),
)
def test_prompt_file_output_stem_uses_source_level_and_numeric_cast(
    female_count,
    male_count,
    expected,
) -> None:
    request = make_story_request(
        female_count=female_count,
        male_count=male_count,
        content_level=ContentLevel.HARDCORE,
        source_prompt_stem="3-view",
    )

    assert (
        run_store._prompt_filename_stem(
            request,
            semantic_name="ignored_for_prompt_files",
        )
        == expected
    )


def test_direct_story_output_stem_keeps_semantic_name_and_cast_slug() -> None:
    request = make_story_request(female_count=1, male_count=1)

    assert (
        run_store._prompt_filename_stem(
            request,
            semantic_name="lost_luggage_reunion",
        )
        == "lost_luggage_reunion_one_woman_one_man"
    )


def test_prompt_file_output_stem_normalizes_filename_characters() -> None:
    request = make_story_request(
        female_count=1,
        male_count=1,
        content_level=ContentLevel.EROTIC,
        source_prompt_stem="My Story.v1",
    )

    assert (
        run_store._prompt_filename_stem(
            request,
            semantic_name="ignored_for_prompt_files",
        )
        == "my_story_v1_erotic_1_woman_1_man"
    )


def test_durable_mkdir_fsyncs_every_created_directory_parent(
    tmp_path,
    monkeypatch,
) -> None:
    synced = []
    monkeypatch.setattr(
        persistence,
        "fsync_directory",
        synced.append,
    )
    target = tmp_path / "first" / "second" / "third"

    persistence.durable_mkdir(target)

    assert target.is_dir()
    assert synced == [
        tmp_path,
        tmp_path / "first",
        tmp_path / "first" / "second",
    ]


def test_publish_story_writes_only_one_prompt_file(tmp_path) -> None:
    result = make_story_result()
    prompt_file = tmp_path / "lost_luggage_reunion_0001.txt"

    published = publish_story(result, prompt_file)

    assert published.prompt_file.exists()
    assert len(published.prompt_file.read_text().splitlines()) == 2
    assert (
        published.prompt_file.read_text()
        .splitlines()[0]
        .startswith("1930年代北平电影风格")
    )
    assert list(tmp_path.glob("*")) == [published.prompt_file]


def test_publish_story_writes_six_hundred_ordered_prompts(tmp_path) -> None:
    result = make_story_result(theme_count=100, frames_per_theme=6)

    published = publish_story(
        result,
        tmp_path / "lost_luggage_reunion_0001.txt",
    )

    lines = published.prompt_file.read_text().splitlines()
    assert len(lines) == 600
    assert "第1站台" in lines[0]
    assert "第100站台" in lines[-1]


def test_story_run_store_persists_checkpoints_attempts_and_completion(
    tmp_path,
) -> None:
    request = make_story_request(
        female_count=1,
        male_count=1,
        content_level=ContentLevel.HARDCORE,
        source_prompt_stem="3-view",
    )
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="test-model"),
        concurrency=1,
    )
    store = LocalStoryRunStore(
        tmp_path / "runs",
        tmp_path / "prompts",
    )
    rules = resolve_story_rules(request)
    snapshot = store.create(request, settings, rules)
    themes = make_theme_batch().themes
    frames = make_frame_sequence()

    store.checkpoint_themes(
        snapshot.run_id,
        themes,
        "lost_luggage_reunion",
    )
    store.checkpoint_frames(snapshot.run_id, "T001", frames)
    store.record_attempt(
        snapshot.run_id,
        StoryAttempt(
            occurred_at=store.now(),
            stage=StoryStage.THEMES,
            operation_id="themes-T001-T001",
            requested_ids=["T001"],
            attempt=1,
            max_output_tokens=6000,
            outcome=StoryAttemptOutcome.ACCEPTED,
            accepted_ids=["T001"],
            issues=[],
            duration_ms=10,
            usage=TokenUsage(total_tokens=10),
        ),
    )
    store.record_attempt(
        snapshot.run_id,
        StoryAttempt(
            occurred_at=store.now(),
            stage=StoryStage.FRAMES,
            operation_id="frames-T001",
            requested_ids=["T001-F01", "T001-F02"],
            attempt=1,
            max_output_tokens=32768,
            outcome=StoryAttemptOutcome.ACCEPTED,
            accepted_ids=["T001-F01", "T001-F02"],
            issues=[],
            duration_ms=20,
            usage=TokenUsage(total_tokens=20),
        ),
    )
    result = make_story_result(
        female_count=1,
        male_count=1,
        content_level=ContentLevel.HARDCORE,
        source_prompt_stem="3-view",
    ).model_copy(
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
    assert restored.rules == rules
    assert restored.manifest.rules_fingerprint == rules.fingerprint()
    assert restored.manifest.status == StoryRunStatus.COMPLETED
    assert completed.result_file.is_file()
    assert completed.published.prompt_file.is_file()
    assert completed.published.prompt_file.parent == (
        tmp_path / "prompts" / snapshot.manifest.created_at[:10] / "hardcore"
    )
    assert completed.published.prompt_file.name == (
        "3-view_hardcore_1_woman_1_man_0001.txt"
    )
    assert list((tmp_path / "prompts").rglob("*.json")) == []
    assert '"json_file"' not in (
        tmp_path / "runs" / snapshot.run_id / "manifest.json"
    ).read_text(encoding="utf-8")
    assert len(tuple((tmp_path / "runs" / snapshot.run_id / "attempts").iterdir())) == 2
    assert [item.run_id for item in listing.runs] == [snapshot.run_id]
    assert listing.runs[0].status == StoryRunStatus.COMPLETED

    (tmp_path / "runs" / snapshot.run_id / "themes" / "T001.json").write_text(
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
    request = make_story_request()
    snapshot = store.create(
        request,
        StoryRunSettings(provider=StoryProviderSettings(model="test-model")),
        resolve_story_rules(request),
    )
    theme_path = tmp_path / "runs" / snapshot.run_id / "themes" / "T001.json"
    theme_path.write_text(
        make_theme_batch(start=2).themes[0].model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(StoryStorageError, match="文件名与内容不匹配"):
        store.inspect(snapshot.run_id)


def test_story_run_store_rejects_changed_frozen_rules(tmp_path) -> None:
    request = make_story_request()
    rules = resolve_story_rules(request)
    store = LocalStoryRunStore(
        tmp_path / "runs",
        tmp_path / "prompts",
    )
    snapshot = store.create(
        request,
        StoryRunSettings(provider=StoryProviderSettings(model="test-model")),
        rules,
    )
    changed_rules = rules.model_copy(
        update={"themes": (*rules.themes, "Changed after run creation.")}
    )
    (tmp_path / "runs" / snapshot.run_id / "rules.json").write_text(
        changed_rules.model_dump_json(), encoding="utf-8"
    )

    with pytest.raises(StoryStorageError, match="rules.json 指纹不匹配"):
        store.inspect(snapshot.run_id)


def test_story_run_listing_ignores_prompt_pipeline_runs(tmp_path) -> None:
    runs = tmp_path / "runs"
    foreign = runs / "20260909T000000Z-abcdef01"
    foreign.mkdir(parents=True)
    (foreign / "request.json").write_text(
        '{"brief": "prompt pipeline request"}',
        encoding="utf-8",
    )

    listing = LocalStoryRunStore(runs).list_runs()

    assert listing.runs == ()
    assert listing.unreadable == ()
