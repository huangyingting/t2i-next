"""Select the configured author-model backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from t2i_model_provider import ModelBackend
from t2i_prompt_pipeline.models import ProviderSettings
from t2i_prompt_pipeline.providers.base import AuthorModel
from t2i_prompt_pipeline.providers.copilot import CopilotProvider
from t2i_prompt_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


@asynccontextmanager
async def author_model(
    settings: ProviderSettings,
) -> AsyncIterator[AuthorModel]:
    model = (
        CopilotProvider(settings)
        if settings.backend == ModelBackend.COPILOT
        else OpenAICompatibleProvider(settings)
    )
    async with model:
        yield model
