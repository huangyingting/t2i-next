from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

import t2i_story_pipeline.cli as story_cli
from t2i_story_pipeline.cli import app
from t2i_story_pipeline.provider import StoryProviderSettings
from t2i_story_pipeline.run_store import (
    LocalStoryRunStore,
    StoryRunSettings,
)
from tests.story_factories import make_story_request


def test_story_cli_exposes_generate_command() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "generate" in result.stdout
    assert "resume" in result.stdout
    assert "runs" in result.stdout
    assert "从一段故事描述" in result.stdout


def test_story_generate_exposes_only_generation_controls() -> None:
    result = CliRunner().invoke(app, ["generate", "--help"])

    assert result.exit_code == 0
    assert "--themes" in result.stdout
    assert "--frames" in result.stdout
    assert "--female-count" in result.stdout
    assert "--male-count" in result.stdout
    assert "--concurrency" in result.stdout
    assert "--prompt-file" in result.stdout
    assert "--prompts-dir" in result.stdout
    assert "--output-dir" not in result.stdout
    assert "[default: 8]" in result.stdout
    assert "--content-level" in result.stdout
    assert "内容尺度" in result.stdout
    assert "[default: aesthetic]" in result.stdout
    assert "--max-revisions" not in result.stdout
    assert "--scenes" not in result.stdout
    assert "--shots" not in result.stdout


def test_story_generate_reads_story_description_from_prompt_file(
    tmp_path,
    monkeypatch,
) -> None:
    prompt_file = tmp_path / "story.txt"
    prompt_file.write_text(
        "\n1930年代秋夜，两个成年人在旧车站重逢。\n"
        "他们共同寻找遗失的行李。\n",
        encoding="utf-8",
    )
    captured = {}

    async def fake_generate(
        request,
        settings,
        *,
        concurrency,
        runs_directory,
        prompts_directory,
    ):
        captured["request"] = request
        captured["concurrency"] = concurrency
        captured["runs_directory"] = runs_directory
        captured["prompts_directory"] = prompts_directory
        return SimpleNamespace(
            run_id="test-run",
            published=SimpleNamespace(
                prompt_file=prompts_directory / "story.txt",
            ),
        )

    monkeypatch.setattr(
        story_cli,
        "load_story_provider_settings",
        lambda: object(),
    )
    monkeypatch.setattr(story_cli, "_generate", fake_generate)

    result = CliRunner().invoke(
        app,
        [
            "generate",
            "--prompt-file",
            str(prompt_file),
            "--female-count",
            "2",
            "--male-count",
            "1",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--prompts-dir",
            str(tmp_path / "prompts"),
        ],
    )

    assert result.exit_code == 0
    assert captured["request"].story == (
        "1930年代秋夜，两个成年人在旧车站重逢。\n"
        "他们共同寻找遗失的行李。"
    )
    assert captured["request"].female_count == 2
    assert captured["request"].male_count == 1
    assert captured["concurrency"] == 8
    assert captured["runs_directory"] == tmp_path / "runs"
    assert captured["prompts_directory"] == tmp_path / "prompts"
    assert "Run：test-run" in result.output


def test_story_generate_rejects_missing_story_input() -> None:
    result = CliRunner().invoke(app, ["generate"])

    assert result.exit_code != 0
    assert "故事描述或 --prompt-file" in result.output


def test_story_generate_rejects_story_and_prompt_file_together(
    tmp_path,
) -> None:
    prompt_file = tmp_path / "story.txt"
    prompt_file.write_text("另一个故事描述", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["generate", "命令行故事描述", "--prompt-file", str(prompt_file)],
    )

    assert result.exit_code != 0
    assert "不能同时提供" in result.output


def test_story_generate_rejects_empty_prompt_file(tmp_path) -> None:
    prompt_file = tmp_path / "empty.txt"
    prompt_file.write_text(" \n\t", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["generate", "--prompt-file", str(prompt_file)],
    )

    assert result.exit_code != 0
    assert "不能为空" in result.output


def test_story_generate_rejects_missing_prompt_file(tmp_path) -> None:
    result = CliRunner().invoke(
        app,
        ["generate", "--prompt-file", str(tmp_path / "missing.txt")],
    )

    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_story_generate_rejects_non_utf8_prompt_file(tmp_path) -> None:
    prompt_file = tmp_path / "invalid.txt"
    prompt_file.write_bytes(b"\xff\xfe")

    result = CliRunner().invoke(
        app,
        ["generate", "--prompt-file", str(prompt_file)],
    )

    assert result.exit_code != 0
    assert "UTF-8" in result.output


def test_story_resume_uses_frozen_run_settings(tmp_path, monkeypatch) -> None:
    provider = StoryProviderSettings(model="test-model")
    store = LocalStoryRunStore(
        tmp_path / "runs",
        tmp_path / "prompts",
    )
    snapshot = store.create(
        make_story_request(),
        StoryRunSettings(provider=provider, concurrency=3),
    )
    captured = {}

    async def fake_resume(run_id, current_provider, settings, current_store):
        captured["run_id"] = run_id
        captured["provider"] = current_provider
        captured["settings"] = settings
        captured["store"] = current_store
        return SimpleNamespace(
            run_id=run_id,
            published=SimpleNamespace(
                prompt_file=tmp_path / "prompts" / "story.txt",
            ),
        )

    monkeypatch.setattr(
        story_cli,
        "load_story_provider_settings",
        lambda: provider,
    )
    monkeypatch.setattr(story_cli, "_resume", fake_resume)

    result = CliRunner().invoke(
        app,
        [
            "resume",
            snapshot.run_id,
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 0
    assert captured["run_id"] == snapshot.run_id
    assert captured["settings"].concurrency == 3
    assert captured["provider"] == provider
    assert isinstance(captured["store"], LocalStoryRunStore)


def test_story_runs_lists_resumable_command(tmp_path) -> None:
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

    result = CliRunner().invoke(
        app,
        ["runs", "--runs-dir", str(tmp_path / "runs")],
    )

    assert result.exit_code == 0
    assert snapshot.run_id in result.output
    assert f"t2i-story resume {snapshot.run_id}" in result.output
