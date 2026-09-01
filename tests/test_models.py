from __future__ import annotations

import pytest
from pydantic import ValidationError

from t2i_prompt_pipeline.errors import ConfigurationError
from t2i_prompt_pipeline.models import (
    ContentLevel,
    Foundation,
    GenerationSpec,
    OutputLanguage,
    PromptBook,
    ProviderSettings,
    RunSettings,
    ThemeBook,
    ThemeSimilaritySettings,
    format_character_id,
    format_frame_id,
    format_theme_id,
    frame_batch_response_model,
    theme_batch_response_model,
)
from tests.factories import make_foundation, make_spec, make_themes


def test_spec_allows_only_adult_character_capacity() -> None:
    with pytest.raises(ValidationError, match="最多包含八名角色"):
        GenerationSpec(
            brief="测试",
            female_count=8,
            male_count=1,
        )


def test_spec_supports_optional_and_male_only_cast_constraints() -> None:
    unconstrained = GenerationSpec(brief="测试")
    spec = GenerationSpec(
        brief="测试",
        female_count=0,
        male_count=2,
    )

    assert unconstrained.female_count is None
    assert unconstrained.male_count is None
    assert spec.female_count == 0
    assert spec.male_count == 2
    with pytest.raises(ValidationError, match="人物约束不能同时为零"):
        GenerationSpec(
            brief="测试",
            female_count=0,
            male_count=0,
        )


def test_ids_scale_without_changing_the_model() -> None:
    theme_id = format_theme_id(100, 100)

    assert theme_id == "T100"
    assert format_character_id(theme_id, 2) == "T100-C02"
    assert format_frame_id(theme_id, 100, 100) == "T100-F100"


def test_content_level_is_a_plain_generation_hint() -> None:
    spec = GenerationSpec(
        brief="测试",
        content_level=ContentLevel.HARDCORE,
    )

    assert spec.content_level == ContentLevel.HARDCORE


def test_output_language_defaults_to_chinese_and_accepts_english() -> None:
    assert GenerationSpec(brief="测试").output_language == OutputLanguage.CHINESE
    assert (
        GenerationSpec(
            brief="test",
            output_language="english",
        ).output_language
        == OutputLanguage.ENGLISH
    )


def test_provider_signature_tracks_generation_behavior_not_token_cap() -> None:
    provider = ProviderSettings(model="model-a", output_token_limit=4096)
    reasoning_provider = ProviderSettings(
        model="model-a",
        reasoning_effort="low",
        temperature=0.2,
    )

    assert provider.signature() == provider.model_copy(
        update={"output_token_limit": 8192}
    ).signature()
    assert provider.signature() == provider.model_copy(
        update={"base_url": f"{provider.base_url}/"}
    ).signature()
    assert provider.signature() != provider.model_copy(
        update={"model": "model-b"}
    ).signature()
    assert reasoning_provider.signature() == reasoning_provider.model_copy(
        update={"temperature": 1.2}
    ).signature()


def test_resume_requires_frozen_theme_similarity_settings() -> None:
    original = RunSettings(
        provider_signature="provider",
        output_token_limit=4096,
        theme_similarity=ThemeSimilaritySettings(
            model="embedding-model",
            dimensions=512,
        ),
    )
    changed = original.model_copy(
        update={
            "theme_similarity": ThemeSimilaritySettings(
                model="embedding-model",
                dimensions=256,
            )
        }
    )

    with pytest.raises(ConfigurationError, match="similarity 配置"):
        original.ensure_resumable_with(changed)


def test_theme_similarity_uses_calibrated_defaults() -> None:
    settings = ThemeSimilaritySettings(model="embedding-model")

    assert settings.scene_threshold == 0.86
    assert settings.style_threshold == 0.815


def test_foundation_semantic_name_is_safe_for_a_filename() -> None:
    values = make_foundation().model_dump()
    values["semantic_name"] = "../unsafe"

    with pytest.raises(ValidationError) as error:
        Foundation.model_validate(values)

    assert error.value.errors()[0]["loc"] == ("semantic_name",)


def test_frame_batch_schema_uses_exact_ids_for_one_theme() -> None:
    model = frame_batch_response_model(
        theme_id="T05",
        frame_ids=(
            "T05-F01",
            "T05-F02",
            "T05-F03",
            "T05-F04",
            "T05-F05",
        ),
        character_ids=("T05-C01", "T05-C02"),
    )
    schema = model.model_json_schema()

    def properties_named(value, name):
        if isinstance(value, dict):
            properties = value.get("properties", {})
            if name in properties:
                yield properties[name]
            for child in value.values():
                yield from properties_named(child, name)
        elif isinstance(value, list):
            for child in value:
                yield from properties_named(child, name)

    assert model.__name__.endswith("T05")
    assert any(
        field.get("const") == "T05"
        for field in properties_named(schema, "theme_id")
    )
    assert any(
        field.get("enum")
        == [
            "T05-F01",
            "T05-F02",
            "T05-F03",
            "T05-F04",
            "T05-F05",
        ]
        for field in properties_named(schema, "frame_id")
    )
    assert any(
        field.get("enum") == ["T05-C01", "T05-C02"]
        for field in properties_named(schema, "character_id")
    )
    assert any(
        field.get("minItems") == 1 and field.get("maxItems") == 2
        for field in properties_named(schema, "characters")
    )


def test_theme_batch_schema_uses_exact_theme_and_character_ids() -> None:
    model = theme_batch_response_model(
        ("T006", "T007"),
        2,
    )
    encoded = str(model.model_json_schema())

    assert "T006" in encoded
    assert "T007" in encoded
    assert "T006-C01" in encoded
    assert "T007-C02" in encoded
    assert "T001-C01" not in encoded
    assert "'minLength': 20" not in encoded
    assert "'maxLength': 60" not in encoded


def test_prompt_book_rejects_theme_that_does_not_match_cast_plan() -> None:
    spec = make_spec(female_count=1, male_count=1)
    foundation = make_foundation(spec)
    theme = make_themes(spec)[0]
    theme.characters = theme.characters[:1]

    with pytest.raises(ValidationError, match="人物数量不符合 Cast Plan"):
        PromptBook(
            semantic_name=foundation.semantic_name,
            cast_plan=foundation.cast_plan,
            themes=[ThemeBook(theme=theme, frames=[])],
        )
