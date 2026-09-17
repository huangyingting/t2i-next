"""GitHub Copilot SDK author-model adapter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel

from t2i_model_provider import CopilotGenerationError, CopilotStructuredModel
from t2i_prompt_pipeline.errors import (
    ConfigurationError,
    ProviderError,
    ProviderTruncatedOutputError,
    StructuredOutputError,
)
from t2i_prompt_pipeline.models import (
    GenerationStage,
    ProviderSettings,
    TokenUsage,
)
from t2i_prompt_pipeline.providers.base import (
    AuthorModel,
    ChatMessage,
    ModelResponse,
)
from t2i_prompt_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from t2i_prompt_pipeline.theme_similarity import EmbeddingResponse

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class CopilotProvider(AuthorModel):
    """Generate typed authoring objects through GitHub Copilot."""

    def __init__(self, settings: ProviderSettings) -> None:
        self._settings = settings
        self._model = CopilotStructuredModel(settings)
        self._embedding: OpenAICompatibleProvider | None = None

    async def __aenter__(self) -> CopilotProvider:
        try:
            await self._model.__aenter__()
        except CopilotGenerationError as exc:
            raise ProviderError(str(exc)) from exc
        if self._settings.embedding_model is not None:
            try:
                self._embedding = OpenAICompatibleProvider(self._settings)
                await self._embedding.__aenter__()
            except (OSError, ConfigurationError, ProviderError):
                await self._model.__aexit__()
                raise
        return self

    async def __aexit__(self, *args: object) -> None:
        try:
            if self._embedding is not None:
                await self._embedding.__aexit__(*args)
        finally:
            await self._model.__aexit__(*args)

    async def generate(
        self,
        *,
        stage: GenerationStage,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        max_output_tokens: int,
    ) -> ModelResponse[ResponseT]:
        try:
            response = await self._model.generate(
                messages=messages,
                response_model=response_model,
                max_output_tokens=max_output_tokens,
            )
        except CopilotGenerationError as exc:
            usage = TokenUsage(
                prompt_tokens=exc.prompt_tokens,
                completion_tokens=exc.completion_tokens,
                total_tokens=exc.total_tokens,
            )
            if exc.truncated:
                raise ProviderTruncatedOutputError(
                    f"{stage.value} Copilot 输出达到 token 上限",
                    raw_content=exc.raw_content,
                    model=self._settings.model,
                    usage=usage,
                    validation_issues=exc.validation_issues,
                ) from exc
            if exc.raw_content or exc.validation_issues:
                raise StructuredOutputError(
                    f"{stage.value} Copilot 返回内容不符合 "
                    f"{response_model.__name__}",
                    raw_content=exc.raw_content,
                    model=self._settings.model,
                    usage=usage,
                    validation_issues=exc.validation_issues,
                ) from exc
            raise ProviderError(str(exc)) from exc
        if not isinstance(response.value, response_model):
            raise ProviderError(
                f"Copilot returned an unexpected {stage.value} response type"
            )
        return ModelResponse(
            value=response.value,
            usage=TokenUsage(
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
            ),
        )

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        dimensions: int | None,
    ) -> EmbeddingResponse:
        if self._embedding is None:
            raise ProviderError(
                "Copilot backend requires OPENAI_EMBEDDING_MODEL and its "
                "OpenAI-compatible credentials for Theme similarity"
            )
        return await self._embedding.embed(
            texts,
            model=model,
            dimensions=dimensions,
        )
