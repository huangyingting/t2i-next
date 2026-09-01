from __future__ import annotations

import json
from pathlib import Path

import pytest

from t2i_prompt_pipeline.errors import RunNotFoundError, RunStoreError
from t2i_prompt_pipeline.models import (
    AttemptOutcome,
    ContentLevel,
    GenerationAttempt,
    GenerationResult,
    GenerationStage,
    PromptBook,
    RunStatus,
    ThemeBook,
    ThemeSimilarityRejection,
    ThemeSimilarityReport,
    ThemeSimilaritySettings,
    ThemeSimilarityState,
    TokenUsage,
)
from t2i_prompt_pipeline.renderers import render_book
from t2i_prompt_pipeline.store import LocalRunStore
from tests.factories import (
    make_foundation,
    make_frame_batch,
    make_rules,
    make_settings,
    make_spec,
    make_themes,
)


def test_local_store_checkpoints_and_completes_idempotently(
    tmp_path,
) -> None:
    spec = make_spec(frames_per_theme=2)
    foundation = make_foundation()
    theme = make_themes(spec)[0]
    frames = make_frame_batch(spec, theme).frames
    runs = tmp_path / "runs"
    prompts = tmp_path / "prompts"
    store = LocalRunStore(runs, prompts)

    created = store.create(spec, make_settings(), make_rules(spec))

    assert (runs / created.run_id / "request.json").is_file()
    assert store.inspect(created.run_id).themes == {}

    store.checkpoint(created.run_id, foundation)
    store.checkpoint(created.run_id, theme)
    for frame in frames:
        store.checkpoint(created.run_id, frame)

    snapshot = store.inspect(created.run_id)
    assert snapshot.foundation == foundation
    assert list(snapshot.themes) == ["T01"]
    assert sorted(snapshot.frames) == ["T01-F01", "T01-F02"]

    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[ThemeBook(theme=theme, frames=frames)],
    )
    result = GenerationResult(
        spec=spec,
        book=book,
        prompts=render_book(book, spec.output_language),
    )
    first = store.complete(created.run_id, result)
    second = store.complete(created.run_id, result)

    assert first.prompt_file == second.prompt_file
    prompt_path = (
        prompts / "aesthetic" / "quiet_cafe_conversation_0001.txt"
    )
    assert first.prompt_file == str(prompt_path)
    lines = prompt_path.read_text().splitlines()
    assert len(lines) == 2
    assert all(lines)
    assert not any(line.startswith("[") for line in lines)
    assert not any("T01-C" in line for line in lines)
    assert len(list(prompts.rglob("*.txt"))) == 1

    reopened = store.inspect(created.run_id)
    assert reopened.completed is not None
    assert reopened.manifest.status == RunStatus.COMPLETED
    manifest = json.loads(
        (runs / created.run_id / "manifest.json").read_text()
    )
    assert manifest["prompt_file"] == str(prompt_path)
    foundation_payload = json.loads(
        (runs / created.run_id / "foundation.json").read_text()
    )
    book_payload = json.loads((runs / created.run_id / "book.json").read_text())
    assert foundation_payload["style_constraints"] == (
        foundation.style_constraints.model_dump(mode="json")
    )
    assert "style" not in foundation_payload
    assert book_payload["themes"][0]["theme"]["style"] == theme.style


def test_local_store_persists_theme_similarity_report(tmp_path) -> None:
    spec = make_spec(theme_count=2)
    settings = make_settings(
        theme_similarity=ThemeSimilaritySettings(model="embedding-model")
    )
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")
    snapshot = store.create(spec, settings, make_rules(spec))
    report = ThemeSimilarityReport(
        model="embedding-model",
        scene_threshold=0.92,
        style_threshold=0.92,
        input_count=4,
        pairs=[],
        usage=TokenUsage(prompt_tokens=10, total_tokens=10),
    )

    store.record_theme_similarity(snapshot.run_id, report)

    reopened = LocalRunStore(runs).inspect(snapshot.run_id)
    assert reopened.theme_similarity_report == report
    assert (runs / snapshot.run_id / "theme-similarity.json").is_file()


