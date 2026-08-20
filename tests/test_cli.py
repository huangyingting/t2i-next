from __future__ import annotations

from typer.testing import CliRunner

from t2i_prompt_pipeline import cli
from t2i_prompt_pipeline.models import (
    AppConfig,
    ContentLevel,
    GenerationResult,
    OutputLanguage,
    PromptBook,
    ProviderSettings,
    RunStatus,
    ThemeBook,
)
from t2i_prompt_pipeline.renderers import render_book
from t2i_prompt_pipeline.store import InMemoryRunStore, LocalRunStore
from tests.factories import (
    make_foundation,
    make_frame_batch,
    make_rules,
    make_settings,
    make_spec,
    make_themes,
)


def test_generate_command_reports_batched_call_count(
    monkeypatch,
    tmp_path,
) -> None:
    spec = make_spec(theme_count=2, frames_per_theme=2)
    foundation = make_foundation()
    themes = make_themes(spec)
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[
            ThemeBook(
                theme=theme,
                frames=make_frame_batch(spec, theme).frames,
            )
            for theme in themes
        ],
    )
    generation_result = GenerationResult(
        spec=spec,
        book=book,
        prompts=render_book(book, spec.output_language),
    )
    settings = make_settings()
    memory = InMemoryRunStore()
    snapshot = memory.create(spec, settings, make_rules(spec))
    archived = memory.complete(snapshot.run_id, generation_result)
    config = AppConfig(
        spec=spec,
        provider=ProviderSettings(model="test"),
        runs_directory=tmp_path / "runs",
        prompts_directory=tmp_path / "prompts",
        run_settings=settings,
        rules=make_rules(spec),
    )
    captured = {}

    def fake_build_config(generated_spec, **kwargs):
        captured["spec"] = generated_spec
        captured["kwargs"] = kwargs
        return config

    monkeypatch.setattr(cli, "build_config", fake_build_config)

    async def fake_run(_config):
        return archived

    monkeypatch.setattr(cli, "_run", fake_run)

    result = CliRunner().invoke(
        cli.app,
        [
            "generate",
            "测试",
            "--theme-count",
            "2",
            "--frames-per-theme",
            "2",
            "--content-level",
            "hardcore",
            "--language",
            "english",
            "--rules-dir",
            str(tmp_path / "custom-rules"),
        ],
    )

    assert result.exit_code == 0
    assert "基础调用约 4 次" in result.output
    assert "缺失项会定向补全" in result.output
    assert "提示词：4" in result.output
    assert captured["spec"].content_level == ContentLevel.HARDCORE
    assert captured["spec"].output_language == OutputLanguage.ENGLISH
    assert captured["spec"].female_count is None
    assert captured["spec"].male_count is None
    assert captured["kwargs"]["rules_directory"] == (
        tmp_path / "custom-rules"
    )


def test_cli_exposes_generate_resume_and_runs_only() -> None:
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "generate" in result.output
    assert "resume" in result.output
    assert "runs" in result.output
    assert "probe" not in result.output
    assert "validate" not in result.output


def test_completed_resume_needs_no_provider_configuration(
    monkeypatch,
    tmp_path,
) -> None:
    spec = make_spec()
    foundation = make_foundation()
    theme = make_themes(spec)[0]
    frames = make_frame_batch(spec, theme).frames
    settings = make_settings()
    store = LocalRunStore(tmp_path / "runs", tmp_path / "prompts")
    snapshot = store.create(spec, settings, make_rules(spec))
    book = PromptBook(
        semantic_name=foundation.semantic_name,
        cast_plan=foundation.cast_plan,
        themes=[ThemeBook(theme=theme, frames=frames)],
    )
    generation_result = GenerationResult(
        spec=spec,
        book=book,
        prompts=render_book(book, spec.output_language),
    )
    store.complete(snapshot.run_id, generation_result)

    def fail_if_loaded():
        raise AssertionError("provider should not be loaded")

    monkeypatch.setattr(cli, "load_provider_settings", fail_if_loaded)
    result = CliRunner().invoke(
        cli.app,
        [
            "resume",
            snapshot.run_id,
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 0
    assert "生成完成" in result.output


def test_resume_rejects_smaller_live_token_cap_without_starting_run(
    monkeypatch,
    tmp_path,
) -> None:
    provider = ProviderSettings(
        model="test",
        output_token_limit=8192,
    )
    settings = make_settings(
        provider_signature=provider.signature(),
        output_token_limit=16384,
    )
    store = LocalRunStore(tmp_path / "runs", tmp_path / "prompts")
    spec = make_spec()
    snapshot = store.create(spec, settings, make_rules(spec))
    store.fail(snapshot.run_id, "interrupted")
    monkeypatch.setattr(cli, "load_provider_settings", lambda: provider)

    result = CliRunner().invoke(
        cli.app,
        [
            "resume",
            snapshot.run_id,
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 2
    assert "小于 run 所需硬上限" in result.output
    assert store.inspect(snapshot.run_id).manifest.status == RunStatus.FAILED


def _publish_local_run(store: LocalRunStore, spec) -> str:
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


def test_runs_command_lists_newest_first_with_resume_hint(tmp_path) -> None:
    runs = tmp_path / "runs"
    store = LocalRunStore(runs, tmp_path / "prompts")
    spec = make_spec()
    completed_id = _publish_local_run(store, spec)
    failed = store.create(spec, make_settings(), make_rules(spec))
    store.fail(failed.run_id, "provider 返回 HTTP 500")

    result = CliRunner().invoke(
        cli.app,
        ["runs", "--runs-dir", str(runs)],
    )

    assert result.exit_code == 0
    assert result.output.index(failed.run_id) < result.output.index(
        completed_id
    )
    assert "completed" in result.output
    assert "failed" in result.output
    assert "provider 返回 HTTP 500" in result.output
    assert f"resume {failed.run_id}" in result.output
    assert "quiet_cafe_conversation_0001.txt" in result.output


def test_runs_command_needs_no_provider_configuration(
    monkeypatch,
    tmp_path,
) -> None:
    runs = tmp_path / "runs"
    _publish_local_run(LocalRunStore(runs, tmp_path / "prompts"), make_spec())

    def fail_if_loaded():
        raise AssertionError("provider should not be loaded")

    monkeypatch.setattr(cli, "load_provider_settings", fail_if_loaded)
    result = CliRunner().invoke(cli.app, ["runs", "--runs-dir", str(runs)])

    assert result.exit_code == 0


def test_runs_command_reports_empty_and_unreadable_runs(tmp_path) -> None:
    runs = tmp_path / "runs"
    empty = CliRunner().invoke(cli.app, ["runs", "--runs-dir", str(runs)])

    assert empty.exit_code == 0
    assert "没有 run" in empty.output

    _publish_local_run(LocalRunStore(runs, tmp_path / "prompts"), make_spec())
    broken = runs / "20260101T000000Z-deadbeef"
    broken.mkdir()
    (broken / "manifest.json").write_text("{ not json", encoding="utf-8")

    result = CliRunner().invoke(cli.app, ["runs", "--runs-dir", str(runs)])

    assert result.exit_code == 0
    assert "20260101T000000Z-deadbeef" in result.output
