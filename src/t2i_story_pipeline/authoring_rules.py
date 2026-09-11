"""Resolve immutable stage rules for one story run."""

from __future__ import annotations

from pathlib import Path

from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.models import (
    OutputLanguage,
    StoryRequest,
    StoryRuleSet,
    StoryStage,
)

_SYSTEM_RULES_DIRECTORY = Path(__file__).resolve().parent / "rule_packs" / "system"
_STAGE_FILENAMES = {
    StoryStage.THEMES: "themes.rules",
    StoryStage.FRAMES: "frames.rules",
}


def resolve_story_rules(
    request: StoryRequest,
    *,
    user_directory: Path | None = None,
) -> StoryRuleSet:
    """Compile the ordered system and optional user rules for a new run."""
    system_directory = _require_directory(
        _SYSTEM_RULES_DIRECTORY,
        "story system rules directory",
    )
    resolved_user_directory = (
        _require_directory(user_directory.resolve(), "story user rules directory")
        if user_directory is not None
        else None
    )
    return StoryRuleSet(
        themes=_compile(
            StoryStage.THEMES,
            request,
            system_directory,
            resolved_user_directory,
        ),
        frames=_compile(
            StoryStage.FRAMES,
            request,
            system_directory,
            resolved_user_directory,
        ),
    )


def _compile(
    stage: StoryStage,
    request: StoryRequest,
    system_directory: Path,
    user_directory: Path | None,
) -> tuple[str, ...]:
    rules = [
        rule
        for path in _selected_paths(system_directory, stage, request)
        for rule in _read_rule_file(path, required=True)
    ]
    if user_directory is not None:
        rules.extend(
            rule
            for path in _selected_paths(user_directory, stage, request)
            for rule in _read_rule_file(path, required=False)
        )
    rules.append(_output_language_rule(request))
    return tuple(rules)


def _selected_paths(
    directory: Path,
    stage: StoryStage,
    request: StoryRequest,
) -> tuple[Path, ...]:
    return (
        directory / "common.rules",
        directory / _STAGE_FILENAMES[stage],
        directory / "content_levels" / f"{request.content_level.value}.rules",
    )


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise StoryConfigurationError(f"{label} does not exist: {path}")
    return path


def _read_rule_file(path: Path, *, required: bool) -> tuple[str, ...]:
    if not path.exists():
        if required:
            raise StoryConfigurationError(f"story rule file does not exist: {path}")
        return ()
    if not path.is_file():
        raise StoryConfigurationError(f"story rule path is not a file: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise StoryConfigurationError(
            f"cannot read story rule file {path}: {exc}"
        ) from exc
    return tuple(
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )


def _output_language_rule(request: StoryRequest) -> str:
    if request.output_language == OutputLanguage.ENGLISH:
        return (
            "Write every natural-language output field in precise, fluent "
            "English. Preserve only literal foreign text explicitly required "
            "by the Story Description."
        )
    return (
        "Write every natural-language output field in precise, fluent Chinese. "
        "Preserve only literal foreign text explicitly required by the Story "
        "Description; do not mix in untranslated foreign prose."
    )
