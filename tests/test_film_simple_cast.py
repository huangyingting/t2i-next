from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from t2i_film_style_pipeline.cli import app
from t2i_film_style_pipeline.diversity import duplicate_theme_issues
from t2i_film_style_pipeline.errors import (
    FilmPromptRunIncompleteError,
    FilmStyleProviderError,
)
from t2i_film_style_pipeline.pipeline import FilmStylePromptRequest
from t2i_film_style_pipeline.prompt_messages import frame_messages, theme_messages
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    FilmPromptRuleSet,
    NarrativeTheme,
    NarrativeThemeDraftBatch,
    TokenUsage,
)
from t2i_film_style_pipeline.prompt_provider import ModelResponse, TextModelResponse
from t2i_film_style_pipeline.prompt_run_store import LocalFilmPromptRunStore
from t2i_film_style_pipeline.prompt_studio import FilmPromptStudio
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from tests.film_prompt_factories import make_prompt_request, make_theme
from tests.test_film_style_pipeline import make_request
from tests.test_film_style_prompt_pipeline import make_settings


@pytest.mark.parametrize("level", list(ContentLevel))
def test_all_levels_share_parameter_controlled_cast_and_full_history(level):
    request = make_prompt_request(
        content_level=level, theme_count=100, female_count=0, male_count=6
    )
    resolved = resolve_film_style_rules(request)
    rules = FilmPromptRuleSet(themes=resolved.themes, frames=resolved.frames)
    existing = [make_theme(index) for index in range(1, 100)]
    payload = json.loads(
        theme_messages(
            request,
            rules,
            start_index=100,
            count=1,
            existing_themes=existing,
        )[1].content
    )
    assert payload["existing_themes"] == [
        theme.model_dump(mode="json") for theme in existing
    ]
    assert {"cast_constraints", "diversity_ledger"}.isdisjoint(payload)
    assert "不得生成重复的 Theme" in "\n".join(rules.themes)
    for stage in (rules.themes, rules.frames):
        assert "人数完全由请求中的男女数量决定" in "\n".join(stage)
        assert "不要求至少一名女性" in "\n".join(stage)
    assert all(
        "cast_size_requirement" not in item
        for item in payload["current_batch_diversity_contracts"]
    )
    frame_payload = json.loads(
        frame_messages(
            request,
            existing[0],
            rules,
            requested_frame_ids=["F01"],
            accepted_frames=[],
        )[1].content
    )
    assert "cast_constraints" not in frame_payload
    assert "requested_cast_counts" not in frame_payload["participant_frame_contracts"]
    assert payload["current_batch_cast_requirements"] == [
        {
            "output_position": 1,
            "participant_count": 6,
            "female_count": 0,
            "male_count": 6,
        }
    ]
    assert frame_payload["theme_cast_requirement"] == {
        "participant_count": 6,
        "female_count": 0,
        "male_count": 6,
    }


@pytest.mark.parametrize("field", ["selected_cast", "source_films"])
def test_removed_film_cast_fields_are_rejected_not_silently_ignored(field):
    for model, data in (
        (FilmPromptRequest, {"context": "A film scene."}),
        (FilmStylePromptRequest, {"film_style": make_request().model_dump()}),
    ):
        with pytest.raises(ValidationError, match=field):
            model.model_validate({**data, field: 1})


