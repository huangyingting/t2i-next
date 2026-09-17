from __future__ import annotations

import pytest

from t2i_story_pipeline.documents import load_story_document
from t2i_story_pipeline.errors import StoryConfigurationError


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
    assert document.generation.theme_count == 1
    assert document.generation.frames_per_theme == 6
    assert document.runtime.concurrency == 8
    assert document.runtime.generation_retries == 2
    assert document.validation.quality.mode == "report"
    assert document.validation.quality.checks == ()
    assert document.authoring.themes == ()


def test_yaml_off_is_a_mode_not_a_boolean(tmp_path):
    path = tmp_path / "story.yaml"
    path.write_text(
        "id: story\ndescription: Story.\n"
        "validation:\n"
        "  quality:\n"
        "    mode: off\n"
        "    checks:\n"
        "      - type: prose_length\n"
        "        min_chars: 5\n"
        "        max_chars: 20\n",
        encoding="utf-8",
    )
    assert load_story_document(path).validation.quality.mode == "off"


@pytest.mark.parametrize(
    "extra",
    [
        "unknown: value",
        "runtime: {unknown: 1}",
        "runtime: {concurrency: true}",
        "runtime: {concurrency: '3'}",
        "runtime: {concurrency: 0}",
        "runtime: {generation_retries: -1}",
        "generation: {theme_count: 101}",
        "generation: {frames_per_theme: 7}",
        "generation: {content_level: unknown}",
        "generation: {cast: {female_count: 0, male_count: 0}}",
        "generation: {cast: {female_count: 8, male_count: 1}}",
        "validation: {quality: {mode: false}}",
        "validation: {quality: {mode: unknown}}",
        "validation: {quality: {checks: [camera_evidence]}}",
        "validation: {quality: {mode: off, checks: [{type: unknown}]}}",
        "validation: {quality: {checks: [{type: prose_length, min_chars: 0}]}}",
        "validation: {quality: {checks: [{type: prose_length, min_chars: '3'}]}}",
        "validation:\n  quality:\n    checks:\n"
        "      - {type: prose_length, min_chars: 10, max_chars: 5}",
        "validation: {quality: {checks: [{type: required_text, values: []}]}}",
        "validation:\n  quality:\n    checks:\n"
        "      - {type: camera_evidence}\n      - {type: camera_evidence}",
        "authoring: {frames: ['']}",
        'authoring: {themes: ["two\\nlines"]}',
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
    with pytest.raises(StoryConfigurationError, match="故事文档无效"):
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
    with pytest.raises(StoryConfigurationError, match="故事文档无效"):
        load_story_document(path)


def test_only_current_yaml_format_is_supported(tmp_path):
    path = tmp_path / "story.txt"
    path.write_text("id: story\ndescription: Story.", encoding="utf-8")
    with pytest.raises(StoryConfigurationError, match=".yaml"):
        load_story_document(path)


def test_io_errors_are_configuration_errors(tmp_path):
    with pytest.raises(StoryConfigurationError, match="无法读取"):
        load_story_document(tmp_path / "missing.yaml")
    path = tmp_path / "directory.yaml"
    path.mkdir()
    with pytest.raises(StoryConfigurationError, match="无法读取"):
        load_story_document(path)
