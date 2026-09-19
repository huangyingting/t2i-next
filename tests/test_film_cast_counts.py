from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import t2i_film_style_pipeline.cli as cli
from t2i_film_style_pipeline.errors import (
    FilmPromptRunIncompleteError,
    FilmStyleProviderError,
)
from t2i_film_style_pipeline.models import FilmWorkAnchors
from t2i_film_style_pipeline.pipeline import FilmStylePromptRequest
from t2i_film_style_pipeline.prompt_messages import frame_messages, theme_messages
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    FilmPromptRuleSet,
    TokenUsage,
)
from t2i_film_style_pipeline.prompt_provider import TextModelResponse
from t2i_film_style_pipeline.prompt_run_store import LocalFilmPromptRunStore
from t2i_film_style_pipeline.prompt_studio import FilmPromptStudio
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from tests.film_prompt_factories import make_prompt_request, make_theme
from tests.test_film_simple_cast import ScriptedModel, draft_batch
from tests.test_film_style_pipeline import make_profile, make_request
from tests.test_film_style_prompt_pipeline import make_settings


def rules_for(request):
    resolved = resolve_film_style_rules(request)
    return FilmPromptRuleSet(themes=resolved.themes, frames=resolved.frames)


def test_defaults_and_single_parameter_inputs_are_fixed_not_random():
    for fields, expected in (
        ({}, (1, 0)),
        ({"female_count": 6}, (6, 0)),
        ({"male_count": 5}, (1, 5)),
    ):
        top = FilmStylePromptRequest(film_style=make_request(), **fields)
        child = top.prompt_request("A quiet reading room.")
        for request in (top, child, FilmPromptRequest(context="A room.", **fields)):
            assert (request.female_count, request.male_count) == expected


@pytest.mark.parametrize("female,male", [(3, 0), (0, 3), (6, 2), (0, 20), (25, 0)])
@pytest.mark.parametrize("level", list(ContentLevel))
def test_exact_counts_reach_both_stages_without_cap_or_required_woman(
    female, male, level
):
    top = FilmStylePromptRequest(
        film_style=make_request(),
        female_count=female,
        male_count=male,
        content_level=level,
        theme_count=3,
    )
    request = top.prompt_request("A quiet reading room.")
    rules = rules_for(request)
    expected = {
        "participant_count": female + male,
        "female_count": female,
        "male_count": male,
    }
    payload = json.loads(
        theme_messages(
            request, rules, start_index=2, count=2, existing_themes=[make_theme()]
        )[1].content
    )
    assert payload["current_batch_cast_requirements"] == [
        {"output_position": 1, **expected},
        {"output_position": 2, **expected},
    ]
    frame_payload = json.loads(
        frame_messages(
            request,
            make_theme(2),
            rules,
            requested_frame_ids=["F01"],
            accepted_frames=[],
        )[1].content
    )
    assert frame_payload["theme_cast_requirement"] == expected
    assert "minimum_female_count" not in frame_payload["theme_cast_requirement"]
    for stage in (rules.themes, rules.frames):
        assert "不要求至少一名女性" in "\n".join(stage)
        assert "不随机抽取" in "\n".join(stage)


@pytest.mark.parametrize("female,male", [(-1, 1), (1, -1), (0, 0), (None, 2)])
def test_invalid_counts_fail_in_both_request_models(female, male):
    with pytest.raises(ValidationError):
        FilmStylePromptRequest(
            film_style=make_request(),
            female_count=female,
            male_count=male,
        )
    with pytest.raises(ValidationError):
        FilmPromptRequest(
            context="A reading room.",
            female_count=female,
            male_count=male,
        )


def test_zero_total_cli_fails_before_loading_providers(monkeypatch):
    def unexpected_provider():
        pytest.fail("Invalid counts must fail before provider setup")

    monkeypatch.setattr(cli, "load_film_style_provider_settings", unexpected_provider)
    result = CliRunner().invoke(
        cli.app,
        [
            "generate",
            "Director",
            "--work",
            "Film (2000)",
            "--female-count",
            "0",
            "--male-count",
            "0",
        ],
    )
    assert result.exit_code != 0
    assert "人数不能同时为零" in result.output


def test_profile_character_roster_has_no_twelve_person_cap():
    anchors = make_profile().work_anchors[0].model_dump()
    prototype = anchors["adult_characters"][0]
    anchors["adult_characters"] = [
        {**prototype, "canonical_name": f"Adult reader {index}"} for index in range(15)
    ]
    assert len(FilmWorkAnchors.model_validate(anchors).adult_characters) == 15


