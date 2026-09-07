from __future__ import annotations

from typer.testing import CliRunner

from t2i_story_pipeline.cli import app


def test_story_cli_exposes_generate_command() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "generate" in result.stdout
    assert "从一段故事描述" in result.stdout


def test_story_generate_exposes_bounded_revision_control() -> None:
    result = CliRunner().invoke(app, ["generate", "--help"])

    assert result.exit_code == 0
    assert "--max-revisions" in result.stdout
    assert "--themes" in result.stdout
    assert "--frames" in result.stdout
    assert "--scenes" not in result.stdout
    assert "--shots" not in result.stdout