@pytest.mark.parametrize(
    ("option", "value"), [("--female-count", "-1"), ("--male-count", "-1")]
)
def test_invalid_count_cli_options_fail_before_provider_setup(option, value):
    result = CliRunner().invoke(
        app, ["generate", "Director", "--work", "Film (2000)", option, value]
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_exact_theme_duplicate_detection_ignores_title_and_checks_batch_and_history():
    first = make_theme()
    repeated = first.model_copy(update={"theme_id": "T002", "title": "New title"})
    assert duplicate_theme_issues([repeated], [first])
    assert duplicate_theme_issues([first, repeated], [])
    assert not duplicate_theme_issues([make_theme(2)], [first])


def test_duplicate_normalization_covers_case_spacing_and_unicode_punctuation():
    first = make_theme().model_copy(
        update={"premise": "A woman reads.", "style": "Soft light."}
    )
    repeated = make_theme(2).model_copy(
        update={"premise": "Ａ WOMAN reads！", "style": "soft   light"}
    )
    assert duplicate_theme_issues([repeated], [first])


class ScriptedModel:
    def __init__(self, themes):
        self.themes = iter(themes)
        self.theme_messages = []

    async def generate(self, **kwargs):
        self.theme_messages.append(kwargs["messages"])
        value = next(self.themes)
        if isinstance(value, Exception):
            raise value
        return ModelResponse(value=value, usage=TokenUsage())

    async def generate_text(self, **kwargs):
        payload = json.loads(kwargs["messages"][1].content)
        return TextModelResponse(
            text="".join(
                f"<FRAME>A quiet view of {payload['theme']['title']}, {slot}.</FRAME>"
                for slot in payload["requested_frame_slots"]
            ),
            usage=TokenUsage(),
        )


def draft_batch(*themes: NarrativeTheme):
    return NarrativeThemeDraftBatch.model_validate(
        {
            "semantic_name": "library",
            "themes": [theme.model_dump(exclude={"theme_id"}) for theme in themes],
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename_fields", "filename"),
    [
        ({}, "library_0001.txt"),
        ({"source_prompt_stem": "Film Source"}, "film_source_aesthetic_0001.txt"),
        (
            {"source_prompt_stem": "Film", "prompt_filename_stem": "My_Film"},
            "my_film_0001.txt",
        ),
    ],
)
async def test_duplicate_batch_retries_without_optional_semantic_validation(
    tmp_path, filename_fields, filename
):
    request = make_prompt_request(theme_count=2, frames_per_theme=1).model_copy(
        update=filename_fields
    )
    settings = make_settings(
        theme_batch_size=2,
        generation_retries=1,
        validate_themes=False,
        validate_frames=False,
    ).prompt
    resolved = resolve_film_style_rules(request)
    rules = FilmPromptRuleSet(themes=resolved.themes, frames=resolved.frames)
    first = make_theme()
    repeated = first.model_copy(update={"title": "Renamed"})
    model = ScriptedModel(
        [draft_batch(first, repeated), draft_batch(first, make_theme(2))]
    )
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    done = await FilmPromptStudio(model, store, settings, rules).run(request)
    assert len(done.result.themes) == 2
    assert done.published.prompt_file.name == filename
    assert done.published.prompt_file.exists()
    assert "T002 repeats T001" in model.theme_messages[1][-1].content
    attempts = [a for a in store.attempts(done.run_id) if a.stage == "themes"]
    assert attempts[0].accepted_ids == []
    assert attempts[1].accepted_ids == ["T001", "T002"]


@pytest.mark.asyncio
async def test_duplicate_retries_are_bounded_and_never_checkpoint_rejected_themes(
    tmp_path,
):
    request = make_prompt_request(theme_count=2, frames_per_theme=1)
    settings = make_settings(theme_batch_size=2, generation_retries=1).prompt
    resolved = resolve_film_style_rules(request)
    rules = FilmPromptRuleSet(themes=resolved.themes, frames=resolved.frames)
    repeated = draft_batch(make_theme(), make_theme())
    model = ScriptedModel([repeated, repeated])
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    with pytest.raises(FilmPromptRunIncompleteError) as failure:
        await FilmPromptStudio(model, store, settings, rules).run(request)
    assert len(model.theme_messages) == 2
    snapshot = store.inspect(failure.value.run_id)
    assert not snapshot.themes
    assert not snapshot.frames
    assert all(
        not attempt.accepted_ids for attempt in store.attempts(failure.value.run_id)
    )


@pytest.mark.asyncio
async def test_resume_retains_complete_history_and_rejects_historical_duplicate(
    tmp_path,
):
    request = make_prompt_request(theme_count=2, frames_per_theme=1)
    settings = make_settings(
        generation_retries=1, validate_themes=False, validate_frames=False
    ).prompt
    resolved = resolve_film_style_rules(request)
    rules = FilmPromptRuleSet(themes=resolved.themes, frames=resolved.frames)
    first = make_theme()
    initial = ScriptedModel([draft_batch(first), FilmStyleProviderError("interrupted")])
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    with pytest.raises(FilmPromptRunIncompleteError) as failure:
        await FilmPromptStudio(initial, store, settings, rules).run(request)
    run_id = failure.value.run_id
    model = ScriptedModel([draft_batch(first), draft_batch(make_theme(2))])
    reopened = LocalFilmPromptRunStore(tmp_path / "runs")
    done = await FilmPromptStudio(model, reopened, settings, rules).resume(run_id)
    payload = json.loads(model.theme_messages[0][1].content)
    assert payload["existing_themes"] == [first.model_dump(mode="json")]
    assert len(done.result.themes) == 2
    assert "T002 repeats T001" in model.theme_messages[1][-1].content
