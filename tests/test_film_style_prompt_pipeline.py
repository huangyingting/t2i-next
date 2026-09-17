from __future__ import annotations

import pytest

from t2i_film_style_pipeline.authoring_rules import resolve_film_style_rules
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
from t2i_story_pipeline.errors import StoryProviderResponseError
from t2i_story_pipeline.models import StoryStage, TokenUsage
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


def make_settings() -> FilmStylePipelineSettings:
    return FilmStylePipelineSettings(
        film_provider=FilmStyleProviderSettings(model="test-model"),
        story=StoryRunSettings(
            provider=StoryProviderSettings(model="test-model"),
            concurrency=1,
            generation_retries=0,
        ),
    )


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
    assert failed.manifest.profile_run_id is not None
    assert failed.manifest.story_run_id is not None
    assert film_model.calls == 1

    resumed_story_model = FakeStoryModel([make_frame_sequence()])
    completed = await FilmStylePromptStudio(
        film_model,
        resumed_story_model,
        store,
        settings,
        rules,
    ).resume(run_id)

    assert completed.run_id == run_id
    assert completed.prompt_file.exists()
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
                make_frame_sequence(),
            ]
        ),
        store,
        settings,
        rules,
    ).resume(run_id)

    assert completed.run_id == run_id
    assert completed.prompt_file.exists()
    assert store.inspect(run_id).manifest.status == FilmStyleRunStatus.COMPLETED
