from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from t2i_film_style_pipeline.cast_validation import (
    validate_cast_prose,
    validate_selected_cast,
)
from t2i_film_style_pipeline.content_validation import FilmStyleContentValidator
from t2i_film_style_pipeline.errors import (
    FilmStyleContractError,
    FilmStyleRunIncompleteError,
    FilmStyleStorageError,
)
from t2i_film_style_pipeline.models import (
    FilmCharacterAnchor,
    FilmWorkAnchors,
    exact_film_style_profile_model,
)
from t2i_film_style_pipeline.pipeline import (
    FilmStylePromptRequest,
    FilmStylePromptStudio,
    FilmStyleRunStatus,
    LocalFilmStyleRunStore,
)
from t2i_film_style_pipeline.prompt_models import (
    FilmPromptOptions,
    FilmPromptRequest,
    FilmPromptResult,
    FilmPromptRuleSet,
    FilmPromptStage,
    NarrativeTheme,
    SelectedFilmCharacter,
    exact_theme_draft_batch_model,
)
from t2i_film_style_pipeline.prompt_run_store import LocalFilmPromptRunStore
from t2i_film_style_pipeline.prompt_storage import publish_film_prompt
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from tests.film_prompt_factories import (
    make_prompt_request,
    make_prompt_result,
    make_source_films,
    make_theme,
)
from tests.test_film_style_pipeline import make_profile, make_request
from tests.test_film_style_prompt_pipeline import (
    FakeFilmModel,
    FakePromptModel,
    frame_batch_text,
    make_film_frame_sequence,
    make_film_theme_batch,
    make_settings,
)


@pytest.mark.parametrize("female_count", [2, 3])
def test_female_only_cast_cannot_pool_films_or_clone(female_count) -> None:
    with pytest.raises(ValidationError, match="impossible.*single frozen source film"):
        make_prompt_request(female_count=female_count, male_count=0)


@pytest.mark.parametrize("mode", ["typed", "dict", "json"])
def test_cast_contract_survives_all_request_formats(mode) -> None:
    original = make_prompt_request(female_count=1, male_count=1)
    if mode == "json":
        request = FilmPromptRequest.model_validate_json(original.model_dump_json())
    else:
        value = original if mode == "typed" else original.model_dump()
        request = FilmPromptRequest.model_validate(value)
    assert request == original
    validate_selected_cast(request, make_theme())
    bad = make_theme().model_copy(
        update={
            "selected_cast": (
                SelectedFilmCharacter(canonical_name="无名", gender="female"),
                SelectedFilmCharacter(canonical_name="飞雪", gender="female"),
            ),
        }
    )
    with pytest.raises(FilmStyleContractError, match="fixed-gender mismatch"):
        validate_selected_cast(request, bad)


@pytest.mark.parametrize("mode", ["typed", "dict", "json"])
def test_duplicate_selected_identity_is_not_a_headcount(mode) -> None:
    original = make_theme()
    original.selected_cast = (original.selected_cast[0], original.selected_cast[0])
    with pytest.raises(ValidationError, match="duplicate selected identity"):
        if mode == "json":
            NarrativeTheme.model_validate_json(original.model_dump_json())
        else:
            value = original if mode == "typed" else original.model_dump()
            NarrativeTheme.model_validate(value)
    with pytest.raises(FilmStyleContractError, match="duplicate selected identity"):
        validate_selected_cast(make_prompt_request(), original)


def test_profile_names_are_unique_case_insensitively() -> None:
    anchors = make_profile().work_anchors[0]
    character = anchors.adult_characters[0].model_copy(
        update={"canonical_name": "Su Lizhen"}
    )
    duplicate = character.model_copy(update={"canonical_name": " su lizhen "})
    with pytest.raises(ValidationError, match="identities must be unique"):
        FilmWorkAnchors(
            adult_characters=(character, duplicate),
            scenes=anchors.scenes,
        )


