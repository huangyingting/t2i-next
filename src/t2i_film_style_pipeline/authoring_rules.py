"""Resolve package-owned director-style rules for story generation."""

from __future__ import annotations

from pathlib import Path

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.models import StoryRequest, StoryRuleSet

_SYSTEM_RULES_DIRECTORY = Path(__file__).resolve().parent / "rule_packs" / "system"


def resolve_film_style_rules(
    request: StoryRequest,
    *,
    user_directory: Path | None = None,
) -> StoryRuleSet:
    base = resolve_story_rules(request, user_directory=user_directory)
    return StoryRuleSet(
        themes=(*base.themes, *_read_rules("themes.rules")),
        frames=(*base.frames, *_read_rules("frames.rules")),
    )


def _read_rules(filename: str) -> tuple[str, ...]:
    path = _SYSTEM_RULES_DIRECTORY / filename
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise StoryConfigurationError(
            f"cannot read film-style system rule file {path}: {exc}"
        ) from exc
    return tuple(
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )
