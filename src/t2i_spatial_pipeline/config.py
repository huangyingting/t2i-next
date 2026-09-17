"""Environment configuration for spatial prompt generation."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from t2i_model_provider.backend import selected_backend_values
from t2i_spatial_pipeline.errors import SpatialConfigurationError
from t2i_spatial_pipeline.provider import SpatialProviderSettings

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


def load_spatial_provider_settings() -> SpatialProviderSettings:
    load_dotenv(Path.cwd() / ".env", override=False)
    values = selected_backend_values(_ENV_FIELDS)
    try:
        return SpatialProviderSettings.model_validate(values)
    except ValidationError as exc:
        raise SpatialConfigurationError(
            f"invalid spatial model configuration: {exc}"
        ) from exc
