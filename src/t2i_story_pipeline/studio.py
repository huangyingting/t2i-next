"""Generate final narrative paragraphs behind one small interface."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from difflib import SequenceMatcher
from uuid import uuid4

from pydantic import BaseModel

from t2i_story_pipeline.errors import (
    StoryContractError,
    StoryProviderResponseError,
    UnsafeStoryError,
)
from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeFrame,
    NarrativeFrameSequence,
    NarrativeTheme,
    NarrativeThemeBatch,
    NarrativeThemeResult,
    QualityFeedback,
    StoryRequest,
    StoryResult,
    StoryStage,
    TokenUsage,
    exact_frame_sequence_model,
    exact_theme_batch_model,
)
from t2i_story_pipeline.prompts import (
    ACTION_CHAIN_MARKERS,
    EROTIC_VISIBLE_MARKERS,
    EROTIC_VISIBLE_MARKERS_EN,
    FRAME_TRANSITION_MARKERS,
    HARDCORE_VISIBLE_MARKERS,
    HARDCORE_VISIBLE_MARKERS_EN,
    PORTRAIT_ACTION_MARKERS,
    SHOT_ANGLES,
    SHOT_SCALES,
    SOURCE_SENSITIVE_MARKERS,
    STATIC_TRANSITION_MARKERS,
    anachronism_markers_for_story,
    frame_messages,
    theme_messages,
)
from t2i_story_pipeline.provider import ChatMessage, StoryModel
from t2i_story_pipeline.safety import (
    validate_generated_story,
    validate_source_story,
)

_CHINESE_SENTENCE_SPLIT = re.compile(r"(?<=[。！？])")
_ASCII_WORD = re.compile(r"[A-Za-z]+")
_PROGRESSIVE_ACTION = re.compile(
    r"^此刻，.{0,40}(?:正在|正)[\u4e00-\u9fff]"
)
_ACTION_SIMILARITY_LIMIT = 0.82


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
        themes, theme_usage, feedback = await self._generate_themes(request)
        semaphore = asyncio.Semaphore(self._concurrency)

        async def generate_theme(
            theme: NarrativeTheme,
        ) -> tuple[NarrativeThemeResult, TokenUsage, list[QualityFeedback]]:
            async with semaphore:
                return await self._generate_frames(request, theme)

        generated = await asyncio.gather(
            *(generate_theme(theme) for theme in themes)
        )
        usage = theme_usage
        results: list[NarrativeThemeResult] = []
        for result, frame_usage, frame_feedback in generated:
            results.append(result)
            usage += frame_usage
            feedback.extend(frame_feedback)
        return StoryResult(
            run_id=uuid4().hex[:12],
            request=request,
            themes=results,
            quality_feedback=feedback,
            usage=usage,
        )

    async def _generate_themes(
        self,
        request: StoryRequest,
    ) -> tuple[list[NarrativeTheme], TokenUsage, list[QualityFeedback]]:
        themes: list[NarrativeTheme] = []
        usage = TokenUsage()
        feedback: list[QualityFeedback] = []
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
            feedback.extend(self._theme_feedback(request, value.themes))
            usage += batch_usage
        return themes, usage, feedback

    async def _generate_frames(
        self,
        request: StoryRequest,
        theme: NarrativeTheme,
    ) -> tuple[NarrativeThemeResult, TokenUsage, list[QualityFeedback]]:
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
        issues = self._frame_issues(request, theme, value.frames)
        feedback = [
            QualityFeedback(
                stage=StoryStage.FRAMES,
                item_id=f"{theme.theme_id}/{frame_id}",
                issues=frame_issues,
            )
            for frame_id, frame_issues in issues.items()
        ]
        return NarrativeThemeResult(theme=theme, frames=value.frames), usage, feedback

    def _theme_feedback(
        self,
        request: StoryRequest,
        themes: list[NarrativeTheme],
    ) -> list[QualityFeedback]:
        allowed_ascii = set(_ASCII_WORD.findall(request.story))
        feedback: list[QualityFeedback] = []
        for theme in themes:
            issues: list[str] = []
            if request.output_language.value == "chinese":
                unexpected = sorted(
                    set(
                        _ASCII_WORD.findall(
                            f"{theme.title} {theme.premise} {theme.style}"
                        )
                    )
                    - allowed_ascii
                )
                if unexpected:
                    issues.append(
                        "含有 story 原文之外的英文词："
                        + ",".join(unexpected)
                    )
            source_issues = self._source_fidelity_issues(
                theme.model_dump_json(ensure_ascii=False),
                request.story,
            )
            if source_issues:
                issues.append(
                    "含有 story 未提供的来源敏感事实："
                    + ",".join(source_issues)
                )
            issues.extend(self._content_level_issues(request, theme.premise))
            issues.extend(
                self._era_consistency_issues(request, theme.premise)
            )
            if issues:
                feedback.append(
                    QualityFeedback(
                        stage=StoryStage.THEMES,
                        item_id=theme.theme_id,
                        issues=issues,
                    )
                )
        return feedback

    def _frame_issues(
        self,
        request: StoryRequest,
        theme: NarrativeTheme,
        frames: list[NarrativeFrame],
    ) -> dict[str, list[str]]:
        allowed_ascii = set(
            _ASCII_WORD.findall(
                f"{request.story} {theme.title} "
                f"{theme.premise} {theme.style}"
            )
        )
        issues: dict[str, list[str]] = {}
        for frame in frames:
            frame_issues: list[str] = []
            if not frame.prose.startswith(theme.style):
                frame_issues.append(f"必须以主题风格开头：{theme.style}")
            source_issues = self._source_fidelity_issues(
                frame.prose,
                request.story,
            )
            if source_issues:
                frame_issues.append(
                    "含有 story 未提供的来源敏感事实："
                    + ",".join(source_issues)
                )
            if request.output_language.value == "chinese":
                frame_issues.extend(
                    self._chinese_frame_shape_issues(
                        frame.prose,
                        allowed_ascii=allowed_ascii,
                    )
                )
            frame_issues.extend(
                self._content_level_issues(request, frame.prose)
            )
            frame_issues.extend(
                self._era_consistency_issues(request, frame.prose)
            )
            if frame_issues:
                issues[frame.frame_id] = frame_issues
        action_sentences: list[tuple[str, str]] = []
        for frame in frames:
            action = self._action_sentence(frame.prose)
            if action is not None:
                action_sentences.append((frame.frame_id, action))
        for index, (frame_id, action) in enumerate(action_sentences):
            for earlier_id, earlier_action in action_sentences[:index]:
                similarity = SequenceMatcher(
                    None,
                    earlier_action,
                    action,
                ).ratio()
                if similarity >= _ACTION_SIMILARITY_LIMIT:
                    issues.setdefault(frame_id, []).append(
                        f"动作句与 {earlier_id} 相似度 "
                        f"{similarity:.0%}，不得复写"
                    )
        return issues

    @staticmethod
    def _content_level_issues(
        request: StoryRequest,
        text: str,
    ) -> list[str]:
        if request.output_language.value == "chinese":
            erotic_markers = EROTIC_VISIBLE_MARKERS
            hardcore_markers = HARDCORE_VISIBLE_MARKERS
            compared_text = text
        else:
            erotic_markers = EROTIC_VISIBLE_MARKERS_EN
            hardcore_markers = HARDCORE_VISIBLE_MARKERS_EN
            compared_text = text.casefold()
        if request.content_level == ContentLevel.AESTHETIC:
            explicit = [
                marker for marker in hardcore_markers if marker in compared_text
            ]
            return (
                [
                    "aesthetic 不得呈现明确性行为："
                    + ",".join(explicit)
                ]
                if explicit
                else []
            )
        if request.content_level == ContentLevel.EROTIC:
            explicit = [
                marker for marker in hardcore_markers if marker in compared_text
            ]
            if explicit:
                return [
                    "erotic 不得升级为明确性行为："
                    + ",".join(explicit)
                ]
            if not any(marker in compared_text for marker in erotic_markers):
                return ["erotic 缺少直接可见的成人情色事实"]
            return []
        if not any(marker in compared_text for marker in hardcore_markers):
            return ["hardcore 缺少直接明确的成人性行为"]
        return []

    @staticmethod
    def _era_consistency_issues(
        request: StoryRequest,
        text: str,
    ) -> list[str]:
        compared_text = text.casefold()
        matches = sorted(
            (
                marker
                for marker in anachronism_markers_for_story(request)
                if marker.casefold() in compared_text
            ),
            key=len,
            reverse=True,
        )
        incompatible: list[str] = []
        for marker in matches:
            if not any(marker.casefold() in kept.casefold() for kept in incompatible):
                incompatible.append(marker)
        return (
            [
                "出现与 story 时代或季节背景不符的事物："
                + ",".join(incompatible)
            ]
            if incompatible
            else []
        )

    @staticmethod
    def _source_fidelity_issues(text: str, source: str) -> list[str]:
        return [
            marker
            for marker in SOURCE_SENSITIVE_MARKERS
            if marker in text and marker not in source
        ]

    @staticmethod
    def _action_sentence(prose: str) -> str | None:
        return next(
            (
                sentence.strip()
                for sentence in _CHINESE_SENTENCE_SPLIT.split(prose)
                if sentence.strip().startswith("此刻")
            ),
            None,
        )

    @staticmethod
    def _chinese_frame_shape_issues(
        prose: str,
        *,
        allowed_ascii: set[str],
    ) -> list[str]:
        issues: list[str] = []
        unexpected_ascii = sorted(
            set(_ASCII_WORD.findall(prose)) - allowed_ascii
        )
        if unexpected_ascii:
            issues.append(
                "不得混入原文之外的英文词："
                + ",".join(unexpected_ascii)
            )
        found_markers = [
            marker for marker in FRAME_TRANSITION_MARKERS if marker in prose
        ]
        if found_markers:
            issues.append(f"不得出现推进词：{','.join(found_markers)}")

        sentences = [
            sentence.strip()
            for sentence in _CHINESE_SENTENCE_SPLIT.split(prose)
            if sentence.strip()
        ]
        action_indexes = [
            index
            for index, sentence in enumerate(sentences)
            if sentence.startswith("此刻")
        ]
        if len(action_indexes) != 1:
            issues.append("必须恰好有一句以“此刻”开头的动作句")
        else:
            action = sentences[action_indexes[0]]
            if not action.startswith("此刻，"):
                issues.append("唯一动作句必须精确以“此刻，”开头")
            elif not _PROGRESSIVE_ACTION.search(action):
                issues.append("唯一动作句必须在施动者后使用“正”或“正在”")
            if action_indexes[0] != len(sentences) - 3:
                issues.append("动作句之后必须恰好只有镜头句和光线句")

        if len(sentences) < 3 or not sentences[-2].startswith("镜头采用"):
            issues.append("倒数第二句必须以“镜头采用”开头")
        else:
            camera = sentences[-2]
            if not any(scale in camera for scale in SHOT_SCALES):
                issues.append("镜头句缺少景别")
            if not any(angle in camera for angle in SHOT_ANGLES):
                issues.append("镜头句缺少拍摄角度")
        if len(sentences) < 2 or not sentences[-1].startswith("光线"):
            issues.append("最后一句必须以“光线”开头")

        if len(action_indexes) == 1:
            action = sentences[action_indexes[0]]
            action_markers = [
                marker
                for marker in ACTION_CHAIN_MARKERS
                if marker in action
            ]
            if "又" in action and "再" in action:
                action_markers.append("又...再")
            if action_markers:
                issues.append(
                    "唯一动作句不得串联动作："
                    + ",".join(action_markers)
                )
            static_section = sentences[action_indexes[0] - 1]
            static_markers = [
                marker
                for marker in STATIC_TRANSITION_MARKERS
                if marker in static_section
            ]
            if static_markers:
                issues.append(
                    "人物静态段不得出现姿态变化："
                    + ",".join(static_markers)
                )
            portrait_actions = [
                marker
                for marker in PORTRAIT_ACTION_MARKERS
                if marker in static_section
            ]
            if portrait_actions:
                issues.append(
                    "人物静态段不得执行次动作："
                    + ",".join(portrait_actions)
                )

        return issues

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
                        "上一份输出未满足基本契约。保留所有合格内容，"
                        "只修正列出的问题。"
                        f"问题：{error}。不要解释，只返回完整 schema 数据。"
                    ),
                )
            )
        raise AssertionError("unreachable")
