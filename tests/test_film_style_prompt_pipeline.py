from __future__ import annotations

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
from t2i_film_style_pipeline.provider import (
    FilmStyleProviderSettings,
)
from t2i_film_style_pipeline.provider import (
    ModelResponse as FilmModelResponse,
)
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from t2i_story_pipeline.errors import StoryProviderResponseError
from t2i_story_pipeline.models import (
    NarrativeFrameSequence,
    StoryStage,
    TokenUsage,
)
from t2i_story_pipeline.provider import (
    ModelResponse as StoryModelResponse,
)
from t2i_story_pipeline.provider import (
    StoryProviderSettings,
)
from t2i_story_pipeline.run_store import StoryRunSettings
from tests.story_factories import make_frame_sequence, make_theme_batch
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


class FakeStoryModel:
    def __init__(self, values: list[object]) -> None:
        self._values = iter(values)
        self.stages: list[StoryStage] = []

    async def generate(
        self,
        *,
        stage,
        messages,
        response_model,
        max_output_tokens,
    ):
        self.stages.append(stage)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        return StoryModelResponse(
            value=value,
            usage=TokenUsage(total_tokens=10),
        )


def make_pipeline_request() -> FilmStylePromptRequest:
    return FilmStylePromptRequest(
        film_style=make_request(),
        theme_count=1,
        frames_per_theme=2,
    )


def make_film_frame_sequence() -> NarrativeFrameSequence:
    sequence = make_frame_sequence()
    source_sentence = frame_source_sentence(make_request())
    for frame in sequence.frames:
        frame.prose = (
            f"{source_sentence}中国古代的雨夜，两名成年人物在庭院灯下"
            "相互注视，前景帘幕与背景砖墙建立纵深，中景人物的克制动作由"
            "平视中景记录，暖灯和冷雨形成清楚反差。灰砖、旧木和粗布分别"
            "吸收来自左侧的暖色灯光，右后方冷色天光沿人物肩线形成清楚轮廓，"
            "两人都以稳固站姿承担自身重量，手臂保持自然放松，视线持续回应，"
            "门洞、廊柱与后窗组成三层空间，焦点落在成熟面容和相触的手部，"
            "前景帘幕略微柔化，背景纹理仍然可辨。低饱和灰黑环境只以深红"
            "灯笼形成色彩重音，潮湿地面留下有限反光，细密颗粒和柔和高光"
            "保持真实、克制、自然可信且可以直接摄影执行的长片质感。"
        )
    return sequence


def make_settings(*, generation_retries: int = 0) -> FilmStylePipelineSettings:
    return FilmStylePipelineSettings(
        film_provider=FilmStyleProviderSettings(model="test-model"),
        story=StoryRunSettings(
            provider=StoryProviderSettings(model="test-model"),
            concurrency=1,
            generation_retries=generation_retries,
        ),
    )


@pytest.mark.asyncio
async def test_pipeline_retries_rejected_film_frame_content(tmp_path) -> None:
    request = make_pipeline_request()
    bad_sequence = make_film_frame_sequence()
    bad_sequence.frames[0].prose = (
        f"{frame_source_sentence(make_request())}抱歉，我无法协助创作这个画面。"
    )
    story_model = FakeStoryModel(
        [
            make_theme_batch(),
            bad_sequence,
            make_film_frame_sequence(),
        ]
    )

    completed = await FilmStylePromptStudio(
        FakeFilmModel(),
        story_model,
        LocalFilmStyleRunStore(tmp_path / "runs"),
        make_settings(generation_retries=1),
        resolve_film_style_rules(
            request.story_request("BRIEF\n\nDirector scene context.")
        ),
    ).run(request, prompts_directory=tmp_path / "prompts")

    assert completed.prompt_file.exists()
    assert story_model.stages == [
        StoryStage.THEMES,
        StoryStage.FRAMES,
        StoryStage.FRAMES,
    ]


@pytest.mark.asyncio
async def test_pipeline_resumes_story_without_regenerating_profile(tmp_path) -> None:
    request = make_pipeline_request()
    settings = make_settings()
    rules = resolve_film_style_rules(
        request.story_request("BRIEF\n\nDirector scene context.")
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    film_model = FakeFilmModel()
    first_story_model = FakeStoryModel(
        [
            make_theme_batch(),
            StoryProviderResponseError("temporary frame failure"),
        ]
    )
    studio = FilmStylePromptStudio(
        film_model,
        first_story_model,
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
    assert failed.manifest.story_run_id is not None
    assert film_model.calls == 1

    resumed_story_model = FakeStoryModel([make_film_frame_sequence()])
    completed = await FilmStylePromptStudio(
        film_model,
        resumed_story_model,
        store,
        settings,
        rules,
    ).resume(run_id)

    assert completed.run_id == run_id
    assert completed.prompt_file.exists()
    assert completed.prompt_file.name == "张艺谋_0001.txt"
    assert completed.compiled_story_file.name == "compiled-story.txt"
    assert completed.compiled_story_file.is_file()
    assert film_model.calls == 1
    assert resumed_story_model.stages == [StoryStage.FRAMES]
    assert store.inspect(run_id).manifest.status == FilmStyleRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_pipeline_can_resume_after_profile_provider_failure(tmp_path) -> None:
    request = make_pipeline_request()
    settings = make_settings()
    rules = resolve_film_style_rules(
        request.story_request("BRIEF\n\nDirector scene context.")
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")

    class FailingFilmModel:
        async def generate(self, **_kwargs):
            raise FilmStyleProviderError("temporary profile failure")

    with pytest.raises(FilmStyleRunIncompleteError) as caught:
        await FilmStylePromptStudio(
            FailingFilmModel(),
            FakeStoryModel([]),
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
        FakeStoryModel(
            [
                make_theme_batch(),
                make_film_frame_sequence(),
            ]
        ),
        store,
        settings,
        rules,
    ).resume(run_id)

    assert completed.run_id == run_id
    assert completed.prompt_file.exists()
    assert store.inspect(run_id).manifest.status == FilmStyleRunStatus.COMPLETED
