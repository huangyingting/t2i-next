"""Environment configuration for spatial prompt generation."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from t2i_spatial_pipeline.errors import SpatialConfigurationError
from t2i_spatial_pipeline.provider import SpatialProviderSettings

_ENV_FIELDS = {
    "SPATIAL_OPENAI_BASE_URL": "base_url",
    "SPATIAL_OPENAI_API_KEY_ENV": "api_key_env",
    "SPATIAL_OPENAI_AUTH_MODE": "auth_mode",
    "SPATIAL_OPENAI_MODEL": "model",
    "SPATIAL_OPENAI_THINKING_MODE": "thinking_mode",
    "SPATIAL_OPENAI_REASONING_EFFORT": "reasoning_effort",
    "SPATIAL_OPENAI_TEMPERATURE": "temperature",
    "SPATIAL_OPENAI_OUTPUT_TOKEN_LIMIT": "output_token_limit",
    "SPATIAL_OPENAI_TIMEOUT_SECONDS": "timeout_seconds",
    "SPATIAL_OPENAI_TRANSPORT_RETRIES": "transport_retries",
}

def load_spatial_provider_settings() -> SpatialProviderSettings:
    load_dotenv(Path.cwd() / ".env", override=False)
    values = {
        field_name: value
        for environment_name, field_name in _ENV_FIELDS.items()
        if (value := os.environ.get(environment_name)) is not None
    }
    try:
        return SpatialProviderSettings.model_validate(values)
    except ValidationError as exc:
        raise SpatialConfigurationError(
            f"invalid spatial model configuration: {exc}"
        ) from exc
