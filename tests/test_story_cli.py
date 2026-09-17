from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import t2i_story_pipeline.cli as story_cli
from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.cli import app
from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.models import FrameQualityPolicy, StoryQualityPolicy
from t2i_story_pipeline.provider import StoryProviderSettings
from t2i_story_pipeline.run_store import (
    LocalStoryRunStore,
    StoryRunSettings,
)
from tests.story_factories import (
    make_frame_sequence,
    make_story_request,
    make_story_result,
    make_theme_batch,
)
from tests.test_story_studio import FakeStoryModel


@pytest.fixture(autouse=True)
def fake_provider_settings(monkeypatch):
    monkeypatch.setattr(
        story_cli,
        "load_story_provider_settings",
        lambda: StoryProviderSettings(model="test-model"),
    )


def completed_run(directory, run_id="test-run"):
    return SimpleNamespace(
        run_id=run_id,
        published=SimpleNamespace(prompt_file=directory / "story.txt"),
        result=make_story_result(),
        result_file=directory / "result.json",
    )


def test_story_settings_reuse_shared_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://shared.example/v1")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.35")

    settings = load_story_provider_settings()

    assert settings.model == "shared-model"
    assert settings.base_url == "https://shared.example/v1"
    assert settings.temperature == 0.35


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
    assert "--input" in result.stdout
    assert "--prompt-file" not in result.stdout
    assert "--theme-quality-mode" in result.stdout
    assert "--frame-quality-mode" in result.stdout
    assert "--theme-batch-size" in result.stdout
    assert "--theme-output-tokens" in result.stdout
    assert "--frame-output-tokens" in result.stdout
    assert "--quality-mode" not in result.stdout
    assert "--generation-retries" in result.stdout
    assert "--prompts-dir" in result.stdout
    assert "--rules-dir" in result.stdout
    assert "story-inputs/rules/" in result.stdout
    assert "--output-dir" not in result.stdout
    assert "--content-level" in result.stdout
    assert "内容尺度" in result.stdout
    assert "aesthetic" in result.stdout
    assert "--max-revisions" not in result.stdout
    assert "--scenes" not in result.stdout
    assert "--shots" not in result.stdout


