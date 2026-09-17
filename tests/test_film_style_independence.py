from __future__ import annotations

from pathlib import Path

from t2i_film_style_pipeline.config import load_film_style_provider_settings
from t2i_film_style_pipeline.prompt_config import (
    load_film_prompt_provider_settings,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FILM_PACKAGE = REPOSITORY_ROOT / "src" / "t2i_film_style_pipeline"
MODEL_ENVIRONMENT_KEYS = (
    "T2I_MODEL_BACKEND",
    "OPENAI_MODEL",
    "COPILOT_MODEL",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY_ENV",
    "OPENAI_AUTH_MODE",
    "OPENAI_THINKING_MODE",
    "OPENAI_REASONING_EFFORT",
    "OPENAI_TEMPERATURE",
    "OPENAI_OUTPUT_TOKEN_LIMIT",
    "OPENAI_TIMEOUT_SECONDS",
    "OPENAI_TRANSPORT_RETRIES",
    "COPILOT_REASONING_EFFORT",
    "COPILOT_OUTPUT_TOKEN_LIMIT",
    "COPILOT_TIMEOUT_SECONDS",
)


def test_film_runtime_has_no_story_pipeline_dependency() -> None:
    for path in FILM_PACKAGE.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "t2i_story_pipeline" not in source, path
        assert "story-runs" not in source, path
        assert "compiled-story" not in source, path


def test_film_configuration_reads_only_env_film(
    tmp_path,
    monkeypatch,
) -> None:
    for key in MODEL_ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text(
        "T2I_MODEL_BACKEND=openai\nOPENAI_MODEL=wrong-model\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.film").write_text(
        "T2I_MODEL_BACKEND=openai\nOPENAI_MODEL=film-model\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert load_film_style_provider_settings().model == "film-model"
    assert load_film_prompt_provider_settings().model == "film-model"
