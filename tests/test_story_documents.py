from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.inputs import (
    CatalogDocument,
    StoryDocument,
    StoryRunConfiguration,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.models import ContentLevel, StoryStage


def test_document_keeps_prose_and_defaults(tmp_path):
    path = tmp_path / "renamed.yaml"
    path.write_text(
        "id: rainy-station\n"
        "description: |\n"
        "  First paragraph.\n"
        "\n"
        "  Second paragraph, with a colon: and # literal text.\n",
        encoding="utf-8",
    )
    document = load_story_document(path)
    assert document.id == "rainy-station"
    assert document.description == (
        "First paragraph.\n\nSecond paragraph, with a colon: and # literal text."
    )
    configuration = resolve_story_input(document).run_configuration
    assert configuration == StoryRunConfiguration()
    assert set(document.model_dump()) == {
        "id", "description", "cast", "authoring", "modules", "requirements",
        "allocation",
    }
    assert document.authoring.themes.common == ()
    assert document.authoring.themes.model_dump() == {"common": ()}
    assert document.authoring.level_refinements == {}


def test_document_loads_shared_and_stage_specific_level_refinements(tmp_path):
    path = tmp_path / "station.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": "station",
                "description": "A quiet station.",
                "authoring": {
                    "level_refinements": {
                        "aesthetic": {
                            "shared": ["Shared station texture."],
                            "themes": ["Choose a station mood."],
                            "frames": ["Render station details."],
                        },
                        "erotic": {"shared": ["Unselected station texture."]},
                    },
                    "themes": {"common": ["Choose a station."]},
                    "frames": {"common": ["Render a station."]},
                },
            }
        ),
        encoding="utf-8",
    )
    document = load_story_document(path)
    assert document.authoring.level_refinements[ContentLevel.AESTHETIC].shared == (
        "Shared station texture.",
    )
    assert document.authoring.selected(StoryStage.THEMES, ContentLevel.AESTHETIC) == (
        "Choose a station.",
        "Shared station texture.",
        "Choose a station mood.",
    )
    assert document.authoring.selected(StoryStage.FRAMES, ContentLevel.AESTHETIC) == (
        "Render a station.",
        "Shared station texture.",
        "Render station details.",
    )


@pytest.mark.parametrize("field", ["generation", "runtime", "validation", "policy"])
@pytest.mark.parametrize("value", ["{}", "null"])
def test_yaml_rejects_execution_roots_even_when_empty(tmp_path, field, value):
    path = tmp_path / "story.yaml"
    path.write_text(
        f"id: story\ndescription: Story.\n{field}: {value}\n",
        encoding="utf-8",
    )
    with pytest.raises(StoryConfigurationError, match=field):
        load_story_document(path)


