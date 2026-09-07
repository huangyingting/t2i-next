"""Environment configuration for the standalone story model."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.provider import StoryProviderSettings

_ENV_FIELDS = {
    "STORY_OPENAI_BASE_URL": "base_url",
    "STORY_OPENAI_API_KEY_ENV": "api_key_env",
    "STORY_OPENAI_AUTH_MODE": "auth_mode",
    "STORY_OPENAI_MODEL": "model",
    "STORY_OPENAI_THINKING_MODE": "thinking_mode",
    "STORY_OPENAI_REASONING_EFFORT": "reasoning_effort",
    "STORY_OPENAI_TEMPERATURE": "temperature",
    "STORY_OPENAI_OUTPUT_TOKEN_LIMIT": "output_token_limit",
    "STORY_OPENAI_TIMEOUT_SECONDS": "timeout_seconds",
    "STORY_OPENAI_TRANSPORT_RETRIES": "transport_retries",
}


def load_story_provider_settings() -> StoryProviderSettings:
    load_dotenv(Path.cwd() / ".env", override=False)
    values = {
        field_name: value
        for environment_name, field_name in _ENV_FIELDS.items()
        if (value := os.environ.get(environment_name)) is not None
    }
    try:
        return StoryProviderSettings.model_validate(values)
    except ValidationError as exc:
        raise StoryConfigurationError(f"故事模型配置无效：{exc}") from exc
