"""Deterministic cast contracts; these do not count bodies in free prose."""

from __future__ import annotations

import re

from pydantic import ValidationError

from t2i_film_style_pipeline.errors import FilmStyleContractError
from t2i_film_style_pipeline.frame_text import frame_body
from t2i_film_style_pipeline.models import CharacterGender
from t2i_film_style_pipeline.prompt_models import (
    FilmPromptRequest,
    NarrativeTheme,
)


def validate_selected_cast(request: FilmPromptRequest, theme: NarrativeTheme) -> None:
    # Revalidate typed instances too: model_copy/update and provider fakes can
    # otherwise bypass Pydantic's normal construction-time validation.
    try:
        request = FilmPromptRequest.model_validate(request)
        theme = NarrativeTheme.model_validate(theme)
    except ValidationError as exc:
        raise FilmStyleContractError(str(exc)) from exc
    if theme.source_work_index not in request.feasible_work_indices():
        raise FilmStyleContractError(
            f"{theme.theme_id}: selected source film cannot satisfy requested cast"
        )
    anchors = request.source_films[theme.source_work_index].anchors
    characters = {item.canonical_name: item for item in anchors.adult_characters}
    explicit_counts = request.female_count is not None or request.male_count is not None
    for selected in theme.selected_cast:
        original = characters.get(selected.canonical_name)
        if original is None:
            raise FilmStyleContractError(
                f"{theme.theme_id}: selected identity {selected.canonical_name!r} "
                "is not in the selected source film"
            )
        if selected.gender != original.gender:
            raise FilmStyleContractError(
                f"{theme.theme_id}: fixed-gender mismatch for "
                f"{selected.canonical_name}: expected {original.gender}"
            )
        if explicit_counts and original.gender == CharacterGender.UNKNOWN:
            raise FilmStyleContractError(
                f"{theme.theme_id}: unknown gender cannot satisfy explicit cast counts"
            )
    for gender, requested in (
        (CharacterGender.FEMALE, request.female_count),
        (CharacterGender.MALE, request.male_count),
    ):
        actual = sum(item.gender == gender for item in theme.selected_cast)
        if requested is not None and actual != requested:
            raise FilmStyleContractError(
                f"{theme.theme_id}: {gender} count mismatch: "
                f"requested={requested}, selected={actual}"
            )


def validate_cast_prose(
    request: FilmPromptRequest, theme: NarrativeTheme, prose: str
) -> None:
    """Check canonical-name presence, never mention frequency or body count."""
    prose = frame_body(request, theme, prose)
    selected = {
        item.canonical_name.casefold(): item.canonical_name
        for item in theme.selected_cast
    }
    known = {
        item.canonical_name
        for film in request.source_films
        for item in film.anchors.adult_characters
    }
    # Longest names win so a short name contained in a different character's
    # canonical name is not evidence of an extra identity.
    alternatives = []
    for name in sorted(known, key=len, reverse=True):
        pattern = re.escape(name)
        if name[0].isascii() and name[0].isalnum():
            pattern = r"(?<![A-Za-z0-9_])" + pattern
        if name[-1].isascii() and name[-1].isalnum():
            pattern += r"(?![A-Za-z0-9_])"
        alternatives.append(pattern)
    canonical = {name.casefold(): name for name in known}
    mentioned = {
        match.group().casefold()
        for match in re.finditer("|".join(alternatives), prose, re.IGNORECASE)
    }
    if mentioned != selected.keys():
        missing = sorted(selected[name] for name in selected.keys() - mentioned)
        unselected = sorted(canonical[name] for name in mentioned - selected.keys())
        raise FilmStyleContractError(
            f"{theme.theme_id}: prose canonical names conflict with selected_cast; "
            f"missing={missing}, unselected={unselected}"
        )
