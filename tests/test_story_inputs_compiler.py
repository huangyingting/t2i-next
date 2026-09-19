"""Neutral, isolated compiler fixtures; no repository input data or providers."""

from __future__ import annotations

import json
import shutil
import string
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.inputs import (
    CatalogDocument,
    InputOverrides,
    ResolvedStoryInput,
    StoryDocument,
    StoryRunConfiguration,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.inputs.loader import load_yaml_model
from t2i_story_pipeline.inputs.schema import FrameAssignment, ModuleDocument
from t2i_story_pipeline.models import (
    ContentLevel,
    QualityMode,
    StoryAuthoring,
    StoryStage,
)


@pytest.fixture
def asset_root() -> Iterator[Path]:
    root = Path.cwd() / f".story-input-fixture-{uuid.uuid4().hex}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root)


def write_yaml(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")
    return path


def module(
    root: Path,
    module_id: str = "neutral-layout",
    kind: str = "layout_multiview",
    **fields: object,
) -> None:
    write_yaml(
        root / "_modules" / f"{module_id}.yaml",
        {"id": module_id, "kind": kind, **fields},
    )


def document(**fields: object) -> StoryDocument:
    return StoryDocument.model_validate(
        {"id": "neutral-input", "description": "A neutral studio portrait.", **fields}
    )


def alphabet(root: Path, *, cast: dict[str, int] | None = None) -> None:
    write_yaml(
        root / "_catalogs" / "neutral-alphabet.yaml",
        {
            "id": "neutral-alphabet",
            "entries": [
                {
                    "id": letter,
                    "themes": [f"Theme fact for {letter}."],
                    "frames": [f"Frame fact for {letter}."],
                    **({"cast": dict(cast)} if cast is not None else {}),
                }
                for letter in string.ascii_lowercase
            ],
            "diversity_order": list(reversed(string.ascii_lowercase)),
        },
    )


def allocated(**fields: object) -> StoryDocument:
    return document(
        allocation={"type": "alphabet_coverage", "catalog": "neutral-alphabet"},
        **fields,
    )


def test_minimal_direct_and_yaml_have_explicit_source_identity(
    asset_root: Path,
) -> None:
    direct = resolve_story_input(StoryDocument(description="A still life."))
    assert direct.request.source_prompt_stem is None
    assert direct.plans[0].theme_id == "T001"
    assert direct.plans[0].cast.total is None
    path = write_yaml(
        asset_root / "input.yaml", {"id": "neutral", "description": "Art."}
    )
    loaded = load_story_document(path)
    resolved = resolve_story_input(loaded)
    assert resolved.request.source_prompt_stem == "neutral"
    assert resolved.sources[0].path == str(path.resolve())
    for value in ({"description": "Art."}, {"id": None, "description": "Art."}):
        write_yaml(path, value)
        with pytest.raises(StoryConfigurationError, match="explicit id"):
            load_story_document(path)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "id: neutral\nid: duplicate\ndescription: Art.",
        "id: neutral\ndescription: Art.\nauthoring:\n  themes:\n    common: &a [x]",
        "id: neutral\ndescription: *missing",
        "id: neutral\ndescription: Art.\ngeneration:\n  <<: {theme_count: 2}",
        "id: neutral\ndescription: !!python/object/apply:os.system ['false']",
        "id: neutral\ndescription: Art.\n1: invalid",
        "id: neutral\ndescription: Art.\ninclude: elsewhere.yaml",
        "id: neutral\ndescription: Art.\nauthoring:\n  themes: [old shape]",
        "id: neutral\ndescription: Art.\n---\nid: second\ndescription: More.",
    ],
)
def test_strict_document_yaml_rejections(asset_root: Path, text: str) -> None:
    path = asset_root / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(StoryConfigurationError, match="bad.yaml"):
        load_story_document(path)


@pytest.mark.parametrize("suffix", [".txt", ".yml", ".json"])
def test_loader_only_accepts_current_yaml_format(asset_root: Path, suffix: str) -> None:
    path = asset_root / f"input{suffix}"
    path.write_text("id: neutral\ndescription: Art.", encoding="utf-8")
    with pytest.raises(StoryConfigurationError, match=".yaml"):
        load_story_document(path)


def test_loader_wraps_missing_and_non_utf8_files(asset_root: Path) -> None:
    path = asset_root / "missing.yaml"
    with pytest.raises(StoryConfigurationError, match="missing.yaml"):
        load_story_document(path)
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(StoryConfigurationError, match="missing.yaml"):
        load_story_document(path)


@pytest.mark.parametrize("level", list(ContentLevel))
def test_stage_and_enum_branches_only_select_effective_level(
    asset_root: Path, level: ContentLevel
) -> None:
    authoring = {
        **{
            stage: {"common": [f"{stage} common marker"]}
            for stage in ("themes", "frames")
        },
        "level_refinements": {
            item.value: {
                stage: [f"{stage} {item.value} selected marker"]
                for stage in ("themes", "frames")
            }
            for item in ContentLevel
        },
    }
    module(asset_root, authoring=authoring)
    value = document(
        authoring=authoring,
        modules=[
            {
                "id": "neutral-layout",
                "parameters": {"layout": "grid", "rows": 2, "columns": 3},
            }
        ],
    )
    resolved = resolve_story_input(
        value, InputOverrides(content_level=level), asset_root=asset_root
    )
    for stage in ("themes", "frames"):
        rules = getattr(resolved.rules, stage)
        assert f"{stage} common marker" in rules
        for candidate in ContentLevel:
            assert (f"{stage} {candidate.value} selected marker" in rules) == (
                candidate == level
            )
        other = "frames" if stage == "themes" else "themes"
        assert not any(other + " common marker" in text for text in rules)
    context = resolved.modules[0].model_dump(mode="json")
    assert context == {
        "id": "neutral-layout",
        "kind": "layout_multiview",
        "parameters": {
            "layout": "grid",
            "rows": 2,
            "columns": 3,
            "min_views": None,
            "max_views": None,
        },
    }
    assert "authoring" not in context


@pytest.mark.parametrize(
    "authoring",
    [
        {"themes": ["old shape"]},
        {"frames": {"common": ["first\nsecond"]}},
        {"level_refinements": {"unknown": {"themes": ["rule"]}}},
        {"themes": {"common": [" "]}},
    ],
)
def test_authoring_rejects_old_arrays_unknown_levels_and_multiline_rules(
    authoring: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        StoryAuthoring.model_validate(authoring)


def test_resolved_input_has_no_nationality_or_country_defaults() -> None:
    resolved = resolve_story_input(document())
    core = resolve_story_rules(resolved.request)
    for rules in (core.themes, core.frames):
        assert not any("分别默认为中国籍" in rule for rule in rules)
        assert not any("场景国家默认为中国" in rule for rule in rules)
        assert any("unmistakable adult" in rule for rule in rules)
        assert any("input_context plans" in rule for rule in rules)
        assert any("sole authority for cast scope" in rule for rule in rules)
        assert any("including plans with no catalog entry" in rule for rule in rules)
    for rules in (resolved.rules.themes, resolved.rules.frames):
        assert not any("分别默认为中国籍" in rule for rule in rules)
        assert not any("场景国家默认为中国" in rule for rule in rules)
    assert all(source.kind != "policy" for source in resolved.sources)


def test_overrides_preserve_zero_and_ignore_none() -> None:
    value = document(
        cast={"female_count": 1, "male_count": 1},
    )
    configuration = StoryRunConfiguration(
        runtime={"generation_retries": 3, "concurrency": 4},
        validation={"themes": {"mode": "enforce"}, "frames": {"mode": "report"}},
    )
    resolved = resolve_story_input(
        value,
        InputOverrides(
            female_count=0,
            male_count=None,
            generation_retries=0,
            concurrency=None,
            theme_count=3,
            frames_per_theme=2,
            theme_batch_size=2,
            theme_output_tokens=7000,
            frame_output_tokens=8000,
            theme_quality_mode="off",
            frame_quality_mode="enforce",
            output_language="english",
        ),
        run_configuration=configuration,
    )
    assert resolved.request.female_count == 0
    assert resolved.request.male_count == 1
    assert resolved.runtime.generation_retries == 0
    assert resolved.runtime.concurrency == 4
    assert resolved.runtime.theme_batch_size == 2
    assert resolved.runtime.theme_output_tokens == 7000
    assert resolved.runtime.frame_output_tokens == 8000
    assert resolved.request.frames_per_theme == 2
    assert resolved.request.output_language == "english"
    assert resolved.quality.themes.mode == QualityMode.OFF
    assert resolved.quality.frames.mode == QualityMode.ENFORCE
    assert len(resolved.plans) == 3
    assert value.cast.female_count == 1
    assert configuration.runtime.generation_retries == 3
    assert configuration.validation.themes.mode == QualityMode.ENFORCE


def test_yaml_rejects_quality_controls(asset_root: Path) -> None:
    path = asset_root / "quality.yaml"
    path.write_text(
        "id: neutral\ndescription: Art.\nvalidation:\n  frames:\n    mode: off\n",
        encoding="utf-8",
    )
    with pytest.raises(StoryConfigurationError, match="validation"):
        load_story_document(path)


@pytest.mark.parametrize(
    ("requirement", "cast", "override", "error"),
    [
        (
            {"allowed_casts": [{"female_count": 1, "male_count": 1}]},
            {"female_count": 1, "male_count": 1},
            {"female_count": 0},
            "allowed_casts",
        ),
        (
            {"female_count": {"min": 1, "max": 2}},
            {"female_count": 1},
            {"female_count": 0},
            "female_count",
        ),
        (
            {"male_count": {"max": 1}},
            {"male_count": 1},
            {"male_count": 2},
            "male_count",
        ),
        (
            {"content_levels": ["aesthetic"]},
            {},
            {"content_level": "erotic"},
            "content_level",
        ),
        (
            {"cast_constraints": "unspecified"},
            {},
            {"female_count": 0},
            "unspecified",
        ),
    ],
)
def test_requirements_rechecked_after_explicit_overrides(
    requirement: dict[str, object],
    cast: dict[str, object],
    override: dict[str, object],
    error: str,
) -> None:
    value = document(requirements=requirement, cast=cast)
    resolve_story_input(value)
    with pytest.raises(StoryConfigurationError, match=error):
        resolve_story_input(value, InputOverrides.model_validate(override))


def test_explicit_run_cast_is_checked_instead_of_unused_visual_defaults() -> None:
    value = document(
        cast={"female_count": 2, "male_count": 0},
        requirements={"allowed_casts": [{"female_count": 1, "male_count": 0}]},
    )
    with pytest.raises(StoryConfigurationError, match="allowed_casts"):
        resolve_story_input(value)
    resolved = resolve_story_input(value, InputOverrides(female_count=1))
    assert resolved.request.female_count == 1


def test_quality_off_cannot_disable_applicability_or_core_safety() -> None:
    value = document(requirements={"content_levels": ["aesthetic"]})
    overrides = InputOverrides(
        theme_quality_mode="off", frame_quality_mode="off", content_level="erotic"
    )
    with pytest.raises(StoryConfigurationError, match="content_level"):
        resolve_story_input(value, overrides)
    resolved = resolve_story_input(
        value, InputOverrides(theme_quality_mode="off", frame_quality_mode="off")
    )
    assert any("unmistakable adult" in rule for rule in resolved.rules.frames)


@pytest.mark.parametrize(
    "requirement",
    [
        {"theme_count": {"min": 3, "max": 1}},
        {"female_count": {"min": -1}},
        {"output_languages": []},
        {"content_levels": []},
        {"allowed_casts": []},
        {"allowed_casts": [{"female_count": 8, "male_count": 1}]},
        {"allowed_casts": [{"female_count": 0, "male_count": 0}]},
        {"cast_constraints": "any"},
    ],
)
def test_requirement_schemas_reject_empty_or_impossible_contracts(
    requirement: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        document(requirements=requirement)


def test_missing_counts_are_not_silently_zero_or_filled_from_requirements() -> None:
    value = document(
        cast={"female_count": 1},
        requirements={"allowed_casts": [{"female_count": 1, "male_count": 0}]},
    )
    with pytest.raises(StoryConfigurationError, match="unspecified"):
        resolve_story_input(value)
    assert resolve_story_input(document()).request.male_count is None


@pytest.mark.parametrize(
    "cast",
    [
        {"scope": "visitors", "female_count": 1},
        {
            "scope": "visitors",
            "female_count": 8,
            "male_count": 0,
            "fixed_roles": [{"id": "host", "sex": "theme_choice"}],
        },
        {"fixed_roles": [{"id": "host", "sex": "female"}]},
        {
            "scope": "visitors",
            "female_count": 1,
            "male_count": 0,
            "fixed_roles": [
                {"id": "host", "sex": "female"},
                {"id": "host", "sex": "male"},
            ],
        },
        {"female_count": True},
    ],
)
def test_invalid_scoped_or_over_capacity_cast_defaults(cast: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        document(cast=cast)


def test_fixed_roles_count_toward_capacity_but_leave_sex_to_theme() -> None:
    value = document(
        cast={
            "scope": "visitors",
            "female_count": 6,
            "male_count": 1,
            "fixed_roles": [{"id": "host", "sex": "theme_choice"}],
        },
    )
    resolved = resolve_story_input(
        value, run_configuration=StoryRunConfiguration(generation={"theme_count": 2})
    )
    assert [plan.cast.total for plan in resolved.plans] == [8, 8]
    assert all(
        plan.cast.fixed_roles[0].sex == "theme_choice" for plan in resolved.plans
    )
    with pytest.raises(StoryConfigurationError, match="exceeds 8"):
        resolve_story_input(value, InputOverrides(female_count=7))


def test_cast_scope_is_a_plain_named_group_not_a_catalog_or_executable_key() -> None:
    resolved = resolve_story_input(
        document(
            cast={
                "scope": "ordinary visitors",
                "female_count": 1,
                "male_count": 0,
                "fixed_roles": [{"id": "host", "sex": "male"}],
            }
        )
    )
    assert resolved.plans[0].cast.scope == "ordinary visitors"
    assert resolved.plans[0].cast.total == 2


@pytest.mark.parametrize(
    ("kind", "parameters"),
    [
        ("layout_multiview", {"layout": "grid", "rows": 2, "columns": 3}),
        ("layout_multiview", {"layout": "collage", "min_views": 2, "max_views": 4}),
        ("visible_copy", {"product": "poster"}),
        ("visible_copy", {"product": "magazine_cover", "ascii": "required"}),
        ("visible_copy", {"product": "sleeve", "copy_language": "english"}),
        ("visible_copy", {"product": "graphic"}),
        ("silk_painting", {}),
    ],
)
def test_all_registered_module_parameter_variants(
    asset_root: Path, kind: str, parameters: dict[str, object]
) -> None:
    module(asset_root, "neutral-module", kind)
    value = document(modules=[{"id": "neutral-module", "parameters": parameters}])
    resolved = resolve_story_input(value, asset_root=asset_root)
    assert resolved.modules[0].kind == kind


@pytest.mark.parametrize(
    ("kind", "parameters"),
    [
        ("layout_multiview", {"layout": "unknown"}),
        ("layout_multiview", {"layout": "grid", "rows": 2}),
        ("layout_multiview", {"layout": "collage", "rows": 2, "columns": 2}),
        ("layout_multiview", {"layout": "grid", "min_views": 3, "max_views": 2}),
        (
            "layout_multiview",
            {"layout": "grid", "rows": 2, "columns": 3, "max_views": 5},
        ),
        ("visible_copy", {"product": "poster", "ascii": True}),
        ("visible_copy", {"product": "poster", "copy_language": "chinese"}),
        ("visible_copy", {"product": "unknown"}),
        ("silk_painting", {"script": "do_something()"}),
    ],
)
def test_invalid_typed_module_parameters_are_source_aware(
    asset_root: Path, kind: str, parameters: dict[str, object]
) -> None:
    module(asset_root, "neutral-module", kind)
    value = document(modules=[{"id": "neutral-module", "parameters": parameters}])
    with pytest.raises(StoryConfigurationError, match="neutral-module.yaml"):
        resolve_story_input(value, asset_root=asset_root)


def test_independent_module_kinds_combine_without_overwriting_constraints(
    asset_root: Path,
) -> None:
    module(
        asset_root,
        "layout",
        requirements={
            "female_count": {"max": 4},
            "content_levels": ["aesthetic", "erotic"],
        },
    )
    module(
        asset_root,
        "copy",
        "visible_copy",
        requirements={"female_count": {"max": 2}},
    )
    value = document(
        cast={"female_count": 1, "male_count": 0},
        modules=[
            {"id": "layout", "parameters": {"layout": "grid"}},
            {"id": "copy", "parameters": {"product": "poster"}},
        ],
    )
    assert len(resolve_story_input(value, asset_root=asset_root).modules) == 2
    with pytest.raises(StoryConfigurationError, match="copy.*female_count"):
        resolve_story_input(
            value, InputOverrides(female_count=3), asset_root=asset_root
        )
    with pytest.raises(StoryConfigurationError, match="layout.*content_level"):
        resolve_story_input(
            value, InputOverrides(content_level="hardcore"), asset_root=asset_root
        )
    module(
        asset_root,
        "copy",
        "visible_copy",
        requirements={"content_levels": ["hardcore"]},
    )
    with pytest.raises(StoryConfigurationError, match="content_level"):
        resolve_story_input(value, asset_root=asset_root)


def test_duplicate_modules_and_capability_owners_reject(asset_root: Path) -> None:
    with pytest.raises(ValidationError, match="module IDs"):
        document(modules=[{"id": "same"}, {"id": "same"}])
    module(asset_root, "first")
    module(asset_root, "second")
    value = document(
        modules=[
            {"id": name, "parameters": {"layout": "grid"}}
            for name in ("first", "second")
        ]
    )
    with pytest.raises(StoryConfigurationError, match="first and second"):
        resolve_story_input(value, asset_root=asset_root)


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "python_plugin"},
        {"modules": [{"id": "nested"}]},
        {"include": "other.yaml"},
        {"runtime": {"concurrency": 1}},
        {"parameters": {"arbitrary_schema": "str"}},
    ],
)
def test_module_files_cannot_execute_code_or_include_dependencies(
    asset_root: Path, fields: dict[str, object]
) -> None:
    data = {"id": "closed", "kind": "silk_painting", **fields}
    path = write_yaml(asset_root / "_modules" / "closed.yaml", data)
    with pytest.raises(StoryConfigurationError, match="closed.yaml"):
        load_yaml_model(path, ModuleDocument)


@pytest.mark.parametrize("directory", ["_modules", "_catalogs"])
def test_assets_share_strict_duplicate_and_alias_yaml_loader(
    asset_root: Path, directory: str
) -> None:
    path = asset_root / directory / "bad.yaml"
    path.parent.mkdir()
    model = ModuleDocument if directory == "_modules" else CatalogDocument
    for text in (
        "id: bad\nid: duplicate",
        "id: bad\nentries: &entries []",
        "id: bad\nentries: *undefined",
        "id: bad\nscript: !!python/name:os.system",
    ):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(StoryConfigurationError, match="bad.yaml"):
            load_yaml_model(path, model)


@pytest.mark.parametrize(
    "asset_id", ["../escape", "/absolute", "https://host/a", "a/b"]
)
def test_asset_ids_reject_paths_and_remote_urls(asset_id: str) -> None:
    with pytest.raises(ValidationError):
        document(modules=[{"id": asset_id}])
    with pytest.raises(ValidationError):
        document(allocation={"type": "fixed_slots", "catalog": asset_id})


def test_asset_root_is_explicit_or_document_relative_never_cwd(
    asset_root: Path,
) -> None:
    module(asset_root)
    value = document(
        modules=[{"id": "neutral-layout", "parameters": {"layout": "grid"}}]
    )
    with pytest.raises(StoryConfigurationError, match="explicit asset_root"):
        resolve_story_input(value)
    path = write_yaml(asset_root / "neutral.yaml", value.model_dump(mode="json"))
    assert (
        resolve_story_input(load_story_document(path)).modules[0].id == "neutral-layout"
    )
    elsewhere = asset_root / "elsewhere"
    elsewhere.mkdir()
    with pytest.raises(StoryConfigurationError, match="elsewhere"):
        resolve_story_input(load_story_document(path), asset_root=elsewhere)


@pytest.mark.parametrize("directory", ["_modules", "_catalogs"])
@pytest.mark.parametrize("directory_symlink", [False, True])
def test_assets_cannot_escape_root_via_symlinks(
    asset_root: Path, directory: str, directory_symlink: bool
) -> None:
    inside = asset_root / "inside"
    outside = asset_root / "outside"
    inside.mkdir()
    outside.mkdir()
    if directory == "_modules":
        module(outside, "escaped", "silk_painting")
        value = document(modules=[{"id": "escaped"}])
    else:
        write_yaml(
            outside / directory / "escaped.yaml",
            {"id": "escaped", "entries": [{"id": "one"}], "slots": ["one"]},
        )
        value = document(allocation={"type": "fixed_slots", "catalog": "escaped"})
    if directory_symlink:
        (inside / directory).symlink_to(outside / directory, target_is_directory=True)
    else:
        (inside / directory).mkdir()
        (inside / directory / "escaped.yaml").symlink_to(
            outside / directory / "escaped.yaml"
        )
    with pytest.raises(StoryConfigurationError, match="escapes asset root"):
        resolve_story_input(value, asset_root=inside)


def test_asset_missing_mismatched_ids_and_directories_are_errors(
    asset_root: Path,
) -> None:
    value = document(modules=[{"id": "wanted"}])
    with pytest.raises(StoryConfigurationError, match="wanted.yaml"):
        resolve_story_input(value, asset_root=asset_root)
    path = write_yaml(
        asset_root / "_modules" / "wanted.yaml",
        {"id": "different", "kind": "silk_painting"},
    )
    with pytest.raises(StoryConfigurationError, match="module id must match"):
        resolve_story_input(value, asset_root=asset_root)
    path.unlink()
    path.mkdir()
    with pytest.raises(StoryConfigurationError, match="not a file"):
        resolve_story_input(value, asset_root=asset_root)


@pytest.mark.parametrize("count", [1, 7, 25, 26, 27, 100])
def test_alphabet_plans_are_run_global_not_batch_local(
    asset_root: Path, count: int
) -> None:
    alphabet(asset_root, cast={"total": 2, "min_female": 1})
    value = allocated(requirements={"cast_constraints": "unspecified"})
    configuration = StoryRunConfiguration(generation={"theme_count": count})
    resolved = resolve_story_input(
        value, run_configuration=configuration, asset_root=asset_root
    )
    expected = (
        list(reversed(string.ascii_lowercase))[:count]
        if count < 26
        else [string.ascii_lowercase[index % 26] for index in range(count)]
    )
    assert [plan.entry.id for plan in resolved.plans] == expected
    assert [plan.theme_id for plan in resolved.plans] == [
        f"T{index:03d}" for index in range(1, count + 1)
    ]
    for plan, letter in zip(resolved.plans, expected, strict=True):
        assert plan.cast.total == 2
        assert plan.cast.min_female == 1
        assert plan.cast.female_count is None
        payload = plan.model_dump(mode="json")
        assert payload["entry"]["themes"] == [f"Theme fact for {letter}."]
        assert payload["entry"]["frames"] == [f"Frame fact for {letter}."]
        assert plan.catalog_id == "neutral-alphabet"
    rebatched = resolve_story_input(
        value,
        InputOverrides(theme_batch_size=1),
        run_configuration=configuration,
        asset_root=asset_root,
    )
    assert resolved.plans == rebatched.plans
    assert not any("Theme fact for" in rule for rule in resolved.rules.themes)


def test_fixed_slots_map_all_100_explicit_entries_and_forbid_truncation(
    asset_root: Path,
) -> None:
    ids = [f"pose-{index:03d}" for index in range(1, 101)]
    write_yaml(
        asset_root / "_catalogs" / "fixed.yaml",
        {
            "id": "fixed",
            "entries": [
                {"id": item_id, "themes": [f"Preserve neutral pose {item_id}."]}
                for item_id in ids
            ],
            "slots": list(reversed(ids)),
        },
    )
    value = document(
        allocation={"type": "fixed_slots", "catalog": "fixed"},
    )
    resolved = resolve_story_input(
        value, InputOverrides(theme_count=100), asset_root=asset_root
    )
    assert [plan.entry.id for plan in resolved.plans] == list(reversed(ids))
    assert resolved.plans[-1].theme_id == "T100"
    with pytest.raises(StoryConfigurationError, match="exactly match"):
        resolve_story_input(
            value, InputOverrides(theme_count=99), asset_root=asset_root
        )


def test_fixed_slots_require_an_explicit_mapping_even_for_one_theme(
    asset_root: Path,
) -> None:
    write_yaml(
        asset_root / "_catalogs" / "fixed.yaml",
        {"id": "fixed", "entries": [{"id": "one"}]},
    )
    with pytest.raises(StoryConfigurationError, match="fixed_slots"):
        resolve_story_input(
            document(allocation={"type": "fixed_slots", "catalog": "fixed"}),
            asset_root=asset_root,
        )


def test_allocation_is_one_closed_typed_document() -> None:
    for allocation in (
        [{"type": "fixed_slots", "catalog": "one"}],
        {"type": "python", "catalog": "one"},
        {"type": "fixed_slots", "catalog": "one", "expression": "index + 1"},
    ):
        with pytest.raises(ValidationError):
            document(allocation=allocation)


@pytest.mark.parametrize(
    "fields",
    [
        {"entries": [{"id": "a"}, {"id": "a"}]},
        {"slots": ["a", "a"]},
        {"slots": ["missing"]},
        {"diversity_order": ["a"]},
        {"diversity_order": ["a", "missing"]},
        {"entries": [{"id": "a", "cast": {"total": 1, "min_female": 2}}]},
        {"entries": [{"id": "a", "cast": {"total": 9}}]},
        {"entries": [{"id": "a", "cast": {"total": 0}}]},
        {"entries": [{"id": "a", "themes": ["multiline\nrule"]}]},
    ],
)
def test_catalog_duplicates_references_permutations_and_cast_feasibility(
    fields: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        CatalogDocument.model_validate(
            {"id": "neutral", "entries": [{"id": "a"}, {"id": "b"}], **fields}
        )


def test_alphabet_requires_26_letters_and_a_diversity_permutation(
    asset_root: Path,
) -> None:
    path = write_yaml(
        asset_root / "_catalogs" / "neutral-alphabet.yaml",
        {"id": "neutral-alphabet", "entries": [{"id": "a"}], "diversity_order": ["a"]},
    )
    with pytest.raises(StoryConfigurationError, match="exactly entries a-z"):
        resolve_story_input(allocated(), asset_root=asset_root)
    write_yaml(
        path,
        {
            "id": "neutral-alphabet",
            "entries": [{"id": item_id} for item_id in string.ascii_lowercase],
        },
    )
    with pytest.raises(StoryConfigurationError, match="explicit diversity_order"):
        resolve_story_input(
            allocated(), InputOverrides(theme_count=26), asset_root=asset_root
        )


def test_catalog_total_can_establish_finite_allowed_casts(asset_root: Path) -> None:
    alphabet(asset_root, cast={"total": 2, "min_female": 1, "min_male": 1})
    value = allocated(
        requirements={"allowed_casts": [{"female_count": 1, "male_count": 1}]}
    )
    resolved = resolve_story_input(
        value, InputOverrides(theme_count=26), asset_root=asset_root
    )
    assert all(plan.cast.total == 2 for plan in resolved.plans)
    assert resolved.request.female_count is None
    with pytest.raises(StoryConfigurationError, match="impossible cast"):
        resolve_story_input(
            value, InputOverrides(female_count=2, male_count=1), asset_root=asset_root
        )


def test_resume_uses_full_frozen_snapshot_after_assets_disappear(
    asset_root: Path,
) -> None:
    alphabet(asset_root)
    module(asset_root, "material", "silk_painting")
    resolved = resolve_story_input(
        allocated(modules=[{"id": "material"}]),
        InputOverrides(theme_count=27),
        asset_root=asset_root,
    )
    frozen = resolved.model_dump_json()
    fingerprint = resolved.fingerprint()
    shutil.rmtree(asset_root / "_catalogs")
    shutil.rmtree(asset_root / "_modules")
    restored = ResolvedStoryInput.model_validate_json(frozen)
    assert restored.fingerprint() == fingerprint
    assert restored.plans == resolved.plans
    assert restored.plans[26].entry.id == "a"
    assert (
        len(
            json.loads(
                next(s.content for s in restored.sources if s.kind == "catalog")
            )["entries"]
        )
        == 26
    )
    assert restored.modules[0].parameters.model_dump() == {}


def test_fingerprints_track_unselected_source_facts_and_selected_parameters(
    asset_root: Path,
) -> None:
    alphabet(asset_root)
    first = resolve_story_input(allocated(), asset_root=asset_root)
    path = asset_root / "_catalogs" / "neutral-alphabet.yaml"
    catalog = load_yaml_model(path, CatalogDocument).model_dump(mode="json")
    catalog["entries"][0]["themes"] = ["Changed unselected source fact."]
    write_yaml(path, catalog)
    second = resolve_story_input(allocated(), asset_root=asset_root)
    assert first.plans == second.plans
    assert first.fingerprint() != second.fingerprint()
    module(asset_root)
    layout = document(
        modules=[{"id": "neutral-layout", "parameters": {"layout": "grid"}}]
    )
    grid = resolve_story_input(layout, asset_root=asset_root)
    layout.modules[0].parameters["layout"] = "collage"
    collage = resolve_story_input(layout, asset_root=asset_root)
    assert grid.fingerprint() != collage.fingerprint()
    assert grid.modules[0].parameters.layout == "grid"


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "wrong_order", "over_capacity", "entry", "cast", "module"],
)
def test_resume_rejects_corrupted_frozen_plans(asset_root: Path, mutation: str) -> None:
    alphabet(asset_root)
    module(asset_root, "material", "silk_painting")
    resolved = resolve_story_input(
        allocated(modules=[{"id": "material"}]),
        InputOverrides(theme_count=27),
        asset_root=asset_root,
    )
    data = resolved.model_dump(mode="json")
    if mutation == "missing":
        data["plans"].pop()
    elif mutation == "duplicate":
        data["plans"][1]["theme_id"] = "T001"
    elif mutation == "wrong_order":
        data["plans"][0], data["plans"][1] = data["plans"][1], data["plans"][0]
    elif mutation == "over_capacity":
        data["plans"][0]["cast"]["total"] = 9
    elif mutation == "entry":
        data["plans"][0]["entry"]["id"] = "b"
    elif mutation == "cast":
        data["plans"][0]["cast"]["female_count"] = 0
    else:
        data["modules"] = []
    with pytest.raises(ValidationError):
        ResolvedStoryInput.model_validate(data)


