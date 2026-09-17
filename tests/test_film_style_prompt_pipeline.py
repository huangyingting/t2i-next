from __future__ import annotations

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
from t2i_film_style_pipeline.prompt_models import (
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


def make_settings(*, generation_retries: int = 0) -> FilmStylePipelineSettings:
    return FilmStylePipelineSettings(
        film_provider=FilmStyleProviderSettings(model="test-model"),
        prompt=FilmPromptRunSettings(
            provider=FilmPromptProviderSettings(model="test-model"),
            concurrency=1,
            generation_retries=generation_retries,
            theme_output_mode=ThemeOutputMode.STRUCTURED_WITHOUT_IDS,
        ),
    )


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
