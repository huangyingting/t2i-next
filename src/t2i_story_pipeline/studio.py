"""Generate final narrative paragraphs behind one small interface."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from pydantic import BaseModel

from t2i_story_pipeline.errors import (
    StoryContractError,
    StoryPipelineError,
    StoryProviderError,
    StoryProviderResponseError,
    StoryRunIncompleteError,
    StoryStorageError,
)
from t2i_story_pipeline.models import (
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
from t2i_story_pipeline.run_store import (
    CompletedStoryRun,
    LocalStoryRunStore,
    StoryAttempt,
    StoryAttemptOutcome,
    StoryRunSettings,
    StoryRunSnapshot,
)

ProgressCallback = Callable[[str], None]


class StoryStudio:
    """Turn one story request directly into final prose image prompts."""

    def __init__(
        self,
        model: StoryModel,
        store: LocalStoryRunStore,
        settings: StoryRunSettings,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._model = model
        self._store = store
        self._settings = settings
        self._on_progress = on_progress

    async def run(self, request: StoryRequest) -> CompletedStoryRun:
        snapshot = self._store.create(request, self._settings)
        self._emit(f"Run 已创建：{snapshot.run_id}")
        return await self._drive(snapshot, restarting=False)

    async def resume(self, run_id: str) -> CompletedStoryRun:
        snapshot = self._store.inspect(run_id)
        if snapshot.completed is not None:
            self._emit(f"Run 已完成：{run_id}")
            return snapshot.completed
        if snapshot.manifest.settings != self._settings:
            raise StoryStorageError("当前生成配置与 story run manifest 不一致")
        self._emit(f"继续 Run：{run_id}")
        return await self._drive(snapshot, restarting=True)

    async def _drive(
        self,
        snapshot: StoryRunSnapshot,
        *,
        restarting: bool,
    ) -> CompletedStoryRun:
        with self._store.lock(snapshot.run_id):
            if restarting:
                snapshot = self._store.start(snapshot.run_id)
            try:
                return await self._continue(snapshot)
            except StoryRunIncompleteError:
                raise
            except StoryStorageError:
                raise
            except StoryPipelineError as exc:
                self._store.fail(snapshot.run_id, str(exc))
                current = self._store.inspect(snapshot.run_id)
                raise self._incomplete(current, (str(exc),)) from exc

    async def _continue(
        self,
        snapshot: StoryRunSnapshot,
    ) -> CompletedStoryRun:
        request = snapshot.request
        themes = await self._generate_themes(
            snapshot.run_id,
            request,
            list(snapshot.themes),
        )
        snapshot = self._store.inspect(snapshot.run_id)
        semaphore = asyncio.Semaphore(self._settings.concurrency)

        async def generate_theme(
            theme: NarrativeTheme,
        ) -> None:
            async with semaphore:
                sequence = await self._generate_frames(
                    snapshot.run_id,
                    request,
                    theme,
                )
                self._store.checkpoint_frames(
                    snapshot.run_id,
                    theme.theme_id,
                    sequence,
                )
                self._emit(f"{theme.theme_id} Frame Sequence 已保存")

        outcomes = await asyncio.gather(
            *(
                generate_theme(theme)
                for theme in themes
                if theme.theme_id not in snapshot.frames
            ),
            return_exceptions=True,
        )
        causes = tuple(
            str(outcome)
            for outcome in outcomes
            if isinstance(outcome, Exception)
        )
        snapshot = self._store.inspect(snapshot.run_id)
        if len(snapshot.frames) != request.theme_count:
            self._store.fail(
                snapshot.run_id,
                "; ".join(causes) or "Frame Sequence 尚未完整",
            )
            raise self._incomplete(snapshot, causes)
        result = StoryResult(
            run_id=snapshot.run_id,
            request=request,
            themes=[
                NarrativeThemeResult(
                    theme=theme,
                    frames=snapshot.frames[theme.theme_id].frames,
                )
                for theme in themes
            ],
            usage=self._store.total_usage(snapshot.run_id),
        )
        completed = self._store.complete(snapshot.run_id, result)
        self._emit("全部 checkpoint 已完成，故事提示词已发布")
        return completed

    async def _generate_themes(
        self,
        run_id: str,
        request: StoryRequest,
        themes: list[NarrativeTheme],
    ) -> list[NarrativeTheme]:
        while len(themes) < request.theme_count:
            start_index = len(themes) + 1
            count = min(
                self._settings.theme_batch_size,
                request.theme_count - len(themes),
            )
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
                expected = [
                    f"T{index:03d}"
                    for index in range(
                        expected_start,
                        expected_start + expected_count,
                    )
                ]
                if len(value.themes) != len(expected):
                    raise StoryContractError(
                        "主题数量不符合请求："
                        f"expected={len(expected)}, actual={len(value.themes)}"
                    )
                for theme, theme_id in zip(
                    value.themes,
                    expected,
                    strict=True,
                ):
                    theme.theme_id = theme_id

            operation_id = (
                f"themes-T{start_index:03d}-"
                f"T{start_index + count - 1:03d}"
            )
            value, _ = await self._generate_validated(
                run_id=run_id,
                operation_id=operation_id,
                stage=StoryStage.THEMES,
                messages=messages,
                response_model=exact_theme_batch_model(count),
                max_output_tokens=self._settings.theme_output_tokens,
                validate=validate,
            )
            if not isinstance(value, NarrativeThemeBatch):
                raise AssertionError("validated theme response changed type")
            self._store.checkpoint_themes(run_id, value.themes)
            themes.extend(value.themes)
            self._emit(
                f"{value.themes[0].theme_id}–{value.themes[-1].theme_id} "
                "Theme 已保存"
            )
        return themes

    async def _generate_frames(
        self,
        run_id: str,
        request: StoryRequest,
        theme: NarrativeTheme,
    ) -> NarrativeFrameSequence:
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
            if len(value.frames) != len(expected_ids):
                raise StoryContractError(
                    "画面数量不符合请求："
                    f"expected={len(expected_ids)}, "
                    f"actual={len(value.frames)}"
                )
            for frame, frame_id in zip(
                value.frames,
                expected_ids,
                strict=True,
            ):
                frame.frame_id = frame_id

        value, _ = await self._generate_validated(
            run_id=run_id,
            operation_id=f"frames-{theme.theme_id}",
            stage=StoryStage.FRAMES,
            messages=frame_messages(request, theme),
            response_model=exact_frame_sequence_model(
                request.frames_per_theme
            ),
            max_output_tokens=self._settings.frame_output_tokens,
            validate=validate_ids,
        )
        if not isinstance(value, NarrativeFrameSequence):
            raise AssertionError("validated frame response changed type")
        return value

    async def _generate_validated(
        self,
        *,
        run_id: str,
        operation_id: str,
        stage: StoryStage,
        messages: list[ChatMessage],
        response_model: type[BaseModel],
        max_output_tokens: int,
        validate: Callable[[BaseModel], None],
    ) -> tuple[BaseModel, TokenUsage]:
        base_messages = messages
        usage = TokenUsage()
        prior_attempts = tuple(
            attempt
            for attempt in self._store.attempts(run_id)
            if attempt.operation_id == operation_id
        )
        if prior_attempts and prior_attempts[-1].error:
            messages = self._retry_messages(
                base_messages,
                prior_attempts[-1].error,
            )
        attempt_offset = len(prior_attempts)
        for attempt in range(self._settings.generation_retries + 1):
            rejected_value: BaseModel | None = None
            attempt_usage = TokenUsage()
            try:
                response = await self._model.generate(
                    stage=stage,
                    messages=messages,
                    response_model=response_model,
                    max_output_tokens=max_output_tokens,
                )
                attempt_usage = response.usage
                usage += attempt_usage
                rejected_value = response.value
                validate(response.value)
            except StoryProviderResponseError as exc:
                attempt_usage = exc.usage
                usage += attempt_usage
                error: Exception = exc
                outcome = StoryAttemptOutcome.PROVIDER_ERROR
            except StoryContractError as exc:
                error = exc
                outcome = StoryAttemptOutcome.REJECTED
            except StoryProviderError as exc:
                self._record_attempt(
                    run_id=run_id,
                    operation_id=operation_id,
                    stage=stage,
                    attempt=attempt_offset + attempt + 1,
                    max_output_tokens=max_output_tokens,
                    outcome=StoryAttemptOutcome.PROVIDER_ERROR,
                    usage=attempt_usage,
                    error=str(exc),
                )
                raise
            else:
                self._record_attempt(
                    run_id=run_id,
                    operation_id=operation_id,
                    stage=stage,
                    attempt=attempt_offset + attempt + 1,
                    max_output_tokens=max_output_tokens,
                    outcome=StoryAttemptOutcome.ACCEPTED,
                    usage=attempt_usage,
                    error=None,
                )
                return response.value, usage

            self._record_attempt(
                run_id=run_id,
                operation_id=operation_id,
                stage=stage,
                attempt=attempt_offset + attempt + 1,
                max_output_tokens=max_output_tokens,
                outcome=outcome,
                usage=attempt_usage,
                error=str(error),
            )
            if attempt >= self._settings.generation_retries:
                raise error
            messages = self._retry_messages(
                base_messages,
                str(error),
                rejected_value,
            )
        raise AssertionError("unreachable")

    def _record_attempt(
        self,
        *,
        run_id: str,
        operation_id: str,
        stage: StoryStage,
        attempt: int,
        max_output_tokens: int,
        outcome: StoryAttemptOutcome,
        usage: TokenUsage,
        error: str | None,
    ) -> None:
        self._store.record_attempt(
            run_id,
            StoryAttempt(
                occurred_at=self._store.now(),
                stage=stage,
                operation_id=operation_id,
                attempt=attempt,
                max_output_tokens=max_output_tokens,
                outcome=outcome,
                error=error,
                usage=usage,
            ),
        )

    @staticmethod
    def _retry_messages(
        base_messages: list[ChatMessage],
        error: str,
        rejected_value: BaseModel | None = None,
    ) -> list[ChatMessage]:
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
                    "上一份输出未满足基本结构契约。"
                    f"问题：{error}。不要解释，只返回完整 schema 数据。"
                ),
            )
        )
        return messages

    @staticmethod
    def _incomplete(
        snapshot: StoryRunSnapshot,
        causes: tuple[str, ...],
    ) -> StoryRunIncompleteError:
        return StoryRunIncompleteError(
            snapshot.run_id,
            missing_themes=(
                snapshot.request.theme_count - len(snapshot.themes)
            ),
            missing_frames=(
                snapshot.request.theme_count - len(snapshot.frames)
            ),
            causes=causes,
        )

    def _emit(self, message: str) -> None:
        if self._on_progress is not None:
            self._on_progress(message)
