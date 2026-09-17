"""Environment configuration for the standalone film prompt model."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from t2i_film_style_pipeline.errors import FilmStyleConfigurationError
from t2i_film_style_pipeline.prompt_provider import FilmPromptProviderSettings
from t2i_model_provider.backend import selected_backend_values

_ENV_FIELDS = {
    "OPENAI_BASE_URL": "base_url",
    "OPENAI_API_KEY_ENV": "api_key_env",
    "OPENAI_AUTH_MODE": "auth_mode",
    "OPENAI_MODEL": "model",
    "OPENAI_THINKING_MODE": "thinking_mode",
    "OPENAI_REASONING_EFFORT": "reasoning_effort",
    "OPENAI_TEMPERATURE": "temperature",
    "OPENAI_OUTPUT_TOKEN_LIMIT": "output_token_limit",
    "OPENAI_TIMEOUT_SECONDS": "timeout_seconds",
    "OPENAI_TRANSPORT_RETRIES": "transport_retries",
}


def load_film_prompt_provider_settings() -> FilmPromptProviderSettings:
    load_dotenv(Path.cwd() / ".env.film", override=False)
    values = selected_backend_values(_ENV_FIELDS)
    try:
        return FilmPromptProviderSettings.model_validate(values)
    except ValidationError as exc:
        raise FilmStyleConfigurationError(
            f"film prompt provider 配置无效：{exc}"
        ) from exc
