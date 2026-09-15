"""OpenAI-compatible structured-output adapter for spatial prompts."""

from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, Literal, TypeVar

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from t2i_spatial_pipeline.errors import (
    SpatialConfigurationError,
    SpatialProviderError,
    SpatialProviderHTTPError,
    SpatialProviderResponseError,
    SpatialProviderTruncatedOutputError,
    SpatialStructuredOutputError,
)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


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


class SpatialProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    auth_mode: ProviderAuthMode = ProviderAuthMode.BEARER
    model: str
    thinking_mode: ThinkingMode | None = None
    reasoning_effort: ReasoningEffort | None = None
    temperature: float = Field(default=0.5, ge=0, le=2)
    output_token_limit: int = Field(default=32768, ge=512, le=65536)
    timeout_seconds: float = Field(default=180, gt=0, le=600)
    transport_retries: int = Field(default=2, ge=0, le=8)

    @model_validator(mode="after")
    def reasoning_controls_do_not_conflict(self) -> SpatialProviderSettings:
        if self.thinking_mode is not None and self.reasoning_effort is not None:
            raise ValueError("thinking_mode and reasoning_effort conflict")
        return self


ResponseT = TypeVar("ResponseT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    value: BaseModel
    usage: TokenUsage


_SCHEMA_MAP_KEYS = frozenset(
    {
        "$defs",
        "definitions",
        "dependentSchemas",
        "patternProperties",
        "properties",
    }
)
_ASCII_PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "\u00a0": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
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


def schema_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return normalized[:64] or "spatial_response"


def normalize_ascii_punctuation(value: str) -> str:
    translated = value.translate(_ASCII_PUNCTUATION_TRANSLATION)
    decomposed = unicodedata.normalize("NFKD", translated)
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )


class OpenAISpatialModel:
    def __init__(
        self,
        settings: SpatialProviderSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise SpatialConfigurationError(
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

    async def __aenter__(self) -> OpenAISpatialModel:
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
        validation_context: dict[str, object] | None = None,
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
        try:
            body = response.json()
            choice = body["choices"][0]
            finish_reason = choice.get("finish_reason")
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise SpatialProviderResponseError(
                "spatial model returned an unsupported response"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise SpatialProviderResponseError("spatial model returned empty content")
        content = normalize_ascii_punctuation(content)
        try:
            value = response_model.model_validate_json(
                content,
                context=validation_context,
            )
        except ValidationError as exc:
            validation_issues = tuple(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            error_type = (
                SpatialProviderTruncatedOutputError
                if finish_reason == "length"
                else SpatialStructuredOutputError
            )
            raise error_type(
                f"spatial response failed {response_model.__name__}: "
                f"{'; '.join(validation_issues)}",
                raw_content=content,
                validation_issues=validation_issues,
            ) from exc
        return ModelResponse(value=value, usage=self._parse_usage(response))

    async def _post(self, payload: dict[str, object]) -> httpx.Response:
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
                    raise SpatialProviderError(
                        f"spatial model request failed: {exc}"
                    ) from exc
                await asyncio.sleep(0.25 * (2**attempt))
                continue
            if response.status_code in {401, 403}:
                raise SpatialProviderError("spatial model rejected the credentials")
            if (
                response.status_code == 429
                and attempt < self._settings.transport_retries
            ):
                await asyncio.sleep(self._rate_limit_retry_delay(response, attempt))
                continue
            if (
                response.status_code >= 500
                and attempt < self._settings.transport_retries
            ):
                await asyncio.sleep(0.25 * (2**attempt))
                continue
            if response.is_error:
                raise SpatialProviderHTTPError(
                    response.status_code,
                    response.text,
                )
            return response
        raise SpatialProviderError("spatial model request did not complete")

    @staticmethod
    def _rate_limit_retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.25, min(float(retry_after), 120.0))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    delay = (
                        retry_at.astimezone(UTC) - datetime.now(UTC)
                    ).total_seconds()
                    return max(0.25, min(delay, 120.0))
                except (TypeError, ValueError, OverflowError):
                    pass
        return min(2.0**attempt, 60.0)

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


async def generate_with_repair(
    model: OpenAISpatialModel,
    *,
    system: str,
    payload: object,
    response_model: type[BaseModel],
    max_output_tokens: int,
    validation_context: dict[str, object] | None = None,
) -> tuple[ModelResponse, list[list[str]]]:
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        ),
    ]
    rejected_issues: list[list[str]] = []
    for attempt in range(3):
        try:
            response = await model.generate(
                messages=messages,
                response_model=response_model,
                max_output_tokens=max_output_tokens,
                validation_context=validation_context,
            )
        except SpatialStructuredOutputError as exc:
            rejected_issues.append(list(exc.validation_issues))
            if attempt == 2:
                raise
            repair_guidance = ""
            if any(
                "ascii" in issue.lower() for issue in exc.validation_issues
            ):
                repair_guidance = (
                    " Use printable ASCII characters only in every string; "
                    "replace smart quotes, long dashes, and accented characters."
                )
            if any(
                "incomplete phrases" in issue.lower()
                for issue in exc.validation_issues
            ):
                repair_guidance += (
                    " Rewrite every named field as a short complete phrase. "
                    "End each phrase with a concrete noun or adjective, never "
                    "with an article, preposition, conjunction, comma, semicolon, "
                    "or unmatched parenthesis."
                )
            if any(
                "mood tags" in issue.lower()
                and (
                    "unsupported" in issue.lower()
                    or "does not cover" in issue.lower()
                )
                for issue in exc.validation_issues
            ) and isinstance(payload, dict):
                allowed_moods = payload.get("allowed_mood_tags")
                if isinstance(allowed_moods, list):
                    repair_guidance += (
                        " Every compatible_moods value must be copied verbatim "
                        "from this allowed_mood_tags list: "
                        + json.dumps(allowed_moods, ensure_ascii=True)
                        + "."
                    )
            if isinstance(exc, SpatialProviderTruncatedOutputError):
                repair_guidance += (
                    " Be concise, omit all reasoning and commentary, and reserve "
                    "the output budget for one complete JSON object."
                )
            messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        "The previous response was rejected. Generate an entirely "
                        "fresh, complete schema. Do not repeat any forbidden word or "
                        "concept named by these validation issues, and correct every "
                        "issue: "
                        + "; ".join(exc.validation_issues)
                        + repair_guidance
                    ),
                )
            )
        else:
            return response, rejected_issues
    raise AssertionError("unreachable")
