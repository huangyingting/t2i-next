from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.errors import (
    StoryProviderHTTPError,
    StoryProviderTruncatedOutputError,
    StoryStructuredOutputError,
)
from t2i_story_pipeline.models import (
    StoryStage,
    exact_frame_sequence_model,
)
from t2i_story_pipeline.prompts import frame_messages as compile_frame_messages
from t2i_story_pipeline.provider import (
    OpenAIStoryModel,
    StoryProviderSettings,
)
from tests.story_factories import (
    make_frame_sequence,
    make_story_request,
    make_theme,
)


def frame_messages(request, theme):
    return compile_frame_messages(
        request,
        theme,
        resolve_story_rules(request),
    )


def test_story_provider_defaults_to_32768_output_tokens() -> None:
    settings = StoryProviderSettings(model="story-model")

    assert settings.output_token_limit == 32768


@pytest.mark.asyncio
async def test_story_provider_sends_strict_minimal_schema(monkeypatch) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")
    captured = {}
    sequence = make_frame_sequence()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": sequence.model_dump_json()},
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )

    settings = StoryProviderSettings(
        model="story-model",
        api_key_env="STORY_TEST_API_KEY",
        reasoning_effort="none",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIStoryModel(settings, client=client)
    response_model = exact_frame_sequence_model(2)

    response = await provider.generate(
        stage=StoryStage.FRAMES,
        messages=frame_messages(make_story_request(), make_theme()),
        response_model=response_model,
        max_output_tokens=10000,
    )
    await client.aclose()

    assert response.value.model_dump() == sequence.model_dump()
    assert response.usage.total_tokens == 30
    assert captured["authorization"].startswith("Bearer ")
    assert captured["reasoning_effort"] == "none"
    assert "temperature" not in captured
    schema = captured["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"frames"}


@pytest.mark.asyncio
async def test_story_provider_accepts_valid_json_at_length_limit(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")
    sequence = make_frame_sequence()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": sequence.model_dump_json()},
                    }
                ],
                "usage": {"total_tokens": 100},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIStoryModel(
        StoryProviderSettings(
            model="story-model",
            api_key_env="STORY_TEST_API_KEY",
        ),
        client=client,
    )

    response = await provider.generate(
        stage=StoryStage.FRAMES,
        messages=frame_messages(make_story_request(), make_theme()),
        response_model=exact_frame_sequence_model(2),
        max_output_tokens=10000,
    )
    await client.aclose()

    assert response.value.model_dump() == sequence.model_dump()


@pytest.mark.asyncio
async def test_story_provider_retries_rate_limit_with_retry_after(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")
    sleep = AsyncMock()
    monkeypatch.setattr("t2i_story_pipeline.provider.asyncio.sleep", sleep)
    sequence = make_frame_sequence()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                request=request,
                headers={"Retry-After": "3"},
                json={"error": {"message": "rate limited"}},
            )
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": sequence.model_dump_json()},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIStoryModel(
        StoryProviderSettings(
            model="story-model",
            api_key_env="STORY_TEST_API_KEY",
            transport_retries=1,
        ),
        client=client,
    )

    response = await provider.generate(
        stage=StoryStage.FRAMES,
        messages=frame_messages(make_story_request(), make_theme()),
        response_model=exact_frame_sequence_model(2),
        max_output_tokens=10000,
    )
    await client.aclose()

    assert response.value.model_dump() == sequence.model_dump()
    assert calls == 2
    sleep.assert_awaited_once_with(3.0)


@pytest.mark.asyncio
async def test_story_provider_supports_http_date_retry_after(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")
    sleep = AsyncMock()
    monkeypatch.setattr("t2i_story_pipeline.provider.asyncio.sleep", sleep)
    sequence = make_frame_sequence()
    calls = 0
    retry_at = format_datetime(
        datetime.now(UTC) + timedelta(seconds=30),
        usegmt=True,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                request=request,
                headers={"Retry-After": retry_at},
                json={"error": {"message": "rate limited"}},
            )
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": sequence.model_dump_json()},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIStoryModel(
        StoryProviderSettings(
            model="story-model",
            api_key_env="STORY_TEST_API_KEY",
            transport_retries=1,
        ),
        client=client,
    )

    await provider.generate(
        stage=StoryStage.FRAMES,
        messages=frame_messages(make_story_request(), make_theme()),
        response_model=exact_frame_sequence_model(2),
        max_output_tokens=10000,
    )
    await client.aclose()

    delay = sleep.await_args.args[0]
    assert 28 <= delay <= 30


@pytest.mark.asyncio
async def test_story_provider_does_not_restart_exhausted_http_retries(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            503,
            request=request,
            json={"error": {"message": "unavailable"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIStoryModel(
        StoryProviderSettings(
            model="story-model",
            api_key_env="STORY_TEST_API_KEY",
            transport_retries=2,
        ),
        client=client,
    )

    with pytest.raises(StoryProviderHTTPError) as error:
        await provider.generate(
            stage=StoryStage.FRAMES,
            messages=frame_messages(make_story_request(), make_theme()),
            response_model=exact_frame_sequence_model(2),
            max_output_tokens=10000,
        )
    await client.aclose()

    assert error.value.status_code == 503
    assert calls == 3


@pytest.mark.asyncio
async def test_story_provider_preserves_usage_on_invalid_output(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"frames":[]}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIStoryModel(
        StoryProviderSettings(
            model="story-model",
            api_key_env="STORY_TEST_API_KEY",
        ),
        client=client,
    )

    with pytest.raises(StoryStructuredOutputError) as error:
        await provider.generate(
            stage=StoryStage.FRAMES,
            messages=frame_messages(make_story_request(), make_theme()),
            response_model=exact_frame_sequence_model(2),
            max_output_tokens=10000,
        )
    await client.aclose()

    assert error.value.usage.total_tokens == 30
    assert error.value.raw_content == '{"frames":[]}'
    assert error.value.validation_issues


@pytest.mark.asyncio
async def test_story_provider_classifies_invalid_truncated_output(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"frames":['},
                    }
                ],
                "usage": {"total_tokens": 40},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIStoryModel(
        StoryProviderSettings(
            model="story-model",
            api_key_env="STORY_TEST_API_KEY",
        ),
        client=client,
    )

    with pytest.raises(StoryProviderTruncatedOutputError) as error:
        await provider.generate(
            stage=StoryStage.FRAMES,
            messages=frame_messages(make_story_request(), make_theme()),
            response_model=exact_frame_sequence_model(2),
            max_output_tokens=10000,
        )
    await client.aclose()

    assert error.value.usage.total_tokens == 40
    assert error.value.raw_content == '{"frames":['
    assert error.value.validation_issues