def test_story_generate_reads_story_document(
    tmp_path,
    monkeypatch,
) -> None:
    prompt_file = tmp_path / "renamed.yaml"
    prompt_file.write_text(
        "id: story\n"
        "description: |\n"
        "  1930年代秋夜，两个成年人在旧车站重逢。\n"
        "  他们共同寻找遗失的行李。\n"
        "generation:\n"
        "  theme_count: 7\n"
        "  frames_per_theme: 3\n"
        "  output_language: english\n"
        "  cast: {female_count: 1, male_count: 2}\n"
        "runtime:\n"
        "  concurrency: 3\n"
        "  generation_retries: 0\n"
        "  theme_batch_size: 3\n"
        "  theme_output_tokens: 12000\n"
        "  frame_output_tokens: 20000\n"
        "authoring:\n"
        "  themes: [Custom theme rule.]\n"
        "  frames: [Custom frame rule.]\n"
        "validation:\n"
        "  themes:\n"
        "    mode: enforce\n"
        "    checks: [{type: forbidden_text, field: title, values: [UNWANTED]}]\n"
        "  frames:\n"
        "    mode: report\n"
        "    checks:\n"
        "      - type: camera_evidence\n",
        encoding="utf-8",
    )
    captured = {}

    async def fake_generate(
        request,
        settings,
        rules,
        *,
        runs_directory,
        prompts_directory,
    ):
        captured["request"] = request
        captured["rules"] = rules
        captured["settings"] = settings
        captured["runs_directory"] = runs_directory
        captured["prompts_directory"] = prompts_directory
        return completed_run(prompts_directory)

    monkeypatch.setattr(story_cli, "_generate", fake_generate)

    result = CliRunner().invoke(
        app,
        [
            "generate",
            "--input",
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
        "1930年代秋夜，两个成年人在旧车站重逢。\n他们共同寻找遗失的行李。"
    )
    assert captured["request"].female_count == 2
    assert captured["request"].male_count == 1
    assert captured["request"].source_prompt_stem == "story"
    assert "The Story Description is authoritative" in "\n".join(
        captured["rules"].themes
    )
    assert captured["request"].theme_count == 7
    assert captured["request"].frames_per_theme == 3
    assert captured["request"].output_language == "english"
    assert captured["settings"].concurrency == 3
    assert captured["settings"].generation_retries == 0
    assert captured["settings"].theme_batch_size == 3
    assert captured["settings"].theme_output_tokens == 12000
    assert captured["settings"].frame_output_tokens == 20000
    assert captured["settings"].quality.themes.mode == "enforce"
    assert captured["settings"].quality.frames.mode == "report"
    assert captured["settings"].quality.frames.checks[0].type == "camera_evidence"
    assert "Custom theme rule." in captured["rules"].themes
    assert "Custom theme rule." not in captured["rules"].frames
    assert "Custom frame rule." in captured["rules"].frames
    assert captured["runs_directory"] == tmp_path / "runs"
    assert captured["prompts_directory"] == tmp_path / "prompts"
    assert "Run：test-run" in result.output


def test_story_generate_rejects_missing_story_input() -> None:
    result = CliRunner().invoke(app, ["generate"])

    assert result.exit_code != 0
    assert "故事描述或 --input" in result.output


def test_story_generate_direct_input_has_no_source_prompt_stem(
    monkeypatch,
) -> None:
    captured = {}

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
        return completed_run(prompts_directory)

    monkeypatch.setattr(story_cli, "_generate", fake_generate)

    result = CliRunner().invoke(app, ["generate", "直接输入的故事"])

    assert result.exit_code == 0
    assert captured["request"].source_prompt_stem is None
    assert captured["request"].theme_count == 1
    assert captured["request"].frames_per_theme == 6
    assert captured["request"].content_level == "aesthetic"
    assert captured["settings"].concurrency == 8
    assert captured["settings"].generation_retries == 2
    assert captured["settings"].quality.frames.checks == ()
    assert captured["settings"].quality.themes.checks == ()
    assert "skipped" in result.output


def test_story_generate_loads_custom_rules(tmp_path, monkeypatch) -> None:
    rules_dir = tmp_path / "custom-story-rules"
    rules_dir.mkdir()
    (rules_dir / "common.rules").write_text(
        "Custom project-wide story rule.\n",
        encoding="utf-8",
    )
    captured = {}

    async def fake_generate(
        request,
        settings,
        rules,
        *,
        runs_directory,
        prompts_directory,
    ):
        captured["rules"] = rules
        return completed_run(prompts_directory)

    monkeypatch.setattr(story_cli, "_generate", fake_generate)

    result = CliRunner().invoke(
        app,
        [
            "generate",
            "直接输入的故事",
            "--rules-dir",
            str(rules_dir),
            "--prompts-dir",
            str(tmp_path / "prompts"),
        ],
    )

    assert result.exit_code == 0
    assert "Custom project-wide story rule." in captured["rules"].themes
    assert "Custom project-wide story rule." in captured["rules"].frames


def test_story_generate_discovers_rules_inside_story_inputs(
    tmp_path,
    monkeypatch,
) -> None:
    rules_dir = tmp_path / "story-inputs" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "common.rules").write_text(
        "Shared story-input rule.\n",
        encoding="utf-8",
    )
    captured = {}

    async def fake_generate(
        request,
        settings,
        rules,
        *,
        runs_directory,
        prompts_directory,
    ):
        captured["rules"] = rules
        return completed_run(prompts_directory)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(story_cli, "_generate", fake_generate)

    result = CliRunner().invoke(app, ["generate", "直接输入的故事"])

    assert result.exit_code == 0
    assert "Shared story-input rule." in captured["rules"].themes
    assert "Shared story-input rule." in captured["rules"].frames


def test_story_generate_rejects_story_and_document_together(
    tmp_path,
) -> None:
    prompt_file = tmp_path / "story.yaml"
    prompt_file.write_text("id: story\ndescription: 另一个故事描述", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["generate", "命令行故事描述", "--input", str(prompt_file)],
    )

    assert result.exit_code != 0
    assert "不能同时提供" in result.output


def test_story_generate_rejects_empty_document(tmp_path) -> None:
    prompt_file = tmp_path / "empty.yaml"
    prompt_file.write_text(" \n\t", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["generate", "--input", str(prompt_file)],
    )

    assert result.exit_code != 0
    assert "不能为空" in result.output


def test_story_generate_rejects_missing_document(tmp_path) -> None:
    result = CliRunner().invoke(
        app,
        ["generate", "--input", str(tmp_path / "missing.yaml")],
    )

    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_story_generate_rejects_non_utf8_document(tmp_path) -> None:
    prompt_file = tmp_path / "invalid.yaml"
    prompt_file.write_bytes(b"\xff\xfe")

    result = CliRunner().invoke(
        app,
        ["generate", "--input", str(prompt_file)],
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
        (request := make_story_request()),
        StoryRunSettings(
            provider=provider,
            concurrency=3,
            quality=StoryQualityPolicy(
                frames=FrameQualityPolicy(
                    mode="enforce", checks=[{"type": "camera_evidence"}]
                )
            ),
        ),
        resolve_story_rules(request),
    )
    captured = {}

    async def fake_resume(run_id, current_provider, settings, current_store):
        captured["run_id"] = run_id
        captured["provider"] = current_provider
        captured["settings"] = settings
        captured["store"] = current_store
        return completed_run(tmp_path / "prompts", run_id)

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
    assert captured["settings"].quality.frames.mode == "enforce"
    assert captured["provider"] == provider
    assert isinstance(captured["store"], LocalStoryRunStore)


