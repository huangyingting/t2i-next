"""Author-model seam used by the generation module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from t2i_prompt_pipeline.models import GenerationStage, TokenUsage


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user"]
    content: str


ResponseT = TypeVar("ResponseT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ModelResponse[ResponseT: BaseModel]:
    value: ResponseT
    usage: TokenUsage


class AuthorModel(Protocol):
    async def generate(
        self,
        *,
        stage: GenerationStage,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        max_output_tokens: int,
    ) -> ModelResponse[ResponseT]: ...
