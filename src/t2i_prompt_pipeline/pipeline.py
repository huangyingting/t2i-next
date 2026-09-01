"""Batched generation with per-object checkpoints and resume."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from functools import partial
from time import perf_counter
from typing import NoReturn

from pydantic import ValidationError

from t2i_prompt_pipeline.contracts import (
    frame_ids,
    normalize_foundation,
    normalize_frame,
    normalize_theme,
    theme_ids,
)
from t2i_prompt_pipeline.errors import (
    GenerationContractError,
    PromptPipelineError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderTruncatedOutputError,
    RunIncompleteError,
    StructuredOutputError,
)
from t2i_prompt_pipeline.models import (
    ArchivedRun,
    AttemptOutcome,
    CastPlan,
    Foundation,
    Frame,
    FrameBatch,
    GenerationAttempt,
    GenerationResult,
    GenerationSpec,
    GenerationStage,
    PromptBook,
    ResolvedRuleSet,
    RunSettings,
    Theme,
    ThemeBatch,
    ThemeBook,
    ThemeSimilarityRejection,
    ThemeSimilarityReport,
    ThemeSimilarityState,
    TokenUsage,
    frame_batch_response_model,
    theme_batch_response_model,
)
from t2i_prompt_pipeline.providers.base import AuthorModel
from t2i_prompt_pipeline.renderers import render_book
from t2i_prompt_pipeline.store import RunSnapshot, RunStore
from t2i_prompt_pipeline.templates import (
    foundation_messages,
    frame_messages,
    theme_batch_messages,
)
from t2i_prompt_pipeline.theme_similarity import ThemeSimilarityAnalyzer

ProgressCallback = Callable[[str], None]
_SIMILARITY_REJECTION_PREFIX = "Theme embedding 相似度判定为重复"


class PromptStudio:
    """Drive a run to completion through one resumable interface."""

    def __init__(
        self,
        author: AuthorModel,
        store: RunStore,
        settings: RunSettings,
        *,
        theme_similarity: ThemeSimilarityAnalyzer | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._author = author
        self._store = store
        self._settings = settings
        self._theme_similarity = theme_similarity
        self._on_progress = on_progress

    async def run(
        self,
        spec: GenerationSpec,
        rules: ResolvedRuleSet,
    ) -> ArchivedRun:
        snapshot = self._store.create(spec, self._settings, rules)
        self._emit(f"Run 已创建：{snapshot.run_id}")
        return await self._drive(snapshot)

    async def resume(self, run_id: str) -> ArchivedRun:
        snapshot = self._store.inspect(run_id)
        if snapshot.completed is not None:
            self._emit(f"Run 已完成：{run_id}")
            return snapshot.completed
        snapshot.settings.ensure_resumable_with(self._settings)
        snapshot = self._store.start(run_id)
        self._emit(f"继续 Run：{run_id}")
        return await self._drive(snapshot)

    async def _drive(self, snapshot: RunSnapshot) -> ArchivedRun:
        try:
            return await self._continue(snapshot)
        except RunIncompleteError:
            raise
        except PromptPipelineError as exc:
            self._store.fail(snapshot.run_id, str(exc))
            raise

    async def _continue(self, snapshot: RunSnapshot) -> ArchivedRun:
        spec = snapshot.spec
        settings = snapshot.settings
        causes: list[str] = []

        foundation = snapshot.foundation
        rules = snapshot.rules
        if foundation is None:
            try:
                foundation = await self._generate_foundation(
                    snapshot.run_id,
                    spec,
                    settings,
                    rules,
                )
            except ProviderAuthenticationError:
                raise
            except ProviderError as exc:
                causes.append(str(exc))
                self._stop_incomplete(snapshot, causes)
            self._store.checkpoint(snapshot.run_id, foundation)
            self._emit("Foundation 已保存")

        expected_theme_ids = theme_ids(spec)
        while True:
            snapshot = self._store.inspect(snapshot.run_id)
            snapshot = self._restore_theme_similarity(snapshot)
            checkpoint_count = len(snapshot.themes) + len(snapshot.frames)
            missing_theme_ids = tuple(
                theme_id
                for theme_id in expected_theme_ids
                if theme_id not in snapshot.themes
            )
            if (
                missing_theme_ids
                and snapshot.theme_similarity_report is not None
                and snapshot.theme_similarity_report.state
                in {
                    ThemeSimilarityState.CLEAN,
                    ThemeSimilarityState.ERROR,
                }
            ):
                self._store.clear_theme_similarity(snapshot.run_id)
                snapshot = self._store.inspect(snapshot.run_id)
            attempt_history = self._store.attempts(snapshot.run_id)
            theme_tasks = [
                partial(
                    self._generate_themes,
                    snapshot.run_id,
                    spec,
                    settings,
                    foundation,
                    batch,
                    tuple(snapshot.themes.values()),
                    rules,
                    self._theme_retry_issues(
                        attempt_history,
                        snapshot.theme_similarity_report,
                        batch,
                    ),
                )
                for batch in self._chunks(
                    missing_theme_ids,
                    settings.theme_batch_size,
                )
            ]
            causes.extend(
                await self._run_independent(
                    theme_tasks,
                    settings.max_concurrency,
                )
            )

            snapshot = self._store.inspect(snapshot.run_id)
            if len(snapshot.themes) != len(expected_theme_ids):
                current_count = len(snapshot.themes) + len(snapshot.frames)
                if current_count == checkpoint_count:
                    self._stop_incomplete(snapshot, causes)
                continue
            report = snapshot.theme_similarity_report
            if (
                report is not None
                and report.state == ThemeSimilarityState.REGENERATING
            ):
                self._store.clear_theme_similarity(snapshot.run_id)
                snapshot = self._store.inspect(snapshot.run_id)
                report = None
            if report is None and self._theme_similarity is not None:
                report = await self._audit_theme_similarity(
                    snapshot,
                    foundation,
                    expected_theme_ids,
                )
                self._store.record_theme_similarity(snapshot.run_id, report)
                snapshot = self._restore_theme_similarity(
                    self._store.inspect(snapshot.run_id)
                )
                report = snapshot.theme_similarity_report
                if (
                    report is not None
                    and report.state == ThemeSimilarityState.REGENERATING
                ):
                    continue
            snapshot = self._store.inspect(snapshot.run_id)
            attempt_history = self._store.attempts(snapshot.run_id)
            frame_tasks: list[Callable[[], Awaitable[None]]] = []
            for theme_id in expected_theme_ids:
                theme = snapshot.themes.get(theme_id)
                if theme is None:
                    continue
                expected_frame_ids = frame_ids(spec, theme_id)
                missing_frame_ids = tuple(
                    frame_id
                    for frame_id in expected_frame_ids
                    if frame_id not in snapshot.frames
                )
                if missing_frame_ids:
                    existing_frames = tuple(
                        snapshot.frames[frame_id]
                        for frame_id in expected_frame_ids
                        if frame_id in snapshot.frames
                    )
                    frame_tasks.append(
                        partial(
                            self._generate_frames,
                            snapshot.run_id,
                            spec,
                            settings,
                            foundation.cast_plan,
                            theme,
                            missing_frame_ids,
                            existing_frames,
                            rules,
                            self._recent_attempt_issues(
                                attempt_history,
                                GenerationStage.FRAMES,
                                missing_frame_ids,
                            ),
                        )
                    )
            causes.extend(
                await self._run_independent(
                    frame_tasks,
                    settings.max_concurrency,
                )
            )

            snapshot = self._store.inspect(snapshot.run_id)
            missing_themes, missing_frames = self._missing_counts(snapshot)
            if not missing_themes and not missing_frames:
                break
            current_count = len(snapshot.themes) + len(snapshot.frames)
            if current_count == checkpoint_count:
                self._stop_incomplete(snapshot, causes)

        book = PromptBook(
            semantic_name=foundation.semantic_name,
            cast_plan=foundation.cast_plan,
            themes=[
                ThemeBook(
                    theme=snapshot.themes[theme_id],
                    frames=[
                        snapshot.frames[frame_id]
                        for frame_id in frame_ids(spec, theme_id)
                    ],
                )
                for theme_id in expected_theme_ids
            ],
        )
        result = GenerationResult(
            spec=spec,
            book=book,
            prompts=render_book(book, spec.output_language),
        )
        archived = self._store.complete(snapshot.run_id, result)
        self._emit("全部 checkpoint 已完成，提示词已发布")
        return archived

    async def _audit_theme_similarity(
        self,
        snapshot: RunSnapshot,
        foundation: Foundation,
        expected_theme_ids: tuple[str, ...],
    ) -> ThemeSimilarityReport:
        assert self._theme_similarity is not None
        started = perf_counter()
        audit_number = 1 + sum(
            attempt.stage == GenerationStage.THEME_SIMILARITY
            for attempt in self._store.attempts(snapshot.run_id)
        )
        try:
            report = await self._theme_similarity.analyze(
                tuple(snapshot.themes[theme_id] for theme_id in expected_theme_ids),
                foundation.style_constraints.required_phrases,
            )
        except ProviderError as exc:
            report = self._theme_similarity.failure_report(str(exc))
            self._emit(f"Theme 相似度审计失败，继续生成：{exc}")
        else:
            candidate_count = sum(
                pair.potential_duplicate for pair in report.pairs
            )
            self._emit(
                f"Theme 相似度审计已保存：{candidate_count} 对候选重复"
            )
        return report.model_copy(
            update={
                "audit_number": audit_number,
                "duration_ms": self._elapsed_ms(started),
            }
        )

    def _restore_theme_similarity(
        self,
        snapshot: RunSnapshot,
    ) -> RunSnapshot:
        report = snapshot.theme_similarity_report
        if report is None:
            return snapshot
        self._validate_theme_similarity_report(snapshot, report)
        if report.state == ThemeSimilarityState.ANALYZED:
            report = self._finalize_theme_similarity(snapshot, report)
            self._store.record_theme_similarity(snapshot.run_id, report)
            snapshot = self._store.inspect(snapshot.run_id)
        self._ensure_similarity_attempt(snapshot, report)
        if report.state == ThemeSimilarityState.EXHAUSTED:
            rejected_ids = [
                rejection.rejected_theme_id
                for rejection in report.rejections
            ]
            message = (
                "Theme embedding 相似度自动重生成已达上限 "
                f"{snapshot.settings.generation_retries} 次，仍有候选重复："
                f"{rejected_ids}"
            )
            self._emit(message)
            self._stop_incomplete(
                snapshot,
                [
                    *(
                        self._similarity_rejection_issue(rejection)
                        for rejection in report.rejections
                    ),
                    message,
                ],
            )
        if report.state == ThemeSimilarityState.REJECTION_PENDING:
            self._store.apply_theme_rejections(snapshot.run_id, report)
            rejected_ids = [
                rejection.rejected_theme_id
                for rejection in report.rejections
            ]
            self._emit(
                "Theme 相似度候选已拒绝并将自动重生成："
                f"{rejected_ids}"
            )
            return self._store.inspect(snapshot.run_id)
        return snapshot

    @staticmethod
    def _validate_theme_similarity_report(
        snapshot: RunSnapshot,
        report: ThemeSimilarityReport,
    ) -> None:
        expected_ids = set(theme_ids(snapshot.spec))
        referenced_ids = {
            theme_id
            for pair in report.pairs
            for theme_id in (pair.first_theme_id, pair.second_theme_id)
        } | {
            theme_id
            for rejection in report.rejections
            for theme_id in (
                rejection.rejected_theme_id,
                rejection.kept_theme_id,
            )
        }
        unknown_ids = sorted(referenced_ids - expected_ids)
        if unknown_ids:
            raise GenerationContractError(
                "Theme similarity report 引用未知 Theme ID："
                f"{unknown_ids}"
            )
        self_pairs = sorted(
            {
                pair.first_theme_id
                for pair in report.pairs
                if pair.first_theme_id == pair.second_theme_id
            }
            | {
                rejection.rejected_theme_id
                for rejection in report.rejections
                if rejection.rejected_theme_id == rejection.kept_theme_id
            }
        )
        if self_pairs:
            raise GenerationContractError(
                "Theme similarity report 包含自身配对："
                f"{self_pairs}"
            )
        rejected_ids = [
            rejection.rejected_theme_id
            for rejection in report.rejections
        ]
        duplicate_rejections = sorted(
            theme_id
            for theme_id in set(rejected_ids)
            if rejected_ids.count(theme_id) > 1
        )
        if duplicate_rejections:
            raise GenerationContractError(
                "Theme similarity report 重复拒绝 Theme ID："
                f"{duplicate_rejections}"
            )
        rejection_states = {
            ThemeSimilarityState.REJECTION_PENDING,
            ThemeSimilarityState.REGENERATING,
            ThemeSimilarityState.EXHAUSTED,
        }
        if report.state in rejection_states and (
            not report.rejections or report.regeneration_round is None
        ):
            raise GenerationContractError(
                "Theme similarity rejection 状态缺少拒绝项或轮次"
            )
        if report.state == ThemeSimilarityState.ERROR and report.error is None:
            raise GenerationContractError(
                "Theme similarity error 状态缺少错误信息"
            )

    def _finalize_theme_similarity(
        self,
        snapshot: RunSnapshot,
        report: ThemeSimilarityReport,
    ) -> ThemeSimilarityReport:
        if report.error is not None:
            return report.model_copy(
                update={"state": ThemeSimilarityState.ERROR}
            )
        candidates = tuple(
            pair for pair in report.pairs if pair.potential_duplicate
        )
        if not candidates:
            return report.model_copy(
                update={"state": ThemeSimilarityState.CLEAN}
            )
        known_theme_ids = set(snapshot.themes)
        unknown_theme_ids = sorted(
            {
                theme_id
                for pair in candidates
                for theme_id in (
                    pair.first_theme_id,
                    pair.second_theme_id,
                )
                if theme_id not in known_theme_ids
            }
        )
        if unknown_theme_ids:
            raise GenerationContractError(
                "Theme similarity report 引用未知 Theme ID："
                f"{unknown_theme_ids}"
            )
        self_pairs = sorted(
            {
                pair.first_theme_id
                for pair in candidates
                if pair.first_theme_id == pair.second_theme_id
            }
        )
        if self_pairs:
            raise GenerationContractError(
                "Theme similarity report 包含自身配对："
                f"{self_pairs}"
            )
        candidates_by_edge = {
            frozenset((pair.first_theme_id, pair.second_theme_id)): pair
            for pair in candidates
        }
        kept_ids: list[str] = []
        rejections: list[ThemeSimilarityRejection] = []
        for theme_id in sorted(snapshot.themes):
            matches = [
                (kept_id, pair)
                for kept_id in kept_ids
                if (
                    pair := candidates_by_edge.get(
                        frozenset((kept_id, theme_id))
                    )
                )
                is not None
            ]
            if not matches:
                kept_ids.append(theme_id)
                continue
            kept_id, pair = max(
                matches,
                key=lambda match: min(
                    match[1].scene_similarity,
                    match[1].style_similarity,
                ),
            )
            rejections.append(
                ThemeSimilarityRejection(
                    rejected_theme_id=theme_id,
                    kept_theme_id=kept_id,
                    scene_similarity=pair.scene_similarity,
                    style_similarity=pair.style_similarity,
                )
            )
        completed_regenerations = sum(
            attempt.stage == GenerationStage.THEME_SIMILARITY
            and attempt.outcome == AttemptOutcome.REJECTED
            for attempt in self._store.attempts(snapshot.run_id)
        )
        state = (
            ThemeSimilarityState.EXHAUSTED
            if completed_regenerations
            >= snapshot.settings.generation_retries
            else ThemeSimilarityState.REJECTION_PENDING
        )
        return report.model_copy(
            update={
                "state": state,
                "regeneration_round": completed_regenerations + 1,
                "rejections": rejections,
            }
        )

    def _ensure_similarity_attempt(
        self,
        snapshot: RunSnapshot,
        report: ThemeSimilarityReport,
    ) -> None:
        if any(
            attempt.operation_id == report.audit_id
            for attempt in self._store.attempts(snapshot.run_id)
        ):
            return
        if report.state == ThemeSimilarityState.ANALYZED:
            raise GenerationContractError(
                "Theme similarity report 尚未完成状态判定"
            )
        issues = tuple(
            self._similarity_rejection_issue(rejection)
            for rejection in report.rejections
        )
        if report.error is not None:
            issues = (*issues, report.error)
        outcome = (
            AttemptOutcome.PROVIDER_ERROR
            if report.state == ThemeSimilarityState.ERROR
            else AttemptOutcome.REJECTED
            if report.rejections
            else AttemptOutcome.ACCEPTED
        )
        self._record_attempt(
            snapshot.run_id,
            GenerationStage.THEME_SIMILARITY,
            tuple(sorted(snapshot.themes)),
            report.audit_number,
            None,
            outcome,
            accepted_ids=(
                tuple(sorted(snapshot.themes))
                if outcome == AttemptOutcome.ACCEPTED
                else ()
            ),
            issues=issues,
            duration_ms=report.duration_ms,
            usage=report.usage,
            operation_id=report.audit_id,
        )

    @staticmethod
    def _similarity_rejection_issue(
        rejection: ThemeSimilarityRejection,
    ) -> str:
        return (
            f"{_SIMILARITY_REJECTION_PREFIX}："
            f"{rejection.rejected_theme_id} 与 {rejection.kept_theme_id}"
            f"（scene={rejection.scene_similarity:.6f}，"
            f"style={rejection.style_similarity:.6f}）；"
            "请为被拒 ID 生成全新的场所、核心装置与摄影方案"
        )

    async def _generate_foundation(
        self,
        run_id: str,
        spec: GenerationSpec,
        settings: RunSettings,
        rules: ResolvedRuleSet,
    ) -> Foundation:
        budget = self._foundation_budget(settings)
        issues: list[str] = []
        for attempt in range(settings.generation_retries + 1):
            started = perf_counter()
            try:
                response = await self._author.generate(
                    stage=GenerationStage.FOUNDATION,
                    messages=foundation_messages(
                        spec,
                        rules,
                        tuple(issues[-3:]),
                    ),
                    response_model=Foundation,
                    max_output_tokens=budget,
                )
            except ProviderTruncatedOutputError as exc:
                issues.append(str(exc))
                self._record_attempt(
                    run_id,
                    GenerationStage.FOUNDATION,
                    (),
                    attempt + 1,
                    budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                    usage=exc.usage,
                )
                budget = settings.output_token_limit
                if attempt == settings.generation_retries:
                    raise
            except StructuredOutputError as exc:
                issues.append(str(exc))
                self._record_attempt(
                    run_id,
                    GenerationStage.FOUNDATION,
                    (),
                    attempt + 1,
                    budget,
                    AttemptOutcome.REJECTED,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                    usage=exc.usage,
                )
                if attempt == settings.generation_retries:
                    raise
            except ProviderAuthenticationError as exc:
                self._record_attempt(
                    run_id,
                    GenerationStage.FOUNDATION,
                    (),
                    attempt + 1,
                    budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                )
                raise
            except ProviderError as exc:
                self._record_attempt(
                    run_id,
                    GenerationStage.FOUNDATION,
                    (),
                    attempt + 1,
                    budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                )
                if attempt == settings.generation_retries:
                    raise
            else:
                try:
                    foundation = normalize_foundation(spec, response.value)
                except GenerationContractError as exc:
                    issues.append(str(exc))
                    self._record_attempt(
                        run_id,
                        GenerationStage.FOUNDATION,
                        (),
                        attempt + 1,
                        budget,
                        AttemptOutcome.REJECTED,
                        issues=(str(exc),),
                        duration_ms=self._elapsed_ms(started),
                        usage=response.usage,
                    )
                    if (
                        attempt == settings.generation_retries
                        or not str(exc).startswith("风格约束")
                    ):
                        raise
                    continue
                self._record_attempt(
                    run_id,
                    GenerationStage.FOUNDATION,
                    (),
                    attempt + 1,
                    budget,
                    AttemptOutcome.ACCEPTED,
                    accepted_ids=("foundation",),
                    duration_ms=self._elapsed_ms(started),
                    usage=response.usage,
                )
                return foundation
        raise AssertionError("Foundation retry loop ended without a result")

    async def _generate_themes(
        self,
        run_id: str,
        spec: GenerationSpec,
        settings: RunSettings,
        foundation: Foundation,
        requested_ids: tuple[str, ...],
        existing_themes: tuple[Theme, ...],
        rules: ResolvedRuleSet,
        initial_issues: tuple[str, ...],
    ) -> None:
        remaining = list(requested_ids)
        completed: dict[str, Theme] = {}
        budget = self._theme_budget(
            settings,
            len(remaining),
            foundation.cast_plan.member_count,
        )
        issues: list[str] = []
        for attempt in range(settings.generation_retries + 1):
            attempt_ids = tuple(remaining)
            attempt_budget = budget
            attempt_issues: list[str] = []
            started = perf_counter()
            try:
                response = await self._author.generate(
                    stage=GenerationStage.THEMES,
                    messages=theme_batch_messages(
                        spec,
                        foundation,
                        tuple(remaining),
                        rules,
                        validation_issues=(
                            *initial_issues,
                            *issues[-3:],
                        ),
                        existing_themes=(
                            *existing_themes,
                            *completed.values(),
                        ),
                    ),
                    response_model=theme_batch_response_model(
                        tuple(remaining),
                        foundation.cast_plan.member_count,
                    ),
                    max_output_tokens=budget,
                )
            except ProviderTruncatedOutputError as exc:
                attempt_issues.append(str(exc))
                issues.extend(attempt_issues)
                self._record_attempt(
                    run_id,
                    GenerationStage.THEMES,
                    attempt_ids,
                    attempt + 1,
                    attempt_budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=tuple(attempt_issues),
                    duration_ms=self._elapsed_ms(started),
                    usage=exc.usage,
                )
                budget = settings.output_token_limit
                if attempt == settings.generation_retries:
                    break
                continue
            except StructuredOutputError as exc:
                attempt_issues.append(str(exc))
                batch, salvage_issues = self._salvage_theme_batch(
                    exc.raw_content
                )
                attempt_issues.extend(salvage_issues)
                if batch is None:
                    issues.extend(attempt_issues)
                    self._record_attempt(
                        run_id,
                        GenerationStage.THEMES,
                        attempt_ids,
                        attempt + 1,
                        attempt_budget,
                        AttemptOutcome.REJECTED,
                        issues=tuple(attempt_issues),
                        duration_ms=self._elapsed_ms(started),
                        usage=exc.usage,
                    )
                    if attempt == settings.generation_retries:
                        break
                    continue
                usage = exc.usage
            except ProviderAuthenticationError as exc:
                self._record_attempt(
                    run_id,
                    GenerationStage.THEMES,
                    attempt_ids,
                    attempt + 1,
                    attempt_budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                )
                raise
            except ProviderError as exc:
                self._record_attempt(
                    run_id,
                    GenerationStage.THEMES,
                    attempt_ids,
                    attempt + 1,
                    attempt_budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                )
                raise
            else:
                batch = response.value
                usage = response.usage

            accepted, rejected = self._accept_themes(
                spec,
                foundation,
                batch,
                tuple(remaining),
                (*existing_themes, *completed.values()),
            )
            returned_ids = {theme.theme_id for theme in batch.themes}
            omitted_ids = [
                theme_id
                for theme_id in attempt_ids
                if theme_id not in returned_ids
            ]
            if omitted_ids:
                attempt_issues.append(
                    f"Theme 响应缺少请求 ID：{omitted_ids}"
                )
            attempt_issues.extend(rejected)
            issues.extend(attempt_issues)
            for theme in accepted:
                self._store.checkpoint(run_id, theme)
                completed[theme.theme_id] = theme
                self._emit(f"Theme 已保存：{theme.theme_id}")
            accepted_ids = tuple(theme.theme_id for theme in accepted)
            outcome = (
                AttemptOutcome.ACCEPTED
                if len(accepted_ids) == len(attempt_ids)
                else AttemptOutcome.PARTIAL
                if accepted_ids
                else AttemptOutcome.REJECTED
            )
            self._record_attempt(
                run_id,
                GenerationStage.THEMES,
                attempt_ids,
                attempt + 1,
                attempt_budget,
                outcome,
                accepted_ids=accepted_ids,
                issues=tuple(attempt_issues),
                duration_ms=self._elapsed_ms(started),
                usage=usage,
            )
            accepted_id_set = set(accepted_ids)
            remaining = [
                theme_id
                for theme_id in remaining
                if theme_id not in accepted_id_set
            ]
            if not remaining:
                return
            budget = self._theme_budget(
                settings,
                len(remaining),
                foundation.cast_plan.member_count,
            )
        raise GenerationContractError(
            f"Theme 补全失败，仍缺少 {remaining}；"
            f"{'; '.join(issues[-3:])}"
        )

    async def _generate_frames(
        self,
        run_id: str,
        spec: GenerationSpec,
        settings: RunSettings,
        cast_plan: CastPlan,
        theme: Theme,
        requested_ids: tuple[str, ...],
        existing_frames: tuple[Frame, ...],
        rules: ResolvedRuleSet,
        initial_issues: tuple[str, ...],
    ) -> None:
        remaining = list(requested_ids)
        completed = {frame.frame_id: frame for frame in existing_frames}
        character_ids = tuple(
            character.character_id for character in theme.characters
        )
        budget = self._frame_budget(
            settings,
            len(remaining),
            len(character_ids),
        )
        issues = list(initial_issues)
        for attempt in range(settings.generation_retries + 1):
            attempt_ids = tuple(remaining)
            attempt_budget = budget
            attempt_issues: list[str] = []
            started = perf_counter()
            try:
                response = await self._author.generate(
                    stage=GenerationStage.FRAMES,
                    messages=frame_messages(
                        spec,
                        cast_plan,
                        theme,
                        tuple(remaining),
                        rules,
                        tuple(completed.values()),
                        tuple(issues[-3:]),
                    ),
                    response_model=frame_batch_response_model(
                        theme.theme_id,
                        tuple(remaining),
                        character_ids,
                    ),
                    max_output_tokens=budget,
                )
            except ProviderTruncatedOutputError as exc:
                attempt_issues.append(str(exc))
                issues.extend(attempt_issues)
                self._record_attempt(
                    run_id,
                    GenerationStage.FRAMES,
                    attempt_ids,
                    attempt + 1,
                    attempt_budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=tuple(attempt_issues),
                    duration_ms=self._elapsed_ms(started),
                    usage=exc.usage,
                )
                budget = settings.output_token_limit
                if attempt == settings.generation_retries:
                    break
                continue
            except StructuredOutputError as exc:
                attempt_issues.append(str(exc))
                batch, salvage_issues = self._salvage_frame_batch(
                    exc.raw_content
                )
                attempt_issues.extend(salvage_issues)
                if batch is None:
                    issues.extend(attempt_issues)
                    self._record_attempt(
                        run_id,
                        GenerationStage.FRAMES,
                        attempt_ids,
                        attempt + 1,
                        attempt_budget,
                        AttemptOutcome.REJECTED,
                        issues=tuple(attempt_issues),
                        duration_ms=self._elapsed_ms(started),
                        usage=exc.usage,
                    )
                    if attempt == settings.generation_retries:
                        break
                    continue
                usage = exc.usage
            except ProviderAuthenticationError as exc:
                self._record_attempt(
                    run_id,
                    GenerationStage.FRAMES,
                    attempt_ids,
                    attempt + 1,
                    attempt_budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                )
                raise
            except ProviderError as exc:
                self._record_attempt(
                    run_id,
                    GenerationStage.FRAMES,
                    attempt_ids,
                    attempt + 1,
                    attempt_budget,
                    AttemptOutcome.PROVIDER_ERROR,
                    issues=(str(exc),),
                    duration_ms=self._elapsed_ms(started),
                )
                raise
            else:
                batch = response.value
                usage = response.usage

            accepted, rejected = self._accept_frames(
                spec,
                theme,
                batch,
                tuple(remaining),
                tuple(completed.values()),
            )
            returned_ids = {frame.frame_id for frame in batch.frames}
            omitted_ids = [
                frame_id
                for frame_id in attempt_ids
                if frame_id not in returned_ids
            ]
            if omitted_ids:
                attempt_issues.append(
                    f"{theme.theme_id} Frame 响应缺少请求 ID：{omitted_ids}"
                )
            attempt_issues.extend(rejected)
            issues.extend(attempt_issues)
            for frame in accepted:
                self._store.checkpoint(run_id, frame)
                completed[frame.frame_id] = frame
                self._emit(f"Frame 已保存：{frame.frame_id}")
            accepted_ids = tuple(frame.frame_id for frame in accepted)
            outcome = (
                AttemptOutcome.ACCEPTED
                if len(accepted_ids) == len(attempt_ids)
                else AttemptOutcome.PARTIAL
                if accepted_ids
                else AttemptOutcome.REJECTED
            )
            self._record_attempt(
                run_id,
                GenerationStage.FRAMES,
                attempt_ids,
                attempt + 1,
                attempt_budget,
                outcome,
                accepted_ids=accepted_ids,
                issues=tuple(attempt_issues),
                duration_ms=self._elapsed_ms(started),
                usage=usage,
            )
            accepted_id_set = set(accepted_ids)
            remaining = [
                frame_id
                for frame_id in remaining
                if frame_id not in accepted_id_set
            ]
            if not remaining:
                return
            budget = self._frame_budget(
                settings,
                len(remaining),
                len(character_ids),
            )
        raise GenerationContractError(
            f"{theme.theme_id} Frame 补全失败，仍缺少 {remaining}；"
            f"{'; '.join(issues[-3:])}"
        )

    async def _run_independent(
        self,
        operations: Sequence[Callable[[], Awaitable[None]]],
        max_concurrency: int,
    ) -> list[str]:
        if not operations:
            return []
        semaphore = asyncio.Semaphore(max_concurrency)

        async def limited(
            operation: Callable[[], Awaitable[None]],
        ) -> None:
            async with semaphore:
                await operation()

        pending = {
            asyncio.create_task(limited(operation))
            for operation in operations
        }
        errors: list[str] = []
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                fatal: BaseException | None = None
                for task in done:
                    exception = task.exception()
                    if exception is None:
                        continue
                    if isinstance(
                        exception,
                        (GenerationContractError, ProviderError),
                    ) and not isinstance(
                        exception,
                        ProviderAuthenticationError,
                    ):
                        errors.append(str(exception))
                        continue
                    fatal = exception
                    break
                if fatal is None:
                    continue
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                raise fatal
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        return errors

    def _accept_themes(
        self,
        spec: GenerationSpec,
        foundation: Foundation,
        batch: ThemeBatch,
        requested_ids: tuple[str, ...],
        existing_themes: tuple[Theme, ...] = (),
    ) -> tuple[list[Theme], list[str]]:
        accepted: list[Theme] = []
        issues: list[str] = []
        seen: set[str] = set()
        scene_owners = {
            " ".join(theme.scene.split()).casefold(): theme.theme_id
            for theme in existing_themes
        }
        title_owners = {
            " ".join(theme.title.split()).casefold(): theme.theme_id
            for theme in existing_themes
        }
        for theme in batch.themes:
            if theme.theme_id in seen:
                issues.append(f"Theme ID 重复：{theme.theme_id}")
                continue
            try:
                normalized = normalize_theme(
                    spec,
                    foundation.style_constraints,
                    foundation.cast_plan,
                    theme,
                    requested_ids,
                )
            except GenerationContractError as exc:
                issues.append(str(exc))
                continue
            scene_key = " ".join(normalized.scene.split()).casefold()
            scene_owner = scene_owners.get(scene_key)
            if scene_owner is not None:
                issues.append(
                    f"{normalized.theme_id} Theme.scene 与已接受 Theme 重复："
                    f"{scene_owner}"
                )
                continue
            title_key = " ".join(normalized.title.split()).casefold()
            title_owner = title_owners.get(title_key)
            if title_owner is not None:
                issues.append(
                    f"{normalized.theme_id} Theme.title 与已接受 Theme 重复："
                    f"{title_owner}"
                )
                continue
            seen.add(theme.theme_id)
            scene_owners[scene_key] = normalized.theme_id
            title_owners[title_key] = normalized.theme_id
            accepted.append(normalized)
        accepted.sort(key=lambda theme: requested_ids.index(theme.theme_id))
        return accepted, issues

    @staticmethod
    def _salvage_theme_batch(
        raw_content: str,
    ) -> tuple[ThemeBatch | None, list[str]]:
        data, issues = PromptStudio._parse_batch_object(raw_content, "Theme")
        if data is None:
            return None, issues
        raw_themes = data.get("themes")
        if not isinstance(raw_themes, list):
            return None, [*issues, "ThemeBatch.themes 不是数组"]
        themes: list[Theme] = []
        for index, raw_theme in enumerate(raw_themes):
            try:
                themes.append(Theme.model_validate(raw_theme))
            except ValidationError as exc:
                issues.append(
                    PromptStudio._validation_issue("Theme", index, exc)
                )
        if not themes:
            return None, issues
        try:
            return ThemeBatch(themes=themes), issues
        except ValidationError as exc:
            issues.append(
                PromptStudio._validation_issue("ThemeBatch", 0, exc)
            )
            return None, issues

    @staticmethod
    def _salvage_frame_batch(
        raw_content: str,
    ) -> tuple[FrameBatch | None, list[str]]:
        data, issues = PromptStudio._parse_batch_object(raw_content, "Frame")
        if data is None:
            return None, issues
        raw_frames = data.get("frames")
        if not isinstance(raw_frames, list):
            return None, [*issues, "FrameBatch.frames 不是数组"]
        frames: list[Frame] = []
        for index, raw_frame in enumerate(raw_frames):
            try:
                frames.append(Frame.model_validate(raw_frame))
            except ValidationError as exc:
                issues.append(
                    PromptStudio._validation_issue("Frame", index, exc)
                )
        if not frames:
            return None, issues
        try:
            return (
                FrameBatch(
                    theme_id=data.get("theme_id"),
                    frames=frames,
                ),
                issues,
            )
        except ValidationError as exc:
            issues.append(
                PromptStudio._validation_issue("FrameBatch", 0, exc)
            )
            return None, issues

    @staticmethod
    def _parse_batch_object(
        raw_content: str,
        kind: str,
    ) -> tuple[dict[str, object] | None, list[str]]:
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            return None, [f"{kind} batch JSON 无法解析：{exc.msg}"]
        if not isinstance(data, dict):
            return None, [f"{kind} batch 顶层不是对象"]
        return data, []

    @staticmethod
    def _validation_issue(
        kind: str,
        index: int,
        error: ValidationError,
    ) -> str:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "<root>"
        return (
            f"{kind}[{index}] 无效：{location}: "
            f"{first['msg']}"
        )

    def _accept_frames(
        self,
        spec: GenerationSpec,
        theme: Theme,
        batch: FrameBatch,
        requested_ids: tuple[str, ...],
        existing_frames: tuple[Frame, ...] = (),
    ) -> tuple[list[Frame], list[str]]:
        if batch.theme_id != theme.theme_id:
            return [], [f"FrameBatch 属于错误 Theme：{batch.theme_id}"]
        accepted: list[Frame] = []
        issues: list[str] = []
        seen: set[str] = set()
        content_owners = {
            self._frame_content_key(frame): frame.frame_id
            for frame in existing_frames
        }
        for frame in batch.frames:
            if frame.frame_id in seen:
                issues.append(f"Frame ID 重复：{frame.frame_id}")
                continue
            try:
                normalized = normalize_frame(
                    spec,
                    theme,
                    frame,
                    requested_ids,
                )
            except GenerationContractError as exc:
                issues.append(str(exc))
                continue
            content_key = self._frame_content_key(normalized)
            content_owner = content_owners.get(content_key)
            if content_owner is not None:
                issues.append(
                    f"{normalized.frame_id} Frame 内容与已接受 Frame 重复："
                    f"{content_owner}"
                )
                continue
            seen.add(frame.frame_id)
            content_owners[content_key] = normalized.frame_id
            accepted.append(normalized)
        accepted.sort(key=lambda frame: requested_ids.index(frame.frame_id))
        return accepted, issues

    @staticmethod
    def _frame_content_key(frame: Frame) -> str:
        return json.dumps(
            frame.model_dump(mode="json", exclude={"frame_id"}),
            ensure_ascii=False,
            sort_keys=True,
        )

    def _stop_incomplete(
        self,
        snapshot: RunSnapshot,
        causes: list[str],
    ) -> NoReturn:
        refreshed = self._store.inspect(snapshot.run_id)
        missing_themes, missing_frames = self._missing_counts(refreshed)
        message = "; ".join(causes[-5:]) or "生成结果不完整"
        self._store.fail(snapshot.run_id, message)
        raise RunIncompleteError(
            snapshot.run_id,
            missing_themes=missing_themes,
            missing_frames=missing_frames,
            causes=tuple(causes),
        )

    @staticmethod
    def _chunks(
        values: tuple[str, ...],
        size: int,
    ) -> list[tuple[str, ...]]:
        return [
            values[index : index + size]
            for index in range(0, len(values), size)
        ]

    def _missing_counts(self, snapshot: RunSnapshot) -> tuple[int, int]:
        expected_theme_ids = theme_ids(snapshot.spec)
        missing_themes = sum(
            theme_id not in snapshot.themes
            for theme_id in expected_theme_ids
        )
        missing_frames = 0
        for theme_id in expected_theme_ids:
            missing_frames += sum(
                frame_id not in snapshot.frames
                for frame_id in frame_ids(snapshot.spec, theme_id)
            )
        return missing_themes, missing_frames

    def _record_attempt(
        self,
        run_id: str,
        stage: GenerationStage,
        requested_ids: tuple[str, ...],
        attempt: int,
        max_output_tokens: int | None,
        outcome: AttemptOutcome,
        *,
        accepted_ids: tuple[str, ...] = (),
        issues: tuple[str, ...] = (),
        duration_ms: int,
        usage: TokenUsage | None = None,
        operation_id: str | None = None,
    ) -> None:
        self._store.record_attempt(
            run_id,
            GenerationAttempt(
                operation_id=operation_id,
                occurred_at=datetime.now(UTC).isoformat(),
                stage=stage,
                requested_ids=list(requested_ids),
                attempt=attempt,
                max_output_tokens=max_output_tokens,
                outcome=outcome,
                accepted_ids=list(accepted_ids),
                issues=list(issues),
                duration_ms=duration_ms,
                usage=usage or TokenUsage(),
            ),
        )

    def _theme_retry_issues(
        self,
        attempts: tuple[GenerationAttempt, ...],
        report: ThemeSimilarityReport | None,
        requested_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        issues = list(
            self._recent_attempt_issues(
                attempts,
                GenerationStage.THEMES,
                requested_ids,
            )
        )
        if (
            report is not None
            and report.state == ThemeSimilarityState.REGENERATING
        ):
            requested = set(requested_ids)
            issues.extend(
                self._similarity_rejection_issue(rejection)
                for rejection in report.rejections
                if rejection.rejected_theme_id in requested
            )
        return tuple(issues)

    @staticmethod
    def _recent_attempt_issues(
        attempts: tuple[GenerationAttempt, ...],
        stage: GenerationStage,
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
    def _foundation_budget(settings: RunSettings) -> int:
        return min(settings.output_token_limit, 1536)

    @staticmethod
    def _theme_budget(
        settings: RunSettings,
        theme_count: int,
        character_count: int,
    ) -> int:
        estimate = theme_count * (500 + 250 * character_count)
        return min(
            settings.output_token_limit,
            max(1024, math.ceil(estimate * 1.3)),
        )

    @staticmethod
    def _frame_budget(
        settings: RunSettings,
        frame_count: int,
        character_count: int,
    ) -> int:
        estimate = frame_count * (300 + 180 * character_count)
        return min(
            settings.output_token_limit,
            max(1024, math.ceil(estimate * 1.3)),
        )

    def _emit(self, message: str) -> None:
        if self._on_progress is not None:
            self._on_progress(message)
