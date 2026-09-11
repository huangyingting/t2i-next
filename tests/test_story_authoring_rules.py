from __future__ import annotations

from pathlib import Path

import pytest

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.models import ContentLevel, StoryStage
from tests.story_factories import make_story_request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_story_rules_compile_only_the_selected_content_level() -> None:
    request = make_story_request(content_level=ContentLevel.EROTIC)

    rules = resolve_story_rules(request)

    for stage in StoryStage:
        text = rules.text_for(stage)
        assert "Use the adult erotic narrative level" in text
        assert "Use the aesthetic narrative level" not in text
        assert "Use the explicit erotic narrative level" not in text


def test_story_rules_append_optional_user_files_in_stage_order(tmp_path) -> None:
    (tmp_path / "content_levels").mkdir()
    (tmp_path / "common.rules").write_text(
        "# ignored\nUser common rule.\n\n",
        encoding="utf-8",
    )
    (tmp_path / "themes.rules").write_text(
        "User Theme rule.\n",
        encoding="utf-8",
    )
    (tmp_path / "frames.rules").write_text(
        "User Frame rule.\n",
        encoding="utf-8",
    )
    (tmp_path / "content_levels" / "aesthetic.rules").write_text(
        "User aesthetic rule.\n",
        encoding="utf-8",
    )
    request = make_story_request(content_level=ContentLevel.AESTHETIC)

    rules = resolve_story_rules(request, user_directory=tmp_path)

    assert rules.themes[-4:-1] == (
        "User common rule.",
        "User Theme rule.",
        "User aesthetic rule.",
    )
    assert rules.frames[-4:-1] == (
        "User common rule.",
        "User Frame rule.",
        "User aesthetic rule.",
    )
    assert "Write every natural-language output field" in rules.themes[-1]
    assert "Write every natural-language output field" in rules.frames[-1]


def test_story_rules_reject_missing_user_directory(tmp_path) -> None:
    request = make_story_request()

    with pytest.raises(
        StoryConfigurationError,
        match="story user rules directory does not exist",
    ):
        resolve_story_rules(
            request,
            user_directory=tmp_path / "missing",
        )


def test_story_rules_fingerprint_changes_with_user_rules(tmp_path) -> None:
    request = make_story_request()
    builtin = resolve_story_rules(request)
    (tmp_path / "common.rules").write_text(
        "Project-specific story rule.\n",
        encoding="utf-8",
    )

    customized = resolve_story_rules(request, user_directory=tmp_path)

    assert customized.fingerprint() != builtin.fingerprint()


def test_specialized_story_inputs_own_their_presentation_contracts() -> None:
    required_contracts = {
        "creative.txt": (
            "FRAME-STAGE GRID CONTRACT",
            "MINIATURE-WORLD CAMERA LANGUAGE",
            "THUMBNAIL SCALE HIERARCHY",
            "BRIGHT CLEAN COLOR STANDARD",
        ),
        "multi-view.txt": (
            "FULL-BLEED MULTI-VIEW LAYOUT",
            "A full-bleed [two/three/four]-view hard-cut tiled composition",
        ),
        "dress.txt": (
            "SIX-VIEW BOARD CONTRACT",
            "exactly six non-overlapping view regions",
        ),
        "edo-warai-e.txt": (
            "SPATIAL AND CONTACT GEOMETRY",
            "PHOTOGRAPHIC REALISM",
            "MALE BODY VOCABULARY GATE",
        ),
    }

    for filename, phrases in required_contracts.items():
        story = (REPOSITORY_ROOT / "story-inputs" / filename).read_text(
            encoding="utf-8"
        )
        assert all(phrase in story for phrase in phrases)
