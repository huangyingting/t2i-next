"""External controls, immutable safety, and frozen execution without recipe defaults."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import t2i_story_pipeline.authoring_rules as authoring_rules
import t2i_story_pipeline.cli as cli
from t2i_story_pipeline import (
    StoryDocument,
    StoryRunConfiguration,
    load_run_configuration,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.errors import (
    StoryConfigurationError,
    StoryRunIncompleteError,
    StoryStorageError,
)
from t2i_story_pipeline.inputs import InputOverrides, ResolvedStoryInput
from t2i_story_pipeline.inputs.schema import FrameAssignment, InputRequirements
from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeFrame,
    NarrativeTheme,
    OutputLanguage,
    QualityMode,
    StoryStage,
    TokenUsage,
)
from t2i_story_pipeline.prompts import frame_messages, theme_messages
from t2i_story_pipeline.provider import (
    ModelResponse,
    StoryProviderSettings,
    TextModelResponse,
)
from t2i_story_pipeline.quality_validation import (
    check_frame_quality,
    check_theme_quality,
    writing_constraints,
)
from t2i_story_pipeline.run_store import LocalStoryRunStore, StoryRunSettings
from t2i_story_pipeline.studio import StoryStudio


@pytest.fixture
def workspace() -> Iterator[Path]:
    path = Path.cwd() / f".story-run-config-test-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def configuration_file(workspace: Path, value: object) -> Path:
    path = workspace / "run.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def configuration(**fields: object) -> StoryRunConfiguration:
    return StoryRunConfiguration.model_validate(fields)


def document(**fields: object) -> StoryDocument:
    return StoryDocument.model_validate(
        {"description": "Two adult travelers at a quiet station.", **fields}
    )


def theme() -> NarrativeTheme:
    return NarrativeTheme(
        theme_id="T001",
        title="Station",
        premise="Adult travelers.",
        style="Ink.",
        diversity={
            "subject": "Adult travelers",
            "setting": "A quiet railway station",
            "situation": "Waiting for a train",
            "visual": "Ink drawing",
        },
    )


@pytest.mark.parametrize("name", ["generation", "runtime", "validation", "policy"])
@pytest.mark.parametrize("value", [{}, None, ""])
def test_visual_document_rejects_all_superseded_control_fields(name, value):
    with pytest.raises(ValidationError):
        document(**{name: value})


@pytest.mark.parametrize(
    "name", ["theme_count", "frames_per_theme", "output_languages"]
)
def test_visual_requirements_reject_execution_controls(name):
    with pytest.raises(ValidationError):
        InputRequirements.model_validate({name: None})


def test_frame_assignment_derives_its_count_only_from_slots():
    slots = [
        {"frame_id": "F01", "rules": ["Front view."]},
        {"frame_id": "F02", "rules": ["Rear view."]},
    ]
    assignment = FrameAssignment(slots=slots)
    assert assignment.slot_count == 2
    assert assignment.model_dump(mode="json") == {"slots": slots}
    assert not hasattr(assignment, "frames_per_theme")
    with pytest.raises(ValidationError):
        FrameAssignment(slots=slots, frames_per_theme=2)
    with pytest.raises(ValidationError, match="sequential"):
        FrameAssignment(slots=list(reversed(slots)))


def test_json_loader_accepts_closed_typed_external_configuration(workspace):
    expected = configuration(
        generation={
            "theme_count": 2,
            "frames_per_theme": 3,
            "output_language": "english",
            "content_level": "aesthetic",
            "female_count": 0,
            "male_count": 2,
        },
        runtime={"concurrency": 1, "generation_retries": 0},
        validation={
            "frames": {
                "mode": "off",
                "checks": [
                    {
                        "type": "word_count",
                        "min_words": 2,
                        "max_words": 4,
                        "when_language": "english",
                    }
                ],
            }
        },
    )
    path = configuration_file(workspace, expected.model_dump(mode="json"))
    assert load_run_configuration(path) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"policy": "legacy"},
        {"safety": False},
        {"generation": {"cast": {}}},
        {"generation": {"theme_count": "2"}},
        {"generation": {"theme_count": True}},
        {"generation": {"frames_per_theme": 2.0}},
        {"generation": {"female_count": False}},
        {"generation": {"output_language": "French"}},
        {"runtime": {"concurrency": "1"}},
        {"runtime": {"generation_retries": -1}},
        {"validation": {"frames": {"mode": False}}},
        {"validation": {"frames": {"checks": [{"type": "unknown"}]}}},
        {
            "validation": {
                "frames": {
                    "checks": [{"type": "word_count", "min_words": 4, "max_words": 2}]
                }
            }
        },
    ],
)
def test_json_loader_rejects_unknown_fields_and_invalid_types(workspace, value):
    with pytest.raises(StoryConfigurationError, match="run.json"):
        load_run_configuration(configuration_file(workspace, value))


@pytest.mark.parametrize(
    "text",
    [
        "",
        '{"generation": {}, "generation": {}}',
        '{"runtime": {"concurrency": 1, "concurrency": 2}}',
        '{"validation":{"frames":{"mode":"off","mode":"report"}}}',
        "generation: {theme_count: 2}",
        '{"generation":{}} trailing',
    ],
)
def test_json_loader_rejects_duplicates_and_non_json(workspace, text):
    path = workspace / "run.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(StoryConfigurationError):
        load_run_configuration(path)


def test_json_loader_rejects_wrong_extension_missing_and_invalid_utf8(workspace):
    with pytest.raises(StoryConfigurationError, match=".json"):
        load_run_configuration(workspace / "run.yaml")
    path = workspace / "run.json"
    with pytest.raises(StoryConfigurationError):
        load_run_configuration(path)
    path.write_bytes(b"\xff")
    with pytest.raises(StoryConfigurationError):
        load_run_configuration(path)


def test_program_defaults_are_uniform_and_do_not_depend_on_recipe_identity():
    first = resolve_story_input(document(id="motion"))
    second = resolve_story_input(document(id="unknown-visual-recipe"))
    assert first.run_configuration == second.run_configuration
    assert first.run_configuration.generation == StoryRunConfiguration().generation
    assert first.runtime == StoryRunConfiguration().runtime
    assert first.request.theme_count == 1
    assert first.request.frames_per_theme == 6
    assert first.request.content_level == ContentLevel.AESTHETIC
    assert first.request.output_language == OutputLanguage.CHINESE
    assert first.runtime.theme_output_tokens == 12000
    assert first.quality.themes.mode == QualityMode.ENFORCE
    assert [
        (check.field, check.min_chars, check.max_chars)
        for check in first.quality.themes.checks
    ] == [
        ("title", 4, 48),
        ("premise", 160, 520),
        ("style", 100, 360),
    ]
    assert first.quality.frames.mode == QualityMode.ENFORCE
    assert [
        (check.min_chars, check.max_chars)
        for check in first.quality.frames.checks
    ] == [(450, 950)]
    assert "whitespace-separated words" not in first.rules.text_for(StoryStage.FRAMES)


@pytest.mark.parametrize(
    ("people", "theme_bounds", "frame_bounds"),
    [
        (1, ((4, 48), (160, 520), (100, 360)), (450, 950)),
        (2, ((4, 48), (160, 520), (100, 360)), (450, 950)),
        (4, ((4, 48), (280, 640), (160, 420)), (650, 1150)),
        (8, ((4, 48), (520, 880), (280, 540)), (1050, 1550)),
    ],
)
def test_default_lengths_expand_for_additional_principal_people(
    people, theme_bounds, frame_bounds
):
    resolved = resolve_story_input(
        document(cast={"female_count": people, "male_count": 0})
    )
    assert tuple(
        (check.min_chars, check.max_chars)
        for check in resolved.quality_for("T001").themes.checks
    ) == theme_bounds
    prose = resolved.quality_for("T001").frames.checks[0]
    assert (prose.min_chars, prose.max_chars) == frame_bounds


def test_explicit_frame_length_override_is_not_cast_scaled():
    resolved = resolve_story_input(
        document(cast={"female_count": 4, "male_count": 0}),
        InputOverrides(frame_min_chars=700),
    )
    prose = resolved.quality.frames.checks[0]
    assert (prose.min_chars, prose.max_chars) == (700, 950)


def test_external_gender_overrides_preserve_visual_structure_and_explicit_zero():
    visual = document(
        cast={
            "female_count": 2,
            "male_count": 1,
            "scope": "travelers",
            "fixed_roles": [{"id": "conductor", "sex": "male"}],
            "background_counts": [{"min": 2, "max": 4}],
        }
    )
    original = resolve_story_input(visual)
    assert original.request.female_count == 2
    assert original.request.male_count == 1
    external = configuration(
        generation={"theme_count": 2, "female_count": 1, "male_count": 2},
        runtime={"concurrency": 3},
    )
    resolved = resolve_story_input(
        visual,
        InputOverrides(female_count=0, concurrency=1),
        run_configuration=external,
    )
    assert resolved.request.theme_count == 2
    assert resolved.request.female_count == 0
    assert resolved.request.male_count == 2
    assert resolved.run_configuration.generation.female_count == 0
    assert resolved.runtime.concurrency == 1
    cast = resolved.plans[0].cast
    assert cast.scope == "travelers"
    assert cast.fixed_roles == visual.cast.fixed_roles
    assert cast.background_counts == visual.cast.background_counts
    assert cast.principal_total == 3
    assert (cast.total_min, cast.total_max) == (5, 7)
    assert visual.cast.female_count == 2
    assert external.generation.female_count == 1


def test_fixed_catalog_requires_explicit_compatible_theme_count(workspace):
    catalogs = workspace / "_catalogs"
    catalogs.mkdir()
    (catalogs / "views.yaml").write_text(
        "id: views\nslots: [front, rear]\nentries:\n"
        "  - id: front\n    themes: [Front composition.]\n"
        "  - id: rear\n    themes: [Rear composition.]\n",
        encoding="utf-8",
    )
    visual = document(allocation={"type": "fixed_slots", "catalog": "views"})
    with pytest.raises(StoryConfigurationError, match="fixed_slots"):
        resolve_story_input(visual, asset_root=workspace)
    resolved = resolve_story_input(
        visual,
        run_configuration=configuration(generation={"theme_count": 2}),
        asset_root=workspace,
    )
    assert [plan.entry.id for plan in resolved.plans] == ["front", "rear"]


def test_visible_copy_language_remains_visual_not_prose_language(workspace):
    modules = workspace / "_modules"
    modules.mkdir()
    (modules / "lettering.yaml").write_text(
        "id: lettering\nkind: visible_copy\nauthoring:\n"
        "  themes: {common: [Retain the sign lettering.]}\n"
        "  frames: {common: [Render the sign lettering.]}\n",
        encoding="utf-8",
    )
    resolved = resolve_story_input(
        document(
            modules=[
                {
                    "id": "lettering",
                    "parameters": {"product": "poster", "copy_language": "english"},
                }
            ]
        ),
        run_configuration=configuration(generation={"output_language": "chinese"}),
        asset_root=workspace,
    )
    messages = frame_messages(
        resolved, theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    payload = json.loads(messages[1].content)
    assert payload["output_language"] == "chinese"
    module = payload["input_context"]["modules"][0]
    assert module["parameters"]["copy_language"] == "english"
    assert "do not change the prose language" in messages[0].content
    assert "450 to 950 characters" in messages[0].content


def test_cli_bounds_merge_into_one_check_preserving_external_applicability():
    external = configuration(
        validation={
            "frames": {
                "checks": [
                    {
                        "type": "word_count",
                        "min_words": 10,
                        "max_words": 30,
                        "when_language": "english",
                    },
                    {"type": "prose_length", "min_chars": 50, "max_chars": 300},
                ]
            }
        }
    )
    resolved = resolve_story_input(
        document(),
        InputOverrides(frame_min_words=12, frame_max_chars=250),
        run_configuration=external,
    )
    word, char = resolved.quality.frames.checks
    assert (word.min_words, word.max_words, word.when_language) == (12, 30, "english")
    assert (char.min_chars, char.max_chars) == (50, 250)
    assert len(resolved.quality.frames.checks) == 2
    assert external.validation.frames.checks[0].min_words == 10
    for override in (
        InputOverrides(frame_min_words=31),
        InputOverrides(frame_max_words=9),
        InputOverrides(frame_min_chars=301),
        InputOverrides(frame_max_chars=49),
    ):
        with pytest.raises(StoryConfigurationError):
            resolve_story_input(document(), override, run_configuration=external)


@pytest.mark.parametrize("mode", list(QualityMode))
@pytest.mark.parametrize("language", list(OutputLanguage))
def test_constraints_use_validator_stage_and_language_applicability(mode, language):
    config = configuration(
        generation={"output_language": language},
        validation={
            "themes": {
                "mode": mode,
                "checks": [
                    {"type": "required_text", "field": "title", "values": ["TITLE"]},
                    {"type": "forbidden_text", "field": "style", "values": ["BLUR"]},
                    {"type": "text_length", "field": "premise", "min_chars": 20},
                ],
            },
            "frames": {
                "mode": mode,
                "checks": [
                    {"type": "camera_evidence"},
                    {"type": "prose_length", "min_chars": 30, "max_chars": 100},
                    {"type": "required_text", "values": ["FRAME"]},
                    {"type": "forbidden_text", "values": ["FUZZY"]},
                    {"type": "ascii", "when_language": "english"},
                    {
                        "type": "word_count",
                        "when_language": "english",
                        "min_words": 7,
                        "max_words": 15,
                    },
                ],
            },
        },
    )
    resolved = resolve_story_input(document(), run_configuration=config)
    themes = theme_messages(resolved, count=1, existing_themes=[])
    frames = frame_messages(
        resolved, theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    theme_text, frame_text = themes[0].content, frames[0].content
    assert "each Theme's title" in theme_text and '"TITLE"' in theme_text
    assert "each Theme's style" in theme_text and '"BLUR"' in theme_text
    assert "20 to 32768 characters" in theme_text
    assert "30 to 100 characters" in frame_text
    assert '"FRAME"' in frame_text and '"FUZZY"' in frame_text
    assert "each Theme's title" not in frame_text
    assert "30 to 100 characters" not in theme_text
    assert ("at least 7 and at most 15" in frame_text) == (language == "english")
    assert ("only ASCII characters" in frame_text) == (language == "english")
    for payload in (json.loads(themes[1].content), json.loads(frames[1].content)):
        assert (
            not {
                "validation",
                "quality",
                "mode",
                "checks",
                "content_level",
                "program_assigns_theme_ids",
                "program_assigns_frame_ids",
            }
            & payload.keys()
        )
    issues = check_frame_quality(
        resolved.quality.frames,
        language,
        "T001",
        NarrativeFrame(frame_id="F01", prose="短"),
    )
    assert bool(issues) == (mode != "off")
    assert any(issue.check == "word_count" for issue in issues) == (
        language == "english" and mode != "off"
    )
    assert bool(check_theme_quality(resolved.quality.themes, "T001", theme())) == (
        mode != "off"
    )
    assert writing_constraints(config.validation, StoryStage.FRAMES, language)


@pytest.mark.parametrize("level", list(ContentLevel))
def test_mandatory_safety_is_frozen_for_both_stages_even_with_quality_off(level):
    resolved = resolve_story_input(
        document(),
        run_configuration=configuration(
            generation={"content_level": level},
            validation={"themes": {"mode": "off"}, "frames": {"mode": "off"}},
        ),
    )
    safety = next(
        source for source in resolved.sources if source.id == "system/safety.rules"
    )
    assert safety.themes == safety.frames
    for rules in (resolved.rules.themes, resolved.rules.frames):
        assert all(rule in rules for rule in safety.themes)
        text = "\n".join(rules)
        for phrase in (
            "unmistakable adult",
            "alert, consenting",
            "able to stop",
            "ordinary animals",
            "anthropomorphic",
            "incest",
            "sexual coercion",
            "impaired",
            "harmful injury",
            "fictional adults",
            "Public-domain",
            "named-creator style shortcuts",
        ):
            assert phrase in text
        assert "empty wineglass" not in text
    if level == ContentLevel.HARDCORE:
        assert "二十一岁以上成年人" in resolved.rules.text_for(StoryStage.FRAMES)
    assert "zero-gravity" in resolved.rules.text_for(StoryStage.FRAMES)


def test_missing_safety_pack_fails_instead_of_falling_back(workspace, monkeypatch):
    source = authoring_rules._SYSTEM_RULES_DIRECTORY
    directory = workspace / "system"
    shutil.copytree(source, directory)
    (directory / "safety.rules").unlink()
    monkeypatch.setattr(authoring_rules, "_SYSTEM_RULES_DIRECTORY", directory)
    with pytest.raises(StoryConfigurationError, match="safety.rules"):
        resolve_story_input(document())


def test_frozen_configuration_is_required_and_consistent():
    resolved = resolve_story_input(
        document(cast={"female_count": 1, "male_count": 1}),
        run_configuration=configuration(
            generation={"frames_per_theme": 2},
            validation={"frames": {"checks": [{"type": "word_count", "min_words": 3}]}},
        ),
    )
    original = resolved.model_dump(mode="json")
    assert (
        ResolvedStoryInput.model_validate_json(resolved.model_dump_json()) == resolved
    )
    missing = dict(original)
    del missing["run_configuration"]
    with pytest.raises(ValidationError):
        ResolvedStoryInput.model_validate(missing)
    for section, field, value in (
        ("generation", "frames_per_theme", 3),
        ("generation", "female_count", 0),
        ("runtime", "concurrency", 1),
    ):
        tampered = json.loads(json.dumps(original))
        tampered["run_configuration"][section][field] = value
        with pytest.raises(ValidationError, match="run_configuration"):
            ResolvedStoryInput.model_validate(tampered)
    tampered = json.loads(json.dumps(original))
    tampered["run_configuration"]["validation"]["frames"]["checks"][0]["min_words"] = 4
    tampered["quality"] = tampered["run_configuration"]["validation"]
    with pytest.raises(ValidationError, match="effective quality differs"):
        ResolvedStoryInput.model_validate(tampered)
    tampered = json.loads(json.dumps(original))
    tampered["sources"] = [
        source
        for source in tampered["sources"]
        if source["id"] != "system/safety.rules"
    ]
    with pytest.raises(ValidationError, match="mandatory system"):
        ResolvedStoryInput.model_validate(tampered)


@pytest.mark.parametrize("route", ["positional", "yaml"])
def test_explain_supports_external_config_and_explicit_budget_overrides(
    workspace, route
):
    path = configuration_file(
        workspace,
        {
            "generation": {"theme_count": 2, "output_language": "english"},
            "runtime": {"concurrency": 3},
        },
    )
    if route == "yaml":
        visual = workspace / "visual.yaml"
        visual.write_text(
            "id: visual\ndescription: An adult traveler.\n"
            "cast: {female_count: 2, male_count: 0}\n",
            encoding="utf-8",
        )
        args = ["--input", str(visual)]
    else:
        args = ["An adult traveler."]
    result = CliRunner().invoke(
        cli.app,
        [
            "explain",
            *args,
            "--run-config",
            str(path),
            "--themes",
            "3",
            "--frame-min-words",
            "2",
            "--frame-max-words",
            "4",
            "--frame-min-chars",
            "5",
            "--frame-max-chars",
            "80",
        ],
    )
    assert result.exit_code == 0, result.output
    frozen = json.loads(result.stdout)["input"]
    assert frozen["request"]["theme_count"] == 3
    assert frozen["request"]["output_language"] == "english"
    assert frozen["runtime"]["concurrency"] == 3
    assert [check["type"] for check in frozen["quality"]["frames"]["checks"]] == [
        "prose_length",
        "word_count",
    ]
    if route == "yaml":
        assert frozen["request"]["female_count"] == 2
        assert frozen["request"]["male_count"] == 0


@pytest.mark.parametrize(
    "options",
    [
        ["--frame-min-words", "0"],
        ["--frame-min-words", "8", "--frame-max-words", "7"],
        ["--frame-min-chars", "80", "--frame-max-chars", "70"],
        ["--frame-max-chars", "32769"],
    ],
)
def test_explain_rejects_invalid_output_budgets(options):
    result = CliRunner().invoke(cli.app, ["explain", "Adult traveler.", *options])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["status"] == "invalid"


class RecordingModel:
    def __init__(self, *, invalid_second: bool = False):
        self.invalid_second = invalid_second
        self.frame_payloads = []
        self.system_messages = []
        self.theme_calls = 0

    async def generate(self, *, messages, response_model, **kwargs):
        self.theme_calls += 1
        self.system_messages.append(messages[0].content)
        return ModelResponse(
            value=response_model.model_validate(
                {
                    "semantic_name": "quiet_station",
                    "themes": [theme().model_dump(exclude={"theme_id"})],
                }
            ),
            usage=TokenUsage(),
        )

    async def generate_text(self, *, messages, **kwargs):
        payload = json.loads(messages[1].content)
        self.frame_payloads.append(payload)
        self.system_messages.append(messages[0].content)
        prose = [
            "Short"
            if self.invalid_second and slot == "F02"
            else "Adult traveler "
            + ("waits.", "rests.", "reads.", "walks.", "sits.", "stands.")[
                int(slot[1:]) - 1
            ]
            for slot in payload["requested_frame_slots"]
        ]
        return TextModelResponse(
            text="".join(f"<FRAME>{value}</FRAME>" for value in prose),
            usage=TokenUsage(),
        )


@pytest.mark.asyncio
async def test_resume_uses_frozen_external_targets_and_only_retries_f02(
    workspace, monkeypatch
):
    path = configuration_file(
        workspace,
        {
            "generation": {"frames_per_theme": 2, "output_language": "english"},
            "runtime": {"generation_retries": 0, "concurrency": 1},
            "validation": {
                "themes": {"mode": "off"},
                "frames": {
                    "mode": "enforce",
                    "checks": [{"type": "word_count", "min_words": 3, "max_words": 4}],
                }
            },
        },
    )
    visual_path = workspace / "visual.yaml"
    visual_path.write_text(
        "id: visual\ndescription: Adult travelers.", encoding="utf-8"
    )
    resolved = resolve_story_input(
        load_story_document(visual_path), run_configuration=load_run_configuration(path)
    )
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="fake"),
        **resolved.runtime.model_dump(),
        quality=resolved.quality,
    )
    store = LocalStoryRunStore(workspace / "runs", workspace / "prompts")
    failed = RecordingModel(invalid_second=True)
    with pytest.raises(StoryRunIncompleteError) as error:
        await StoryStudio(failed, store, settings).run(resolved)
    run_id = error.value.run_id
    saved = store.inspect(run_id)
    assert [frame.frame_id for frame in saved.frames["T001"].frames] == ["F01"]
    path.unlink()
    visual_path.unlink()
    monkeypatch.setattr(
        authoring_rules, "_SYSTEM_RULES_DIRECTORY", workspace / "missing"
    )
    resumed = RecordingModel()
    result = await StoryStudio(resumed, store, settings).resume(run_id)
    assert resumed.theme_calls == 0
    assert resumed.frame_payloads[0]["requested_frame_slots"] == ["F02"]
    assert [
        frame["frame_id"] for frame in resumed.frame_payloads[0]["accepted_frames"]
    ] == ["F01"]
    assert "at least 3 and at most 4" in resumed.system_messages[0]
    assert "alert, consenting" in resumed.system_messages[0]
    assert result.published.prompt_file.is_file()
    assert result.result.quality.frames.status == "passed"
    assert store.inspect(run_id).input.run_configuration == resolved.run_configuration
    frozen_path = workspace / "runs" / run_id / "resolved-input.json"
    tampered = json.loads(frozen_path.read_text(encoding="utf-8"))
    del tampered["run_configuration"]
    frozen_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(StoryStorageError):
        store.inspect(run_id)


def test_generate_direct_story_uses_external_config_and_publishes(
    workspace, monkeypatch
):
    path = configuration_file(
        workspace,
        {
            "generation": {"frames_per_theme": 1, "output_language": "english"},
            "validation": {
                "themes": {"mode": "off"},
                "frames": {"mode": "off"},
            },
        },
    )
    model = RecordingModel()

    @asynccontextmanager
    async def model_context(settings):
        yield model

    monkeypatch.setattr(cli, "story_model", model_context)
    monkeypatch.setattr(
        cli, "load_story_provider_settings", lambda: StoryProviderSettings(model="fake")
    )
    result = CliRunner().invoke(
        cli.app,
        [
            "generate",
            "An adult traveler.",
            "--run-config",
            str(path),
            "--frame-min-words",
            "500",
            "--runs-dir",
            str(workspace / "runs"),
            "--prompts-dir",
            str(workspace / "prompts"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(model.frame_payloads) == 1
    assert "at least 500" in model.system_messages[-1]
    assert "alert, consenting" in model.system_messages[-1]
    assert list((workspace / "prompts").rglob("*.txt"))


def test_generate_rejects_invalid_config_before_provider_setup(workspace, monkeypatch):
    path = configuration_file(workspace, {"runtime": {"concurrency": "8"}})

    def forbidden_provider_setup():
        pytest.fail("invalid run configuration must fail before provider setup")

    monkeypatch.setattr(cli, "load_story_provider_settings", forbidden_provider_setup)
    result = CliRunner().invoke(
        cli.app,
        ["generate", "An adult traveler.", "--run-config", str(path)],
    )
    assert result.exit_code == 2
    assert "run.json" in result.output


@pytest.mark.parametrize("command", ["generate", "explain"])
def test_direct_story_has_only_the_existing_positional_route(command):
    help_result = CliRunner().invoke(cli.app, [command, "--help"])
    assert help_result.exit_code == 0
    assert "--story" not in help_result.output
    result = CliRunner().invoke(cli.app, [command, "--story", "An adult traveler."])
    assert result.exit_code == 2