@pytest.mark.parametrize(
    "extra",
    [
        "unknown: value",
        "runtime: {unknown: 1}",
        "runtime: {concurrency: true}",
        "runtime: {concurrency: '3'}",
        "runtime: {concurrency: 0}",
        "runtime: {generation_retries: -1}",
        "runtime: {theme_batch_size: 0}",
        "runtime: {theme_batch_size: 11}",
        "runtime: {theme_batch_size: '2'}",
        "runtime: {theme_output_tokens: 511}",
        "runtime: {frame_output_tokens: 65537}",
        "runtime: {frame_output_tokens: true}",
        "generation: {theme_count: 101}",
        "generation: {frames_per_theme: 7}",
        "generation: {content_level: unknown}",
        "generation: {cast: {female_count: 0, male_count: 0}}",
        "generation: {cast: {female_count: 8, male_count: 1}}",
        "validation: {quality: {mode: off}}",
        "validation: {frames: {mode: false}}",
        "validation: {frames: {mode: unknown}}",
        "validation: {frames: {checks: [camera_evidence]}}",
        "validation: {frames: {mode: off, checks: [{type: unknown}]}}",
        "validation: {frames: {checks: [{type: prose_length, min_chars: 0}]}}",
        "validation: {frames: {checks: [{type: prose_length, min_chars: '3'}]}}",
        "validation:\n  frames:\n    checks:\n"
        "      - {type: prose_length, min_chars: 10, max_chars: 5}",
        "validation: {frames: {checks: [{type: required_text, values: []}]}}",
        "validation:\n  frames:\n    checks:\n"
        "      - {type: camera_evidence}\n      - {type: camera_evidence}",
        "validation: {themes: {mode: off, checks: [{type: camera_evidence}]}}",
        "validation: {themes: {checks: [{type: required_text, values: [clock]}]}}",
        "validation: {themes: {checks: "
        "[{type: required_text, field: prose, values: [clock]}]}}",
        "validation: {themes: {checks: "
        "[{type: text_length, field: premise, min_chars: 10, max_chars: 2}]}}",
        "validation: {themes: {checks: "
        "[{type: required_text, field: title, values: [one]}, "
        "{type: required_text, field: title, values: [two]}]}}",
        "authoring: {frames: {common: ['']}}",
        'authoring: {themes: {common: ["two\\nlines"]}}',
        "authoring: {themes: [Old array interface.]}",
        "authoring: {frames: {content_levels: {unknown: [Rule.]}}}",
        "authoring: {content_levels: {unknown: [Rule.]}}",
        "authoring: {content_levels: {}}",
        "authoring: {themes: {content_levels: {}}}",
        "authoring: {frames: {content_levels: {}}}",
        "authoring: {level_refinements: {unknown: {shared: [Rule.]}}}",
        "authoring: {level_refinements: {aesthetic: {shared: ['']}}}",
        'authoring: {level_refinements: {aesthetic: {shared: ["two\\nlines"]}}}',
        "generation:\n  theme_count: 2\n  theme_count: 3",
        "description: Another story.",
        "authoring: &rules {themes: []}",
        "authoring: *missing",
        "authoring: {<<: {themes: []}}",
        "authoring: !!python/object:builtins.object {}",
        "---\nid: second\ndescription: Second document.",
    ],
)
def test_invalid_configuration_fails_explicitly(tmp_path, extra):
    path = tmp_path / "story.yaml"
    path.write_text("id: story\ndescription: Story.\n" + extra, encoding="utf-8")
    with pytest.raises(StoryConfigurationError, match="Invalid Story input"):
        load_story_document(path)


@pytest.mark.parametrize(
    "text",
    [
        "raw prose is not a document",
        "[]",
        "null",
        "id: story",
        "description: Story.",
        "id: ../story\ndescription: Story.",
        "id: story\ndescription: '   '",
    ],
)
def test_document_requires_id_and_description_mapping(tmp_path, text):
    path = tmp_path / "story.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(
        StoryConfigurationError, match="requires an explicit id|Invalid Story input"
    ):
        load_story_document(path)


def test_only_current_yaml_format_is_supported(tmp_path):
    path = tmp_path / "story.txt"
    path.write_text("id: story\ndescription: Story.", encoding="utf-8")
    with pytest.raises(StoryConfigurationError, match=".yaml"):
        load_story_document(path)


def test_direct_document_can_omit_id():
    document = StoryDocument(description="A quiet station.")
    assert document.id is None
    assert resolve_story_input(document).request.source_prompt_stem is None


def test_io_errors_are_configuration_errors(tmp_path):
    with pytest.raises(StoryConfigurationError, match="missing.yaml"):
        load_story_document(tmp_path / "missing.yaml")
    path = tmp_path / "directory.yaml"
    path.mkdir()
    with pytest.raises(StoryConfigurationError, match="directory.yaml"):
        load_story_document(path)


@pytest.mark.parametrize("document", ["README.md", "docs/story-pipeline.md"])
def test_documented_yaml_examples_use_the_current_contract(tmp_path, document):
    root = Path(__file__).resolve().parents[1]
    blocks = re.findall(
        r"```yaml\n(.*?)```", (root / document).read_text(encoding="utf-8"), re.DOTALL
    )
    examples = [block for block in blocks if block.startswith("id:")]
    assert examples
    for example in examples:
        value = yaml.safe_load(example)
        if "entries" in value:
            catalog = CatalogDocument.model_validate(value)
            assert catalog.entries
            assert catalog.slots
            continue
        path = tmp_path / "example.yaml"
        path.write_text(example, encoding="utf-8")
        loaded = load_story_document(path)
        assert loaded.description
        assert not {"generation", "runtime", "validation", "policy"} & value.keys()


@pytest.mark.parametrize(
    "field", ["theme_count", "frames_per_theme", "output_languages"]
)
def test_visual_requirements_reject_execution_requirements(tmp_path, field):
    path = tmp_path / "story.yaml"
    path.write_text(
        f"id: visual\ndescription: A quiet station.\nrequirements:\n  {field}: null\n",
        encoding="utf-8",
    )
    with pytest.raises(StoryConfigurationError, match=field):
        load_story_document(path)
