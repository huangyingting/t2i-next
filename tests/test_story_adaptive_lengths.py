from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

import t2i_story_pipeline.inputs.compiler as compiler
from t2i_story_pipeline.errors import StoryRunIncompleteError
from t2i_story_pipeline.inputs import (
    InputOverrides,
    ResolvedStoryInput,
    StoryDocument,
    StoryRunConfiguration,
    resolve_story_input,
)
from t2i_story_pipeline.models import (
    NarrativeFrame,
    StoryQualityPolicy,
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
    StoryQualityError,
    check_frame_quality,
    quality_report,
)
from t2i_story_pipeline.run_store import LocalStoryRunStore, StoryRunSettings
from t2i_story_pipeline.studio import StoryStudio
from tests.story_factories import make_theme


@pytest.fixture
def workspace() -> Iterator[Path]:
    path = Path.cwd() / f".story-adaptive-test-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def visual(**cast) -> StoryDocument:
    return StoryDocument(description="Adult travelers at a station.", cast=cast)


def bounds(policy: StoryQualityPolicy):
    return (
        tuple((check.min_chars, check.max_chars) for check in policy.themes.checks),
        (policy.frames.checks[0].min_chars, policy.frames.checks[0].max_chars),
    )


def forms(policy: StoryQualityPolicy):
    return policy, policy.model_dump(), json.loads(policy.model_dump_json())


@pytest.mark.parametrize("language", ["chinese", "english"])
def test_explicit_equal_base_bounds_are_fixed_for_typed_and_serialized_policies(
    language,
):
    policy = StoryQualityPolicy(
        themes={
            "checks": [
                {
                    "type": "text_length",
                    "field": field,
                    "min_chars": minimum,
                    "max_chars": maximum,
                }
                for field, minimum, maximum in (
                    ("title", 4, 48),
                    ("premise", 160, 520),
                    ("style", 100, 360),
                )
            ]
        },
        frames={
            "checks": [{"type": "prose_length", "min_chars": 450, "max_chars": 950}]
        },
    )
    resolved = [
        resolve_story_input(
            visual(female_count=8, male_count=0),
            run_configuration=StoryRunConfiguration(
                generation={"output_language": language}, validation=value
            ),
        )
        for value in forms(policy)
    ]
    assert all(item == resolved[0] for item in resolved)
    assert bounds(resolved[0].quality_for("T001")) == (
        ((4, 48), (160, 520), (100, 360)),
        (450, 950),
    )
    assert all(
        check.extra_person_chars == 0
        for check in resolved[0].quality_for("T001").frames.checks
    )


@pytest.mark.parametrize("mode", ["off", "report", "enforce"])
@pytest.mark.parametrize("checks", [None, [], [{"type": "camera_evidence"}]])
def test_mode_only_inherits_but_explicit_checks_replace_with_stable_roundtrips(
    mode,
    checks,
):
    stage = {"mode": mode}
    if checks is not None:
        stage["checks"] = checks
    policy = StoryQualityPolicy(frames=stage)
    snapshots = [
        resolve_story_input(
            visual(female_count=8),
            run_configuration=StoryRunConfiguration(validation=value),
        )
        for value in forms(policy)
    ]
    assert snapshots[0] == snapshots[1] == snapshots[2]
    frames = snapshots[0].quality_for("T001").frames
    assert frames.mode == mode
    if checks is None:
        assert (frames.checks[0].min_chars, frames.checks[0].max_chars) == (1050, 1550)
    else:
        assert [check.type for check in frames.checks] == [
            check["type"] for check in checks
        ]
    assert len(snapshots[0].quality_for("T001").themes.checks) == 3


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"frame_min_chars": 450}, (450, 950)),
        ({"frame_max_chars": 950}, (450, 950)),
        ({"frame_min_chars": 700}, (700, 950)),
        ({"frame_max_chars": 1200}, (450, 1200)),
        ({"frame_min_chars": 450, "frame_max_chars": 950}, (450, 950)),
    ],
)
def test_partial_cli_override_fixes_whole_length_check(overrides, expected):
    resolved = resolve_story_input(
        visual(female_count=8, male_count=0), InputOverrides(**overrides)
    )
    assert bounds(resolved.quality_for("T001")) == (
        ((4, 48), (520, 880), (280, 540)),
        expected,
    )


