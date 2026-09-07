"""Independent OpenAI-compatible structured-output adapter."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol, TypeVar

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from t2i_story_pipeline.errors import (
    StoryConfigurationError,
    StoryProviderAuthenticationError,
    StoryProviderError,
    StoryProviderResponseError,
)
from t2i_story_pipeline.models import (
    StoryStage,
    TokenUsage,
    schema_name,
)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user"]
    content: str


class ProviderAuthMode(StrEnum):
    BEARER = "bearer"
    API_KEY = "api_key"


class ThinkingMode(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class ReasoningEffort(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class StoryProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    auth_mode: ProviderAuthMode = ProviderAuthMode.BEARER
    model: str
    thinking_mode: ThinkingMode | None = None
    reasoning_effort: ReasoningEffort | None = None
    temperature: float = Field(default=0.5, ge=0, le=2)
    output_token_limit: int = Field(default=12000, ge=512, le=65536)
    timeout_seconds: float = Field(default=180, gt=0, le=600)
    transport_retries: int = Field(default=2, ge=0, le=8)

    @model_validator(mode="after")
    def reasoning_controls_do_not_conflict(
        self,
    ) -> StoryProviderSettings:
        if self.thinking_mode is not None and self.reasoning_effort is not None:
            raise ValueError("thinking_mode 与 reasoning_effort 不能同时配置")
        return self


ResponseT = TypeVar("ResponseT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    value: BaseModel
    usage: TokenUsage


class StoryModel(Protocol):
    async def generate(
        self,
        *,
        stage: StoryStage,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        max_output_tokens: int,
    ) -> ModelResponse: ...


_SCHEMA_MAP_KEYS = frozenset(
    {
        "$defs",
        "definitions",
        "dependentSchemas",
        "patternProperties",
        "properties",
    }
)


def strict_json_schema(value: Any, *, schema_map: bool = False) -> Any:
    if isinstance(value, list):
        return [strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    if schema_map:
        return {key: strict_json_schema(item) for key, item in value.items()}
    normalized = {
        key: strict_json_schema(
            item,
            schema_map=key in _SCHEMA_MAP_KEYS,
        )
        for key, item in value.items()
        if key not in {"default", "title"}
    }
    properties = normalized.get("properties")
    if isinstance(properties, dict):
        normalized["required"] = list(properties)
    return normalized


class OpenAIStoryModel(StoryModel):
    """Call one OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        settings: StoryProviderSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise StoryConfigurationError(
                f"环境变量 {settings.api_key_env} 未设置，无法调用故事模型"
            )
        auth_header = (
            {"api-key": api_key}
            if settings.auth_mode == ProviderAuthMode.API_KEY
            else {"Authorization": f"Bearer {api_key}"}
        )
        self._settings = settings
        self._headers = {
            **auth_header,
            "Content-Type": "application/json",
        }
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)

    async def __aenter__(self) -> OpenAIStoryModel:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate(
        self,
        *,
        stage: StoryStage,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        max_output_tokens: int,
    ) -> ModelResponse:
        schema = strict_json_schema(response_model.model_json_schema())
        payload = {
            "model": self._settings.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "max_tokens": min(
                max_output_tokens,
                self._settings.output_token_limit,
            ),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name(response_model.__name__),
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        if (
            self._settings.thinking_mode is None
            and self._settings.reasoning_effort is None
        ):
            payload["temperature"] = self._settings.temperature
        if self._settings.thinking_mode is not None:
            payload["thinking"] = {"type": self._settings.thinking_mode.value}
        if self._settings.reasoning_effort is not None:
            payload["reasoning_effort"] = self._settings.reasoning_effort.value
        response = await self._post(payload)
        usage = self._parse_usage(response)
        try:
            body = response.json()
            choice = body["choices"][0]
            finish_reason = choice.get("finish_reason")
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise StoryProviderResponseError(
                f"{stage.value} 返回了不支持的响应结构",
                usage=usage,
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise StoryProviderResponseError(
                f"{stage.value} 返回了空内容",
                usage=usage,
            )
        try:
            value = response_model.model_validate_json(content)
        except ValidationError as exc:
            if finish_reason == "length":
                raise StoryProviderResponseError(
                    f"{stage.value} 输出达到 token 上限",
                    usage=usage,
                ) from exc
            issues = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            raise StoryProviderResponseError(
                f"{stage.value} 返回内容不符合 {response_model.__name__}: {issues}",
                usage=usage,
            ) from exc
        return ModelResponse(value=value, usage=usage)

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self._settings.base_url.rstrip('/')}/chat/completions"
        for attempt in range(self._settings.transport_retries + 1):
            try:
                response = await self._client.post(
                    url,
                    headers=self._headers,
                    content=json.dumps(payload, ensure_ascii=False),
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._settings.transport_retries:
                    raise StoryProviderError(f"故事模型请求失败：{exc}") from exc
                await asyncio.sleep(0.25 * (2**attempt))
                continue
            if response.status_code in {401, 403}:
                raise StoryProviderAuthenticationError("故事模型拒绝了当前凭据")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self._settings.transport_retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
            if response.is_error:
                raise StoryProviderResponseError(
                    f"故事模型返回 HTTP {response.status_code}: {response.text[:500]}"
                )
            return response
        raise StoryProviderError("故事模型请求未完成")

    @staticmethod
    def _parse_usage(response: httpx.Response) -> TokenUsage:
        try:
            usage = response.json().get("usage", {})
        except (ValueError, TypeError):
            return TokenUsage()
        if not isinstance(usage, dict):
            return TokenUsage()
        values = {
            key: value
            for key, value in {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }.items()
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        }
        return TokenUsage.model_validate(values)
