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
async def test_analyzer_batches_fields_and_requires_both_thresholds() -> None:
    themes = make_themes(make_spec(theme_count=3))
    for theme in themes:
        theme.style = f"固定风格，{theme.style}"
    model = FakeEmbeddingModel(
        (
            (1.0, 0.0, 0.0),
            (0.99, 0.1, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.99, 0.1, 0.0),
            (1.0, 0.0, 0.0),
        )
    )
    analyzer = ThemeSimilarityAnalyzer(
        model,
        ThemeSimilaritySettings(
            model="embedding-model",
            dimensions=3,
            scene_threshold=0.9,
            style_threshold=0.9,
        ),
    )

    report = await analyzer.analyze(themes, ("固定风格",))

    assert len(model.requests) == 1
    assert len(model.requests[0]) == 6
    assert all("固定风格" not in text for text in model.requests[0][3:])
    assert report.input_count == 6
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

    report = await analyzer.analyze(make_themes(make_spec()), ())

    assert model.requests == []
    assert report.input_count == 0
    assert report.pairs == []


@pytest.mark.asyncio
async def test_analyzer_uses_placeholder_when_style_is_only_required_text() -> None:
    themes = make_themes(make_spec(theme_count=2))
    for theme in themes:
        theme.style = "电影摄影，摄影"
    model = FakeEmbeddingModel(
        (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        )
    )
    analyzer = ThemeSimilarityAnalyzer(
        model,
        ThemeSimilaritySettings(model="embedding-model", dimensions=3),
    )

    await analyzer.analyze(themes, ("摄影", "电影摄影"))

    assert model.requests[0][2:] == ("无额外风格", "无额外风格")