def test_story_runs_lists_resumable_command(tmp_path) -> None:
    store = LocalStoryRunStore(
        tmp_path / "runs",
        tmp_path / "prompts",
    )
    snapshot = store.create(
        (request := make_story_request()),
        StoryRunSettings(provider=StoryProviderSettings(model="test-model")),
        resolve_story_rules(request),
    )

    result = CliRunner().invoke(
        app,
        ["runs", "--runs-dir", str(tmp_path / "runs")],
    )

    assert result.exit_code == 0
    assert snapshot.run_id in result.output
    assert f"t2i-story resume {snapshot.run_id}" in result.output


def test_explicit_cli_options_override_document_and_preserve_zero(
    tmp_path, monkeypatch
):
    path = tmp_path / "story.yaml"
    path.write_text(
        "id: story\ndescription: Story.\n"
        "generation:\n"
        "  theme_count: 7\n"
        "  frames_per_theme: 3\n"
        "  content_level: erotic\n"
        "  output_language: english\n"
        "  cast: {female_count: 2, male_count: 1}\n"
        "runtime:\n"
        "  concurrency: 3\n"
        "  generation_retries: 2\n"
        "  theme_batch_size: 4\n"
        "  theme_output_tokens: 12000\n"
        "  frame_output_tokens: 20000\n"
        "validation:\n"
        "  themes:\n"
        "    mode: enforce\n"
        "    checks: [{type: required_text, field: style, values: [rain]}]\n"
        "  frames:\n"
        "    mode: enforce\n"
        "    checks: [{type: camera_evidence}]\n",
        encoding="utf-8",
    )
    captured = {}

    async def fake_generate(request, settings, rules, **kwargs):
        captured["request"] = request
        captured["settings"] = settings
        return completed_run(tmp_path)

    monkeypatch.setattr(story_cli, "_generate", fake_generate)
    result = CliRunner().invoke(
        app,
        [
            "generate",
            "--input",
            str(path),
            "--themes",
            "1",
            "--frames",
            "6",
            "--female-count",
            "0",
            "--content-level",
            "aesthetic",
            "--language",
            "chinese",
            "--concurrency",
            "8",
            "--generation-retries",
            "0",
            "--frame-quality-mode",
            "off",
            "--theme-quality-mode",
            "report",
            "--theme-batch-size",
            "2",
            "--theme-output-tokens",
            "9000",
            "--frame-output-tokens",
            "18000",
        ],
    )
    assert result.exit_code == 0, result.output
    request = captured["request"]
    assert request.theme_count == 1
    assert request.frames_per_theme == 6
    assert request.female_count == 0
    assert request.male_count == 1
    assert request.content_level == "aesthetic"
    assert request.output_language == "chinese"
    assert captured["settings"].concurrency == 8
    assert captured["settings"].generation_retries == 0
    assert captured["settings"].theme_batch_size == 2
    assert captured["settings"].theme_output_tokens == 9000
    assert captured["settings"].frame_output_tokens == 18000
    assert captured["settings"].quality.themes.mode == "report"
    assert captured["settings"].quality.themes.checks[0].field == "style"
    assert captured["settings"].quality.frames.mode == "off"
    assert captured["settings"].quality.frames.checks[0].type == "camera_evidence"


def test_invalid_document_fails_before_provider_configuration(tmp_path, monkeypatch):
    path = tmp_path / "story.yaml"
    path.write_text("id: story\ndescription: Story.\nunknown: 1", encoding="utf-8")

    def fail_if_provider_loaded():
        pytest.fail("invalid document must not reach provider configuration")

    monkeypatch.setattr(
        story_cli, "load_story_provider_settings", fail_if_provider_loaded
    )
    result = CliRunner().invoke(app, ["generate", "--input", str(path)])
    assert result.exit_code == 2
    assert "unknown" in result.output


