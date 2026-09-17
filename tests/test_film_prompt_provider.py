from __future__ import annotations

import json

import httpx
import pytest

from t2i_film_style_pipeline.prompt_models import (
    FilmPromptStage,
    exact_theme_draft_batch_model,
)
from t2i_film_style_pipeline.prompt_provider import (
    ChatMessage,
    FilmPromptProviderSettings,
    OpenAIFilmPromptModel,
)


@pytest.mark.asyncio
async def test_film_prompt_provider_generates_structured_theme(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FILM_TEST_API_KEY", "secret")
    captured = {}
    response_model = exact_theme_draft_batch_model(1)
    response_value = response_model(
        semantic_name="lantern_chamber",
        themes=[
            {
                "title": "灯下对坐",
                "premise": "两名成年人物在内宅厢房对坐。",
                "style": "以固定中景和实景灯组织封闭空间。",
            }
        ],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": response_value.model_dump_json(),
                        },
                    }
                ],
                "usage": {"total_tokens": 20},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIFilmPromptModel(
        FilmPromptProviderSettings(
            model="film-model",
            api_key_env="FILM_TEST_API_KEY",
        ),
        client=client,
    )

    response = await provider.generate(
        stage=FilmPromptStage.THEMES,
        messages=[ChatMessage(role="user", content="生成一个 Theme。")],
        response_model=response_model,
        max_output_tokens=12000,
    )
    await client.aclose()

    assert response.value == response_value
    assert captured["response_format"]["json_schema"]["strict"] is True


@pytest.mark.asyncio
async def test_film_prompt_provider_generates_frame_text_without_schema(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FILM_TEST_API_KEY", "secret")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "完整的单段电影画面正文。"},
                    }
                ],
                "usage": {"total_tokens": 12},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIFilmPromptModel(
        FilmPromptProviderSettings(
            model="film-model",
            api_key_env="FILM_TEST_API_KEY",
        ),
        client=client,
    )

    response = await provider.generate_text(
        stage=FilmPromptStage.FRAMES,
        messages=[ChatMessage(role="user", content="生成一个 Frame。")],
        max_output_tokens=32768,
    )
    await client.aclose()

    assert response.text == "完整的单段电影画面正文。"
    assert "response_format" not in captured
