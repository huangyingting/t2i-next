from __future__ import annotations

import json

import httpx
import pytest

from t2i_prompt_pipeline.errors import (
    ProviderResponseError,
    ProviderTruncatedOutputError,
)
from t2i_prompt_pipeline.models import (
    Foundation,
    GenerationStage,
    ProviderSettings,
    StructuredOutputMode,
    frame_batch_response_model,
)
from t2i_prompt_pipeline.providers.base import ChatMessage
from t2i_prompt_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider,
    _strict_json_schema,
)
from tests.factories import make_foundation


@pytest.mark.asyncio
async def test_provider_sends_strict_compatible_model_schema(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")
    captured: dict[str, object] = {}
    foundation = make_foundation()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {"message": {"content": foundation.model_dump_json()}}
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

    settings = ProviderSettings(
        model="test-model",
        api_key_env="TEST_API_KEY",
        output_token_limit=1234,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    response = await provider.generate(
        stage=GenerationStage.FOUNDATION,
        messages=[ChatMessage(role="user", content="request")],
        response_model=Foundation,
        max_output_tokens=1000,
    )
    await client.aclose()

    assert response.value == foundation
    assert response.usage.total_tokens == 150
    assert captured["authorization"] == "Bearer secret"
    assert captured["max_tokens"] == 1000
    schema = captured["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "title" not in schema
    assert "title" not in schema["$defs"]["StyleConstraints"]
    assert "default" not in schema["$defs"]["CastMember"]["properties"]["role"]
    assert set(schema["$defs"]["CastMember"]["required"]) == {
        "role",
        "gender",
    }


@pytest.mark.asyncio
async def test_provider_sends_one_batched_embedding_request(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
        )

    settings = ProviderSettings(model="test-model", api_key_env="TEST_API_KEY")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    response = await provider.embed(
        ("scene", "style"),
        model="embedding-model",
        dimensions=3,
    )
    await client.aclose()

    assert captured == {
        "path": "/v1/embeddings",
        "model": "embedding-model",
        "input": ["scene", "style"],
        "encoding_format": "float",
        "dimensions": 3,
    }
    assert response.vectors == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert response.usage.total_tokens == 7


@pytest.mark.asyncio
async def test_provider_rejects_invalid_embedding_indexes(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0]},
                    {"index": 0, "embedding": [0.0, 1.0]},
                ]
            },
        )

    settings = ProviderSettings(model="test-model", api_key_env="TEST_API_KEY")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    with pytest.raises(ProviderResponseError, match="向量 index"):
        await provider.embed(
            ("scene", "style"),
            model="embedding-model",
            dimensions=None,
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_rejects_non_finite_embedding_values(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=b'{"data":[{"index":0,"embedding":[1.0,NaN]}]}',
            headers={"Content-Type": "application/json"},
        )

    settings = ProviderSettings(model="test-model", api_key_env="TEST_API_KEY")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    with pytest.raises(ProviderResponseError, match="无效的向量项"):
        await provider.embed(
            ("scene",),
            model="embedding-model",
            dimensions=None,
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_rejects_unexpected_embedding_dimensions(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ]
            },
        )

    settings = ProviderSettings(model="test-model", api_key_env="TEST_API_KEY")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    with pytest.raises(ProviderResponseError, match="配置维度 2"):
        await provider.embed(
            ("scene",),
            model="embedding-model",
            dimensions=2,
        )
    await client.aclose()


def test_strict_schema_requires_nullable_frame_fields() -> None:
    response_model = frame_batch_response_model(
        "T01",
        ("T01-F01",),
        ("T01-C01",),
    )

    schema = _strict_json_schema(response_model.model_json_schema())
    moment_schema = schema["$defs"]["CharacterMomentForT01"]

    assert "default" not in moment_schema["properties"]["expression"]
    assert set(moment_schema["required"]) == {
        "character_id",
        "expression",
        "action",
    }


@pytest.mark.asyncio
async def test_json_object_mode_includes_the_schema_in_messages(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")
    foundation = make_foundation()
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {"message": {"content": foundation.model_dump_json()}}
                ]
            },
        )

    settings = ProviderSettings(
        model="test-model",
        api_key_env="TEST_API_KEY",
        structured_output_mode=StructuredOutputMode.JSON_OBJECT,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    await provider.generate(
        stage=GenerationStage.FOUNDATION,
        messages=[ChatMessage(role="user", content="request")],
        response_model=Foundation,
        max_output_tokens=1000,
    )
    await client.aclose()

    assert captured["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in captured["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_provider_surfaces_length_truncation(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")
    foundation = make_foundation()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": foundation.model_dump_json()
                        },
                        "finish_reason": "length",
                    }
                ]
            },
        )

    settings = ProviderSettings(
        model="test-model",
        api_key_env="TEST_API_KEY",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    with pytest.raises(ProviderTruncatedOutputError):
        await provider.generate(
            stage=GenerationStage.FOUNDATION,
            messages=[ChatMessage(role="user", content="request")],
            response_model=Foundation,
            max_output_tokens=1000,
        )

    await client.aclose()


@pytest.mark.asyncio
async def test_provider_surfaces_invalid_usage_metadata(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")
    foundation = make_foundation()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {"message": {"content": foundation.model_dump_json()}}
                ],
                "usage": {"total_tokens": -1},
            },
        )

    settings = ProviderSettings(
        model="test-model",
        api_key_env="TEST_API_KEY",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    with pytest.raises(ProviderResponseError, match="token usage"):
        await provider.generate(
            stage=GenerationStage.FOUNDATION,
            messages=[ChatMessage(role="user", content="request")],
            response_model=Foundation,
            max_output_tokens=1000,
        )

    await client.aclose()


@pytest.mark.asyncio
async def test_provider_rejects_non_object_json_response(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=[])

    settings = ProviderSettings(
        model="test-model",
        api_key_env="TEST_API_KEY",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(settings, client=client)

    with pytest.raises(ProviderResponseError, match="JSON 顶层不是对象"):
        await provider.generate(
            stage=GenerationStage.FOUNDATION,
            messages=[ChatMessage(role="user", content="request")],
            response_model=Foundation,
            max_output_tokens=1000,
        )

    await client.aclose()