@pytest.mark.parametrize("counts", [{}, {"female_count": 1, "male_count": 0}])
def test_fixed_gender_cannot_be_changed_even_without_requested_counts(counts) -> None:
    request = make_prompt_request(**counts)
    theme = make_theme().model_copy(
        update={
            "selected_cast": (
                SelectedFilmCharacter(canonical_name="无名", gender="female"),
            ),
        }
    )
    with pytest.raises(FilmStyleContractError, match="fixed-gender mismatch"):
        validate_selected_cast(request, theme)


@pytest.mark.parametrize("name", ["小妹", "invented character"])
def test_selected_identity_must_belong_to_selected_film(name) -> None:
    theme = make_theme().model_copy(
        update={
            "selected_cast": (
                SelectedFilmCharacter(canonical_name=name, gender="female"),
            ),
        }
    )
    with pytest.raises(FilmStyleContractError, match="not in the selected source film"):
        validate_selected_cast(make_prompt_request(), theme)


def test_partial_counts_are_exact_and_zero_is_not_unspecified() -> None:
    request = make_prompt_request(female_count=0)
    with pytest.raises(FilmStyleContractError, match="female count mismatch"):
        validate_selected_cast(request, make_theme())
    only_man = make_theme().model_copy(
        update={
            "selected_cast": (make_theme().selected_cast[0],),
        }
    )
    validate_selected_cast(request, only_man)
    assert request.male_count is None


def test_authoritative_work_index_disambiguates_shared_canonical_names() -> None:
    profile = make_profile()
    profile = profile.model_copy(
        update={
            "work_anchors": (profile.work_anchors[0], profile.work_anchors[0]),
        }
    )
    request = FilmStylePromptRequest(
        film_style=make_request(), female_count=1, male_count=1
    ).prompt_request("Frozen context", profile)
    theme = make_theme().model_copy(
        update={
            "source_work_index": 1,
            "premise": "无名与飞雪位于秦宫大殿。",
        }
    )
    FilmStyleContentValidator(make_request(), profile).validate_theme(request, theme)


def test_unknown_gender_is_never_guessed_for_an_explicit_count() -> None:
    source = make_source_films()[0].model_dump()
    source["anchors"]["adult_characters"][0]["gender"] = "unknown"
    source["anchors"]["adult_characters"] = source["anchors"]["adult_characters"][:1]
    with pytest.raises(ValidationError, match="unknown gender"):
        FilmPromptRequest(
            context="Frozen unknown-gender source",
            frame_source_sentence="Frozen source.",
            source_films=(source,),
            female_count=1,
        )
    unrestricted = FilmPromptRequest(
        context="Frozen unknown-gender source",
        source_films=(source,),
        frame_source_sentence="Frozen source.",
    )
    theme = make_theme().model_copy(
        update={
            "selected_cast": (
                SelectedFilmCharacter(canonical_name="无名", gender="unknown"),
            ),
        }
    )
    validate_selected_cast(unrestricted, theme)
    guessed = theme.model_copy(
        update={
            "selected_cast": (
                SelectedFilmCharacter(canonical_name="无名", gender="male"),
            ),
        }
    )
    with pytest.raises(FilmStyleContractError, match="fixed-gender mismatch"):
        validate_selected_cast(unrestricted, guessed)


def test_known_count_does_not_license_extra_unknown_gender_identity() -> None:
    source = make_source_films()[0].model_dump()
    source["anchors"]["adult_characters"][0]["gender"] = "unknown"
    request = FilmPromptRequest(
        context="Frozen context",
        source_films=(source,),
        female_count=1,
        frame_source_sentence="Frozen source.",
    )
    theme = make_theme().model_copy(
        update={
            "selected_cast": (
                SelectedFilmCharacter(canonical_name="无名", gender="unknown"),
                SelectedFilmCharacter(canonical_name="飞雪", gender="female"),
            ),
        }
    )
    with pytest.raises(FilmStyleContractError, match="unknown gender"):
        validate_selected_cast(request, theme)


