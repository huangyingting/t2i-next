"""Compact, complete coverage memory for already accepted Themes."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

if TYPE_CHECKING:
    from t2i_story_pipeline.models import NarrativeTheme, NarrativeThemeDraft


MemoryText = Annotated[
    str, StringConstraints(min_length=1, max_length=80, strip_whitespace=True)
]


class ThemeDiversity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: MemoryText = Field(description="Actual subjects and their relationship")
    setting: MemoryText = Field(
        description="Specific place and time or spatial context"
    )
    situation: MemoryText = Field(
        description=(
            "Concrete shared action and its object, or static visual proposition; "
            "must match premise, not a generic topic or a sequence of events"
        )
    )
    visual: MemoryText = Field(
        description="Distinguishing visual organization, not generic genre labels"
    )

    def key(self) -> tuple[str, ...]:
        return tuple(
            normalized_text(value)
            for value in (self.subject, self.setting, self.situation, self.visual)
        )


def normalized_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def theme_history(themes: Sequence[NarrativeTheme]) -> dict[str, object]:
    return {
        "existing_themes": [
            {
                "theme_id": theme.theme_id,
                "title": theme.title,
                "diversity": theme.diversity.model_dump(mode="json"),
            }
            for theme in themes
        ],
        "recent_themes": [theme.model_dump(mode="json") for theme in themes[-2:]],
    }


def duplicate_themes(
    candidates: Sequence[NarrativeThemeDraft],
    requested_ids: Sequence[str],
    existing: Sequence[NarrativeTheme],
) -> tuple[str, ...]:
    signatures: dict[tuple[str, ...], str] = {}
    prose: dict[tuple[str, str], str] = {}
    for theme in existing:
        signatures[theme.diversity.key()] = theme.theme_id
        prose[(normalized_text(theme.premise), normalized_text(theme.style))] = (
            theme.theme_id
        )
    issues = []
    for theme, theme_id in zip(candidates, requested_ids, strict=True):
        signature = theme.diversity.key()
        text = normalized_text(theme.premise), normalized_text(theme.style)
        previous = signatures.get(signature) or prose.get(text)
        if previous is not None:
            issues.append(
                f"{theme_id} repeats {previous}: change the actual subject, setting, "
                "situation or visual design, not just the title or diversity wording."
            )
        signatures[signature] = theme_id
        prose[text] = theme_id
    return tuple(issues)