@pytest.mark.parametrize("field", ["requirements", "themes", "id"])
def test_resume_rejects_source_metadata_diverging_from_full_content(field: str) -> None:
    resolved = resolve_story_input(
        document(requirements={"content_levels": ["aesthetic"]})
    )
    data = resolved.model_dump(mode="json")
    source = data["sources"][0]
    source[field] = {
        "requirements": None,
        "themes": ["Injected stage rule."],
        "id": "different-id",
    }[field]
    with pytest.raises(ValidationError, match="metadata differs"):
        ResolvedStoryInput.model_validate(data)


def test_description_and_filename_never_trigger_hidden_genre_branches(
    asset_root: Path,
) -> None:
    ordinary = document()
    unusual = document(
        id="silk-photographic-alphabet", description=ordinary.description
    )
    left = resolve_story_input(ordinary)
    right = resolve_story_input(unusual, source_path=asset_root / "hidden-layout.yaml")
    assert left.rules == right.rules
    assert left.plans == right.plans
    assert not right.modules
    with pytest.raises(TypeError):
        resolve_story_rules(left.request, user_directory=asset_root)


@pytest.mark.parametrize("stage", list(StoryStage))
def test_context_projects_only_requested_slots_and_stage_rules(
    asset_root: Path, stage: StoryStage
) -> None:
    alphabet(asset_root, cast={"total": 2, "min_female": 1})
    resolved = resolve_story_input(
        allocated(), InputOverrides(theme_count=27), asset_root=asset_root
    )
    context = resolved.context_for(stage, ["T027", "T002"])
    assert set(context) == {"modules", "plans"}
    assert json.loads(json.dumps(context)) == context
    assert [plan["theme_id"] for plan in context["plans"]] == ["T027", "T002"]
    for plan, letter in zip(context["plans"], ("a", "b"), strict=True):
        assert set(plan["entry"]) == {"id", "rules", "cast"}
        prefix = "Theme" if stage == StoryStage.THEMES else "Frame"
        assert plan["entry"]["rules"] == [f"{prefix} fact for {letter}."]
        assert plan["cast"]["total"] == 2
        assert plan["cast"]["female_count"] is None
        assert plan["cast"]["min_female"] == 1
    serialized = json.dumps(context)
    assert str(asset_root) not in serialized
    assert "sources" not in serialized
    assert "content_levels" not in serialized
    assert "level_refinements" not in serialized
    assert (
        "Theme fact" not in serialized
        if stage == StoryStage.FRAMES
        else ("Frame fact" not in serialized)
    )


@pytest.mark.parametrize("stage", list(StoryStage))
@pytest.mark.parametrize("level", list(ContentLevel))
def test_context_modules_follow_selected_stage_authoring(
    asset_root: Path, stage: StoryStage, level: ContentLevel
) -> None:
    module(
        asset_root,
        "layout",
        authoring={"themes": {"common": ["Plan a grid."]}},
    )
    module(
        asset_root,
        "copy",
        "visible_copy",
        authoring={"level_refinements": {"aesthetic": {"frames": ["Visible copy."]}}},
    )
    module(asset_root, "silk", "silk_painting")
    resolved = resolve_story_input(
        document(
            modules=[
                {
                    "id": "layout",
                    "parameters": {"layout": "grid", "rows": 2, "columns": 3},
                },
                {"id": "copy", "parameters": {"product": "poster"}},
                {"id": "silk"},
            ]
        ),
        InputOverrides(content_level=level),
        asset_root=asset_root,
    )
    context = resolved.context_for(stage, ["T001"])
    expected = (
        ["layout"]
        if stage == StoryStage.THEMES
        else (["copy"] if level == ContentLevel.AESTHETIC else [])
    )
    assert [item["id"] for item in context["modules"]] == expected
    for item in context["modules"]:
        assert set(item) == {"id", "kind", "parameters"}
    assert "authoring" not in json.dumps(context)
    assert len(resolved.modules) == 3


@pytest.mark.parametrize("theme_ids", [[], ["T001", "T001"], ["T002"], ["bad-id"]])
def test_context_rejects_empty_duplicate_unknown_or_malformed_theme_selection(
    theme_ids: list[str],
) -> None:
    resolved = resolve_story_input(document())
    with pytest.raises(StoryConfigurationError, match="context"):
        resolved.context_for(StoryStage.THEMES, theme_ids)


@pytest.mark.parametrize("stage", list(StoryStage))
def test_context_preserves_scoped_cast_without_allocation_and_is_detached(
    stage: StoryStage,
) -> None:
    resolved = resolve_story_input(
        document(
            cast={
                "scope": "visitors",
                "female_count": 0,
                "male_count": 1,
                "fixed_roles": [{"id": "host", "sex": "theme_choice"}],
            }
        )
    )
    fingerprint = resolved.fingerprint()
    context = resolved.context_for(stage, ["T001"])
    plan = context["plans"][0]
    assert plan["entry"] is None
    assert plan["catalog_id"] is None
    assert plan["cast"]["female_count"] == 0
    assert plan["cast"]["scope"] == "visitors"
    assert plan["cast"]["total"] == 2
    assert plan["cast"]["fixed_roles"] == [{"id": "host", "sex": "theme_choice"}]
    plan["cast"]["fixed_roles"][0]["sex"] = "female"
    assert resolved.plans[0].cast.fixed_roles[0].sex == "theme_choice"
    assert resolved.fingerprint() == fingerprint


@pytest.mark.parametrize("stage", list(StoryStage))
def test_context_preserves_different_per_theme_cast_facts(
    asset_root: Path, stage: StoryStage
) -> None:
    write_yaml(
        asset_root / "_catalogs" / "cast-table.yaml",
        {
            "id": "cast-table",
            "entries": [
                {
                    "id": "pair",
                    "cast": {"total": 2, "min_female": 1, "min_male": 1},
                },
                {"id": "trio", "cast": {"total": 3, "min_female": 2}},
            ],
            "slots": ["pair", "trio"],
        },
    )
    resolved = resolve_story_input(
        document(
            requirements={"cast_constraints": "unspecified"},
            allocation={"type": "fixed_slots", "catalog": "cast-table"},
        ),
        InputOverrides(theme_count=2),
        asset_root=asset_root,
    )
    context = resolved.context_for(stage, ["T001", "T002"])
    casts = [plan["cast"] for plan in context["plans"]]
    assert [cast["total"] for cast in casts] == [2, 3]
    assert [cast["min_female"] for cast in casts] == [1, 2]
    assert [cast["min_male"] for cast in casts] == [1, 0]
    assert all(cast["female_count"] is None for cast in casts)
    assert all(cast["male_count"] is None for cast in casts)


@pytest.mark.parametrize("stage", list(StoryStage))
def test_background_bands_preserve_model_choice_and_count_every_adult(
    stage: StoryStage,
) -> None:
    bands = [
        {"min": 0, "max": 0},
        {"min": 2, "max": 5},
        {"min": 6, "max": 15},
        {"min": 16, "max": 30},
    ]
    resolved = resolve_story_input(
        document(
            cast={
                "scope": "primary_people",
                "female_count": 2,
                "male_count": 1,
                "background_counts": bands,
            }
        )
    )
    cast = resolved.context_for(stage, ["T001"])["plans"][0]["cast"]
    assert cast["background_counts"] == bands
    assert cast["principal_total"] == 3
    assert cast["total"] is None
    assert cast["total_min"] == 3
    assert cast["total_max"] == 33
    assert not any(
        band["min"] <= 1 <= band["max"] for band in cast["background_counts"]
    )
    assert all("chosen" not in field for field in cast)


@pytest.mark.parametrize(
    "bands",
    [
        [{"min": -1, "max": 0}],
        [{"min": 0, "max": 31}],
        [{"min": 3, "max": 2}],
        [{"min": 2, "max": 5}, {"min": 5, "max": 8}],
        [{"min": 2, "max": 5}, {"min": 2, "max": 5}],
        [{"min": 6, "max": 15}, {"min": 2, "max": 7}],
        [{"min": 0, "max": True}],
        [{"min": 0}],
    ],
)
def test_background_bands_reject_invalid_ranges_overlaps_and_duplicates(
    bands: list[dict[str, object]],
) -> None:
    with pytest.raises(ValidationError):
        document(
            cast={
                "scope": "primary_people",
                "female_count": 1,
                "male_count": 1,
                "background_counts": bands,
            }
        )


@pytest.mark.parametrize(
    "cast",
    [
        {"female_count": 1, "male_count": 1},
        {"scope": "primary_people", "female_count": 1},
        {"scope": "primary_people", "male_count": 1},
    ],
)
def test_background_population_needs_explicit_scope_and_both_principal_counts(
    cast: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        document(
            cast={
                **cast,
                "background_counts": [{"min": 0, "max": 30}],
            }
        )


def test_background_capacity_does_not_relax_requested_plus_fixed_limit() -> None:
    value = document(
        cast={
            "scope": "visitors",
            "female_count": 7,
            "male_count": 0,
            "fixed_roles": [{"id": "host", "sex": "theme_choice"}],
            "background_counts": [{"min": 0, "max": 30}],
        }
    )
    resolved = resolve_story_input(value)
    cast = resolved.plans[0].cast
    assert cast.principal_total == 8
    assert cast.total is None
    assert cast.total_min == 8
    assert cast.total_max == 38
    assert cast.fixed_roles[0].sex == "theme_choice"
    with pytest.raises(StoryConfigurationError, match="principal cast"):
        resolve_story_input(value, InputOverrides(female_count=8))


@pytest.mark.parametrize(
    ("bands", "principal_total", "total", "total_min", "total_max"),
    [
        ([], 2, 2, 2, 2),
        ([{"min": 0, "max": 0}], 2, 2, 2, 2),
        ([{"min": 2, "max": 2}], 2, 4, 4, 4),
        ([{"min": 4, "max": 6}, {"min": 0, "max": 1}], 2, None, 2, 8),
    ],
)
def test_exact_population_only_when_determined(
    bands: list[dict[str, int]],
    principal_total: int,
    total: int | None,
    total_min: int,
    total_max: int,
) -> None:
    resolved = resolve_story_input(
        document(
            cast={
                "scope": "primary_people",
                "female_count": 1,
                "male_count": 1,
                "background_counts": bands,
            }
        )
    )
    cast = resolved.plans[0].cast
    assert (cast.principal_total, cast.total, cast.total_min, cast.total_max) == (
        principal_total,
        total,
        total_min,
        total_max,
    )
    assert cast.model_dump(mode="json")["background_counts"] == bands


def test_unspecified_principals_remain_unknown_but_have_bounded_total() -> None:
    resolved = resolve_story_input(document())
    cast = resolved.plans[0].cast
    assert cast.principal_total is None
    assert cast.total is None
    assert (cast.total_min, cast.total_max) == (1, 8)
    assert cast.background_counts == ()


@pytest.mark.parametrize(
    "field",
    ["principal_total", "total", "total_min", "total_max", "background_counts"],
)
def test_background_snapshot_roundtrip_and_corruption_rejection(field: str) -> None:
    resolved = resolve_story_input(
        document(
            cast={
                "scope": "primary_people",
                "female_count": 1,
                "male_count": 1,
                "background_counts": [
                    {"min": 0, "max": 0},
                    {"min": 2, "max": 30},
                ],
            }
        )
    )
    restored = ResolvedStoryInput.model_validate_json(resolved.model_dump_json())
    assert restored.fingerprint() == resolved.fingerprint()
    assert restored.context_for(StoryStage.FRAMES, ["T001"]) == resolved.context_for(
        StoryStage.FRAMES, ["T001"]
    )
    corrupted = resolved.model_dump(mode="json")
    corrupted["plans"][0]["cast"][field] = {
        "principal_total": 3,
        "total": 2,
        "total_min": 3,
        "total_max": 31,
        "background_counts": [{"min": 0, "max": 30}],
    }[field]
    with pytest.raises(ValidationError):
        ResolvedStoryInput.model_validate(corrupted)


def test_context_rehydrates_after_assets_disappear(asset_root: Path) -> None:
    alphabet(asset_root)
    module(
        asset_root,
        "material",
        "silk_painting",
        authoring={"frames": {"common": ["Preserve the material surface."]}},
    )
    resolved = resolve_story_input(
        allocated(modules=[{"id": "material"}]),
        InputOverrides(theme_count=27),
        asset_root=asset_root,
    )
    expected = resolved.context_for(StoryStage.FRAMES, ["T026", "T027"])
    frozen = resolved.model_dump_json()
    shutil.rmtree(asset_root / "_catalogs")
    shutil.rmtree(asset_root / "_modules")
    restored = ResolvedStoryInput.model_validate_json(frozen)
    assert restored.context_for(StoryStage.FRAMES, ["T026", "T027"]) == expected
    assert restored.fingerprint() == resolved.fingerprint()


def cyclic_catalog(root: Path, length: int = 30) -> list[str]:
    ids = [f"slot-{index:03d}" for index in range(1, length + 1)]
    write_yaml(
        root / "_catalogs" / "neutral-cycle.yaml",
        {
            "id": "neutral-cycle",
            "entries": [
                {
                    "id": item_id,
                    "themes": [f"Theme fact {item_id}."],
                    "frames": [f"Frame fact {item_id}."],
                }
                for item_id in ids
            ],
            "slots": ids,
        },
    )
    return ids


def cyclic_document() -> StoryDocument:
    return document(
        allocation={"type": "cyclic_slots", "catalog": "neutral-cycle"},
    )


@pytest.mark.parametrize("cycle_length", [4, 30])
@pytest.mark.parametrize("count", [1, 3, 4, 9, 10, 26, 27, 30, 31, 100])
def test_cyclic_slots_use_global_ordinal_and_wrap_only_after_complete_cycle(
    asset_root: Path, cycle_length: int, count: int
) -> None:
    ids = cyclic_catalog(asset_root, cycle_length)
    value = cyclic_document()
    configuration = StoryRunConfiguration(generation={"theme_count": count})
    resolved = resolve_story_input(
        value, run_configuration=configuration, asset_root=asset_root
    )
    assert [plan.entry.id for plan in resolved.plans] == [
        ids[index % cycle_length] for index in range(count)
    ]
    assert [plan.theme_id for plan in resolved.plans] == [
        f"T{index:03d}" for index in range(1, count + 1)
    ]
    for batch_size in (1, 7, 10):
        rebatched = resolve_story_input(
            value,
            InputOverrides(theme_batch_size=batch_size),
            run_configuration=configuration,
            asset_root=asset_root,
        )
        assert rebatched.plans == resolved.plans


def test_cyclic_slots_use_explicit_slot_order_not_entry_order(asset_root: Path) -> None:
    ids = cyclic_catalog(asset_root, 4)
    path = asset_root / "_catalogs" / "neutral-cycle.yaml"
    catalog = load_yaml_model(path, CatalogDocument).model_dump(mode="json")
    catalog["slots"] = list(reversed(ids))
    write_yaml(path, catalog)
    resolved = resolve_story_input(
        cyclic_document(), InputOverrides(theme_count=6), asset_root=asset_root
    )
    assert [plan.entry.id for plan in resolved.plans] == [
        ids[3],
        ids[2],
        ids[1],
        ids[0],
        ids[3],
        ids[2],
    ]


def test_composed_thirty_slot_table_preserves_independent_three_and_ten_cycles(
    asset_root: Path,
) -> None:
    ids = cyclic_catalog(asset_root)
    path = asset_root / "_catalogs" / "neutral-cycle.yaml"
    catalog = load_yaml_model(path, CatalogDocument).model_dump(mode="json")
    for index, entry in enumerate(catalog["entries"]):
        entry["themes"] = [
            f"First dimension {index % 3}.",
            f"Second dimension {index % 10}.",
        ]
    write_yaml(path, catalog)
    resolved = resolve_story_input(
        cyclic_document(), InputOverrides(theme_count=100), asset_root=asset_root
    )
    for index, plan in enumerate(resolved.plans):
        assert plan.entry.id == ids[index % 30]
        assert plan.entry.themes == (
            f"First dimension {index % 3}.",
            f"Second dimension {index % 10}.",
        )
    assert resolved.plans[29].entry.id == ids[-1]
    assert resolved.plans[30].entry.id == ids[0]
    assert resolved.plans[0].entry.themes[1] == "Second dimension 0."
    assert resolved.plans[9].entry.themes[1] == "Second dimension 9."
    assert resolved.plans[10].entry.themes[1] == "Second dimension 0."


def test_cyclic_bucket_seed_order_exhausts_thirty_slots_before_reuse(
    asset_root: Path,
) -> None:
    ids = cyclic_catalog(asset_root)
    path = asset_root / "_catalogs" / "neutral-cycle.yaml"
    catalog = load_yaml_model(path, CatalogDocument).model_dump(mode="json")
    for index, entry in enumerate(catalog["entries"]):
        entry["themes"] = [
            f"Bucket {string.ascii_uppercase[index % 10]}.",
            f"Unique seed {index + 1}.",
        ]
    write_yaml(path, catalog)
    resolved = resolve_story_input(
        cyclic_document(), InputOverrides(theme_count=31), asset_root=asset_root
    )
    assert [plan.entry.id for plan in resolved.plans[:30]] == ids
    assert resolved.plans[0].entry.themes == ("Bucket A.", "Unique seed 1.")
    assert resolved.plans[10].entry.themes == ("Bucket A.", "Unique seed 11.")
    assert resolved.plans[20].entry.themes == ("Bucket A.", "Unique seed 21.")
    assert resolved.plans[30].entry.themes == resolved.plans[0].entry.themes
    smaller = resolve_story_input(
        cyclic_document(), InputOverrides(theme_count=3), asset_root=asset_root
    )
    assert [plan.entry.themes[0] for plan in smaller.plans] == [
        "Bucket A.",
        "Bucket B.",
        "Bucket C.",
    ]


@pytest.mark.parametrize("slots", [None, [], ["one", "one"], ["missing"]])
def test_cyclic_slots_require_explicit_nonempty_unique_resolvable_order(
    asset_root: Path, slots: list[str] | None
) -> None:
    write_yaml(
        asset_root / "_catalogs" / "neutral-cycle.yaml",
        {
            "id": "neutral-cycle",
            "entries": [{"id": "one", "themes": ["One neutral fact."]}],
            **({"slots": slots} if slots is not None else {}),
        },
    )
    with pytest.raises(StoryConfigurationError, match="neutral-cycle"):
        resolve_story_input(cyclic_document(), asset_root=asset_root)


@pytest.mark.parametrize("stage", list(StoryStage))
def test_cyclic_snapshot_context_is_stage_filtered_and_resume_subset_stable(
    asset_root: Path, stage: StoryStage
) -> None:
    ids = cyclic_catalog(asset_root)
    resolved = resolve_story_input(
        cyclic_document(), InputOverrides(theme_count=31), asset_root=asset_root
    )
    frozen = resolved.model_dump_json()
    fingerprint = resolved.fingerprint()
    shutil.rmtree(asset_root / "_catalogs")
    restored = ResolvedStoryInput.model_validate_json(frozen)
    context = restored.context_for(stage, ["T031", "T030", "T001"])
    prefix = "Theme" if stage == StoryStage.THEMES else "Frame"
    assert [plan["entry"]["id"] for plan in context["plans"]] == [
        ids[0],
        ids[-1],
        ids[0],
    ]
    assert [plan["entry"]["rules"] for plan in context["plans"]] == [
        [f"{prefix} fact {item_id}."] for item_id in (ids[0], ids[-1], ids[0])
    ]
    assert str(asset_root) not in json.dumps(context)
    assert (
        "Frame fact" not in json.dumps(context)
        if stage == StoryStage.THEMES
        else ("Theme fact" not in json.dumps(context))
    )
    assert restored.fingerprint() == fingerprint
    corrupt = restored.model_dump(mode="json")
    corrupt["plans"][30]["entry"]["id"] = ids[1]
    with pytest.raises(ValidationError, match="frozen allocation"):
        ResolvedStoryInput.model_validate(corrupt)


def test_cyclic_context_preserves_existing_explicit_frame_assignments(
    asset_root: Path,
) -> None:
    cyclic_catalog(asset_root, 4)
    path = asset_root / "_catalogs" / "neutral-cycle.yaml"
    catalog = load_yaml_model(path, CatalogDocument).model_dump(mode="json")
    catalog["entries"][0]["frame_assignment"] = {
        "slots": [
            {"frame_id": "F01", "rules": ["First view."]},
            {"frame_id": "F02", "rules": ["Second view."]},
        ],
    }
    write_yaml(path, catalog)
    resolved = resolve_story_input(
        cyclic_document(),
        InputOverrides(theme_count=5, frames_per_theme=2),
        asset_root=asset_root,
    )
    theme_context = resolved.context_for(StoryStage.THEMES, ["T005"])
    assert theme_context["plans"][0]["frame_slots"] == []
    frame_context = resolved.context_for(StoryStage.FRAMES, ["T005"], frame_ids=["F02"])
    assert frame_context["plans"][0]["frame_slots"] == [
        {"frame_id": "F02", "rules": ["Second view."]}
    ]


@pytest.mark.parametrize("frames_per_theme", [1, 2, 3, 4, 5, 6])
def test_twelve_slot_cycle_combines_four_theme_bands_and_conditional_three_view_pairs(
    asset_root: Path, frames_per_theme: int
) -> None:
    cyclic_catalog(asset_root, 12)
    path = asset_root / "_catalogs" / "neutral-cycle.yaml"
    catalog = load_yaml_model(path, CatalogDocument).model_dump(mode="json")
    pairs = [
        ("Front view.", "Left view."),
        ("Right view.", "Rear view."),
        ("Front three-quarter view.", "Rear three-quarter view."),
    ]
    for index, entry in enumerate(catalog["entries"]):
        entry["themes"] = [f"Age band {index % 4}."]
        entry["frame_assignment"] = {
            "slots": [
                {"frame_id": f"F{slot:02d}", "rules": [rule]}
                for slot, rule in enumerate(pairs[index % 3], start=1)
            ],
        }
    write_yaml(path, catalog)
    resolved = resolve_story_input(
        cyclic_document(),
        InputOverrides(theme_count=25, frames_per_theme=frames_per_theme),
        asset_root=asset_root,
    )
    for index, plan in enumerate(resolved.plans):
        assert plan.entry.themes == (f"Age band {index % 4}.",)
        theme_context = resolved.context_for(StoryStage.THEMES, [plan.theme_id])
        assert theme_context["plans"][0]["frame_slots"] == []
        frame_context = resolved.context_for(StoryStage.FRAMES, [plan.theme_id])
        slots = frame_context["plans"][0]["frame_slots"]
        assert [slot["rules"][0] for slot in slots] == (
            list(pairs[index % 3]) if frames_per_theme == 2 else []
        )
        if frames_per_theme == 2:
            retry_context = resolved.context_for(
                StoryStage.FRAMES, [plan.theme_id], frame_ids=["F02"]
            )
            assert retry_context["plans"][0]["frame_slots"] == [
                {"frame_id": "F02", "rules": [pairs[index % 3][1]]}
            ]
    assert resolved.plans[0].entry == resolved.plans[12].entry
    restored = ResolvedStoryInput.model_validate_json(resolved.model_dump_json())
    assert restored.fingerprint() == resolved.fingerprint()


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6])
def test_frame_assignment_schema_accepts_complete_bounded_slot_tables(
    count: int,
) -> None:
    value = FrameAssignment.model_validate(
        {
            "slots": [
                {"frame_id": f"F{index:02d}", "rules": [f"View {index}."]}
                for index in range(1, count + 1)
            ],
        }
    )
    assert [slot.frame_id for slot in value.slots] == [
        f"F{index:02d}" for index in range(1, count + 1)
    ]


