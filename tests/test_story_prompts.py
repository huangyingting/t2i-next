from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.models import ContentLevel
from t2i_story_pipeline.prompts import (
    frame_messages as compile_frame_messages,
)
from t2i_story_pipeline.prompts import (
    theme_messages as compile_theme_messages,
)
from tests.story_factories import (
    make_story_request,
    make_theme,
    make_theme_batch,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def theme_messages(request, **kwargs):
    return compile_theme_messages(
        request,
        resolve_story_rules(request),
        **kwargs,
    )


def frame_messages(request, theme):
    return compile_frame_messages(
        request,
        theme,
        resolve_story_rules(request),
    )


def test_theme_prompt_requests_distinct_coherent_story_concepts() -> None:
    request = make_story_request(theme_count=100, frames_per_theme=6)
    messages = theme_messages(
        request,
        start_index=1,
        count=10,
        existing_themes=[],
    )
    prompt = messages[0].content
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert payload["theme_ids"] == [f"T{index:03d}" for index in range(1, 11)]
    assert payload["content_level"] == "aesthetic"
    assert payload["semantic_name"] is None
    assert "concise lowercase English snake_case name" in prompt
    assert "The Story Description is the authoritative presentation contract" in prompt
    assert "Follow any exact Theme-stage structure" in prompt
    assert "Do not infer a known brief type" in prompt
    assert "Theme-stage facts from Frame-stage rendering detail" in prompt
    assert "unless the Story Description explicitly promotes that detail" in prompt
    assert "Do not impose narrative conflict, chronology, or a decision" in prompt
    assert "defines another organizing principle" in prompt
    assert "axes that the Story Description makes important" in prompt


def test_later_theme_batches_preserve_the_run_semantic_name() -> None:
    request = make_story_request(theme_count=20)

    messages = theme_messages(
        request,
        start_index=11,
        count=10,
        existing_themes=make_theme_batch(count=10).themes,
        semantic_name="lost_luggage_reunion",
    )

    prompt = messages[0].content
    payload = json.loads(messages[1].content)
    assert payload["semantic_name"] == "lost_luggage_reunion"
    assert "If semantic_name is supplied, return it exactly" in prompt


def test_prompts_compile_exact_cast_constraints() -> None:
    request = make_story_request(female_count=2, male_count=1)

    for messages in (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content
        payload = json.loads(messages[1].content)

        assert payload["cast_constraints"] == {
            "female_count": 2,
            "male_count": 1,
        }
        assert "Use cast_constraints from the request exactly" in prompt
        assert "Do not add, omit, merge, or replace people" in prompt


def test_prompts_preserve_unspecified_cast_from_story() -> None:
    request = make_story_request()

    for messages in (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        assert json.loads(messages[1].content)["cast_constraints"] == {
            "female_count": None,
            "male_count": None,
        }
        assert (
            "Otherwise follow the people explicitly established" in messages[0].content
        )


def test_prompts_default_unspecified_people_and_setting_to_china() -> None:
    request = make_story_request()

    for messages in (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content

        assert "otherwise each person's nationality defaults" in prompt
        assert "Never infer nationality from setting, name, language" in prompt
        assert "state it explicitly in every Theme premise and Frame" in prompt
        assert "otherwise the setting country defaults to China" in prompt
        assert "State the country explicitly in every Theme premise and Frame" in prompt


def test_frame_prompt_prioritizes_coherent_standalone_prose() -> None:
    request = make_story_request(frames_per_theme=6)
    messages = frame_messages(request, make_theme())
    prompt = messages[0].content
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert payload["theme"]["theme_id"] == "T001"
    assert payload["frame_ids"] == [
        "F01",
        "F02",
        "F03",
        "F04",
        "F05",
        "F06",
    ]
    assert "Each Narrative Frame is one standalone renderable image" in prompt
    assert "Fully redescribe every visible person's adult identity" in prompt
    assert "currently visible states and direct physical results" in prompt
    assert "one physically possible held pose" in prompt
    assert "must not travel between positions" in prompt
    assert "The Story Description is the authoritative Frame contract" in prompt
    assert "Follow any exact fields, labels, order, counts, grouping" in prompt
    assert "subdivisions of that one renderable image" in prompt
    assert "do not spread one required image across Narrative Frames" in prompt
    assert "Repeated depictions of one named person inside a single image" in prompt
    assert "Preserve the requested medium" in prompt
    assert "Do not default to cinematic photography" in prompt
    assert "viewpoint and illumination in terms appropriate to that medium" in prompt
    assert "final state explicitly required by the Story Description" in prompt
    assert "Resolve conditional instructions only from the current request" in prompt
    assert "never borrow a branch assigned to another alternative" in prompt
    assert "Explicit Story Description constraints take priority" in prompt
    assert "rope art" not in prompt
    assert "do not mix in untranslated foreign prose" in prompt
    assert "parallel visual alternatives" in prompt
    assert "Let length follow the Story Description's exact contract" in prompt
    assert "follow exactly six sections" not in prompt
    assert "must begin exactly with" not in prompt
    assert "penultimate sentence" not in prompt
    assert "exact quality gate" not in prompt


def test_prompt_compiler_does_not_encode_story_input_archetypes() -> None:
    request = make_story_request()
    prompts = (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        )[0].content,
        frame_messages(request, make_theme())[0].content,
    )

    archetype_phrases = (
        "campaign",
        "design board",
        "multi-view",
        "six-region",
        "Region 1",
        "miniature-world",
        "thumbnail scale",
        "visual-stunt",
        "rope paths",
    )
    assert all(
        phrase not in prompt for prompt in prompts for phrase in archetype_phrases
    )


def test_english_frame_prompt_requires_english_only_output() -> None:
    request = make_story_request(output_language="english")

    prompt = frame_messages(request, make_theme())[0].content

    assert "Write every natural-language output field" in prompt
    assert "in precise, fluent English" in prompt
    assert "Preserve only literal foreign text explicitly required" in prompt


def test_chinese_prompts_allow_story_required_english_labels_and_copy() -> None:
    request = make_story_request(output_language="chinese")

    theme_prompt = theme_messages(
        request,
        start_index=1,
        count=1,
        existing_themes=[],
    )[0].content
    frame_prompt = frame_messages(request, make_theme())[0].content

    assert "in precise, fluent Chinese" in theme_prompt
    assert "in precise, fluent Chinese" in frame_prompt
    assert "Preserve only literal foreign text explicitly required" in theme_prompt
    assert "Preserve only literal foreign text explicitly required" in frame_prompt


@pytest.mark.parametrize("output_language", ("chinese", "english"))
def test_system_instructions_are_written_entirely_in_english(
    output_language: str,
) -> None:
    request = make_story_request(output_language=output_language)

    prompts = (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        )[0].content,
        frame_messages(request, make_theme())[0].content,
    )

    assert all(re.search(r"[\u4e00-\u9fff]", prompt) is None for prompt in prompts)


@pytest.mark.parametrize(
    ("level", "required", "excluded"),
    (
        (
            ContentLevel.AESTHETIC,
            "Use the aesthetic narrative level",
            (
                "Use the adult erotic narrative level",
                "Use the explicit erotic narrative level",
            ),
        ),
        (
            ContentLevel.EROTIC,
            "Use the adult erotic narrative level",
            (
                "Use the aesthetic narrative level",
                "Use the explicit erotic narrative level",
            ),
        ),
        (
            ContentLevel.HARDCORE,
            "Use the explicit erotic narrative level",
            (
                "Use the aesthetic narrative level",
                "Use the adult erotic narrative level",
            ),
        ),
    ),
)
def test_prompts_compile_only_selected_content_level(
    level: ContentLevel,
    required: str,
    excluded: tuple[str, str],
) -> None:
    request = make_story_request(content_level=level)

    for messages in (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content
        assert required in prompt
        assert all(item not in prompt for item in excluded)
        assert "more specific" in prompt
        assert "without importing requirements from another content level" in prompt


@pytest.mark.parametrize(
    ("level", "required_contract"),
    (
        (
            ContentLevel.AESTHETIC,
            (
                "At aesthetic level, the dominant hero photograph must remain "
                "unmistakably non-explicit"
            ),
        ),
        (
            ContentLevel.EROTIC,
            (
                "At erotic level, every Frame must make non-explicit adult "
                "intimacy unmistakably visible in the dominant hero photograph"
            ),
        ),
        (
            ContentLevel.HARDCORE,
            (
                "At hardcore level, every Frame must place the direct explicit "
                "adult interaction in the dominant hero photograph"
            ),
        ),
    ),
)
def test_post_layout_prompt_compiles_dominant_hero_content_contract(
    level: ContentLevel,
    required_contract: str,
) -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "post-layout.txt").read_text(
        encoding="utf-8"
    )
    request = make_story_request(
        content_level=level,
        frames_per_theme=1,
        female_count=1,
        male_count=1,
    ).model_copy(update={"story": brief})

    messages = frame_messages(request, make_theme())
    compiled = " ".join(
        "\n".join(message.content for message in messages).replace("\\n", " ").split()
    )
    payload = json.loads(messages[1].content)

    assert payload["content_level"] == level.value
    assert "Apply only the branch matching the CLI-selected content level" in compiled
    assert required_contract in compiled
    assert "content-level visibility anchor" in compiled
    assert "cannot satisfy the selected content level" in compiled


def test_prompts_express_era_consistency_holistically() -> None:
    request = make_story_request()

    for messages in (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content
        assert "Architecture, furnishings, objects, materials, clothing, hair" in prompt
        assert "titles, etiquette, season, and language" in prompt
        assert "When historical facts are uncertain" in prompt
        assert "temporal dislocation" in prompt
