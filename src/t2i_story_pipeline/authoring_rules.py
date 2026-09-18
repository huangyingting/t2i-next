"""Resolve immutable stage rules for one story run."""

from __future__ import annotations

from pathlib import Path

from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.models import (
    OutputLanguage,
    StoryAuthoring,
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
    authoring: StoryAuthoring | None = None,
) -> StoryRuleSet:
    """Compile core contracts and already selected authoring; never discover files."""
    system_directory = _require_directory(
        _SYSTEM_RULES_DIRECTORY,
        "story system rules directory",
    )
    return StoryRuleSet(
        themes=_compile(
            StoryStage.THEMES,
            request,
            system_directory,
            authoring or StoryAuthoring(),
        ),
        frames=_compile(
            StoryStage.FRAMES,
            request,
            system_directory,
            authoring or StoryAuthoring(),
        ),
    )


def _compile(
    stage: StoryStage,
    request: StoryRequest,
    system_directory: Path,
    authoring: StoryAuthoring,
) -> tuple[str, ...]:
    rules = [
        rule
        for path in _selected_paths(system_directory, stage, request)
        for rule in _read_rule_file(path)
    ]
    rules.extend(authoring.selected(stage, request.content_level))
    rules.append(output_language_rule(request))
    return tuple(rules)


def system_rule_sources(
    request: StoryRequest, stage: StoryStage | None = None
) -> tuple[Path, ...]:
    """The exact packaged files used by the compiler, in stable first-use order."""
    return tuple(
        dict.fromkeys(
            path
            for selected_stage in (StoryStage if stage is None else (stage,))
            for path in _selected_paths(
                _SYSTEM_RULES_DIRECTORY, selected_stage, request
            )
        )
    )


def system_rule_source_id(path: Path) -> str:
    """Logical provenance IDs do not depend on the installation directory."""
    group = "content_levels" if path.parent.name == "content_levels" else "system"
    return f"{group}/{path.name}"


def _selected_paths(
    directory: Path,
    stage: StoryStage,
    request: StoryRequest,
) -> tuple[Path, ...]:
    return (
        directory / "common.rules",
        directory / "safety.rules",
        directory / _STAGE_FILENAMES[stage],
        directory / "content_levels" / f"{request.content_level.value}.rules",
    )


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise StoryConfigurationError(f"{label} does not exist: {path}")
    return path


def _read_rule_file(path: Path) -> tuple[str, ...]:
    if not path.exists():
        raise StoryConfigurationError(f"story rule file does not exist: {path}")
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


def output_language_rule(request: StoryRequest) -> str:
    if request.output_language == OutputLanguage.ENGLISH:
        return (
            "Write every natural-language output field in precise, fluent "
            "English. Preserve only literal foreign text explicitly required "
            "by the visual input, including module parameters for visible image copy. "
            "Those literal image-copy languages do not change the prose language."
        )
    return (
        "Write every natural-language output field in precise, fluent Chinese. "
        "Preserve only literal foreign text explicitly required by the Story "
        "Description or module parameters for visible image copy; those literal "
        "image-copy languages do not change the prose language. Do not mix in "
        "untranslated foreign prose."
    )
