"""Application service for work-specific film-style compilation."""

from __future__ import annotations

import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from t2i_film_style_pipeline.compiler import compile_film_context
from t2i_film_style_pipeline.models import (
    FilmStyleProfile,
    FilmStyleRequest,
    FilmStyleResult,
    exact_film_style_profile_model,
)
from t2i_film_style_pipeline.profile_messages import profile_messages
from t2i_film_style_pipeline.provider import FilmStyleModel
from t2i_film_style_pipeline.storage import (
    PublishedFilmStyle,
    publish_film_style,
)


@dataclass(frozen=True, slots=True)
class CompletedFilmStyleRun:
    result: FilmStyleResult
    published: PublishedFilmStyle


class FilmStyleStudio:
    def __init__(
        self,
        model: FilmStyleModel,
        profile_rules: Sequence[str],
        *,
        runs_directory: Path = Path("runs") / "film-style",
    ) -> None:
        if not profile_rules:
            raise ValueError("profile_rules must not be empty")
        self._model = model
        self._profile_rules = tuple(profile_rules)
        self._runs_directory = runs_directory

    async def run(
        self,
        request: FilmStyleRequest,
        *,
        scene_direction: str | None = None,
    ) -> CompletedFilmStyleRun:
        response = await self._model.generate(
            messages=profile_messages(request, self._profile_rules),
            response_model=exact_film_style_profile_model(len(request.works)),
            max_output_tokens=8000,
        )
        if not isinstance(response.value, FilmStyleProfile):
            raise TypeError("film-style model returned an unexpected value")
        profile = exact_film_style_profile_model(len(request.works)).model_validate(
            response.value.model_dump()
        )
        profile = _normalize_source_labels(profile, request)
        run_id = _new_run_id()
        compiled = compile_film_context(
            request,
            profile,
            scene_direction=scene_direction,
        )
        result = FilmStyleResult(
            run_id=run_id,
            request=request,
            profile=profile,
            compiled_context=compiled,
            usage=response.usage,
        )
        published = publish_film_style(
            result,
            runs_directory=self._runs_directory,
        )
        return CompletedFilmStyleRun(result=result, published=published)


def _new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{secrets.token_hex(4)}"


def _normalize_source_labels(
    profile: FilmStyleProfile,
    request: FilmStyleRequest,
) -> FilmStyleProfile:
    values = profile.model_dump()
    work_summaries = tuple(
        _strip_work_prefix(summary, work.title, work.year)
        for work, summary in zip(
            request.works,
            profile.work_style_summaries,
            strict=True,
        )
    )
    style_summary = _strip_source_prefix(profile.style_summary, request)
    if len(work_summaries) == 1:
        style_summary = _first_sentence(work_summaries[0])
    elif (
        _contains_source_label(style_summary, request)
        or not _ends_with_sentence_punctuation(style_summary)
    ):
        style_summary = _combine_work_summaries(work_summaries)
    else:
        style_summary = _first_sentence(style_summary)
    values["style_summary"] = style_summary
    values["work_style_summaries"] = work_summaries
    return FilmStyleProfile.model_validate(values)


def _strip_source_prefix(
    value: str,
    request: FilmStyleRequest,
) -> str:
    normalized = value.strip()
    for work in request.works:
        normalized = _strip_work_prefix(normalized, work.title, work.year)
    director_pattern = rf"^{re.escape(request.director)}\s*[:：\-—]\s*"
    return re.sub(director_pattern, "", normalized).strip()


def _strip_work_prefix(
    value: str,
    title: str,
    year: int | None,
) -> str:
    year_pattern = (
        rf"(?:\s*\({year}\)|（{year}）)?"
        if year is not None
        else ""
    )
    pattern = (
        rf"^\s*(?:《{re.escape(title)}》|{re.escape(title)})"
        rf"{year_pattern}\s*[:：\-—]\s*"
    )
    return re.sub(pattern, "", value, count=1, flags=re.IGNORECASE).strip()


def _contains_source_label(
    value: str,
    request: FilmStyleRequest,
) -> bool:
    normalized = value.casefold()
    return (
        request.director.casefold() in normalized
        or any(work.title.casefold() in normalized for work in request.works)
    )


def _combine_work_summaries(summaries: tuple[str, ...]) -> str:
    pieces = [_first_sentence(summary) for summary in summaries]
    selected: list[str] = []
    for piece in pieces:
        candidate = "；".join([*selected, piece.rstrip("。； ")]) + "。"
        if len(candidate) > 240:
            break
        selected.append(piece.rstrip("。； "))
    if selected:
        return "；".join(selected) + "。"
    first = pieces[0]
    boundary = max(
        first.rfind(mark, 0, 239)
        for mark in "，、；,:; "
    )
    if boundary > 0:
        return first[:boundary].rstrip("，、；,:; ") + "。"
    return first[:238].rstrip() + "…。"


def _first_sentence(value: str) -> str:
    match = re.match(r"^.*?[。.!?！？]", value)
    return (match.group(0) if match is not None else value).strip()


def _ends_with_sentence_punctuation(value: str) -> bool:
    return value.rstrip().endswith(("。", ".", "!", "?", "！", "？"))
