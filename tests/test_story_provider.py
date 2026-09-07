from __future__ import annotations

import json

import httpx
import pytest

from t2i_story_pipeline.models import StoryBlueprint, StoryStage
from t2i_story_pipeline.prompts import interpretation_messages
from t2i_story_pipeline.provider import (
    OpenAIStoryModel,
    StoryProviderSettings,
)
from tests.story_factories import (
    make_story_blueprint,
    make_story_request,
)


@pytest.mark.asyncio
async def test_story_provider_sends_strict_schema(monkeypatch) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")
    captured = {}
    blueprint = make_story_blueprint()

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
                        "message": {"content": blueprint.model_dump_json()},
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

    response = await provider.generate(
        stage=StoryStage.INTERPRET,
        messages=interpretation_messages(make_story_request()),
        response_model=StoryBlueprint,
        max_output_tokens=2000,
    )
    await client.aclose()

    assert response.value == blueprint
    assert response.usage.total_tokens == 30
    assert captured["authorization"] == "Bearer secret"
    assert captured["reasoning_effort"] == "none"
    assert "temperature" not in captured
    schema = captured["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "title" not in schema
    assert set(schema["required"]) == {
        "title",
        "logline",
        "time",
        "location",
        "environment",
        "atmosphere",
        "characters",
        "relationships",
        "beats",
        "cinematography",
    }


@pytest.mark.asyncio
async def test_story_provider_accepts_valid_json_when_finish_reason_is_length(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STORY_TEST_API_KEY", "secret")
    blueprint = make_story_blueprint()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": blueprint.model_dump_json()},
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
        stage=StoryStage.INTERPRET,
        messages=interpretation_messages(make_story_request()),
        response_model=StoryBlueprint,
        max_output_tokens=2000,
    )
    await client.aclose()

    assert response.value == blueprint
