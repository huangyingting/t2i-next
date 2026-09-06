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
    """Compare the stable settings selected by each Theme."""

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
    ) -> ThemeSimilarityReport:
        ordered = tuple(sorted(themes, key=lambda theme: theme.theme_id))
        if len(ordered) < 2:
            return self._report(input_count=0, pairs=[])

        settings = tuple(self._setting_text(theme) for theme in ordered)
        response = await self._model.embed(
            settings,
            model=self._settings.model,
            dimensions=self._settings.dimensions,
        )
        if len(response.vectors) != len(ordered):
            raise ProviderResponseError(
                "Embedding provider 返回的向量数量与输入不一致"
            )
        pairs = [
            self._compare(
                ordered[first_index],
                ordered[second_index],
                response.vectors[first_index],
                response.vectors[second_index],
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

    @staticmethod
    def _setting_text(theme: Theme) -> str:
        return "\n".join(
            (
                f"time_context: {theme.setting.time_context}",
                f"location: {theme.setting.location}",
                "fixed_elements: "
                + "；".join(theme.setting.fixed_elements),
                "available_light_sources: "
                + "；".join(theme.setting.available_light_sources),
                "background_population: "
                + theme.setting.background_population,
                f"atmosphere: {theme.setting.atmosphere}",
            )
        )

    def _compare(
        self,
        first: Theme,
        second: Theme,
        first_setting: Sequence[float],
        second_setting: Sequence[float],
    ) -> ThemeSimilarityPair:
        setting_similarity = self._cosine(first_setting, second_setting)
        return ThemeSimilarityPair(
            first_theme_id=first.theme_id,
            second_theme_id=second.theme_id,
            setting_similarity=round(setting_similarity, 6),
            potential_duplicate=setting_similarity
            >= self._settings.setting_threshold,
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
            setting_threshold=self._settings.setting_threshold,
            input_count=input_count,
            pairs=pairs,
            usage=usage or TokenUsage(),
            error=error,
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