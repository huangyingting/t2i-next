from __future__ import annotations

import pytest
from pydantic import ValidationError

from t2i_film_style_pipeline.cast_validation import validate_cast_prose
from t2i_film_style_pipeline.compiler import compile_film_context, frame_source_sentence
from t2i_film_style_pipeline.diversity import (
    build_diversity_report,
    normalize_frame_anchor_prefix,
    theme_anchor_contract,
)
from t2i_film_style_pipeline.errors import FilmStyleContractError, FilmStyleStorageError
from t2i_film_style_pipeline.frame_text import frame_body
from t2i_film_style_pipeline.models import (
    FilmCharacterAnchor,
    FilmStyleRequest,
    FilmWorkReference,
)
from t2i_film_style_pipeline.pipeline import FilmStylePromptRequest
from t2i_film_style_pipeline.prompt_models import (
    FilmPromptRequest,
    FilmPromptResult,
    FilmPromptRuleSet,
    NarrativeFrame,
    NarrativeTheme,
    NarrativeThemeBatch,
    NarrativeThemeResult,
    SourceFilmCharacter,
    TokenUsage,
)
from t2i_film_style_pipeline.prompt_run_store import LocalFilmPromptRunStore
from t2i_film_style_pipeline.prompt_studio import FilmPromptStudio
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from tests.film_prompt_factories import make_authored_character
from tests.test_film_style_pipeline import make_profile
from tests.test_film_style_prompt_pipeline import FakePromptModel, make_settings


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
    characters = tuple(
        FilmCharacterAnchor(
            canonical_name=name,
            gender=gender,
            identity_and_appearance="An adult character in a silent comedy.",
            canonical_costume="A period costume.",
            costume_features=("period costume",),
        )
        for name, gender in (
            ("The Boy / Sherlock Jr.", "male"),
            ("The Girl", "female"),
            ("Mr. Keaton", "male"),
        )
    )
    anchors = original.work_anchors[0].model_copy(
        update={
            "adult_characters": characters,
            "scenes": (
                original.work_anchors[0]
                .scenes[0]
                .model_copy(
                    update={
                        "canonical_name": "Movie Theater Auditorium",
                    }
                ),
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
        film_style=film,
        female_count=1,
        male_count=1,
        output_language=language,
    ).prompt_request(compile_film_context(film, profile), profile)
    assert request.frame_source_sentence == frame_source_sentence(film)
    theme = NarrativeTheme(
        source_work_index=0,
        selected_cast=tuple(
            SourceFilmCharacter(
                origin="source", canonical_name=item.canonical_name, gender=item.gender
            )
            for item in characters[:2]
        ),
        theme_id="T001",
        title="A comedy misunderstanding",
        premise=(
            "The Boy / Sherlock Jr. and The Girl are in the Movie Theater Auditorium."
        ),
        style="A silent-comedy frame with period costumes and clear staging.",
    )
    return request, theme


@pytest.mark.parametrize("language", ["english", "chinese"])
@pytest.mark.parametrize("director", ["Buster Keaton", "C. G. Director Jr."])
def test_anchor_follows_complete_frozen_source_not_abbreviation(language, director):
    request, theme = make_sherlock_request(director=director, language=language)
    body = "  The Boy / Sherlock Jr. watches The Girl examine a film reel."
    raw = request.frame_source_sentence + body
    anchor = theme_anchor_contract(request, theme)["deterministic_anchor_sentence"]
    separator = " " if language == "english" else ""

    normalized = normalize_frame_anchor_prefix(request, theme, raw)

    assert normalized == request.frame_source_sentence + separator + anchor + body
    assert normalized.startswith(request.frame_source_sentence)
    assert normalized.count(request.frame_source_sentence) == 1
    assert normalize_frame_anchor_prefix(request, theme, normalized) == normalized
    assert frame_body(request, theme, normalized) == body
    validate_cast_prose(request, theme, raw)
    validate_cast_prose(request, theme, normalized)


def test_source_titles_and_director_names_are_not_cast_evidence() -> None:
    request, theme = make_sherlock_request(
        title="The Boy / Sherlock Jr.", director="Mr. Keaton"
    )
    missing_boy = request.frame_source_sentence + " The Girl examines the projector."
    with pytest.raises(FilmStyleContractError, match="missing=.*The Boy"):
        validate_cast_prose(request, theme, missing_boy)
    normalized = normalize_frame_anchor_prefix(request, theme, missing_boy)
    with pytest.raises(FilmStyleContractError, match="missing=.*The Boy"):
        validate_cast_prose(request, theme, normalized)

    body = " The Boy / Sherlock Jr. and The Girl examine a projector."
    valid = normalize_frame_anchor_prefix(
        request, theme, request.frame_source_sentence + body
    )
    validate_cast_prose(request, theme, valid)
    report = build_diversity_report(
        FilmPromptResult(
            run_id="source_prefix_test",
            semantic_name="silent_comedy",
            request=request,
            themes=[
                NarrativeThemeResult(
                    theme=theme, frames=[NarrativeFrame(frame_id="F01", prose=valid)]
                )
            ],
            usage=TokenUsage(),
        )
    )
    assert report.anchor_forbidden_term_frames == 0


def test_nonleading_anchor_text_is_preserved_verbatim() -> None:
    request, theme = make_sherlock_request()
    anchor = theme_anchor_contract(request, theme)["deterministic_anchor_sentence"]
    body = f" The Boy / Sherlock Jr. hands The Girl a note reading: {anchor}"
    normalized = normalize_frame_anchor_prefix(
        request, theme, request.frame_source_sentence + body
    )
    assert frame_body(request, theme, normalized) == body
    assert normalized.count(anchor) == 2


def test_no_authoritative_source_prefix_means_no_guessed_insertion() -> None:
    request, theme = make_sherlock_request()
    raw = "Sherlock Jr. (1924). The Boy / Sherlock Jr. watches The Girl."
    assert normalize_frame_anchor_prefix(request, theme, raw) == raw
    assert frame_body(request, theme, raw) == raw


def test_frozen_source_sentence_survives_json_and_is_required() -> None:
    request, _ = make_sherlock_request()
    restored = FilmPromptRequest.model_validate_json(request.model_dump_json())
    assert restored.frame_source_sentence == request.frame_source_sentence
    with pytest.raises(ValidationError, match="frame_source_sentence"):
        FilmPromptRequest.model_validate(
            request.model_dump(exclude={"frame_source_sentence"})
        )


def test_mixed_origin_prefix_preserves_periods_without_false_canon_attribution():
    request, theme = make_sherlock_request()
    request = request.model_copy(update={"female_count": 3, "male_count": 0})
    theme = theme.model_copy(
        update={
            "selected_cast": (
                theme.selected_cast[1],
                make_authored_character(1).model_copy(update={"name": "Ms. A. Vale"}),
                make_authored_character(2).model_copy(update={"name": "B. Moss"}),
            ),
            "premise": (
                "The Girl, Ms. A. Vale and B. Moss are in the Movie Theater Auditorium."
            ),
        }
    )
    body = " The Girl watches Ms. A. Vale and B. Moss examine a reel."
    raw = request.frame_source_sentence + body
    normalized = normalize_frame_anchor_prefix(request, theme, raw)
    assert normalized.startswith(request.frame_source_sentence + " ")
    assert (
        "original characters The Girl and the authored adult characters" in normalized
    )
    assert frame_body(request, theme, normalized) == body
    assert normalize_frame_anchor_prefix(request, theme, normalized) == normalized
    validate_cast_prose(request, theme, normalized)


@pytest.mark.asyncio
async def test_exact_source_prefix_survives_publication_and_resume(tmp_path) -> None:
    request, theme = make_sherlock_request()
    request = request.model_copy(update={"frames_per_theme": 1})
    body = " The Boy / Sherlock Jr. watches The Girl examine a film reel."
    raw = request.frame_source_sentence + body
    model = FakePromptModel(
        [
            NarrativeThemeBatch(semantic_name="sherlock_comedy", themes=[theme]),
            f"<FRAME>{raw}</FRAME>",
        ]
    )
    resolved = resolve_film_style_rules(request)
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    studio = FilmPromptStudio(
        model,
        store,
        make_settings().prompt,
        FilmPromptRuleSet(themes=resolved.themes, frames=resolved.frames),
    )

    completed = await studio.run(request)
    published = completed.published.prompt_file.read_text().rstrip("\n")

    assert published == normalize_frame_anchor_prefix(request, theme, raw)
    assert published.startswith(request.frame_source_sentence + " ")
    assert frame_body(request, theme, published) == body
    assert store.inspect(completed.run_id).request.frame_source_sentence == (
        request.frame_source_sentence
    )
    assert await studio.resume(completed.run_id) == completed
    assert len(model.stages) == 2

    # The scaffold cannot rescue a tampered stored body that omits the boy.
    frame_file = tmp_path / "runs" / completed.run_id / "frames" / "T001" / "F01.json"
    missing_boy = normalize_frame_anchor_prefix(
        request,
        theme,
        request.frame_source_sentence + " The Girl examines a film reel.",
    )
    frame_file.write_text(
        NarrativeFrame(frame_id="F01", prose=missing_boy).model_dump_json()
    )
    with pytest.raises(FilmStyleStorageError, match="missing=.*The Boy"):
        store.inspect(completed.run_id)
