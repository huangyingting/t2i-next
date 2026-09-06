from __future__ import annotations

from collections.abc import Sequence

import pytest

from t2i_prompt_pipeline.models import ThemeSimilaritySettings, TokenUsage
from t2i_prompt_pipeline.theme_similarity import (
    EmbeddingResponse,
    ThemeSimilarityAnalyzer,
)
from tests.factories import make_spec, make_themes


class FakeEmbeddingModel:
    def __init__(self, vectors: tuple[tuple[float, ...], ...]) -> None:
        self.vectors = vectors
        self.requests: list[tuple[str, ...]] = []

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        dimensions: int | None,
    ) -> EmbeddingResponse:
        self.requests.append(tuple(texts))
        assert model == "embedding-model"
        assert dimensions == 3
        return EmbeddingResponse(
            vectors=self.vectors,
            usage=TokenUsage(prompt_tokens=42, total_tokens=42),
        )


@pytest.mark.asyncio
async def test_analyzer_batches_one_setting_per_theme() -> None:
    themes = make_themes(make_spec(theme_count=3))
    model = FakeEmbeddingModel(
        (
            (1.0, 0.0, 0.0),
            (0.99, 0.1, 0.0),
            (0.0, 1.0, 0.0),
        )
    )
    analyzer = ThemeSimilarityAnalyzer(
        model,
        ThemeSimilaritySettings(
            model="embedding-model",
            dimensions=3,
            setting_threshold=0.9,
        ),
    )

    report = await analyzer.analyze(themes)

    assert len(model.requests) == 1
    assert len(model.requests[0]) == 3
    assert all("location:" in text for text in model.requests[0])
    assert all("fixed_elements:" in text for text in model.requests[0])
    assert report.input_count == 3
    assert report.dimensions == 3
    assert report.usage.total_tokens == 42
    assert [pair.potential_duplicate for pair in report.pairs] == [
        True,
        False,
        False,
    ]
    assert report.pairs[0].first_theme_id == "T01"
    assert report.pairs[0].second_theme_id == "T02"


@pytest.mark.asyncio
async def test_single_theme_skips_embedding_request() -> None:
    model = FakeEmbeddingModel(())
    analyzer = ThemeSimilarityAnalyzer(
        model,
        ThemeSimilaritySettings(model="embedding-model", dimensions=3),
    )

    report = await analyzer.analyze(make_themes(make_spec()))

    assert model.requests == []
    assert report.input_count == 0
    assert report.pairs == []


@pytest.mark.asyncio
async def test_analyzer_includes_all_setting_fields() -> None:
    themes = make_themes(make_spec(theme_count=2))
    model = FakeEmbeddingModel(
        (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        )
    )
    analyzer = ThemeSimilarityAnalyzer(
        model,
        ThemeSimilaritySettings(model="embedding-model", dimensions=3),
    )

    await analyzer.analyze(themes)

    assert "available_light_sources: 窗外自然光" in model.requests[0][0]
    assert "background_population: 无他人" in model.requests[0][0]
    assert "atmosphere: 暖调、安静、亲密" in model.requests[0][0]