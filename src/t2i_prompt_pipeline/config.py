"""Combine CLI run inputs with provider-only environment configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from t2i_prompt_pipeline.authoring_rules import resolve_rules
from t2i_prompt_pipeline.errors import ConfigurationError
from t2i_prompt_pipeline.models import (
    AppConfig,
    GenerationSpec,
    ProviderSettings,
    RunSettings,
    ThemeSimilaritySettings,
)

_PROVIDER_ENV_FIELDS = {
    "OPENAI_BASE_URL": "base_url",
    "OPENAI_API_KEY_ENV": "api_key_env",
    "OPENAI_AUTH_MODE": "auth_mode",
    "OPENAI_MODEL": "model",
    "OPENAI_STRUCTURED_OUTPUT_MODE": "structured_output_mode",
    "OPENAI_THINKING_MODE": "thinking_mode",
    "OPENAI_REASONING_EFFORT": "reasoning_effort",
    "OPENAI_TEMPERATURE": "temperature",
    "OPENAI_OUTPUT_TOKEN_LIMIT": "output_token_limit",
    "OPENAI_TIMEOUT_SECONDS": "timeout_seconds",
    "OPENAI_TRANSPORT_RETRIES": "transport_retries",
    "OPENAI_EMBEDDING_MODEL": "embedding_model",
    "OPENAI_EMBEDDING_DIMENSIONS": "embedding_dimensions",
}


def build_config(
    spec: GenerationSpec,
    *,
    runs_directory: Path = Path("runs"),
    prompts_directory: Path = Path("prompts"),
    rules_directory: Path | None = None,
    max_concurrency: int = 8,
    theme_batch_size: int = 5,
    generation_retries: int = 2,
) -> AppConfig:
    load_environment()
    default_rules_directory = Path("rules")
    user_rules_directory = (
        rules_directory
        if rules_directory is not None
        else (
            default_rules_directory
            if default_rules_directory.is_dir()
            else None
        )
    )
    rules = resolve_rules(spec, user_directory=user_rules_directory)
    try:
        provider = load_provider_settings(load_dotenv_file=False)
        return AppConfig(
            spec=spec,
            provider=provider,
            runs_directory=runs_directory.resolve(),
            prompts_directory=prompts_directory.resolve(),
            rules=rules,
            run_settings=RunSettings(
                theme_batch_size=theme_batch_size,
                generation_retries=generation_retries,
                max_concurrency=max_concurrency,
                provider_signature=provider.signature(),
                output_token_limit=provider.output_token_limit,
                theme_similarity=load_theme_similarity_settings(provider),
            ),
        )
    except (ValueError, ValidationError) as exc:
        raise ConfigurationError(f"配置内容无效: {exc}") from exc


def load_environment() -> None:
    load_dotenv(Path.cwd() / ".env", override=False)


def load_provider_settings(
    *,
    load_dotenv_file: bool = True,
) -> ProviderSettings:
    if load_dotenv_file:
        load_environment()
    values = {
        field_name: value
        for environment_name, field_name in _PROVIDER_ENV_FIELDS.items()
        if (value := os.environ.get(environment_name)) is not None
    }
    try:
        return ProviderSettings.model_validate(values)
    except ValidationError as exc:
        raise ConfigurationError(f"Provider 配置无效: {exc}") from exc


def load_theme_similarity_settings(
    provider: ProviderSettings,
) -> ThemeSimilaritySettings | None:
    if provider.embedding_model is None:
        return None
    values: dict[str, object] = {
        "model": provider.embedding_model,
        "dimensions": provider.embedding_dimensions,
    }
    if value := os.environ.get("THEME_SIMILARITY_SCENE_THRESHOLD"):
        values["scene_threshold"] = value
    if value := os.environ.get("THEME_SIMILARITY_STYLE_THRESHOLD"):
        values["style_threshold"] = value
    try:
        return ThemeSimilaritySettings.model_validate(values)
    except ValidationError as exc:
        raise ConfigurationError(
            f"Theme similarity 配置无效: {exc}"
        ) from exc
