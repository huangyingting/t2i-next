from __future__ import annotations

import asyncio
import json

import pytest

from t2i_film_style_pipeline.compiler import frame_source_sentence
from t2i_film_style_pipeline.errors import (
    FilmStyleProviderError,
    FilmStyleRunIncompleteError,
)
from t2i_film_style_pipeline.models import TokenUsage as FilmTokenUsage
from t2i_film_style_pipeline.pipeline import (
    FilmStylePipelineSettings,
    FilmStylePromptRequest,
    FilmStylePromptStudio,
    FilmStyleRunStatus,
    LocalFilmStyleRunStore,
)
from t2i_film_style_pipeline.prompt_messages import theme_messages
from t2i_film_style_pipeline.prompt_models import (
    FilmPromptRuleSet,
    FilmPromptStage,
    NarrativeFrameSequence,
    NarrativeThemeBatch,
    NarrativeThemeDraftBatch,
    TokenUsage,
)
from t2i_film_style_pipeline.prompt_provider import (
    FilmPromptProviderSettings,
    TextModelResponse,
)
from t2i_film_style_pipeline.prompt_provider import (
    ModelResponse as PromptModelResponse,
)
from t2i_film_style_pipeline.prompt_run_store import (
    FilmPromptRunSettings,
    LocalFilmPromptRunStore,
    ThemeOutputMode,
)
from t2i_film_style_pipeline.provider import (
    FilmStyleProviderSettings,
)
from t2i_film_style_pipeline.provider import (
    ModelResponse as FilmModelResponse,
)
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from tests.film_prompt_factories import make_frame_sequence, make_theme_batch
from tests.test_film_style_pipeline import make_profile, make_request


class FakeFilmModel:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        return FilmModelResponse(
            value=make_profile(),
            usage=FilmTokenUsage(total_tokens=20),
        )


class FakePromptModel:
    def __init__(self, values: list[object]) -> None:
        self._values = iter(values)
        self.stages: list[FilmPromptStage] = []
        self.messages = []

    async def generate(
        self,
        *,
        stage,
        messages,
        response_model,
        max_output_tokens,
    ):
        self.stages.append(stage)
        self.messages.append(messages)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        if (
            isinstance(value, NarrativeThemeBatch)
            and issubclass(response_model, NarrativeThemeDraftBatch)
        ):
            value = response_model.model_validate(
                {
                    "semantic_name": value.semantic_name,
                    "themes": [
                        theme.model_dump(exclude={"theme_id"})
                        for theme in value.themes
                    ],
                }
            )
        return PromptModelResponse(
            value=value,
            usage=TokenUsage(total_tokens=10),
        )

    async def generate_text(
        self,
        *,
        stage,
        messages,
        max_output_tokens,
    ) -> TextModelResponse:
        self.stages.append(stage)
        self.messages.append(messages)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        if not isinstance(value, str):
            raise TypeError("fake text response must be a string")
        return TextModelResponse(
            text=value,
            usage=TokenUsage(total_tokens=10),
        )


def frame_batch_text(sequence: NarrativeFrameSequence) -> str:
    return "\n".join(f"<FRAME>{frame.prose}</FRAME>" for frame in sequence.frames)


def make_pipeline_request() -> FilmStylePromptRequest:
    return FilmStylePromptRequest(
        film_style=make_request(),
        theme_count=1,
        frames_per_theme=2,
    )


def make_film_theme_batch():
    batch = make_theme_batch()
    for theme in batch.themes:
        theme.premise = (
            f"原作成年人物无名与飞雪位于秦宫大殿。{theme.premise}"
        )
    return batch


def make_film_frame_sequence() -> NarrativeFrameSequence:
    sequence = make_frame_sequence()
    source_sentence = frame_source_sentence(make_request())
    for frame in sequence.frames:
        frame.prose = (
            f"{source_sentence}战国秦宫大殿的雨夜，原作成年人物无名与飞雪"
            "站在深远中轴两侧，黑色殿柱与石质地面向后延伸，长剑横放在"
            "两人之间；无名穿深色战国长袍与黑色束冠，飞雪穿单色交领长袍"
            "与宽大衣袖。两人在庭院灯下"
            "相互注视，前景帘幕与背景砖墙建立纵深。摄影机机位设在两人"
            "正面约三米处，以眼平高度和轻微三分之二侧前角度平视，使用"
            "五十毫米标准镜头拍摄中景，自然透视保持人物与庭院尺度，"
            "主焦点落在成熟面容和相触的手部，前景帘幕略微柔化形成框景，"
            "背景砖墙在中等景深内仍清晰可辨。暖灯和冷雨形成清楚反差。"
            "灰砖、旧木和粗布分别"
            "吸收来自左侧的暖色灯光，右后方冷色天光沿人物肩线形成清楚轮廓，"
            "两人都以稳固站姿承担自身重量，手臂保持自然放松，视线持续回应，"
            "门洞、廊柱与后窗组成三层空间，焦点落在成熟面容和相触的手部，"
            "背景纹理仍然可辨。低饱和灰黑环境只以深红"
            "灯笼形成色彩重音，潮湿地面留下有限反光，细密颗粒和柔和高光"
            "保持真实、克制、自然可信且可以直接摄影执行的长片质感。"
        )
    return sequence