def test_local_store_rejects_theme_and_dependent_checkpoints(tmp_path) -> None:
    spec = make_spec(theme_count=2)
    settings = make_settings(
        theme_similarity=ThemeSimilaritySettings(model="embedding-model")
    )
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")
    snapshot = store.create(spec, settings, make_rules(spec))
    foundation = make_foundation(spec)
    themes = make_themes(spec)
    store.checkpoint(snapshot.run_id, foundation)
    for theme in themes:
        store.checkpoint(snapshot.run_id, theme)
        for frame in make_frame_batch(spec, theme).frames:
            store.checkpoint(snapshot.run_id, frame)
    store.record_theme_similarity(
        snapshot.run_id,
        report := ThemeSimilarityReport(
            state=ThemeSimilarityState.REJECTION_PENDING,
            model="embedding-model",
            scene_threshold=0.86,
            style_threshold=0.815,
            input_count=4,
            pairs=[],
            regeneration_round=1,
            rejections=[
                ThemeSimilarityRejection(
                    rejected_theme_id="T02",
                    kept_theme_id="T01",
                    scene_similarity=0.9,
                    style_similarity=0.9,
                )
            ],
        ),
    )

    store.apply_theme_rejections(snapshot.run_id, report)
    store.apply_theme_rejections(snapshot.run_id, report)

    reopened = LocalRunStore(runs).inspect(snapshot.run_id)
    assert list(reopened.themes) == ["T01"]
    assert sorted(reopened.frames) == ["T01-F01"]
    assert reopened.theme_similarity_report is not None
    assert (
        reopened.theme_similarity_report.state
        == ThemeSimilarityState.REGENERATING
    )
    assert not (runs / snapshot.run_id / "themes" / "T02.json").exists()
    assert not list((runs / snapshot.run_id / "frames").glob("T02-F*.json"))

    store.clear_theme_similarity(snapshot.run_id)

    assert LocalRunStore(runs).inspect(
        snapshot.run_id
    ).theme_similarity_report is None


def test_local_store_appends_and_reloads_generation_attempts(tmp_path) -> None:
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")
    snapshot = store.create(make_spec(), make_settings(), make_rules(make_spec()))
    attempt = GenerationAttempt(
        operation_id="frame-attempt-1",
        occurred_at="2026-08-20T00:00:00+00:00",
        stage=GenerationStage.FRAMES,
        requested_ids=["T01-F01"],
        attempt=1,
        max_output_tokens=2048,
        outcome=AttemptOutcome.PARTIAL,
        accepted_ids=[],
        issues=["T01-F01 action 包含不可见描述：出画"],
        duration_ms=1250,
        usage=TokenUsage(
            prompt_tokens=100,
            completion_tokens=40,
            total_tokens=140,
        ),
    )

    store.record_attempt(snapshot.run_id, attempt)
    store.record_attempt(snapshot.run_id, attempt)

    assert (runs / snapshot.run_id / "attempts.jsonl").read_text().count("\n") == 1
    assert LocalRunStore(runs).attempts(snapshot.run_id) == (attempt,)


def test_attempt_journal_repairs_only_a_torn_trailing_record(tmp_path) -> None:
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")
    snapshot = store.create(make_spec(), make_settings(), make_rules(make_spec()))
    first = GenerationAttempt(
        occurred_at="2026-08-20T00:00:00+00:00",
        stage=GenerationStage.THEMES,
        requested_ids=["T01"],
        attempt=1,
        max_output_tokens=2048,
        outcome=AttemptOutcome.ACCEPTED,
        accepted_ids=["T01"],
        duration_ms=100,
    )
    second = first.model_copy(
        update={
            "occurred_at": "2026-08-20T00:01:00+00:00",
            "stage": GenerationStage.FRAMES,
            "requested_ids": ["T01-F01"],
            "accepted_ids": ["T01-F01"],
        }
    )
    store.record_attempt(snapshot.run_id, first)
    journal = runs / snapshot.run_id / "attempts.jsonl"
    with journal.open("a", encoding="utf-8") as handle:
        handle.write('{"occurred_at":')

    assert store.attempts(snapshot.run_id) == (first,)

    store.record_attempt(snapshot.run_id, second)
    assert store.attempts(snapshot.run_id) == (first, second)


def test_store_rejects_invalid_resume_path(tmp_path) -> None:
    store = LocalRunStore(tmp_path / "runs", tmp_path / "prompts")

    with pytest.raises(RunNotFoundError):
        store.inspect("../../etc")


