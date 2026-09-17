from __future__ import annotations

import json

import httpx
import pytest

from t2i_film_style_pipeline.errors import FilmStyleProviderResponseError
from t2i_film_style_pipeline.models import FilmStyleProfile
from t2i_film_style_pipeline.profile_messages import profile_messages
from t2i_film_style_pipeline.provider import (
    FilmStyleProviderSettings,
    OpenAIFilmStyleModel,
)
from tests.test_film_style_pipeline import (
    make_profile,
    make_profile_rules,
    make_request,
)


@pytest.mark.asyncio
async def test_provider_sends_strict_profile_schema(monkeypatch) -> None:
    monkeypatch.setenv("FILM_STYLE_TEST_KEY", "secret")
    captured = {}
    profile = make_profile()

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
                        "message": {"content": profile.model_dump_json()},
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
    provider = OpenAIFilmStyleModel(
        FilmStyleProviderSettings(
            model="film-style-model",
            api_key_env="FILM_STYLE_TEST_KEY",
            reasoning_effort="none",
        ),
        client=client,
    )

    response = await provider.generate(
        messages=profile_messages(make_request(), make_profile_rules()),
        response_model=FilmStyleProfile,
        max_output_tokens=6000,
    )
    await client.aclose()

    assert response.value == profile
    assert response.usage.total_tokens == 30
    assert captured["authorization"].startswith("Bearer ")
    assert captured["reasoning_effort"] == "none"
    assert "temperature" not in captured
    schema = captured["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "style_summary",
        "work_style_summaries",
        "palette",
        "composition",
        "blocking",
        "camera",
        "lighting",
        "movement",
        "production_design",
        "material_and_finish",
        "signature_devices",
        "refusal_rules",
    }


@pytest.mark.asyncio
async def test_provider_rejects_non_object_json(monkeypatch) -> None:
    monkeypatch.setenv("FILM_STYLE_TEST_KEY", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=[])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIFilmStyleModel(
        FilmStyleProviderSettings(
            model="film-style-model",
            api_key_env="FILM_STYLE_TEST_KEY",
        ),
        client=client,
    )

    with pytest.raises(
        FilmStyleProviderResponseError,
        match="non-object response",
    ):
        await provider.generate(
            messages=profile_messages(make_request(), make_profile_rules()),
            response_model=FilmStyleProfile,
            max_output_tokens=6000,
        )
    await client.aclose()
