"""Generate final narrative paragraphs behind one small interface."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from pydantic import BaseModel

from t2i_story_pipeline.errors import (
    StoryContractError,
    StoryProviderResponseError,
    UnsafeStoryError,
)
from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeFrameSequence,
    NarrativeTheme,
    NarrativeThemeBatch,
    NarrativeThemeResult,
    StoryRequest,
    StoryResult,
    StoryStage,
    TokenUsage,
    exact_frame_sequence_model,
    exact_theme_batch_model,
)
from t2i_story_pipeline.prompts import frame_messages, theme_messages
from t2i_story_pipeline.provider import ChatMessage, StoryModel
from t2i_story_pipeline.safety import (
    normalize_generated_adult_language,
    validate_generated_story,
    validate_source_story,
)


class StoryStudio:
    """Turn one story request directly into final prose image prompts."""

    def __init__(
        self,
        model: StoryModel,
        *,
        concurrency: int = 10,
        generation_retries: int = 2,
    ) -> None:
        if not 1 <= concurrency <= 32:
            raise ValueError("concurrency 必须介于 1 和 32")
        if not 0 <= generation_retries <= 5:
            raise ValueError("generation_retries 必须介于 0 和 5")
        self._model = model
        self._concurrency = concurrency
        self._generation_retries = generation_retries

    async def generate(self, request: StoryRequest) -> StoryResult:
        validate_source_story(
            request.story,
            require_intimate_consent=(
                request.content_level
                in {ContentLevel.EROTIC, ContentLevel.HARDCORE}
            ),
        )
        themes, theme_usage = await self._generate_themes(request)
        semaphore = asyncio.Semaphore(self._concurrency)

        async def generate_theme(
            theme: NarrativeTheme,
        ) -> tuple[NarrativeThemeResult, TokenUsage]:
            async with semaphore:
                return await self._generate_frames(request, theme)

        generated = await asyncio.gather(
            *(generate_theme(theme) for theme in themes)
        )
        usage = theme_usage
        results: list[NarrativeThemeResult] = []
        for result, frame_usage in generated:
            results.append(result)
            usage += frame_usage
        return StoryResult(
            run_id=uuid4().hex[:12],
            request=request,
            themes=results,
            usage=usage,
        )

    async def _generate_themes(
        self,
        request: StoryRequest,
    ) -> tuple[list[NarrativeTheme], TokenUsage]:
        themes: list[NarrativeTheme] = []
        usage = TokenUsage()
        while len(themes) < request.theme_count:
            start_index = len(themes) + 1
            count = min(10, request.theme_count - len(themes))
            messages = theme_messages(
                request,
                start_index=start_index,
                count=count,
                existing_themes=themes,
            )

            def validate(
                value: BaseModel,
                expected_start: int = start_index,
                expected_count: int = count,
            ) -> None:
                if not isinstance(value, NarrativeThemeBatch):
                    raise StoryContractError("provider 返回了错误的主题类型")
                for theme in value.themes:
                    theme.title = normalize_generated_adult_language(
                        theme.title
                    )
                    theme.premise = normalize_generated_adult_language(
                        theme.premise
                    )
                    theme.style = normalize_generated_adult_language(
                        theme.style
                    )
                expected = [
                    f"T{index:03d}"
                    for index in range(
                        expected_start,
                        expected_start + expected_count,
                    )
                ]
                actual = [theme.theme_id for theme in value.themes]
                if actual != expected:
                    raise StoryContractError(
                        "主题数量或顺序不符合请求："
                        f"expected={expected}, actual={actual}"
                    )
                validate_generated_story(
                    value.model_dump_json(ensure_ascii=False)
                )

            value, batch_usage = await self._generate_validated(
                stage=StoryStage.THEMES,
                messages=messages,
                response_model=exact_theme_batch_model(count),
                max_output_tokens=6000,
                validate=validate,
            )
            if not isinstance(value, NarrativeThemeBatch):
                raise AssertionError("validated theme response changed type")
            themes.extend(value.themes)
            usage += batch_usage
        return themes, usage

    async def _generate_frames(
        self,
        request: StoryRequest,
        theme: NarrativeTheme,
    ) -> tuple[NarrativeThemeResult, TokenUsage]:
        expected = [
            f"F{index:02d}"
            for index in range(1, request.frames_per_theme + 1)
        ]

        def validate_ids(
            value: BaseModel,
            expected_ids: list[str] = expected,
        ) -> None:
            if not isinstance(value, NarrativeFrameSequence):
                raise StoryContractError("provider 返回了错误的画面类型")
            for frame in value.frames:
                frame.prose = normalize_generated_adult_language(frame.prose)
            actual = [frame.frame_id for frame in value.frames]
            if actual != expected_ids:
                raise StoryContractError(
                    "画面数量或顺序不符合请求："
                    f"expected={expected_ids}, actual={actual}"
                )
            for frame in value.frames:
                validate_generated_story(frame.prose)

        value, usage = await self._generate_validated(
            stage=StoryStage.FRAMES,
            messages=frame_messages(request, theme),
            response_model=exact_frame_sequence_model(
                request.frames_per_theme
            ),
            max_output_tokens=16000,
            validate=validate_ids,
        )
        if not isinstance(value, NarrativeFrameSequence):
            raise AssertionError("validated frame response changed type")
        return NarrativeThemeResult(theme=theme, frames=value.frames), usage

    async def _generate_validated(
        self,
        *,
        stage: StoryStage,
        messages: list[ChatMessage],
        response_model: type[BaseModel],
        max_output_tokens: int,
        validate: Callable[[BaseModel], None],
    ) -> tuple[BaseModel, TokenUsage]:
        base_messages = messages
        usage = TokenUsage()
        for attempt in range(self._generation_retries + 1):
            rejected_value: BaseModel | None = None
            try:
                response = await self._model.generate(
                    stage=stage,
                    messages=messages,
                    response_model=response_model,
                    max_output_tokens=max_output_tokens,
                )
                usage += response.usage
                rejected_value = response.value
                validate(response.value)
            except StoryProviderResponseError as exc:
                usage += exc.usage
                error: Exception = exc
            except (StoryContractError, UnsafeStoryError) as exc:
                error = exc
            else:
                return response.value, usage

            if attempt >= self._generation_retries:
                raise error
            messages = list(base_messages)
            if rejected_value is not None:
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=rejected_value.model_dump_json(
                            ensure_ascii=False
                        ),
                    )
                )
            messages.append(
                ChatMessage(
                    role="user",
                    content=(
                        "上一份输出未满足基本结构或安全契约。"
                        f"问题：{error}。不要解释，只返回完整 schema 数据。"
                    ),
                )
            )
        raise AssertionError("unreachable")