@pytest.mark.parametrize(
    "value",
    [
        {"slots": []},
        {
            "slots": [
                {"frame_id": f"F{index:02d}", "rules": ["View."]}
                for index in range(1, 8)
            ]
        },
        {"frames_per_theme": 1, "slots": [{"frame_id": "F01", "rules": ["View."]}]},
        {
            "slots": [
                {"frame_id": "F01", "rules": ["View."]},
                {"frame_id": "F01", "rules": ["Duplicate."]},
            ],
        },
        {
            "slots": [
                {"frame_id": "F02", "rules": ["Out of order."]},
                {"frame_id": "F01", "rules": ["View."]},
            ],
        },
        {
            "slots": [
                {"frame_id": "F01", "rules": ["View."]},
                {"frame_id": "F03", "rules": ["Outside declared count."]},
            ],
        },
        {"slots": [{"frame_id": "F01", "rules": []}]},
        {
            "slots": [{"frame_id": "F01", "rules": ["two\nlines"]}],
        },
    ],
)
def test_frame_assignment_schema_rejects_incomplete_duplicate_or_invalid_slots(
    value: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        FrameAssignment.model_validate(value)


def test_frame_context_follows_requested_ids_without_reindexing_saved_slot_facts(
    asset_root: Path,
) -> None:
    cyclic_catalog(asset_root, 4)
    path = asset_root / "_catalogs" / "neutral-cycle.yaml"
    catalog = load_yaml_model(path, CatalogDocument).model_dump(mode="json")
    catalog["entries"][0]["frame_assignment"] = {
        "slots": [
            {"frame_id": "F01", "rules": ["Original first view."]},
            {"frame_id": "F02", "rules": ["Original second view."]},
        ],
    }
    write_yaml(path, catalog)
    resolved = resolve_story_input(
        cyclic_document(),
        InputOverrides(theme_count=5, frames_per_theme=2),
        asset_root=asset_root,
    )
    frozen = resolved.model_dump_json()
    shutil.rmtree(asset_root / "_catalogs")
    restored = ResolvedStoryInput.model_validate_json(frozen)
    retry = restored.context_for(StoryStage.FRAMES, ["T005"], frame_ids=["F02"])
    assert retry["plans"][0]["frame_slots"] == [
        {"frame_id": "F02", "rules": ["Original second view."]}
    ]
    reordered = restored.context_for(
        StoryStage.FRAMES, ["T005"], frame_ids=["F02", "F01"]
    )
    assert reordered["plans"][0]["frame_slots"] == [
        {"frame_id": "F02", "rules": ["Original second view."]},
        {"frame_id": "F01", "rules": ["Original first view."]},
    ]
    theme_context = restored.context_for(StoryStage.THEMES, ["T005"])
    assert "Original first view." not in json.dumps(theme_context)
    assert "Original second view." not in json.dumps(theme_context)


@pytest.mark.parametrize(
    ("stage", "frame_ids"),
    [
        (StoryStage.THEMES, ["F01"]),
        (StoryStage.FRAMES, []),
        (StoryStage.FRAMES, ["F01", "F01"]),
        (StoryStage.FRAMES, ["F03"]),
        (StoryStage.FRAMES, ["not-a-frame"]),
    ],
)
def test_frame_context_rejects_invalid_subsets_before_prompt_construction(
    stage: StoryStage,
    frame_ids: list[str],
) -> None:
    resolved = resolve_story_input(document(), InputOverrides(frames_per_theme=2))
    with pytest.raises(StoryConfigurationError, match="context"):
        resolved.context_for(stage, ["T001"], frame_ids=frame_ids)


def test_visual_cycles_do_not_impose_execution_count_minimums(
    asset_root: Path,
) -> None:
    ids = cyclic_catalog(asset_root, 30)
    value = document(
        allocation={"type": "cyclic_slots", "catalog": "neutral-cycle"},
    )
    resolved = resolve_story_input(
        value, InputOverrides(theme_count=3, theme_batch_size=1), asset_root=asset_root
    )
    assert [plan.entry.id for plan in resolved.plans] == ids[:3]
    for count in (1, 2):
        selected = resolve_story_input(
            value,
            InputOverrides(theme_count=count, theme_quality_mode="off"),
            asset_root=asset_root,
        )
        assert [plan.entry.id for plan in selected.plans] == ids[:count]
