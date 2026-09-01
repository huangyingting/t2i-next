"""Optional semantic duplicate diagnostics for complete Theme sets."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol

from t2i_prompt_pipeline.errors import ProviderResponseError
from t2i_prompt_pipeline.models import (
    Theme,
    ThemeSimilarityPair,
    ThemeSimilarityReport,
    ThemeSimilaritySettings,
    ThemeSimilarityState,
    TokenUsage,
)


@dataclass(frozen=True, slots=True)
class EmbeddingResponse:
    vectors: tuple[tuple[float, ...], ...]
    usage: TokenUsage


class EmbeddingModel(Protocol):
    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        dimensions: int | None,
    ) -> EmbeddingResponse: ...


class ThemeSimilarityAnalyzer:
    """Compare Theme decisions without treating shared brief facts as style."""

    def __init__(
        self,
        model: EmbeddingModel,
        settings: ThemeSimilaritySettings,
    ) -> None:
        self._model = model
        self._settings = settings

    async def analyze(
        self,
        themes: Sequence[Theme],
        required_phrases: Sequence[str],
    ) -> ThemeSimilarityReport:
        ordered = tuple(sorted(themes, key=lambda theme: theme.theme_id))
        if len(ordered) < 2:
            return self._report(input_count=0, pairs=[])

        scenes = tuple(theme.scene for theme in ordered)
        styles = tuple(
            self._unconstrained_style(theme.style, required_phrases)
            for theme in ordered
        )
        response = await self._model.embed(
            (*scenes, *styles),
            model=self._settings.model,
            dimensions=self._settings.dimensions,
        )
        if len(response.vectors) != len(ordered) * 2:
            raise ProviderResponseError(
                "Embedding provider 返回的向量数量与输入不一致"
            )
        scene_vectors = response.vectors[: len(ordered)]
        style_vectors = response.vectors[len(ordered) :]
        pairs = [
            self._compare(
                ordered[first_index],
                ordered[second_index],
                scene_vectors[first_index],
                scene_vectors[second_index],
                style_vectors[first_index],
                style_vectors[second_index],
            )
            for first_index, second_index in combinations(range(len(ordered)), 2)
        ]
        return self._report(
            input_count=len(response.vectors),
            pairs=pairs,
            usage=response.usage,
            dimensions=len(response.vectors[0]) if response.vectors else None,
        )

    def failure_report(self, error: str) -> ThemeSimilarityReport:
        return self._report(
            input_count=0,
            pairs=[],
            error=error,
            state=ThemeSimilarityState.ERROR,
        )

    def _compare(
        self,
        first: Theme,
        second: Theme,
        first_scene: Sequence[float],
        second_scene: Sequence[float],
        first_style: Sequence[float],
        second_style: Sequence[float],
    ) -> ThemeSimilarityPair:
        scene_similarity = self._cosine(first_scene, second_scene)
        style_similarity = self._cosine(first_style, second_style)
        return ThemeSimilarityPair(
            first_theme_id=first.theme_id,
            second_theme_id=second.theme_id,
            scene_similarity=round(scene_similarity, 6),
            style_similarity=round(style_similarity, 6),
            potential_duplicate=(
                scene_similarity >= self._settings.scene_threshold
                and style_similarity >= self._settings.style_threshold
            ),
        )

    def _report(
        self,
        *,
        input_count: int,
        pairs: list[ThemeSimilarityPair],
        usage: TokenUsage | None = None,
        dimensions: int | None = None,
        error: str | None = None,
        state: ThemeSimilarityState = ThemeSimilarityState.ANALYZED,
    ) -> ThemeSimilarityReport:
        return ThemeSimilarityReport(
            state=state,
            model=self._settings.model,
            dimensions=dimensions or self._settings.dimensions,
            scene_threshold=self._settings.scene_threshold,
            style_threshold=self._settings.style_threshold,
            input_count=input_count,
            pairs=pairs,
            usage=usage or TokenUsage(),
            error=error,
        )

    @staticmethod
    def _unconstrained_style(
        style: str,
        required_phrases: Sequence[str],
    ) -> str:
        unconstrained = style
        for phrase in sorted(required_phrases, key=len, reverse=True):
            unconstrained = unconstrained.replace(phrase, "")
        return (
            " ".join(unconstrained.split()).strip(" ，,；;。.")
            or "无额外风格"
        )

    @staticmethod
    def _cosine(first: Sequence[float], second: Sequence[float]) -> float:
        if not first or len(first) != len(second):
            raise ProviderResponseError("Embedding provider 返回的向量维度不一致")
        first_norm = math.sqrt(sum(value * value for value in first))
        second_norm = math.sqrt(sum(value * value for value in second))
        if first_norm == 0 or second_norm == 0:
            raise ProviderResponseError("Embedding provider 返回了零向量")
        return sum(
            first_value * second_value
            for first_value, second_value in zip(first, second, strict=True)
        ) / (first_norm * second_norm)