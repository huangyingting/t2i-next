from __future__ import annotations

import pytest

from t2i_prompt_pipeline.config import build_config
from t2i_prompt_pipeline.errors import ConfigurationError
from tests.factories import make_spec


def test_config_uses_explicit_run_policy_arguments(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_MODEL", "model-name")
    monkeypatch.setenv("T2I_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("T2I_THEME_BATCH_SIZE", "7")
    monkeypatch.setenv("T2I_GENERATION_RETRIES", "1")

    config = build_config(
        make_spec(),
        runs_directory=tmp_path / "runs",
        prompts_directory=tmp_path / "prompts",
        max_concurrency=3,
        theme_batch_size=7,
        generation_retries=1,
    )

    assert config.provider.model == "model-name"
    assert config.run_settings.max_concurrency == 3
    assert config.run_settings.theme_batch_size == 7
    assert config.run_settings.generation_retries == 1
    assert config.runs_directory == (tmp_path / "runs").resolve()
    assert config.prompts_directory == (tmp_path / "prompts").resolve()
    assert config.rules is not None


def test_config_defaults_to_benchmarked_concurrency(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_MODEL", "model-name")
    monkeypatch.setenv("T2I_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("T2I_THEME_BATCH_SIZE", "7")
    monkeypatch.setenv("T2I_GENERATION_RETRIES", "1")

    config = build_config(make_spec())

    assert config.run_settings.max_concurrency == 8
    assert config.run_settings.theme_batch_size == 5
    assert config.run_settings.generation_retries == 2


def test_provider_output_token_limit_uses_current_environment_key(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_MODEL", "model-name")
    monkeypatch.setenv("OPENAI_OUTPUT_TOKEN_LIMIT", "4096")
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "2048")

    config = build_config(make_spec())

    assert config.provider.output_token_limit == 4096
    assert config.run_settings.output_token_limit == 4096


def test_config_auto_loads_project_user_rules(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_MODEL", "model-name")
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "common.rules").write_text(
        "项目自定义规则\n",
        encoding="utf-8",
    )

    config = build_config(make_spec())

    assert config.rules is not None
    assert "项目自定义规则" in config.rules.foundation
    assert "项目自定义规则" in config.rules.themes
    assert "项目自定义规则" in config.rules.frames


def test_config_rejects_missing_explicit_rule_directory(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigurationError, match="用户规则目录不存在"):
        build_config(
            make_spec(),
            rules_directory=tmp_path / "missing",
        )