@pytest.mark.parametrize(
    "counts",
    [
        {"female_count": 0, "male_count": 0},
        {"female_count": 5, "male_count": 4},
        {"female_count": True},
        {"female_count": "3"},
        {"male_count": 1.5},
    ],
)
def test_top_level_rejects_invalid_counts_before_profile_call(counts) -> None:
    with pytest.raises(ValidationError):
        FilmStylePromptRequest(film_style=make_request(), **counts)


def test_schema_requires_current_cast_fields_without_legacy_fallback() -> None:
    assert "gender" in FilmCharacterAnchor.model_json_schema()["required"]
    theme_schema = exact_theme_draft_batch_model(2).model_json_schema()
    required = theme_schema["$defs"]["NarrativeThemeDraft"]["required"]
    assert {"source_work_index", "selected_cast"} <= set(required)
    profile_schema = exact_film_style_profile_model(2).model_json_schema()
    assert set(profile_schema["$defs"]["CharacterGender"]["enum"]) == {
        "female",
        "male",
        "unknown",
    }
    with pytest.raises(ValidationError, match="source_films"):
        FilmPromptRequest(context="prose-only old request")
    old_theme = make_theme().model_dump(exclude={"source_work_index", "selected_cast"})
    with pytest.raises(ValidationError, match="selected_cast"):
        NarrativeTheme.model_validate(old_theme)


def test_repeated_name_and_mirror_are_one_identity_not_extra_people() -> None:
    request = make_prompt_request(female_count=1, male_count=0)
    theme = make_theme().model_copy(
        update={
            "selected_cast": (make_theme().selected_cast[1],),
            "premise": "飞雪独自位于秦宫大殿，飞雪与自己的镜中倒影同姿。",
        }
    )
    validate_selected_cast(request, theme)
    validate_cast_prose(request, theme, theme.premise)
    validate_cast_prose(request, theme, "飞雪握剑。飞雪的镜中倒影来自同一人。")
    with pytest.raises(FilmStyleContractError, match="unselected=.*无名"):
        validate_cast_prose(request, theme, "飞雪与无名相对而立。")


def test_name_presence_does_not_claim_to_detect_free_prose_cloned_bodies() -> None:
    request = make_prompt_request(female_count=1, male_count=0)
    theme = make_theme().model_copy(
        update={
            "selected_cast": (make_theme().selected_cast[1],),
        }
    )
    # Deliberate limitation: body duplication is forbidden by writing rules,
    # but arbitrary natural language is not deterministically certified here.
    validate_cast_prose(request, theme, "飞雪的两个独立身体站在殿内。")


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "这是一个基于测试导演的《Ann》原作人物与场景重新构图的电影画面。",
        "This film image recomposes characters and settings from Ann, "
        "directed by Example Director. ",
    ],
)
def test_name_presence_ignores_source_title_and_embedded_shorter_name(prefix) -> None:
    source = make_source_films()[0].model_dump()
    source["anchors"]["adult_characters"][0]["canonical_name"] = "Ann"
    source["anchors"]["adult_characters"][1]["canonical_name"] = "Anna"
    request = FilmPromptRequest(
        context="Frozen source",
        source_films=(source,),
        female_count=1,
        male_count=0,
        frame_source_sentence=prefix.strip() or "Frozen source.",
    )
    theme = make_theme().model_copy(
        update={
            "selected_cast": (
                SelectedFilmCharacter(canonical_name="Anna", gender="female"),
            ),
        }
    )
    validate_selected_cast(request, theme)
    validate_cast_prose(request, theme, prefix + "Anna独自站在原作场景中。")


def test_result_json_rejects_requested_count_conflict() -> None:
    payload = make_prompt_result().model_dump(mode="json")
    payload["request"]["female_count"] = 1
    payload["request"]["male_count"] = 0
    with pytest.raises(ValidationError, match="male count mismatch"):
        FilmPromptResult.model_validate_json(json.dumps(payload))


