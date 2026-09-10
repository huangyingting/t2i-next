from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from t2i_story_pipeline.models import ContentLevel
from t2i_story_pipeline.prompts import frame_messages, theme_messages
from tests.story_factories import (
    make_story_request,
    make_theme,
    make_theme_batch,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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
    assert payload["batch_count"] == 10
    assert payload["content_level"] == "aesthetic"
    assert payload["semantic_name"] is None
    assert "concise lowercase English snake_case name" in prompt
    assert "Premise must contain no more than two sentences" in prompt
    assert "Do not put concrete poses, rope paths, equipment" in prompt
    assert "Leave those details to each frame" in prompt
    assert "unless the story explicitly requires them during Theme generation" in prompt
    assert "material state or operating rule instead" in prompt
    assert "non-narrative character or design board" in prompt
    assert "campaign, editorial concept board" in prompt
    assert "visual proposition, hero system, and conceptual leap" in prompt
    assert "six distinct visual-stunt seeds separated by semicolons" in prompt
    assert "even though shot-level detail is otherwise deferred" in prompt
    assert "generic tactile exploration" in prompt
    assert "relationship, setting function, decision, or conflict" in prompt


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
    assert "Return semantic_name exactly as lost_luggage_reunion" in prompt


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
        assert (
            "exactly 2 adult female participant(s) and 1 adult male participant(s)"
            in prompt
        )
        assert "Do not omit, replace, or add anyone" in prompt


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
        assert "must follow the explicit facts in the story" in messages[0].content


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

        assert "otherwise that person defaults to Chinese" in prompt
        assert "Do not infer nationality from location, name, language" in prompt
        assert (
            "Every theme premise and frame prose must state each person's "
            "nationality explicitly"
        ) in prompt
        assert 'Use "Chinese" in English output' in prompt
        assert "otherwise the setting defaults to China" in prompt
        assert "Do not move it to another country" in prompt
        assert (
            "Every theme premise and frame prose must state the country explicitly"
            in prompt
        )


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
    assert "Narrative coherence, fluency, and visual plausibility" in prompt
    assert "Treat each frame as the only image in the set" in prompt
    assert (
        "Fully redescribe every visible person's unmistakable adult identity"
        in prompt
    )
    assert "currently visible state and direct physical result" in prompt
    assert "one physically possible held pose" in prompt
    assert "must not travel between positions" in prompt
    assert "repeated views of the same person" in prompt
    assert "every region must deliver a distinct visual stunt" in prompt
    assert "Realize all six stunt seeds recorded in the Theme premise" in prompt
    assert "Explicitly describe Region 1 through Region 6" in prompt
    assert "general board synopsis" in prompt
    assert (
        "every Narrative Frame must independently contain one complete board"
        in prompt
    )
    assert "regardless of frames_per_theme" in prompt
    assert "Never distribute one board across multiple Frames" in prompt
    assert "use one Frame per region" in prompt
    assert "When frames_per_theme is 1" not in prompt
    assert "roughly 450 to 650 words" in prompt
    assert "flexible panel dramaturgy" in prompt
    assert "do not impose a fixed climax position" in prompt
    assert "Camera and lighting must be explicit and professional" in prompt
    assert "final state explicitly required by the story must appear directly" in prompt
    assert "read theme.theme_id from the current payload first" in prompt
    assert "apply only requirements matching that ID" in prompt
    assert "Explicit story constraints take priority" in prompt
    assert "rope art" not in prompt
    assert "do not mix in English pronouns" in prompt
    assert "not in the requested output language" in prompt
    assert "parallel visual alternatives" in prompt
    assert "Length should be driven by cast size and visual complexity" in prompt
    assert "follow exactly six sections" not in prompt
    assert "must begin exactly with" not in prompt
    assert "penultimate sentence" not in prompt
    assert "exact quality gate" not in prompt


def test_english_frame_prompt_requires_english_only_output() -> None:
    request = make_story_request(output_language="english")

    prompt = frame_messages(request, make_theme())[0].content

    assert "Write every prose paragraph entirely" in prompt
    assert "Do not include Chinese characters" in prompt
    assert "or switch to another language" in prompt


def test_chinese_prompts_allow_story_required_english_labels_and_copy() -> None:
    request = make_story_request(output_language="chinese")

    theme_prompt = theme_messages(
        request,
        start_index=1,
        count=1,
        existing_themes=[],
    )[0].content
    frame_prompt = frame_messages(request, make_theme())[0].content

    assert "explicitly requires a foreign-language title verbatim" in theme_prompt
    assert "requires a fixed field structure" in frame_prompt
    assert "English labels or visible image text explicitly required" in frame_prompt
    assert (
        "fixed field labels explicitly required by the story are allowed"
        in frame_prompt
    )


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
        assert (
            "If the story sets stricter visible requirements for this selected "
            "level, every one of them is mandatory"
        ) in prompt
        assert "presentation contract" in prompt
        assert "non-narrative design or pose board" in prompt
        assert "wardrobe, coverage, and pose-intensity rules" in prompt
        assert "do not invent a sexual act or missing partner" in prompt


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
        assert "era, region, season, time of day, and social setting" in prompt
        assert "When historical facts are uncertain" in prompt
        assert "time travel, alternate history, or temporal dislocation" in prompt