@pytest.mark.parametrize(
    ("cast", "frame_bounds"),
    [
        ({}, (450, 950)),
        ({"female_count": 0}, (450, 950)),
        ({"female_count": 4}, (650, 1150)),
        ({"male_count": 5}, (750, 1250)),
        ({"female_count": 8}, (1050, 1550)),
        (
            {
                "scope": "travelers",
                "female_count": 1,
                "male_count": 1,
                "fixed_roles": [
                    {"id": "conductor", "sex": "male"},
                    {"id": "porter", "sex": "theme_choice"},
                ],
                "background_counts": [{"min": 20, "max": 30}],
            },
            (650, 1150),
        ),
    ],
)
def test_known_principal_minimum_includes_fixed_roles_but_not_backgrounds(
    cast,
    frame_bounds,
):
    resolved = resolve_story_input(visual(**cast))
    assert bounds(resolved.quality_for("T001"))[1] == frame_bounds
    assert resolved.request.theme_count == 1
    assert resolved.request.frames_per_theme == 6
    assert resolved.runtime == StoryRunConfiguration().runtime


@pytest.mark.parametrize(
    ("language", "people", "expected"),
    [
        ("chinese", 2, (((4, 48), (160, 520), (100, 360)), (450, 950))),
        ("english", 2, (((4, 96), (320, 1040), (200, 720)), (900, 1900))),
        ("english", 8, (((4, 96), (1040, 1760), (560, 1080)), (2100, 3100))),
    ],
)
def test_language_defaults_are_selected_before_cast_scaling(language, people, expected):
    resolved = resolve_story_input(
        visual(female_count=people, male_count=0),
        InputOverrides(output_language=language),
    )
    assert bounds(resolved.quality_for("T001")) == expected
    assert (
        ResolvedStoryInput.model_validate_json(resolved.model_dump_json()) == resolved
    )
    policy = resolved.quality_for("T001")
    frame = policy.frames.checks[0]
    assert not check_frame_quality(
        policy.frames,
        language,
        "T001",
        NarrativeFrame(frame_id="F01", prose="a" * frame.min_chars),
    )
    assert check_frame_quality(
        policy.frames,
        language,
        "T001",
        NarrativeFrame(frame_id="F01", prose="a" * (frame.min_chars - 1)),
    )
    assert (
        f"{frame.min_chars} to {frame.max_chars} characters"
        in frame_messages(
            resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
        )[0].content
    )


def test_english_partial_override_retains_english_base_other_bound():
    resolved = resolve_story_input(
        visual(female_count=8),
        InputOverrides(output_language="english", frame_min_chars=450),
    )
    assert bounds(resolved.quality_for("T001"))[1] == (450, 1900)


def mixed_input(workspace: Path) -> ResolvedStoryInput:
    catalogs = workspace / "_catalogs"
    catalogs.mkdir()
    (catalogs / "cast.yaml").write_text(
        "id: cast\nslots: [solo, group]\nentries:\n"
        "  - id: solo\n    cast: {total: 1}\n"
        "  - id: group\n    cast: {total: 8}\n",
        encoding="utf-8",
    )
    return resolve_story_input(
        StoryDocument(
            description="Adult travelers at a station.",
            allocation={"type": "fixed_slots", "catalog": "cast"},
        ),
        run_configuration=StoryRunConfiguration(
            generation={"theme_count": 2},
            runtime={"generation_retries": 0, "concurrency": 1},
        ),
        asset_root=workspace,
    )


def test_mixed_catalog_freezes_distinct_theme_policies_and_prompt_targets(workspace):
    resolved = mixed_input(workspace)
    assert bounds(resolved.quality_for("T001")) == (
        ((4, 48), (160, 520), (100, 360)),
        (450, 950),
    )
    assert bounds(resolved.quality_for("T002")) == (
        ((4, 48), (520, 880), (280, 540)),
        (1050, 1550),
    )
    prompt = theme_messages(resolved, count=2, existing_themes=[])[0].content
    assert "For T001 only: Write each Theme's premise using 160 to 520" in prompt
    assert "For T002 only: Write each Theme's premise using 520 to 880" in prompt
    single = theme_messages(resolved, count=1, existing_themes=[make_theme()])[
        0
    ].content
    assert "520 to 880" in single
    assert "160 to 520" not in single
    for theme_id, text, absent in (
        ("T001", "450 to 950", "1050 to 1550"),
        ("T002", "1050 to 1550", "450 to 950"),
    ):
        prompt = frame_messages(
            resolved,
            make_theme(int(theme_id[1:])),
            requested_frame_ids=["F01"],
            accepted_frames=[],
        )[0].content
        assert text in prompt and absent not in prompt
    payload = resolved.model_dump(mode="json")
    payload["effective_quality"][1]["policy"]["frames"]["checks"][0]["min_chars"] = 450
    with pytest.raises(ValidationError, match="effective quality"):
        ResolvedStoryInput.model_validate(payload)
    payload = resolved.model_dump(mode="json")
    del payload["effective_quality"]
    with pytest.raises(ValidationError, match="effective_quality"):
        ResolvedStoryInput.model_validate(payload)
    with pytest.raises(ValidationError, match="frozen"):
        resolved.quality_for("T001").frames.checks[0].min_chars = 1