def test_publication_revalidates_mutated_typed_result(tmp_path) -> None:
    result = make_prompt_result()
    result.themes[0].theme.selected_cast = (
        result.themes[0].theme.selected_cast[0],
    ) * 2
    target = tmp_path / "invalid.txt"
    with pytest.raises(ValidationError, match="duplicate selected identity"):
        publish_film_prompt(result, target)
    assert not target.exists()


def test_typed_request_cannot_bypass_feasibility_at_store_boundary(tmp_path) -> None:
    request = make_prompt_request().model_copy(
        update={"female_count": 3, "male_count": 0}
    )
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    with pytest.raises(ValidationError, match="requested cast is impossible"):
        store.create(
            request,
            make_settings().prompt,
            FilmPromptRuleSet(themes=("Theme rule",), frames=("Frame rule",)),
        )
    assert not (tmp_path / "runs").exists()


@pytest.mark.asyncio
async def test_valid_female_only_cast_is_frozen_and_published_unchanged(
    tmp_path,
) -> None:
    request = FilmStylePromptRequest(
        film_style=make_request(), female_count=1, male_count=0, frames_per_theme=1
    )
    batch = make_film_theme_batch()
    batch.themes[0].selected_cast = (make_theme().selected_cast[1],)
    batch.themes[0].premise = "飞雪独自位于秦宫大殿。"
    prompt_model = FakePromptModel(
        [
            batch,
            "<FRAME>飞雪站在秦宫大殿，飞雪的镜中倒影与她保持同一姿态。</FRAME>",
        ]
    )
    film_model = FakeFilmModel()
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    studio = FilmStylePromptStudio(
        film_model,
        prompt_model,
        store,
        make_settings(validate_themes=False, validate_frames=False),
        resolve_film_style_rules(request),
    )
    completed = await studio.run(request, prompts_directory=tmp_path / "prompts")
    child = LocalFilmPromptRunStore(
        store.prompt_runs_directory(completed.run_id)
    ).inspect(completed.prompt_run_id)
    assert child.request.female_count == 1
    assert child.request.male_count == 0
    assert [item.canonical_name for item in child.themes[0].selected_cast] == ["飞雪"]
    assert child.request.source_films == make_source_films()
    assert "镜中倒影" in completed.prompt_file.read_text()
    assert "selected_cast" not in completed.prompt_file.read_text()
    assert await studio.resume(completed.run_id) == completed
    assert film_model.calls == 1
    assert prompt_model.stages == [FilmPromptStage.THEMES, FilmPromptStage.FRAMES]