class RecordingModel(ScriptedModel):
    def __init__(self, themes, *, fail_frame_theme=None, reject_first_frame=False):
        super().__init__(themes)
        self.frame_payloads = []
        self.fail_frame_theme = fail_frame_theme
        self.reject_first_frame = reject_first_frame

    async def generate_text(self, **kwargs):
        payload = json.loads(kwargs["messages"][1].content)
        self.frame_payloads.append(payload)
        if payload["theme"]["theme_id"] == self.fail_frame_theme:
            raise FilmStyleProviderError("Interrupted frame generation")
        if self.reject_first_frame and len(self.frame_payloads) == 1:
            return TextModelResponse(
                text="Missing frame delimiters", usage=TokenUsage()
            )
        return await super().generate_text(**kwargs)


@pytest.mark.asyncio
async def test_frame_retry_retains_exact_gender_counts(tmp_path):
    request = make_prompt_request(female_count=3, male_count=0)
    settings = make_settings(generation_retries=1).prompt
    model = RecordingModel([draft_batch(make_theme())], reject_first_frame=True)
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    completed = await FilmPromptStudio(model, store, settings, rules_for(request)).run(
        request
    )
    assert len(model.frame_payloads) == 2
    assert all(
        p["theme_cast_requirement"]
        == {
            "participant_count": 3,
            "female_count": 3,
            "male_count": 0,
        }
        for p in model.frame_payloads
    )
    assert len(completed.result.themes[0].frames) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("female,male", [(3, 0), (0, 6), (5, 4)])
async def test_fixed_counts_survive_theme_retry_and_publication(tmp_path, female, male):
    request = make_prompt_request(
        theme_count=2,
        frames_per_theme=2,
        female_count=female,
        male_count=male,
    )
    settings = make_settings(theme_batch_size=2, generation_retries=1).prompt
    first = make_theme()
    model = RecordingModel(
        [
            draft_batch(first, first),
            draft_batch(first, make_theme(2)),
        ]
    )
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    completed = await FilmPromptStudio(model, store, settings, rules_for(request)).run(
        request
    )
    expected = {
        "participant_count": female + male,
        "female_count": female,
        "male_count": male,
    }
    assert len(model.theme_messages) == 2
    for messages in model.theme_messages:
        payload = json.loads(messages[1].content)
        assert [
            {k: v for k, v in item.items() if k != "output_position"}
            for item in payload["current_batch_cast_requirements"]
        ] == [expected, expected]
    assert all(p["theme_cast_requirement"] == expected for p in model.frame_payloads)
    assert completed.published.prompt_file.exists()
    snapshot = store.inspect(completed.run_id)
    assert snapshot.request.female_count == female
    assert snapshot.request.male_count == male
    assert "theme_cast_sizes" not in snapshot.manifest.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["themes", "frames"])
async def test_resume_retains_fixed_counts_in_remaining_theme_and_frame_calls(
    tmp_path, stage
):
    request = make_prompt_request(
        theme_count=2,
        frames_per_theme=2,
        female_count=0,
        male_count=7,
    )
    settings = make_settings(theme_batch_size=1).prompt
    rules = rules_for(request)
    initial = RecordingModel(
        [
            draft_batch(make_theme()),
            (
                FilmStyleProviderError("Interrupted Theme generation")
                if stage == "themes"
                else draft_batch(make_theme(2))
            ),
        ],
        fail_frame_theme="T002" if stage == "frames" else None,
    )
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    with pytest.raises(FilmPromptRunIncompleteError) as failure:
        await FilmPromptStudio(initial, store, settings, rules).run(request)
    run_id = failure.value.run_id
    model = RecordingModel([draft_batch(make_theme(2))] if stage == "themes" else [])
    reopened = LocalFilmPromptRunStore(tmp_path / "runs")
    studio = FilmPromptStudio(model, reopened, settings, rules)
    completed = await studio.resume(run_id)
    expected = {"participant_count": 7, "female_count": 0, "male_count": 7}
    for messages in model.theme_messages:
        payload = json.loads(messages[1].content)
        assert payload["current_batch_cast_requirements"] == [
            {"output_position": 1, **expected},
        ]
    assert model.frame_payloads
    assert all(p["theme_cast_requirement"] == expected for p in model.frame_payloads)
    assert completed.result.request.female_count == 0
    assert completed.result.request.male_count == 7
    assert len(completed.result.themes) == 2
    calls = (len(model.theme_messages), len(model.frame_payloads))
    await studio.resume(run_id)
    assert (len(model.theme_messages), len(model.frame_payloads)) == calls