def test_complete_reuses_prompt_path_persisted_before_reboot(
    tmp_path,
) -> None:
    spec = make_spec()
    foundation = make_foundation()
    theme = make_themes(spec)[0]
    frames = make_frame_batch(spec, theme).frames
    runs = tmp_path / "runs"
    prompts = tmp_path / "prompts"
    store = LocalRunStore(runs, prompts)
    snapshot = store.create(spec, make_settings(), make_rules(spec))
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[ThemeBook(theme=theme, frames=frames)],
    )
    result = GenerationResult(
        spec=spec,
        book=book,
        prompts=render_book(book, spec.output_language),
    )
    prompt_path = (
        prompts / "aesthetic" / "quiet_cafe_conversation_0001.txt"
    )
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("interrupted publication")
    manifest_path = runs / snapshot.run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["prompt_file"] = str(prompt_path)
    manifest_path.write_text(json.dumps(manifest))

    resumed_store = LocalRunStore(runs, tmp_path / "other-prompts")
    archived = resumed_store.complete(snapshot.run_id, result)

    assert archived.prompt_file == str(prompt_path)
    assert len(list(prompts.rglob("*.txt"))) == 1
    assert "interrupted publication" not in prompt_path.read_text()


def test_store_setup_errors_use_application_error_boundary(tmp_path) -> None:
    root_file = tmp_path / "not-a-directory"
    root_file.write_text("occupied")
    store = LocalRunStore(root_file, tmp_path / "prompts")

    with pytest.raises(RunStoreError):
        spec = make_spec()
        store.create(spec, make_settings(), make_rules(spec))


def test_store_freezes_rules_and_validates_their_fingerprint(tmp_path) -> None:
    spec = make_spec()
    rules = make_rules(spec)
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")

    created = store.create(spec, make_settings(), rules)
    reopened = store.inspect(created.run_id)
    run_directory = runs / created.run_id
    manifest = json.loads((run_directory / "manifest.json").read_text())

    assert reopened.rules == rules
    assert manifest["rules_fingerprint"] == rules.fingerprint()
    assert (run_directory / "rules.json").is_file()

    rule_payload = json.loads((run_directory / "rules.json").read_text())
    rule_payload["frames"].append("被篡改的规则")
    (run_directory / "rules.json").write_text(json.dumps(rule_payload))

    with pytest.raises(RunStoreError, match="指纹不匹配"):
        store.inspect(created.run_id)


def test_store_requires_current_rule_snapshot_and_matching_run_id(
    tmp_path,
) -> None:
    spec = make_spec()
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")

    missing_rules = store.create(spec, make_settings(), make_rules(spec))
    (runs / missing_rules.run_id / "rules.json").unlink()
    with pytest.raises(RunStoreError, match="checkpoint 损坏"):
        store.inspect(missing_rules.run_id)

    wrong_manifest = store.create(spec, make_settings(), make_rules(spec))
    manifest_path = runs / wrong_manifest.run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["run_id"] = "20000101T000000Z-deadbeef"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(RunStoreError, match="manifest run_id 不匹配"):
        store.inspect(wrong_manifest.run_id)

    mismatched_artifact = store.create(
        spec,
        make_settings(),
        make_rules(spec),
    )
    theme = make_themes(spec)[0].model_copy(update={"theme_id": "T02"})
    theme_path = runs / mismatched_artifact.run_id / "themes" / "T01.json"
    theme_path.write_text(theme.model_dump_json())
    with pytest.raises(RunStoreError, match="文件名与内容不匹配"):
        store.inspect(mismatched_artifact.run_id)

    invalid_graph = store.create(spec, make_settings(), make_rules(spec))
    valid_theme = make_themes(spec)[0]
    invalid_frame = make_frame_batch(spec, valid_theme).frames[0]
    invalid_frame.characters[0].character_id = "T02-C01"
    store.checkpoint(invalid_graph.run_id, make_foundation())
    store.checkpoint(invalid_graph.run_id, valid_theme)
    store.checkpoint(invalid_graph.run_id, invalid_frame)
    with pytest.raises(RunStoreError, match="人物 ID 重复或不属于 Theme"):
        store.inspect(invalid_graph.run_id)

    missing_foundation = store.create(
        spec,
        make_settings(),
        make_rules(spec),
    )
    store.checkpoint(missing_foundation.run_id, valid_theme)
    with pytest.raises(RunStoreError, match="缺少 Foundation checkpoint"):
        store.inspect(missing_foundation.run_id)


def test_store_rejects_legacy_style_checkpoint(tmp_path) -> None:
    spec = make_spec()
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")
    snapshot = store.create(spec, make_settings(), make_rules(spec))
    foundation_path = runs / snapshot.run_id / "foundation.json"
    foundation_path.write_text(
        json.dumps(
            {
                "semantic_name": "legacy_style",
                "style": {"description": "旧风格字段"},
            }
        )
    )

    with pytest.raises(RunStoreError, match="checkpoint 损坏"):
        store.inspect(snapshot.run_id)


