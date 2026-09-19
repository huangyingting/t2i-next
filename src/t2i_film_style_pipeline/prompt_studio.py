"""Generate final narrative paragraphs behind one small interface."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from time import perf_counter

from pydantic import BaseModel, ValidationError

from t2i_film_style_pipeline.cast_validation import (
    validate_cast_prose,
    validate_selected_cast,
)
from t2i_film_style_pipeline.diversity import (
    normalize_frame_anchor_prefix,
    normalize_theme_anchor_terms,
)
from t2i_film_style_pipeline.errors import (
    FilmPromptRunIncompleteError,
    FilmStyleContractError,
    FilmStylePipelineError,
    FilmStyleProviderError,
    FilmStyleProviderResponseError,
    FilmStyleProviderTruncatedOutputError,
    FilmStyleStorageError,
    FilmStyleStructuredOutputError,
)
from t2i_film_style_pipeline.prompt_messages import frame_messages, theme_messages
from t2i_film_style_pipeline.prompt_models import (
    FilmPromptRequest,
    FilmPromptResult,
    FilmPromptRuleSet,
    FilmPromptStage,
    NarrativeFrame,
    NarrativeFrameSequence,
    NarrativeTheme,
    NarrativeThemeBatch,
    NarrativeThemeDraftBatch,
    NarrativeThemeResult,
    TokenUsage,
    exact_theme_batch_model,
    exact_theme_draft_batch_model,
)
from t2i_film_style_pipeline.prompt_provider import (
    ChatMessage,
    FilmPromptModel,
    ModelResponse,
)
from t2i_film_style_pipeline.prompt_run_store import (
    CompletedFilmPromptRun,
    FilmPromptAttempt,
    FilmPromptAttemptOutcome,
    FilmPromptRunSettings,
    FilmPromptRunSnapshot,
    LocalFilmPromptRunStore,
    ThemeOutputMode,
)

ProgressCallback = Callable[[str], None]
ThemeValidator = Callable[[FilmPromptRequest, NarrativeTheme], None]
FrameValidator = Callable[[FilmPromptRequest, NarrativeTheme, NarrativeFrame], None]
GenerateResponse = Callable[
    [list[ChatMessage], int],
    Awaitable[ModelResponse],
]

class FilmPromptStudio:
    """Turn one film context directly into final prose image prompts."""

    def __init__(
        self,
        model: FilmPromptModel,
        store: LocalFilmPromptRunStore,
        settings: FilmPromptRunSettings,
        rules: FilmPromptRuleSet,
        *,
        on_progress: ProgressCallback | None = None,
        theme_validator: ThemeValidator | None = None,
        frame_validator: FrameValidator | None = None,
    ) -> None:
        self._model = model
        self._store = store
        self._settings = settings
        self._rules = rules
        self._on_progress = on_progress
        self._theme_validator = theme_validator
        self._frame_validator = frame_validator

    async def run(self, request: FilmPromptRequest) -> CompletedFilmPromptRun:
        snapshot = self._store.create(request, self._settings, self._rules)
        self._emit(f"Run 已创建：{snapshot.run_id}")
        return await self._drive(snapshot, restarting=False)

    async def resume(self, run_id: str) -> CompletedFilmPromptRun:
        snapshot = self._store.inspect(run_id)
        if snapshot.completed is not None:
            self._emit(f"Run 已完成：{run_id}")
            return snapshot.completed
        if snapshot.manifest.settings != self._settings:
            raise FilmStyleStorageError(
                "当前生成配置与 film prompt run manifest 不一致"
            )
        if snapshot.rules != self._rules:
            raise FilmStyleStorageError(
                "当前 film prompt rules 与 run 冻结规则不一致"
            )
        self._emit(f"继续 Run：{run_id}")
        return await self._drive(snapshot, restarting=True)

    async def _drive(
        self,
        snapshot: FilmPromptRunSnapshot,
        *,
        restarting: bool,
    ) -> CompletedFilmPromptRun:
        with self._store.lock(snapshot.run_id):
            if restarting:
                snapshot = self._store.start(snapshot.run_id)
            try:
                return await self._continue(snapshot)
            except FilmPromptRunIncompleteError:
                raise
            except FilmStyleStorageError:
                raise
            except FilmStylePipelineError as exc:
                self._store.fail(snapshot.run_id, str(exc))
                current = self._store.inspect(snapshot.run_id)
                raise self._incomplete(current, (str(exc),)) from exc

    async def _continue(
        self,
        snapshot: FilmPromptRunSnapshot,
    ) -> CompletedFilmPromptRun:
        request = snapshot.request
        rules = snapshot.rules
        themes = list(snapshot.themes)
        existing_frames = dict(snapshot.frames)
        semaphore = asyncio.Semaphore(self._settings.concurrency)
        queue: asyncio.Queue[NarrativeTheme | None] = asyncio.Queue(
            maxsize=self._settings.concurrency
        )
        causes: list[str] = []

        def needs_frames(theme: NarrativeTheme) -> bool:
            sequence = existing_frames.get(theme.theme_id)
            return (
                sequence is None
                or len(sequence.frames) != request.frames_per_theme
            )

        async def generate_theme_frames(theme: NarrativeTheme) -> None:
            try:
                async with semaphore:
                    current = self._store.inspect(snapshot.run_id)
                    await self._generate_frames(
                        snapshot.run_id,
                        request,
                        theme,
                        rules,
                        current.frames.get(theme.theme_id),
                    )
                self._emit(f"{theme.theme_id} Frame Sequence 已保存")
            except Exception as exc:
                causes.append(str(exc))

        async def frame_worker() -> None:
            while True:
                theme = await queue.get()
                try:
                    if theme is None:
                        return
                    await generate_theme_frames(theme)
                finally:
                    queue.task_done()

        workers = [
            asyncio.create_task(frame_worker())
            for _ in range(self._settings.concurrency)
        ]
        for theme in themes:
            if needs_frames(theme):
                await queue.put(theme)

        async def enqueue_theme(theme: NarrativeTheme) -> None:
            if needs_frames(theme):
                await queue.put(theme)

        try:
            await self._generate_themes(
                snapshot.run_id,
                request,
                rules,
                themes,
                snapshot.manifest.semantic_name,
                semaphore=semaphore,
                on_theme=enqueue_theme,
            )
        except Exception as exc:
            causes.append(str(exc))
        finally:
            for _ in workers:
                await queue.put(None)

        await queue.join()
        worker_outcomes = await asyncio.gather(
            *workers,
            return_exceptions=True,
        )
        causes.extend(
            str(outcome)
            for outcome in worker_outcomes
            if isinstance(outcome, Exception)
        )
        snapshot = self._store.inspect(snapshot.run_id)
        if snapshot.manifest.semantic_name is None:
            causes.append("Film prompt run 缺少 semantic_name")
        if (
            len(snapshot.themes) != request.theme_count
            or len(snapshot.frames) != request.theme_count
            or any(
                len(sequence.frames) != request.frames_per_theme
                for sequence in snapshot.frames.values()
            )
        ):
            self._store.fail(
                snapshot.run_id,
                "; ".join(causes)
                or "Theme 或 Frame Sequence 尚未完整",
            )
            raise self._incomplete(snapshot, tuple(causes))
        if snapshot.manifest.semantic_name is None:
            raise FilmStyleStorageError("Film prompt run 缺少 semantic_name")
        result = FilmPromptResult(
            run_id=snapshot.run_id,
            semantic_name=snapshot.manifest.semantic_name,
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
        self._emit("全部 checkpoint 已完成，电影提示词已发布")
        return completed

    async def _generate_themes(
        self,
        run_id: str,
        request: FilmPromptRequest,
        rules: FilmPromptRuleSet,
        themes: list[NarrativeTheme],
        semantic_name: str | None,
        *,
        semaphore: asyncio.Semaphore,
        on_theme: Callable[[NarrativeTheme], Awaitable[None]],
    ) -> list[NarrativeTheme]:
        while len(themes) < request.theme_count:
            start_index = len(themes) + 1
            count = min(
                self._settings.theme_batch_size,
                request.theme_count - len(themes),
            )
            messages = theme_messages(
                request,
                rules,
                start_index=start_index,
                count=count,
                existing_themes=themes,
                semantic_name=semantic_name,
                program_assigns_ids=(
                    self._settings.theme_output_mode
                    == ThemeOutputMode.STRUCTURED_WITHOUT_IDS
                ),
            )
            generated_themes: list[NarrativeTheme] = []
            generated_themes_target = generated_themes

            def validate(
                value: BaseModel,
                expected_start: int = start_index,
                expected_count: int = count,
                expected_semantic_name: str | None = semantic_name,
                target: list[NarrativeTheme] = generated_themes_target,
            ) -> None:
                expected = [
                    f"T{index:03d}"
                    for index in range(
                        expected_start,
                        expected_start + expected_count,
                    )
                ]
                if not isinstance(
                    value,
                    (NarrativeThemeBatch, NarrativeThemeDraftBatch),
                ):
                    raise FilmStyleContractError("provider 返回了错误的主题类型")
                if len(value.themes) != len(expected):
                    raise FilmStyleContractError(
                        "主题数量不符合请求："
                        f"expected={len(expected)}, actual={len(value.themes)}"
                    )
                if isinstance(value, NarrativeThemeDraftBatch):
                    candidate_themes = [
                        NarrativeTheme(
                            theme_id=theme_id,
                            title=draft.title,
                            premise=draft.premise,
                            style=draft.style,
                            source_work_index=draft.source_work_index,
                            selected_cast=draft.selected_cast,
                        )
                        for draft, theme_id in zip(
                            value.themes,
                            expected,
                            strict=True,
                        )
                    ]
                else:
                    candidate_themes = value.themes
                    for theme, theme_id in zip(
                        candidate_themes,
                        expected,
                        strict=True,
                    ):
                        theme.theme_id = theme_id
                for theme in candidate_themes:
                    validate_selected_cast(request, theme)
                    validate_cast_prose(request, theme, theme.premise)
                candidate_themes = [
                    normalize_theme_anchor_terms(request, theme)
                    for theme in candidate_themes
                ]
                if (
                    expected_semantic_name is not None
                    and value.semantic_name != expected_semantic_name
                ):
                    raise FilmStyleContractError(
                        "semantic_name 与 run 不一致："
                        f"expected={expected_semantic_name}, "
                        f"actual={value.semantic_name}"
                    )
                for theme in candidate_themes:
                    if self._theme_validator is not None:
                        self._theme_validator(request, theme)
                target[:] = candidate_themes

            operation_id = f"themes-T{start_index:03d}-T{start_index + count - 1:03d}"
            requested_ids = tuple(
                f"T{index:03d}" for index in range(start_index, start_index + count)
            )
            async with semaphore:
                value, _ = await self._generate_validated(
                    run_id=run_id,
                    operation_id=operation_id,
                    requested_ids=requested_ids,
                    stage=FilmPromptStage.THEMES,
                    messages=messages,
                    response_model=(
                        exact_theme_draft_batch_model(count)
                        if self._settings.theme_output_mode
                        == ThemeOutputMode.STRUCTURED_WITHOUT_IDS
                        else exact_theme_batch_model(count)
                    ),
                    max_output_tokens=self._settings.theme_output_tokens,
                    validate=validate,
                )
            if not isinstance(
                value,
                (NarrativeThemeBatch, NarrativeThemeDraftBatch),
            ):
                raise AssertionError("validated theme response changed type")
            self._store.checkpoint_themes(
                run_id,
                generated_themes,
                value.semantic_name,
            )
            semantic_name = value.semantic_name
            themes.extend(generated_themes)
            for theme in generated_themes:
                await on_theme(theme)
            self._emit(
                f"{generated_themes[0].theme_id}–"
                f"{generated_themes[-1].theme_id} Theme 已保存"
            )
        return themes

    async def _generate_frames(
        self,
        run_id: str,
        request: FilmPromptRequest,
        theme: NarrativeTheme,
        rules: FilmPromptRuleSet,
        existing_sequence: NarrativeFrameSequence | None,
    ) -> NarrativeFrameSequence:
        expected_ids = [
            f"F{index:02d}" for index in range(1, request.frames_per_theme + 1)
        ]
        accepted = {
            frame.frame_id: frame
            for frame in (
                existing_sequence.frames if existing_sequence is not None else []
            )
        }
        remaining_ids = list(expected_ids)
        remaining_ids = [
            frame_id for frame_id in remaining_ids if frame_id not in accepted
        ]
        operation_id = f"frames-{theme.theme_id}"
        prior_attempts = tuple(self._store.attempts(run_id))
        attempt_offset = sum(
            attempt.operation_id == operation_id for attempt in prior_attempts
        )
        budget = (
            self._settings.provider.output_token_limit
            if any(
                attempt.stage == FilmPromptStage.FRAMES
                and attempt.outcome == FilmPromptAttemptOutcome.TRUNCATED
                and any(
                    requested_id.startswith(f"{theme.theme_id}-")
                    for requested_id in attempt.requested_ids
                )
                for attempt in prior_attempts
            )
            else min(
                self._settings.frame_output_tokens,
                self._settings.provider.output_token_limit,
            )
        )
        feedback_issues = list(
            self._recent_attempt_issues(
                prior_attempts,
                FilmPromptStage.FRAMES,
                tuple(f"{theme.theme_id}-{item}" for item in remaining_ids),
            )
        )
        for attempt in range(self._settings.generation_retries + 1):
            requested_ids = tuple(
                f"{theme.theme_id}-{frame_id}" for frame_id in remaining_ids
            )
            base_messages = frame_messages(
                request,
                theme,
                rules,
                requested_frame_ids=remaining_ids,
                accepted_frames=[
                    accepted[frame_id]
                    for frame_id in expected_ids
                    if frame_id in accepted
                ],
            )
            messages = (
                self._retry_messages(
                    base_messages,
                    tuple(feedback_issues[-3:]),
                    expects_plain_text=True,
                )
                if feedback_issues
                else base_messages
            )
            started = perf_counter()
            attempt_usage = TokenUsage()
            accepted_this_attempt: tuple[str, ...] = ()
            try:
                response = await self._model.generate_text(
                    stage=FilmPromptStage.FRAMES,
                    messages=messages,
                    max_output_tokens=budget,
                )
                attempt_usage = response.usage
                frame_prose = self._split_frame_batch(
                    response.text,
                    len(remaining_ids),
                )
                rejected_ids: list[str] = []
                validation_issues: list[str] = []
                accepted_ids: list[str] = []
                for frame_id, prose in zip(
                    remaining_ids,
                    frame_prose,
                    strict=True,
                ):
                    try:
                        validate_cast_prose(request, theme, prose)
                        prose = normalize_frame_anchor_prefix(
                            request,
                            theme,
                            prose,
                        )
                        frame = NarrativeFrame(frame_id=frame_id, prose=prose)
                        if self._frame_validator is not None:
                            self._frame_validator(request, theme, frame)
                    except (FilmStyleContractError, ValidationError) as exc:
                        rejected_ids.append(frame_id)
                        frame_issues = (
                            "; ".join(
                                f"{'.'.join(str(part) for part in issue['loc'])}: "
                                f"{issue['msg']}"
                                for issue in exc.errors()
                            )
                            if isinstance(exc, ValidationError)
                            else str(exc)
                        )
                        validation_issues.append(
                            f"{theme.theme_id}-{frame_id}: {frame_issues}"
                        )
                    else:
                        accepted[frame_id] = frame
                        self._store.checkpoint_frame(
                            run_id,
                            theme.theme_id,
                            frame,
                        )
                        accepted_ids.append(f"{theme.theme_id}-{frame_id}")
                accepted_this_attempt = tuple(accepted_ids)
                if rejected_ids:
                    raise FilmStyleContractError("; ".join(validation_issues))
            except FilmStyleProviderTruncatedOutputError as exc:
                attempt_usage = exc.usage
                error: Exception = exc
                outcome = FilmPromptAttemptOutcome.TRUNCATED
                issues = (str(exc), *exc.validation_issues)
                budget = self._settings.provider.output_token_limit
            except FilmStyleStructuredOutputError as exc:
                attempt_usage = exc.usage
                error = exc
                outcome = FilmPromptAttemptOutcome.REJECTED
                issues = (str(exc), *exc.validation_issues)
            except FilmStyleProviderResponseError as exc:
                attempt_usage = exc.usage
                error = exc
                outcome = FilmPromptAttemptOutcome.PROVIDER_ERROR
                issues = (str(exc),)
            except (FilmStyleContractError, ValidationError) as exc:
                error = exc
                outcome = FilmPromptAttemptOutcome.REJECTED
                issues = (
                    tuple(
                        f"{'.'.join(str(part) for part in issue['loc'])}: "
                        f"{issue['msg']}"
                        for issue in exc.errors()
                    )
                    if isinstance(exc, ValidationError)
                    else (str(exc),)
                )
                if accepted_this_attempt:
                    remaining_ids = [
                        frame_id
                        for frame_id in remaining_ids
                        if f"{theme.theme_id}-{frame_id}"
                        not in accepted_this_attempt
                    ]
            except FilmStyleProviderError as exc:
                self._record_attempt(
                    run_id=run_id,
                    operation_id=operation_id,
                    requested_ids=requested_ids,
                    stage=FilmPromptStage.FRAMES,
                    attempt=attempt_offset + attempt + 1,
                    max_output_tokens=budget,
                    outcome=FilmPromptAttemptOutcome.PROVIDER_ERROR,
                    accepted_ids=accepted_this_attempt,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                    usage=attempt_usage,
                    error=str(exc),
                )
                raise
            else:
                self._record_attempt(
                    run_id=run_id,
                    operation_id=operation_id,
                    requested_ids=requested_ids,
                    stage=FilmPromptStage.FRAMES,
                    attempt=attempt_offset + attempt + 1,
                    max_output_tokens=budget,
                    outcome=FilmPromptAttemptOutcome.ACCEPTED,
                    accepted_ids=requested_ids,
                    issues=(),
                    duration_ms=self._elapsed_ms(started),
                    usage=attempt_usage,
                    error=None,
                )
                return NarrativeFrameSequence(
                    frames=[accepted[frame_id] for frame_id in expected_ids]
                )

            self._record_attempt(
                run_id=run_id,
                operation_id=operation_id,
                requested_ids=requested_ids,
                stage=FilmPromptStage.FRAMES,
                attempt=attempt_offset + attempt + 1,
                max_output_tokens=budget,
                outcome=outcome,
                accepted_ids=accepted_this_attempt,
                issues=issues,
                duration_ms=self._elapsed_ms(started),
                usage=attempt_usage,
                error=str(error),
            )
            feedback_issues.extend(issues)
            if attempt >= self._settings.generation_retries:
                raise error
        raise AssertionError("unreachable")

    @staticmethod
    def _split_frame_batch(
        text: str,
        expected_count: int,
    ) -> list[str]:
        pattern = re.compile(r"<FRAME>\s*(.*?)\s*</FRAME>", re.DOTALL)
        matches = list(pattern.finditer(text))
        cursor = 0
        for match in matches:
            if text[cursor : match.start()].strip():
                raise FilmStyleContractError("Frame 批次包含标签之外的正文")
            cursor = match.end()
        if text[cursor:].strip():
            raise FilmStyleContractError("Frame 批次包含标签之外的正文")
        if len(matches) != expected_count:
            raise FilmStyleContractError(
                "Frame 批次数量不符合请求："
                f"expected={expected_count}, actual={len(matches)}"
            )
        return [match.group(1) for match in matches]

    async def _generate_validated(
        self,
        *,
        run_id: str,
        operation_id: str,
        requested_ids: tuple[str, ...],
        stage: FilmPromptStage,
        messages: list[ChatMessage],
        response_model: type[BaseModel],
        max_output_tokens: int,
        validate: Callable[[BaseModel], None],
        generate_response: GenerateResponse | None = None,
    ) -> tuple[BaseModel, TokenUsage]:
        base_messages = messages
        usage = TokenUsage()
        prior_attempts = tuple(attempt for attempt in self._store.attempts(run_id))
        feedback_issues = list(
            self._recent_attempt_issues(
                prior_attempts,
                stage,
                requested_ids,
            )
        )
        expects_plain_text = generate_response is not None
        if feedback_issues:
            messages = self._retry_messages(
                base_messages,
                tuple(feedback_issues[-3:]),
                expects_plain_text=expects_plain_text,
            )
        attempt_offset = sum(
            attempt.operation_id == operation_id for attempt in prior_attempts
        )
        relevant_attempts = tuple(
            attempt
            for attempt in prior_attempts
            if (
                attempt.stage == stage
                and set(requested_ids).intersection(attempt.requested_ids)
            )
        )
        budget = (
            self._settings.provider.output_token_limit
            if any(
                attempt.outcome == FilmPromptAttemptOutcome.TRUNCATED
                for attempt in relevant_attempts
            )
            else min(
                max_output_tokens,
                self._settings.provider.output_token_limit,
            )
        )
        for attempt in range(self._settings.generation_retries + 1):
            rejected_value: BaseModel | None = None
            attempt_usage = TokenUsage()
            attempt_issues: tuple[str, ...]
            started = perf_counter()
            try:
                response = (
                    await generate_response(messages, budget)
                    if generate_response is not None
                    else await self._model.generate(
                        stage=stage,
                        messages=messages,
                        response_model=response_model,
                        max_output_tokens=budget,
                    )
                )
                attempt_usage = response.usage
                usage += attempt_usage
                rejected_value = response.value
                validate(response.value)
            except FilmStyleProviderTruncatedOutputError as exc:
                attempt_usage = exc.usage
                usage += attempt_usage
                error: Exception = exc
                outcome = FilmPromptAttemptOutcome.TRUNCATED
                attempt_issues = (
                    str(exc),
                    *exc.validation_issues,
                )
            except FilmStyleStructuredOutputError as exc:
                attempt_usage = exc.usage
                usage += attempt_usage
                error = exc
                outcome = FilmPromptAttemptOutcome.REJECTED
                attempt_issues = (
                    str(exc),
                    *exc.validation_issues,
                )
            except FilmStyleProviderResponseError as exc:
                attempt_usage = exc.usage
                usage += attempt_usage
                error = exc
                outcome = FilmPromptAttemptOutcome.PROVIDER_ERROR
                attempt_issues = (str(exc),)
            except (FilmStyleContractError, ValidationError) as exc:
                error = exc
                outcome = FilmPromptAttemptOutcome.REJECTED
                attempt_issues = (str(exc),)
            except FilmStyleProviderError as exc:
                self._record_attempt(
                    run_id=run_id,
                    operation_id=operation_id,
                    requested_ids=requested_ids,
                    stage=stage,
                    attempt=attempt_offset + attempt + 1,
                    max_output_tokens=budget,
                    outcome=FilmPromptAttemptOutcome.PROVIDER_ERROR,
                    accepted_ids=(),
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                    usage=attempt_usage,
                    error=str(exc),
                )
                raise
            else:
                self._record_attempt(
                    run_id=run_id,
                    operation_id=operation_id,
                    requested_ids=requested_ids,
                    stage=stage,
                    attempt=attempt_offset + attempt + 1,
                    max_output_tokens=budget,
                    outcome=FilmPromptAttemptOutcome.ACCEPTED,
                    accepted_ids=requested_ids,
                    issues=(),
                    duration_ms=self._elapsed_ms(started),
                    usage=attempt_usage,
                    error=None,
                )
                return response.value, usage

            self._record_attempt(
                run_id=run_id,
                operation_id=operation_id,
                requested_ids=requested_ids,
                stage=stage,
                attempt=attempt_offset + attempt + 1,
                max_output_tokens=budget,
                outcome=outcome,
                accepted_ids=(),
                issues=attempt_issues,
                duration_ms=self._elapsed_ms(started),
                usage=attempt_usage,
                error=str(error),
            )
            feedback_issues.extend(attempt_issues)
            if attempt >= self._settings.generation_retries:
                raise error
            if isinstance(error, FilmStyleProviderTruncatedOutputError):
                budget = self._settings.provider.output_token_limit
            messages = self._retry_messages(
                base_messages,
                tuple(feedback_issues[-3:]),
                rejected_value,
                expects_plain_text=expects_plain_text,
            )
        raise AssertionError("unreachable")

    def _record_attempt(
        self,
        *,
        run_id: str,
        operation_id: str,
        requested_ids: tuple[str, ...],
        stage: FilmPromptStage,
        attempt: int,
        max_output_tokens: int,
        outcome: FilmPromptAttemptOutcome,
        accepted_ids: tuple[str, ...],
        issues: tuple[str, ...],
        duration_ms: int,
        usage: TokenUsage,
        error: str | None,
    ) -> None:
        self._store.record_attempt(
            run_id,
            FilmPromptAttempt(
                occurred_at=self._store.now(),
                stage=stage,
                operation_id=operation_id,
                requested_ids=list(requested_ids),
                attempt=attempt,
                max_output_tokens=max_output_tokens,
                outcome=outcome,
                accepted_ids=list(accepted_ids),
                issues=list(issues),
                duration_ms=duration_ms,
                error=error,
                usage=usage,
            ),
        )

    @staticmethod
    def _retry_messages(
        base_messages: list[ChatMessage],
        issues: tuple[str, ...],
        rejected_value: BaseModel | None = None,
        *,
        expects_plain_text: bool = False,
    ) -> list[ChatMessage]:
        messages = list(base_messages)
        if rejected_value is not None and not expects_plain_text:
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=rejected_value.model_dump_json(ensure_ascii=False),
                )
            )
        return_instruction = (
            "不要解释，只返回请求数量的完整 Frame；每个 Frame 严格写成"
            "<FRAME>单段纯自然语言画面正文</FRAME>，不要返回 JSON、ID、"
            "Markdown 或标签之外的说明。"
            if expects_plain_text
            else "不要解释，只返回完整 schema 数据。"
        )
        messages.append(
            ChatMessage(
                role="user",
                content=(
                    "上一份输出未满足发布契约。"
                    f"问题：{'; '.join(issues)}。"
                    f"{return_instruction}"
                ),
            )
        )
        return messages

    @staticmethod
    def _recent_attempt_issues(
        attempts: tuple[FilmPromptAttempt, ...],
        stage: FilmPromptStage,
        requested_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        requested = set(requested_ids)
        for attempt in reversed(attempts):
            if (
                attempt.stage == stage
                and requested.intersection(attempt.requested_ids)
                and attempt.issues
            ):
                return tuple(attempt.issues[-3:])
        return ()

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))

    @staticmethod
    def _incomplete(
        snapshot: FilmPromptRunSnapshot,
        causes: tuple[str, ...],
    ) -> FilmPromptRunIncompleteError:
        return FilmPromptRunIncompleteError(
            snapshot.run_id,
            missing_themes=(snapshot.request.theme_count - len(snapshot.themes)),
            missing_frames=(
                snapshot.request.theme_count
                - sum(
                    len(sequence.frames) == snapshot.request.frames_per_theme
                    for sequence in snapshot.frames.values()
                )
            ),
            causes=causes,
        )

    def _emit(self, message: str) -> None:
        if self._on_progress is not None:
            self._on_progress(message)
