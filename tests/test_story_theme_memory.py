from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from t2i_story_pipeline.models import NarrativeTheme, NarrativeThemeDraft
from t2i_story_pipeline.theme_memory import (
    ThemeDiversity,
    duplicate_themes,
    theme_history,
)


def theme(index: int = 1) -> NarrativeTheme:
    return NarrativeTheme(
        theme_id=f"T{index:03d}",
        title=f"Station composition {index}",
        premise=f"Adult travelers examine platform {index}. " * 10,
        style=f"A daylight composition of platform {index}. " * 6,
        diversity=ThemeDiversity(
            subject="Two adult travelers",
            setting=f"Platform {index}",
            situation=f"Looking for the departure point {index}",
            visual=f"Perspective through station column {index}",
        ),
    )


def draft(value: NarrativeTheme) -> NarrativeThemeDraft:
    return NarrativeThemeDraft.model_validate(value.model_dump(exclude={"theme_id"}))


def test_memory_keeps_all_theme_signatures_and_only_two_recent_full_themes():
    themes = [theme(index) for index in range(1, 101)]
    memory = theme_history(themes)
    assert len(memory["existing_themes"]) == 100
    assert memory["existing_themes"][0] == {
        "theme_id": "T001",
        "title": themes[0].title,
        "diversity": themes[0].diversity.model_dump(mode="json"),
    }
    assert memory["recent_themes"] == [
        value.model_dump(mode="json") for value in themes[-2:]
    ]
    assert "premise" not in memory["existing_themes"][0]
    full = json.dumps(
        {"existing_themes": [value.model_dump(mode="json") for value in themes]},
        ensure_ascii=False,
    )
    compact = json.dumps(memory, ensure_ascii=False)
    assert len(compact) < len(full) * 0.5
    assert theme_history(()) == {"existing_themes": [], "recent_themes": []}


def test_repeated_signature_is_rejected_even_with_new_title_and_prose():
    old = theme()
    candidate = draft(old).model_copy(
        update={"title": "Renamed", "premise": "A rewording of the same scene."}
    )
    issues = duplicate_themes([candidate], ["T002"], [old])
    assert len(issues) == 1
    assert "T002 repeats T001" in issues[0]


def test_repeated_prose_is_rejected_even_if_signature_is_reworded():
    old = theme()
    candidate = draft(old).model_copy(update={"diversity": theme(2).diversity})
    assert duplicate_themes([candidate], ["T002"], [old])


def test_duplicate_checks_cover_the_current_batch_and_normalize_whitespace_case():
    first = draft(theme())
    second = first.model_copy(
        update={
            "diversity": ThemeDiversity(
                **{
                    key: f"  {value.upper()}  "
                    for key, value in first.diversity.model_dump().items()
                }
            )
        }
    )
    assert duplicate_themes([first, second], ["T001", "T002"], ())
    assert not duplicate_themes(
        [draft(theme(1)), draft(theme(2))], ["T001", "T002"], ()
    )


def test_diversity_fields_are_required_and_bounded():
    with pytest.raises(ValidationError):
        ThemeDiversity(subject="Travelers", setting="Station", situation="Waiting")
    with pytest.raises(ValidationError):
        ThemeDiversity(
            subject="x" * 81, setting="Station", situation="Waiting", visual="Wide"
        )
