from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

import t2i_film_style_pipeline.cli as film_style_cli
from t2i_film_style_pipeline.cli import app


def test_film_style_cli_exposes_generate_command() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "generate" in result.stdout
    assert "具体作品集合" in result.stdout


def test_generate_compiles_repeated_work_options(tmp_path, monkeypatch) -> None:
    brief = tmp_path / "base.txt"
    brief.write_text("BRIEF\n\nCreate original stills.", encoding="utf-8")
    captured = {}

    async def fake_generate(
        request,
        *,
        source_stem,
        settings,
        runs_directory,
        output_directory,
    ):
        captured["request"] = request
        captured["source_stem"] = source_stem
        captured["runs_directory"] = runs_directory
        captured["output_directory"] = output_directory
        return SimpleNamespace(
            result=SimpleNamespace(run_id="film-run"),
            published=SimpleNamespace(
                profile_file=runs_directory / "film-run" / "profile.json",
                prompt_file=output_directory / "compiled.txt",
            ),
        )

    monkeypatch.setattr(
        film_style_cli,
        "load_film_style_provider_settings",
        lambda: object(),
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
            "--brief-file",
            str(brief),
            "--output-dir",
            str(tmp_path / "outputs"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 0
    assert captured["request"].director == "张艺谋"
    assert [work.year for work in captured["request"].works] == [2002, 2004]
    assert captured["source_stem"] == "base"
    assert "Run：film-run" in result.output


def test_generate_rejects_legacy_brief(tmp_path) -> None:
    brief = tmp_path / "legacy.txt"
    brief.write_text("not a current Story Description", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "generate",
            "Director",
            "--work",
            "Film (2000)",
            "--brief-file",
            str(brief),
        ],
    )

    assert result.exit_code == 1
    assert "base brief must start" in result.output
