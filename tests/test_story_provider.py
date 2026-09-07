from __future__ import annotations

import json

import httpx
import pytest

from t2i_story_pipeline.errors import StoryProviderResponseError
from t2i_story_pipeline.models import (
    StoryStage,
    exact_frame_sequence_model,
)
from t2i_story_pipeline.prompts import frame_messages
from t2i_story_pipeline.provider import (
    OpenAIStoryModel,
    StoryProviderSettings,
)
from tests.story_factories import (
    make_frame_sequence,
    make_story_request,
    make_theme,
)


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

    with pytest.raises(StoryProviderResponseError) as error:
        await provider.generate(
            stage=StoryStage.FRAMES,
            messages=frame_messages(make_story_request(), make_theme()),
            response_model=exact_frame_sequence_model(2),
            max_output_tokens=10000,
        )
    await client.aclose()

    assert error.value.usage.total_tokens == 30
