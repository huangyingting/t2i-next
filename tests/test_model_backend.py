from __future__ import annotations

from dataclasses import dataclass

import pytest

import t2i_film_style_pipeline.provider as film_style_provider
import t2i_prompt_pipeline.providers.configured as prompt_provider
import t2i_spatial_pipeline.provider as spatial_provider
import t2i_story_pipeline.provider as story_provider
from t2i_film_style_pipeline.config import (
    load_film_style_provider_settings,
)
from t2i_film_style_pipeline.provider import FilmStyleProviderSettings
from t2i_model_provider import ModelBackend
from t2i_prompt_pipeline.config import load_provider_settings
from t2i_prompt_pipeline.errors import ConfigurationError
from t2i_prompt_pipeline.models import ProviderSettings
from t2i_spatial_pipeline.config import load_spatial_provider_settings
from t2i_spatial_pipeline.provider import SpatialProviderSettings
from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.provider import StoryProviderSettings


@dataclass
class SelectedModel:
    name: str

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


def test_all_pipelines_select_copilot_without_openai_model(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("T2I_MODEL_BACKEND", "copilot")
    monkeypatch.setenv("COPILOT_MODEL", "gpt-5")
    monkeypatch.setenv("COPILOT_REASONING_EFFORT", "high")
    monkeypatch.setenv("COPILOT_OUTPUT_TOKEN_LIMIT", "12000")

    settings = (
        load_film_style_provider_settings(),
        load_story_provider_settings(),
        load_spatial_provider_settings(),
        load_provider_settings(),
    )

    assert all(item.backend == ModelBackend.COPILOT for item in settings)
    assert all(item.model == "gpt-5" for item in settings)
    assert all(item.reasoning_effort.value == "high" for item in settings)
    assert all(item.output_token_limit == 12000 for item in settings)


def test_copilot_defaults_to_auto_model(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("T2I_MODEL_BACKEND", "copilot")
    monkeypatch.delenv("COPILOT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    settings = load_story_provider_settings()

    assert settings.backend == ModelBackend.COPILOT
    assert settings.model == "auto"


def test_invalid_backend_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("T2I_MODEL_BACKEND", "unsupported")

    with pytest.raises(ConfigurationError, match="Provider 配置无效"):
        load_provider_settings()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "module",
        "factory_name",
        "copilot_name",
        "openai_name",
        "settings_type",
    ),
    [
        (
            film_style_provider,
            "film_style_model",
            "CopilotFilmStyleModel",
            "OpenAIFilmStyleModel",
            FilmStyleProviderSettings,
        ),
        (
            story_provider,
            "story_model",
            "CopilotStoryModel",
            "OpenAIStoryModel",
            StoryProviderSettings,
        ),
        (
            spatial_provider,
            "spatial_model",
            "CopilotSpatialModel",
            "OpenAISpatialModel",
            SpatialProviderSettings,
        ),
        (
            prompt_provider,
            "author_model",
            "CopilotProvider",
            "OpenAICompatibleProvider",
            ProviderSettings,
        ),
    ],
)
@pytest.mark.parametrize("backend", list(ModelBackend))
async def test_all_model_factories_select_configured_backend(
    monkeypatch,
    module,
    factory_name,
    copilot_name,
    openai_name,
    settings_type,
    backend,
) -> None:
    monkeypatch.setattr(
        module,
        copilot_name,
        lambda _settings: SelectedModel("copilot"),
    )
    monkeypatch.setattr(
        module,
        openai_name,
        lambda _settings: SelectedModel("openai"),
    )

    factory = getattr(module, factory_name)
    async with factory(settings_type(backend=backend, model="test")) as model:
        assert model.name == backend.value
