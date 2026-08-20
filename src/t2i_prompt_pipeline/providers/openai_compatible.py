"""OpenAI-compatible author-model adapter."""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from t2i_prompt_pipeline.errors import (
    ConfigurationError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderResponseError,
    ProviderTruncatedOutputError,
    StructuredOutputError,
)
from t2i_prompt_pipeline.models import (
    GenerationStage,
    ProviderAuthMode,
    ProviderSettings,
    StructuredOutputMode,
    TokenUsage,
)
from t2i_prompt_pipeline.providers.base import (
    AuthorModel,
    ChatMessage,
    ModelResponse,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)
_SCHEMA_MAP_KEYS = frozenset(
    {"$defs", "definitions", "dependentSchemas", "patternProperties", "properties"}
)


def _strict_json_schema(value: Any, *, schema_map: bool = False) -> Any:
    if isinstance(value, list):
        return [_strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    if schema_map:
        return {key: _strict_json_schema(item) for key, item in value.items()}
    normalized = {
        key: _strict_json_schema(item, schema_map=key in _SCHEMA_MAP_KEYS)
        for key, item in value.items()
        if key not in {"default", "title"}
    }
    properties = normalized.get("properties")
    if isinstance(properties, dict):
        normalized["required"] = list(properties)
    return normalized


class OpenAICompatibleProvider(AuthorModel):
    """Call an OpenAI-compatible endpoint and parse one typed response."""

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise ConfigurationError(
                f"环境变量 {settings.api_key_env} 未设置，无法调用 LLM"
            )
        auth_header = (
            {"api-key": api_key}
            if settings.auth_mode == ProviderAuthMode.API_KEY
            else {"Authorization": f"Bearer {api_key}"}
        )
        self._headers = {**auth_header, "Content-Type": "application/json"}
        self._sensitive_values = (api_key, *auth_header.values())
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=settings.timeout_seconds
        )

    async def __aenter__(self) -> OpenAICompatibleProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate(
        self,
        *,
        stage: GenerationStage,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        max_output_tokens: int,
    ) -> ModelResponse[ResponseT]:
        schema = _strict_json_schema(response_model.model_json_schema())
        request_messages = list(messages)
        if self._settings.structured_output_mode != StructuredOutputMode.JSON_SCHEMA:
            request_messages.append(
                ChatMessage(
                    role="system",
                    content=(
                        "只输出符合以下 JSON Schema 的单个 JSON 对象，不要输出 "
                        "Markdown 或解释："
                        f"{json.dumps(schema, ensure_ascii=False)}"
                    ),
                )
            )

        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request_messages
            ],
            "max_tokens": min(
                max_output_tokens,
                self._settings.output_token_limit,
            ),
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
        if self._settings.structured_output_mode == StructuredOutputMode.JSON_SCHEMA:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": self._schema_name(response_model.__name__),
                    "strict": True,
                    "schema": schema,
                },
            }
        elif self._settings.structured_output_mode == StructuredOutputMode.JSON_OBJECT:
            payload["response_format"] = {"type": "json_object"}

        response = await self._post_with_retry(payload)
        usage = self._parse_usage(response)
        if self._finish_reason(response) == "length":
            try:
                content = self._extract_content(response)
            except ProviderResponseError:
                content = ""
            raise ProviderTruncatedOutputError(
                f"{stage.value} 输出达到 token 上限",
                raw_content=content,
                model=self._settings.model,
                usage=usage,
                validation_issues=("finish_reason=length",),
            )
        content = self._extract_content(response)
        try:
            value = response_model.model_validate_json(content)
        except ValidationError as exc:
            issues = tuple(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            raise StructuredOutputError(
                f"{stage.value} 返回内容不符合 {response_model.__name__}",
                raw_content=content,
                model=self._settings.model,
                usage=usage,
                validation_issues=issues,
            ) from exc
        return ModelResponse(value=value, usage=usage)

    @staticmethod
    def _finish_reason(response: httpx.Response) -> str | None:
        try:
            reason = response.json()["choices"][0].get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        return reason if isinstance(reason, str) else None

    async def _post_with_retry(self, payload: dict[str, Any]) -> httpx.Response:
        url = f"{self._settings.base_url.rstrip('/')}/chat/completions"
        attempts = self._settings.transport_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    url,
                    json=payload,
                    headers=self._headers,
                    timeout=self._settings.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 == attempts:
                    raise ProviderError(
                        "LLM 请求在传输重试后仍失败："
                        f"{type(exc).__name__}"
                    ) from exc
                await self._backoff(attempt)
                continue

            if response.status_code in {401, 403}:
                raise ProviderAuthenticationError(
                    f"LLM provider 认证失败，HTTP {response.status_code}"
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 == attempts:
                    raise ProviderError(
                        "LLM provider 在传输重试后仍返回 "
                        f"HTTP {response.status_code}"
                    )
                await self._backoff(attempt)
                continue
            if response.is_error:
                raise ProviderResponseError(
                    "LLM provider 返回不可重试的 "
                    f"HTTP {response.status_code}："
                    f"{self._safe_error_detail(response)}"
                )
            return response
        raise ProviderError("LLM 请求未返回结果")

    @staticmethod
    async def _backoff(attempt: int) -> None:
        await asyncio.sleep(min(2**attempt, 8) + random.uniform(0, 0.25))

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                "LLM provider 返回了不支持的响应结构"
            ) from exc
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if not isinstance(part, dict) or not isinstance(
                    part.get("text"), str
                ):
                    raise ProviderResponseError(
                        "LLM provider 返回了不支持的内容块"
                    )
                parts.append(part["text"])
            return "".join(parts)
        raise ProviderResponseError("LLM provider 的 message.content 不是文本")

    @staticmethod
    def _parse_usage(response: httpx.Response) -> TokenUsage:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError(
                "LLM provider 返回的响应不是有效 JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError("LLM provider 返回的 JSON 顶层不是对象")
        data = payload.get("usage", {})
        if not isinstance(data, dict):
            data = {}
        details = data.get("prompt_tokens_details")
        if not isinstance(details, dict):
            details = {}
        try:
            return TokenUsage(
                prompt_tokens=data.get("prompt_tokens"),
                cached_prompt_tokens=details.get("cached_tokens"),
                completion_tokens=data.get("completion_tokens"),
                total_tokens=data.get("total_tokens"),
            )
        except ValidationError as exc:
            raise ProviderResponseError(
                "LLM provider 返回了无效的 token usage"
            ) from exc

    def _safe_error_detail(self, response: httpx.Response) -> str:
        detail = "provider 未返回错误详情"
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict):
            error = data.get("error", data)
            if isinstance(error, dict):
                candidate = error.get("message") or error.get("code")
                if isinstance(candidate, str) and candidate.strip():
                    detail = candidate
        for value in self._sensitive_values:
            detail = detail.replace(value, "<REDACTED>")
        return re.sub(r"\s+", " ", detail).strip()[:500]

    @staticmethod
    def _schema_name(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64]