def _publish_run(store: LocalRunStore, spec) -> str:
    foundation = make_foundation()
    theme = make_themes(spec)[0]
    frames = make_frame_batch(spec, theme).frames
    snapshot = store.create(spec, make_settings(), make_rules(spec))
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[ThemeBook(theme=theme, frames=frames)],
    )
    store.complete(
        snapshot.run_id,
        GenerationResult(
            spec=spec,
            book=book,
            prompts=render_book(book, spec.output_language),
        ),
    )
    return snapshot.run_id


def test_store_allocates_sequences_independently_by_content_level(
    tmp_path,
) -> None:
    prompts = tmp_path / "prompts"
    store = LocalRunStore(tmp_path / "runs", prompts)

    for content_level in ContentLevel:
        spec = make_spec().model_copy(
            update={"content_level": content_level}
        )
        run_id = _publish_run(store, spec)

        completed = store.inspect(run_id).completed
        assert completed is not None
        assert Path(completed.prompt_file) == (
            prompts
            / content_level.value
            / "quiet_cafe_conversation_0001.txt"
        )


def test_completed_inspect_does_not_revalidate_frozen_checkpoints(
    tmp_path,
    monkeypatch,
) -> None:
    store = LocalRunStore(tmp_path / "runs", tmp_path / "prompts")
    run_id = _publish_run(store, make_spec())

    def reject_current_contract(*_args, **_kwargs):
        raise AssertionError("completed checkpoints were revalidated")

    monkeypatch.setattr(
        "t2i_prompt_pipeline.store.normalize_checkpoint_graph",
        reject_current_contract,
    )

    snapshot = store.inspect(run_id)

    assert snapshot.completed is not None
    assert snapshot.themes == {
        item.theme.theme_id: item.theme
        for item in snapshot.completed.result.book.themes
    }


def test_list_runs_orders_by_creation_and_summarises_manifests(
    tmp_path,
) -> None:
    store = LocalRunStore(tmp_path / "runs", tmp_path / "prompts")
    spec = make_spec()
    completed_id = _publish_run(store, spec)
    failed_snapshot = store.create(spec, make_settings(), make_rules(spec))
    store.fail(failed_snapshot.run_id, "provider 返回 HTTP 500")

    listing = store.list_runs()

    assert listing.unreadable == ()
    assert [summary.run_id for summary in listing.runs] == [
        failed_snapshot.run_id,
        completed_id,
    ]
    newest, oldest = listing.runs
    assert newest.status == RunStatus.FAILED
    assert newest.error == "provider 返回 HTTP 500"
    assert newest.prompt_file is None
    assert newest.brief == spec.brief
    assert newest.theme_count == spec.theme_count
    assert oldest.status == RunStatus.COMPLETED
    assert oldest.prompt_file is not None


def test_list_runs_reports_unreadable_runs_instead_of_hiding_them(
    tmp_path,
) -> None:
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")
    healthy_id = _publish_run(store, make_spec())
    broken = runs / "20260101T000000Z-deadbeef"
    broken.mkdir()
    (broken / "manifest.json").write_text("{ not json", encoding="utf-8")

    listing = store.list_runs()

    assert [summary.run_id for summary in listing.runs] == [healthy_id]
    assert listing.unreadable == ("20260101T000000Z-deadbeef",)


def test_list_runs_ignores_absent_root_and_staging_directories(
    tmp_path,
) -> None:
    runs = tmp_path / "runs"
    assert LocalRunStore(runs).list_runs().runs == ()

    store = LocalRunStore(runs, tmp_path / "prompts")
    _publish_run(store, make_spec())
    (runs / ".20260101T000000Z-abcdef01-staging").mkdir()

    listing = store.list_runs()

    assert len(listing.runs) == 1
    assert listing.unreadable == ()


def test_store_without_prompts_root_refuses_to_create_but_still_completes(
    tmp_path,
) -> None:
    runs = tmp_path / "runs"
    prompts = tmp_path / "prompts"
    spec = make_spec()
    foundation = make_foundation()
    theme = make_themes(spec)[0]
    frames = make_frame_batch(spec, theme).frames
    snapshot = LocalRunStore(runs, prompts).create(
        spec,
        make_settings(),
        make_rules(spec),
    )
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[ThemeBook(theme=theme, frames=frames)],
    )
    result = GenerationResult(
        spec=spec,
        book=book,
        prompts=render_book(book, spec.output_language),
    )

    resume_store = LocalRunStore(runs)
    archived = resume_store.complete(snapshot.run_id, result)

    assert archived.prompt_file.startswith(str(prompts))
    with pytest.raises(RunStoreError):
        resume_store.create(spec, make_settings(), make_rules(spec))