@pytest.mark.asyncio
async def test_frame_prefix_cannot_hide_missing_or_extra_selected_people(
    tmp_path,
) -> None:
    request = FilmStylePromptRequest(film_style=make_request(), frames_per_theme=1)
    prompt_model = FakePromptModel(
        [
            make_film_theme_batch(),
            "<FRAME>无名在秦宫大殿等候小妹。</FRAME>",
        ]
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    studio = FilmStylePromptStudio(
        FakeFilmModel(),
        prompt_model,
        store,
        make_settings(generation_retries=0),
        resolve_film_style_rules(request),
    )
    with pytest.raises(FilmStyleRunIncompleteError, match="prose canonical names"):
        await studio.run(request, prompts_directory=tmp_path / "prompts")
    assert not list((tmp_path / "runs").rglob("F01.json"))
    assert not list((tmp_path / "prompts").rglob("*.txt"))


@pytest.mark.asyncio
async def test_impossible_cast_fails_after_profile_and_before_theme_even_on_resume(
    tmp_path,
) -> None:
    request = FilmStylePromptRequest(
        film_style=make_request(), female_count=3, male_count=0
    )
    film_model = FakeFilmModel()
    prompt_model = FakePromptModel([])
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    studio = FilmStylePromptStudio(
        film_model,
        prompt_model,
        store,
        make_settings(),
        resolve_film_style_rules(request),
    )
    with pytest.raises(
        FilmStyleRunIncompleteError, match="requested cast is impossible"
    ):
        await studio.run(request, prompts_directory=tmp_path / "prompts")
    run_id = next((tmp_path / "runs").iterdir()).name
    assert store.inspect(run_id).manifest.status == FilmStyleRunStatus.FAILED
    with pytest.raises(
        FilmStyleRunIncompleteError, match="requested cast is impossible"
    ):
        await studio.resume(run_id)
    assert film_model.calls == 1
    assert prompt_model.stages == []
    assert not list((tmp_path / "prompts").rglob("*.txt"))


@pytest.mark.asyncio
async def test_cast_validation_is_mandatory_when_semantic_checks_are_off(
    tmp_path,
) -> None:
    request = FilmStylePromptRequest(
        film_style=make_request(), female_count=1, male_count=0
    )
    prompt_model = FakePromptModel([make_film_theme_batch()])
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    studio = FilmStylePromptStudio(
        FakeFilmModel(),
        prompt_model,
        store,
        make_settings(
            generation_retries=0, validate_themes=False, validate_frames=False
        ),
        resolve_film_style_rules(request),
    )
    with pytest.raises(FilmStyleRunIncompleteError, match="male count mismatch"):
        await studio.run(request, prompts_directory=tmp_path / "prompts")
    assert prompt_model.stages == [FilmPromptStage.THEMES]
    assert not list((tmp_path / "runs").rglob("T001.json"))


def test_frozen_theme_is_revalidated_on_inspection(tmp_path) -> None:
    request = make_prompt_request(female_count=1, male_count=1)
    store = LocalFilmPromptRunStore(tmp_path / "runs", tmp_path / "prompts")
    snapshot = store.create(
        request,
        make_settings().prompt,
        FilmPromptRuleSet(themes=("Theme rule",), frames=("Frame rule",)),
    )
    store.checkpoint_themes(snapshot.run_id, [make_theme()], "test_cast")
    theme_file = tmp_path / "runs" / snapshot.run_id / "themes" / "T001.json"
    payload = json.loads(theme_file.read_text())
    payload["selected_cast"][0]["gender"] = "female"
    theme_file.write_text(json.dumps(payload))
    with pytest.raises(FilmStyleStorageError, match="fixed-gender mismatch"):
        store.inspect(snapshot.run_id)


@pytest.mark.asyncio
async def test_completed_resume_checks_parent_counts_against_frozen_child(
    tmp_path,
) -> None:
    request = FilmStylePromptRequest(film_style=make_request(), frames_per_theme=2)
    film_model = FakeFilmModel()
    prompt_model = FakePromptModel(
        [
            make_film_theme_batch(),
            frame_batch_text(make_film_frame_sequence()),
        ]
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    studio = FilmStylePromptStudio(
        film_model,
        prompt_model,
        store,
        make_settings(),
        resolve_film_style_rules(request),
    )
    completed = await studio.run(request, prompts_directory=tmp_path / "prompts")
    request_file = store.run_directory(completed.run_id) / "request.json"
    payload = json.loads(request_file.read_text())
    payload["female_count"] = 1
    payload["male_count"] = 1
    request_file.write_text(json.dumps(payload))
    with pytest.raises(FilmStyleStorageError, match="conflicts with parent counts"):
        await studio.resume(completed.run_id)
    assert film_model.calls == 1
    assert len(prompt_model.stages) == 2


def test_count_and_no_clone_rules_are_frozen_without_content_level_edits() -> None:
    rules = resolve_film_style_rules(FilmPromptOptions())
    for stage in (rules.themes, rules.frames):
        text = "\n".join(stage)
        assert "source_work_index" in text
        assert "selected_cast" in text
        assert "镜中倒影属于同一身份" in text
        assert "不得把同一 canonical_name 写成多个独立身体" in text