def test_resume_freezes_document_rules_and_quality_without_reading_source(
    tmp_path, monkeypatch
):
    path = tmp_path / "source.yaml"
    path.write_text(
        "id: stable-name\ndescription: An old station.\n"
        "generation: {frames_per_theme: 1}\n"
        "runtime:\n"
        "  generation_retries: 0\n"
        "  theme_batch_size: 1\n"
        "  theme_output_tokens: 512\n"
        "  frame_output_tokens: 1024\n"
        "authoring:\n  frames: [Keep the station clock visible.]\n"
        "validation:\n"
        "  themes:\n"
        "    mode: enforce\n"
        "    checks: [{type: forbidden_text, field: title, values: [UNWANTED]}]\n"
        "  frames:\n"
        "    mode: enforce\n"
        "    checks: [{type: required_text, values: [station clock]}]\n",
        encoding="utf-8",
    )
    model = FakeStoryModel([make_theme_batch(), make_frame_sequence(frame_count=1)])

    @asynccontextmanager
    async def fake_model(_settings):
        yield model

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(story_cli, "story_model", fake_model)
    result = CliRunner().invoke(app, ["generate", "--input", str(path)])
    assert result.exit_code == 1, result.output
    store = LocalStoryRunStore(tmp_path / "runs")
    run_id = store.list_runs().runs[0].run_id
    snapshot = store.inspect(run_id)
    assert snapshot.request.source_prompt_stem == "stable-name"
    assert snapshot.manifest.settings.quality.frames.mode == "enforce"
    assert snapshot.manifest.settings.quality.themes.mode == "enforce"
    assert snapshot.manifest.settings.theme_batch_size == 1
    assert snapshot.manifest.settings.theme_output_tokens == 512
    assert snapshot.manifest.settings.frame_output_tokens == 1024
    assert model.max_output_tokens == [512, 1024]
    assert snapshot.manifest.settings.generation_retries == 0
    assert "Keep the station clock visible." in snapshot.rules.frames

    path.unlink()
    failed_again = FakeStoryModel([make_frame_sequence(frame_count=1)])
    model = failed_again
    result = CliRunner().invoke(app, ["resume", run_id])
    assert result.exit_code == 1, result.output
    assert len(failed_again.stages) == 1
    assert failed_again.max_output_tokens == [1024]
    assert "station clock" in failed_again.messages[0][-1].content
    assert "Keep the station clock visible." in failed_again.messages[0][0].content

    sequence = make_frame_sequence(frame_count=1)
    sequence.frames[0].prose += " A station clock."
    model = FakeStoryModel([sequence])
    result = CliRunner().invoke(app, ["resume", run_id])
    assert result.exit_code == 0, result.output
    assert "passed" in result.output
    completed = store.inspect(run_id).completed
    assert completed is not None
    assert completed.result.request.story == "An old station."
    assert completed.result.quality.frames.mode == "enforce"
    assert completed.result.quality.themes.mode == "enforce"
    assert completed.published.prompt_file.name.startswith("stable-name_")
    result = CliRunner().invoke(app, ["resume", run_id])
    assert result.exit_code == 0, result.output
    assert len(model.stages) == 1
    assert model.max_output_tokens == [1024]


def test_report_mode_publishes_plain_prose_and_displays_quality_warnings(
    tmp_path, monkeypatch
):
    path = tmp_path / "report.yaml"
    path.write_text(
        "id: report\ndescription: An old station.\n"
        "generation: {frames_per_theme: 1}\n"
        "validation:\n"
        "  frames:\n"
        "    mode: report\n"
        "    checks: [{type: required_text, values: [station clock]}]\n",
        encoding="utf-8",
    )
    sequence = make_frame_sequence(frame_count=1)
    model = FakeStoryModel([make_theme_batch(), sequence])

    @asynccontextmanager
    async def fake_model(_settings):
        yield model

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(story_cli, "story_model", fake_model)
    result = CliRunner().invoke(app, ["generate", "--input", str(path)])
    assert result.exit_code == 0, result.output
    assert "warnings" in result.output
    assert "1 条质量告警" in result.output
    assert "station clock" in result.output
    assert len(model.stages) == 2
    store = LocalStoryRunStore(tmp_path / "runs")
    completed = store.inspect(store.list_runs().runs[0].run_id).completed
    assert completed is not None
    assert completed.published.prompt_file.read_text(encoding="utf-8").strip() == (
        sequence.frames[0].prose
    )
    assert completed.result.quality.issues[0].check == "required_text"


@pytest.mark.parametrize(
    "options",
    [
        ["--theme-batch-size", "0"],
        ["--theme-batch-size", "11"],
        ["--theme-output-tokens", "511"],
        ["--frame-output-tokens", "65537"],
        ["--theme-quality-mode", "unknown"],
        ["--quality-mode", "off"],
    ],
)
def test_invalid_execution_options_fail_before_provider_loading(monkeypatch, options):
    def unexpected_provider_load():
        pytest.fail("invalid CLI options must not load a provider")

    monkeypatch.setattr(
        story_cli,
        "load_story_provider_settings",
        unexpected_provider_load,
    )
    result = CliRunner().invoke(app, ["generate", "An old station.", *options])
    assert result.exit_code == 2
