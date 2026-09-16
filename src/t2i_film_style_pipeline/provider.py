"""OpenAI-compatible structured-output adapter for film-style profiling."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from t2i_film_style_pipeline.errors import (
    FilmStyleConfigurationError,
    FilmStyleProviderError,
    FilmStyleProviderHTTPError,
    FilmStyleProviderResponseError,
    FilmStyleProviderTruncatedOutputError,
    FilmStyleStructuredOutputError,
)
from t2i_film_style_pipeline.models import TokenUsage


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant"]
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


class FilmStyleProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    auth_mode: ProviderAuthMode = ProviderAuthMode.BEARER
    model: str
    thinking_mode: ThinkingMode | None = None
    reasoning_effort: ReasoningEffort | None = None
    temperature: float = Field(default=0.3, ge=0, le=2)
    output_token_limit: int = Field(default=8000, ge=512, le=65536)
    timeout_seconds: float = Field(default=180, gt=0, le=600)
    transport_retries: int = Field(default=2, ge=0, le=8)

    @model_validator(mode="after")
    def reasoning_controls_do_not_conflict(
        self,
    ) -> FilmStyleProviderSettings:
        if self.thinking_mode is not None and self.reasoning_effort is not None:
            raise ValueError("thinking_mode and reasoning_effort conflict")
        return self


ResponseT = TypeVar("ResponseT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    value: BaseModel
    usage: TokenUsage


class FilmStyleModel(Protocol):
    async def generate(
        self,
        *,
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
    normalized = {
        key: strict_json_schema(item, schema_map=key in _SCHEMA_MAP_KEYS)
        for key, item in value.items()
        if key not in {"default", "title"}
    }
    if schema_map:
        return normalized
    properties = normalized.get("properties")
    if isinstance(properties, dict):
        normalized["required"] = list(properties)
    return normalized


class OpenAIFilmStyleModel:
    """Call one OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        settings: FilmStyleProviderSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise FilmStyleConfigurationError(
                f"environment variable {settings.api_key_env} is not set"
            )
        auth_header = (
            {"api-key": api_key}
            if settings.auth_mode == ProviderAuthMode.API_KEY
            else {"Authorization": f"Bearer {api_key}"}
        )
        self._settings = settings
        self._headers = {**auth_header, "Content-Type": "application/json"}
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)

    async def __aenter__(self) -> OpenAIFilmStyleModel:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate(
        self,
        *,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        max_output_tokens: int,
    ) -> ModelResponse:
        schema = strict_json_schema(response_model.model_json_schema())
        payload: dict[str, object] = {
            "model": self._settings.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "max_tokens": min(max_output_tokens, self._settings.output_token_limit),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "film_style_profile",
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
        try:
            body = response.json()
        except ValueError as exc:
            raise FilmStyleProviderResponseError(
                "film-style model returned non-JSON content"
            ) from exc
        if not isinstance(body, dict):
            raise FilmStyleProviderResponseError(
                "film-style model returned a non-object response"
            )
        usage = self._parse_usage(body)
        try:
            choice = body["choices"][0]
            finish_reason = choice.get("finish_reason")
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise FilmStyleProviderResponseError(
                "film-style model returned an unsupported response"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise FilmStyleProviderResponseError(
                "film-style model returned empty content"
            )
        try:
            value = response_model.model_validate_json(content)
        except ValidationError as exc:
            issues = tuple(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            error_type = (
                FilmStyleProviderTruncatedOutputError
                if finish_reason == "length"
                else FilmStyleStructuredOutputError
            )
            raise error_type(
                f"film-style response failed {response_model.__name__}: "
                f"{'; '.join(issues)}",
                raw_content=content,
                validation_issues=issues,
            ) from exc
        return ModelResponse(value=value, usage=usage)

    async def _post(self, payload: dict[str, object]) -> httpx.Response:
        url = f"{self._settings.base_url.rstrip('/')}/chat/completions"
        for attempt in range(self._settings.transport_retries + 1):
            try:
                response = await self._client.post(
                    url,
                    headers=self._headers,
                    content=json.dumps(payload, ensure_ascii=False),
                )
            except httpx.RequestError as exc:
                if attempt == self._settings.transport_retries:
                    raise FilmStyleProviderError(
                        f"film-style model transport failed: {exc}"
                    ) from exc
                await asyncio.sleep(min(2**attempt, 8))
                continue
            if response.status_code < 400:
                return response
            if response.status_code in {401, 403}:
                raise FilmStyleProviderHTTPError(
                    response.status_code,
                    response.text,
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self._settings.transport_retries:
                    await asyncio.sleep(
                        self._retry_delay(response, attempt)
                    )
                    continue
            raise FilmStyleProviderHTTPError(
                response.status_code,
                response.text,
            )
        raise AssertionError("transport retry loop exited unexpectedly")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    return max(
                        0.0,
                        retry_at.timestamp()
                        - __import__("time").time(),
                    )
                except (TypeError, ValueError):
                    pass
        return float(min(2**attempt, 8))

    @staticmethod
    def _parse_usage(body: dict[str, object]) -> TokenUsage:
        usage = body.get("usage")
        if not isinstance(usage, dict):
            return TokenUsage()

        def count(name: str) -> int:
            value = usage.get(name)
            return value if isinstance(value, int) and value >= 0 else 0

        return TokenUsage(
            prompt_tokens=count("prompt_tokens"),
            completion_tokens=count("completion_tokens"),
            total_tokens=count("total_tokens"),
        )