def make_settings(
    *,
    generation_retries: int = 0,
    validate_themes: bool = True,
    validate_frames: bool = True,
    concurrency: int = 1,
    theme_batch_size: int = 1,
) -> FilmStylePipelineSettings:
    return FilmStylePipelineSettings(
        film_provider=FilmStyleProviderSettings(model="test-model"),
        prompt=FilmPromptRunSettings(
            provider=FilmPromptProviderSettings(model="test-model"),
            concurrency=concurrency,
            generation_retries=generation_retries,
            theme_batch_size=theme_batch_size,
            theme_output_mode=ThemeOutputMode.STRUCTURED_WITHOUT_IDS,
        ),
        validate_themes=validate_themes,
        validate_frames=validate_frames,
    )


def test_theme_messages_use_compact_global_diversity_ledger() -> None:
    request = make_pipeline_request().prompt_request(
        "BRIEF\n\nDirector scene context."
    )
    existing = make_theme_batch(start=1, count=2).themes
    existing[0].premise = "甲" * 400
    existing[0].style = "乙" * 400
    resolved_rules = resolve_film_style_rules(request)
    rules = FilmPromptRuleSet(
        themes=resolved_rules.themes,
        frames=resolved_rules.frames,
    )

    payload = json.loads(
        theme_messages(
            request,
            rules,
            start_index=3,
            count=2,
            existing_themes=existing,
            semantic_name="film_run",
            program_assigns_ids=True,
        )[1].content
    )

    assert "existing_themes" not in payload
    assert payload["diversity_ledger"]["used_titles"] == [
        theme.title for theme in existing
    ]
    signatures = payload["diversity_ledger"]["used_theme_signatures"]
    assert [item["theme_id"] for item in signatures] == ["T001", "T002"]
    assert len(signatures[0]["premise_excerpt"]) == 180
    assert len(signatures[0]["style_excerpt"]) == 140
    targets = payload["current_batch_novelty_targets"]
    assert [target["output_position"] for target in targets] == [1, 2]
    assert all(len(target["novelty_priorities"]) == 2 for target in targets)


