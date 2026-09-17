from __future__ import annotations

from types import SimpleNamespace

from typer.main import get_command
from typer.testing import CliRunner

import t2i_film_style_pipeline.cli as film_style_cli
from t2i_film_style_pipeline.cli import app
from t2i_film_style_pipeline.prompt_provider import FilmPromptProviderSettings
from t2i_film_style_pipeline.provider import FilmStyleProviderSettings


def test_film_style_cli_exposes_generate_command() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "generate" in result.stdout
    assert "resume" in result.stdout
    assert "具体作品集合" in result.stdout


def test_generate_defaults_semantic_validation_off() -> None:
    command = get_command(app).commands["generate"]
    defaults = {parameter.name: parameter.default for parameter in command.params}

    assert defaults["validate_themes"] is False
    assert defaults["validate_frames"] is False
    assert defaults["theme_batch_size"] == 10


def test_generate_compiles_repeated_work_options(tmp_path, monkeypatch) -> None:
    captured = {}
    original_resolve_rules = film_style_cli.resolve_film_style_rules

    def capture_rules(request, *, user_directory=None):
        captured["rules_user_directory"] = user_directory
        return original_resolve_rules(
            request,
            user_directory=user_directory,
        )

    async def fake_generate(
        request,
        settings,
        rules,
        *,
        runs_directory,
        prompts_directory,
    ):
        captured["request"] = request
        captured["settings"] = settings
        captured["rules"] = rules
        captured["runs_directory"] = runs_directory
        captured["prompts_directory"] = prompts_directory
        return SimpleNamespace(
            run_id="film-run",
            profile_file=runs_directory / "film-run" / "profile.json",
            compiled_context_file=runs_directory / "film-run" / "compiled-context.txt",
            prompt_file=prompts_directory / "prompts.txt",
        )

    monkeypatch.setattr(
        film_style_cli,
        "load_film_style_provider_settings",
        lambda: FilmStyleProviderSettings(model="test-model"),
    )
    monkeypatch.setattr(
        film_style_cli,
        "load_film_prompt_provider_settings",
        lambda: FilmPromptProviderSettings(model="test-model"),
    )
    monkeypatch.setattr(
        film_style_cli,
        "resolve_film_style_rules",
        capture_rules,
    )
    monkeypatch.setattr(film_style_cli, "_generate", fake_generate)

    result = CliRunner().invoke(
        app,
        [
            "generate",
            "张艺谋",
            "--work",
            "英雄 (2002)",
            "--work",
            "十面埋伏 (2004)",
            "--scene",
            "只生成雨夜室内场景。",
            "--filename-stem",
            "Zhang_Yimou",
            "--themes",
            "4",
            "--frames",
            "1",
            "--theme-batch-size",
            "3",
            "--validate-themes",
            "--validate-frames",
            "--prompts-dir",
            str(tmp_path / "prompts"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 0
    assert captured["request"].film_style.director == "张艺谋"
    assert [
        work.year for work in captured["request"].film_style.works
    ] == [2002, 2004]
    assert captured["request"].scene_direction == "只生成雨夜室内场景。"
    assert captured["request"].output_filename_stem == "Zhang_Yimou"
    assert captured["request"].theme_count == 4
    assert captured["request"].frames_per_theme == 1
    assert captured["settings"].prompt.theme_batch_size == 3
    assert captured["settings"].prompt.theme_output_tokens == 12000
    assert captured["settings"].validate_themes is True
    assert captured["settings"].validate_frames is True
    assert any(
        "每个画面都是完全独立的图像提示词" in rule
        for rule in captured["rules"].frames
    )
    assert captured["rules_user_directory"] is None
    assert captured["prompts_directory"] == tmp_path / "prompts"
    assert "Run：film-run" in result.output
    assert "电影提示词：" in result.output


def test_generate_no_longer_accepts_brief_file() -> None:
    result = CliRunner().invoke(
        app,
        [
            "generate",
            "Director",
            "--work",
            "Film (2000)",
            "--brief-file",
            "story-inputs/film.txt",
        ],
    )

    assert result.exit_code == 2
    assert "No such option: --brief-file" in result.output


def test_generate_help_exposes_scene_not_intermediate_output() -> None:
    result = CliRunner().invoke(app, ["generate", "--help"])

    assert result.exit_code == 0
    assert "--scene" in result.output
    assert "--brief-file" not in result.output
    assert "--output-dir" not in result.output
    assert "可选 film-style" in result.output
    assert "story-inputs/rules/" not in result.output
