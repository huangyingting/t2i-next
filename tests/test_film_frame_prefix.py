from __future__ import annotations

import pytest

from t2i_film_style_pipeline.compiler import compile_film_context, frame_source_sentence
from t2i_film_style_pipeline.diversity import (
    build_diversity_report,
    normalize_frame_anchor_prefix,
    theme_anchor_contract,
)
from t2i_film_style_pipeline.frame_text import frame_body, source_sentence
from t2i_film_style_pipeline.models import FilmStyleRequest, FilmWorkReference
from t2i_film_style_pipeline.pipeline import FilmStylePromptRequest
from t2i_film_style_pipeline.prompt_models import (
    FilmPromptRequest,
    FilmPromptResult,
    NarrativeFrame,
    NarrativeTheme,
    NarrativeThemeResult,
    TokenUsage,
)
from tests.test_film_style_pipeline import make_profile


def make_sherlock_request(
    *,
    director: str = "Buster Keaton",
    title: str = "Sherlock Jr.",
    language: str = "english",
) -> tuple[FilmPromptRequest, NarrativeTheme]:
    film = FilmStyleRequest(
        director=director,
        works=(FilmWorkReference(title=title, year=1924),),
        output_language=language,
    )
    original = make_profile()
    anchors = original.work_anchors[0].model_copy(
        update={
            "adult_characters": tuple(
                character.model_copy(update={"canonical_name": name})
                for character, name in zip(
                    original.work_anchors[0].adult_characters,
                    ("The Boy / Sherlock Jr.", "The Girl"),
                    strict=True,
                )
            ),
            "scenes": (
                original.work_anchors[0]
                .scenes[0]
                .model_copy(update={"canonical_name": "Movie Theater Auditorium"}),
            ),
        }
    )
    profile = original.model_copy(
        update={
            "work_anchors": (anchors,),
            "work_style_summaries": original.work_style_summaries[:1],
        }
    )
    request = FilmStylePromptRequest(
        film_style=film, output_language=language, female_count=1, male_count=1
    ).prompt_request(compile_film_context(film, profile))
    assert source_sentence(request.context) == frame_source_sentence(film)
    theme = NarrativeTheme(
        theme_id="T001",
        title="A comedy misunderstanding",
        premise="The Boy / Sherlock Jr. and The Girl are in Movie Theater Auditorium.",
        style="A silent-comedy frame with period costumes and clear staging.",
    )
    return request, theme


@pytest.mark.parametrize("language", ["english", "chinese"])
@pytest.mark.parametrize("director", ["Buster Keaton", "C. G. Director Jr."])
def test_anchor_follows_complete_frozen_source_not_abbreviation(language, director):
    request, theme = make_sherlock_request(director=director, language=language)
    source = source_sentence(request.context)
    body = "  The Boy / Sherlock Jr. watches The Girl examine a film reel."
    raw = source + body
    anchor = theme_anchor_contract(request, theme)["deterministic_anchor_sentence"]
    separator = " " if language == "english" else ""

    normalized = normalize_frame_anchor_prefix(request, theme, raw)

    assert normalized == source + separator + anchor + body
    assert normalized.count(source) == 1
    assert normalize_frame_anchor_prefix(request, theme, normalized) == normalized
    assert frame_body(request.context, normalized) == separator + anchor + body


def test_nonleading_anchor_text_is_preserved_verbatim():
    request, theme = make_sherlock_request()
    anchor = theme_anchor_contract(request, theme)["deterministic_anchor_sentence"]
    body = f" The Boy / Sherlock Jr. hands The Girl a note reading: {anchor}"
    normalized = normalize_frame_anchor_prefix(
        request, theme, source_sentence(request.context) + body
    )
    assert normalized.endswith(body)
    assert normalized.count(anchor) == 2


@pytest.mark.parametrize("language", ["chinese", "english"])
@pytest.mark.parametrize("separator", ["", " ", "  "])
def test_existing_leading_anchor_is_not_duplicated_for_spacing(language, separator):
    request, theme = make_sherlock_request(language=language)
    anchor = theme_anchor_contract(request, theme)["deterministic_anchor_sentence"]
    raw = source_sentence(request.context) + separator + anchor + " The film begins."
    assert normalize_frame_anchor_prefix(request, theme, raw) == raw


def test_no_authoritative_source_prefix_means_no_guessed_insertion():
    request, theme = make_sherlock_request()
    raw = "Sherlock Jr. (1924). The Boy / Sherlock Jr. watches The Girl."
    assert normalize_frame_anchor_prefix(request, theme, raw) == raw
    assert frame_body(request.context, raw) == raw
    uncompiled = FilmPromptRequest(context="An original film brief.")
    assert source_sentence(uncompiled.context) is None


def test_source_sentence_survives_request_json_without_extra_cast_schema():
    request, _ = make_sherlock_request()
    restored = FilmPromptRequest.model_validate_json(request.model_dump_json())
    assert source_sentence(restored.context) == source_sentence(request.context)
    assert "selected_cast" not in NarrativeTheme.model_fields
    assert "source_films" not in FilmPromptRequest.model_fields


def test_report_uses_complete_source_boundary_and_excludes_inserted_cast_evidence():
    request, theme = make_sherlock_request()
    normalized = normalize_frame_anchor_prefix(
        request,
        theme,
        source_sentence(request.context) + " The Girl examines the projector.",
    )
    result = FilmPromptResult(
        run_id="source_prefix_test",
        semantic_name="silent_comedy",
        request=request,
        themes=[
            NarrativeThemeResult(
                theme=theme,
                frames=[NarrativeFrame(frame_id="F01", prose=normalized)],
            )
        ],
        usage=TokenUsage(),
    )
    report = build_diversity_report(result)
    assert report.anchor_forbidden_term_frames == 0
    assert report.participant_description_complete_slots < report.participant_slot_count