class BudgetModel:
    def __init__(self, resolved, *, fail_group=False):
        self.resolved = resolved
        self.fail_group = fail_group
        self.calls = []

    async def generate(self, *, messages, response_model, **kwargs):
        payload = json.loads(messages[1].content)
        self.calls.append((StoryStage.THEMES, messages[0].content, payload))
        themes = []
        for plan in payload["input_context"]["plans"]:
            policy = self.resolved.quality_for(plan["theme_id"])
            themes.append(
                {
                    "diversity": make_theme(int(plan["theme_id"][1:])).diversity,
                    **{
                        check.field: "字" * check.min_chars
                        for check in policy.themes.checks
                    },
                }
            )
        return ModelResponse(
            value=response_model(semantic_name="station_travelers", themes=themes),
            usage=TokenUsage(),
        )

    async def generate_text(self, *, messages, **kwargs):
        payload = json.loads(messages[1].content)
        self.calls.append((StoryStage.FRAMES, messages[0].content, payload))
        theme_id = payload["theme"]["theme_id"]
        minimum = self.resolved.quality_for(theme_id).frames.checks[0].min_chars
        frames = []
        for frame_id in payload["requested_frame_slots"]:
            invalid = self.fail_group and theme_id == "T002" and frame_id == "F02"
            description = (
                f"第{int(frame_id[1:])}幅画面中成年旅人正在站台边等候列车。"
                + "侧后方站灯勾勒外套纹理，浅景深清楚保留人物视线与手部动作。" * 100
            )
            prose = description[: minimum - int(invalid)]
            frames.append(f"<FRAME>{prose}</FRAME>")
        return TextModelResponse(text="".join(frames), usage=TokenUsage())


@pytest.mark.asyncio
async def test_mixed_policies_drive_validation_publication_and_frozen_recovery(
    workspace,
    monkeypatch,
):
    resolved = mixed_input(workspace)
    store = LocalStoryRunStore(workspace / "runs", workspace / "prompts")
    settings = StoryRunSettings(
        provider=StoryProviderSettings(model="fake"),
        **resolved.runtime.model_dump(),
        quality=resolved.quality,
    )
    model = BudgetModel(resolved, fail_group=True)
    with pytest.raises(StoryRunIncompleteError) as error:
        await StoryStudio(model, store, settings).run(resolved)
    run_id = error.value.run_id
    frozen = store.inspect(run_id)
    assert len(frozen.frames["T001"].frames) == 6
    assert [frame.frame_id for frame in frozen.frames["T002"].frames] == [
        "F01",
        "F03",
        "F04",
        "F05",
        "F06",
    ]
    assert any(
        issue.theme_id == "T002" and issue.frame_id == "F02"
        for attempt in store.attempts(run_id)
        for issue in attempt.quality_issues
    )
    shutil.rmtree(workspace / "_catalogs")

    def no_current_defaults(*args, **kwargs):
        pytest.fail("resume must not resolve current length defaults")

    monkeypatch.setattr(compiler, "default_validation", no_current_defaults)
    resumed = BudgetModel(frozen.input)
    completed = await StoryStudio(resumed, store, settings).resume(run_id)
    assert len(resumed.calls) == 1
    stage, system, payload = resumed.calls[0]
    assert stage == StoryStage.FRAMES
    assert payload["requested_frame_slots"] == ["F02"]
    assert "1050 to 1550" in system
    assert completed.result.quality.status == "passed"
    assert completed.published.prompt_file.is_file()
    assert store.inspect(run_id).input.effective_quality == resolved.effective_quality
    damaged = completed.result.themes[1].model_copy(
        update={"frames": [NarrativeFrame(frame_id="F01", prose="字" * 950)]}
    )
    with pytest.raises(StoryQualityError, match="T002-F01"):
        quality_report(
            frozen.input.effective_quality,
            frozen.request.output_language,
            [completed.result.themes[0], damaged],
        )
