"""Environment configuration for film-style profiling."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from t2i_film_style_pipeline.errors import FilmStyleConfigurationError
from t2i_film_style_pipeline.provider import FilmStyleProviderSettings

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


def load_film_style_provider_settings() -> FilmStyleProviderSettings:
    load_dotenv(Path.cwd() / ".env", override=False)
    values = {
        field_name: value
        for environment_name, field_name in _ENV_FIELDS.items()
        if (value := os.environ.get(environment_name)) is not None
    }
    try:
        return FilmStyleProviderSettings.model_validate(values)
    except ValidationError as exc:
        raise FilmStyleConfigurationError(
            f"invalid film-style model configuration: {exc}"
        ) from exc