@pytest.mark.asyncio
async def test_pipeline_can_disable_all_semantic_validation(tmp_path) -> None:
    request = make_pipeline_request()
    theme_batch = make_film_theme_batch()
    theme_batch.themes[0].premise = (
        "这是一段不包含原作人物、场景或内容证据的普通主题描述。"
    )
    sequence = make_film_frame_sequence()
    for index, frame in enumerate(sequence.frames, start=1):
        frame.prose = f"第 {index} 个没有来源、锚点或摄影证据的未验证画面正文。"
    prompt_model = FakePromptModel(
        [theme_batch, frame_batch_text(sequence)]
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")

    completed = await FilmStylePromptStudio(
        FakeFilmModel(),
        prompt_model,
        store,
        make_settings(
            validate_themes=False,
            validate_frames=False,
        ),
        resolve_film_style_rules(
            request.prompt_request("BRIEF\n\nDirector scene context.")
        ),
    ).run(request, prompts_directory=tmp_path / "prompts")

    snapshot = store.inspect(completed.run_id)
    assert completed.prompt_file.exists()
    assert snapshot.settings.validate_themes is False
    assert snapshot.settings.validate_frames is False
    assert prompt_model.stages == [
        FilmPromptStage.THEMES,
        FilmPromptStage.FRAMES,
    ]


@pytest.mark.asyncio
async def test_pipeline_generates_frames_while_next_theme_is_in_flight(
    tmp_path,
) -> None:
    request = FilmStylePromptRequest(
        film_style=make_request(),
        theme_count=4,
        frames_per_theme=1,
    )

    class PipelinedPromptModel:
        def __init__(self) -> None:
            self.theme_calls = 0
            self.active_calls = 0
            self.max_active_calls = 0
            self.second_theme_started = asyncio.Event()
            self.first_frame_started = asyncio.Event()
            self.overlap_recorded = asyncio.Event()
            self.overlap_observed = False

        def _start_call(self) -> None:
            self.active_calls += 1
            self.max_active_calls = max(
                self.max_active_calls,
                self.active_calls,
            )

        def _finish_call(self) -> None:
            self.active_calls -= 1

        async def generate(
            self,
            *,
            stage,
            messages,
            response_model,
            max_output_tokens,
        ):
            assert stage == FilmPromptStage.THEMES
            self._start_call()
            try:
                self.theme_calls += 1
                index = self.theme_calls
                if index == 2:
                    self.second_theme_started.set()
                    await asyncio.wait_for(
                        self.first_frame_started.wait(),
                        timeout=1,
                    )
                    self.overlap_observed = self.active_calls == 2
                    self.overlap_recorded.set()
                start = 1 if index == 1 else 3
                batch = make_theme_batch(start=start, count=2)
                for theme in batch.themes:
                    theme.premise = (
                        f"原作成年人物无名与飞雪位于秦宫大殿。"
                        f"{theme.premise}"
                    )
                value = response_model.model_validate(
                    {
                        "semantic_name": batch.semantic_name,
                        "themes": [
                            theme.model_dump(exclude={"theme_id"})
                            for theme in batch.themes
                        ],
                    }
                )
                return PromptModelResponse(
                    value=value,
                    usage=TokenUsage(total_tokens=10),
                )
            finally:
                self._finish_call()

        async def generate_text(
            self,
            *,
            stage,
            messages,
            max_output_tokens,
        ) -> TextModelResponse:
            assert stage == FilmPromptStage.FRAMES
            self._start_call()
            try:
                await asyncio.wait_for(
                    self.second_theme_started.wait(),
                    timeout=1,
                )
                if not self.first_frame_started.is_set():
                    self.first_frame_started.set()
                    await asyncio.wait_for(
                        self.overlap_recorded.wait(),
                        timeout=1,
                    )
                sequence = make_film_frame_sequence()
                return TextModelResponse(
                    text=frame_batch_text(
                        NarrativeFrameSequence(
                            frames=[sequence.frames[0]]
                        )
                    ),
                    usage=TokenUsage(total_tokens=10),
                )
            finally:
                self._finish_call()

    prompt_model = PipelinedPromptModel()
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    completed = await FilmStylePromptStudio(
        FakeFilmModel(),
        prompt_model,
        store,
        make_settings(
            concurrency=2,
            theme_batch_size=2,
            validate_themes=False,
            validate_frames=False,
        ),
        resolve_film_style_rules(
            request.prompt_request("BRIEF\n\nDirector scene context.")
        ),
    ).run(request, prompts_directory=tmp_path / "prompts")

    assert completed.prompt_file.exists()
    assert prompt_model.overlap_observed is True
    assert prompt_model.max_active_calls == 2
    snapshot = LocalFilmPromptRunStore(
        store.prompt_runs_directory(completed.run_id)
    ).inspect(completed.prompt_run_id)
    assert len(snapshot.themes) == 4
    assert set(snapshot.frames) == {"T001", "T002", "T003", "T004"}
    assert all(len(sequence.frames) == 1 for sequence in snapshot.frames.values())


@pytest.mark.asyncio
async def test_pipeline_retries_rejected_film_frame_content(tmp_path) -> None:
    request = make_pipeline_request()
    bad_sequence = make_film_frame_sequence()
    bad_sequence.frames[0].prose = (
        f"{frame_source_sentence(make_request())}抱歉，我无法协助创作这个画面。"
    )
    prompt_model = FakePromptModel(
        [
            make_film_theme_batch(),
            frame_batch_text(bad_sequence),
            frame_batch_text(
                NarrativeFrameSequence(
                    frames=[make_film_frame_sequence().frames[0]]
                )
            ),
        ]
    )

    completed = await FilmStylePromptStudio(
        FakeFilmModel(),
        prompt_model,
        LocalFilmStyleRunStore(tmp_path / "runs"),
        make_settings(generation_retries=1),
        resolve_film_style_rules(
            request.prompt_request("BRIEF\n\nDirector scene context.")
        ),
    ).run(request, prompts_directory=tmp_path / "prompts")

    assert completed.prompt_file.exists()
    assert prompt_model.stages == [
        FilmPromptStage.THEMES,
        FilmPromptStage.FRAMES,
        FilmPromptStage.FRAMES,
    ]
    initial_payload = json.loads(prompt_model.messages[1][1].content)
    retry_payload = json.loads(prompt_model.messages[2][1].content)
    assert initial_payload["requested_frame_slots"] == ["F01", "F02"]
    assert initial_payload["accepted_frame_prose"] == []
    assert retry_payload["requested_frame_slots"] == ["F01"]
    assert retry_payload["accepted_frame_prose"] == [
        make_film_frame_sequence().frames[1].prose
    ]


@pytest.mark.asyncio
async def test_pipeline_resumes_prompt_without_regenerating_profile(tmp_path) -> None:
    request = make_pipeline_request()
    settings = make_settings()
    rules = resolve_film_style_rules(
        request.prompt_request("BRIEF\n\nDirector scene context.")
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    film_model = FakeFilmModel()
    partial_sequence = make_film_frame_sequence()
    partial_sequence.frames[1].prose = (
        f"{frame_source_sentence(make_request())}抱歉，我无法协助创作这个画面。"
    )
    first_prompt_model = FakePromptModel(
        [make_film_theme_batch(), frame_batch_text(partial_sequence)]
    )
    studio = FilmStylePromptStudio(
        film_model,
        first_prompt_model,
        store,
        settings,
        rules,
    )

    with pytest.raises(FilmStyleRunIncompleteError) as caught:
        await studio.run(
            request,
            prompts_directory=tmp_path / "prompts",
        )

    run_id = caught.value.run_id
    failed = store.inspect(run_id)
    assert failed.manifest.status == FilmStyleRunStatus.FAILED
    assert failed.rules.profile == rules.profile
    assert failed.manifest.profile_run_id is not None
    assert failed.manifest.prompt_run_id is not None
    assert film_model.calls == 1
    prompt_run = next(
        (tmp_path / "runs" / run_id / "prompt-runs").iterdir()
    )
    assert (prompt_run / "frames/T001/F01.json").is_file()
    assert not (prompt_run / "frames/T001/F02.json").exists()

    resumed_sequence = make_film_frame_sequence()
    resumed_prompt_model = FakePromptModel(
        [
            frame_batch_text(
                NarrativeFrameSequence(frames=[resumed_sequence.frames[1]])
            )
        ]
    )
    completed = await FilmStylePromptStudio(
        film_model,
        resumed_prompt_model,
        store,
        settings,
        rules,
    ).resume(run_id)

    assert completed.run_id == run_id
    assert completed.prompt_file.exists()
    assert completed.prompt_file.name == "张艺谋_0001.txt"
    assert completed.compiled_context_file.name == "compiled-context.txt"
    assert completed.compiled_context_file.is_file()
    assert film_model.calls == 1
    assert resumed_prompt_model.stages == [
        FilmPromptStage.FRAMES,
    ]
    resumed_payload = json.loads(resumed_prompt_model.messages[0][1].content)
    assert resumed_payload["requested_frame_slots"] == ["F02"]
    assert resumed_payload["accepted_frame_prose"] == [
        resumed_sequence.frames[0].prose
    ]
    assert store.inspect(run_id).manifest.status == FilmStyleRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_pipeline_can_resume_after_profile_provider_failure(tmp_path) -> None:
    request = make_pipeline_request()
    settings = make_settings()
    rules = resolve_film_style_rules(
        request.prompt_request("BRIEF\n\nDirector scene context.")
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")

    class FailingFilmModel:
        async def generate(self, **_kwargs):
            raise FilmStyleProviderError("temporary profile failure")

    with pytest.raises(FilmStyleRunIncompleteError) as caught:
        await FilmStylePromptStudio(
            FailingFilmModel(),
            FakePromptModel([]),
            store,
            settings,
            rules,
        ).run(
            request,
            prompts_directory=tmp_path / "prompts",
        )

    run_id = caught.value.run_id
    failed = store.inspect(run_id)
    assert failed.manifest.status == FilmStyleRunStatus.FAILED
    assert failed.manifest.profile_run_id is None

    completed = await FilmStylePromptStudio(
        FakeFilmModel(),
        FakePromptModel(
            [
                make_film_theme_batch(),
                frame_batch_text(make_film_frame_sequence()),
            ]
        ),
        store,
        settings,
        rules,
    ).resume(run_id)

    assert completed.run_id == run_id
    assert completed.prompt_file.exists()
    assert store.inspect(run_id).manifest.status == FilmStyleRunStatus.COMPLETED
