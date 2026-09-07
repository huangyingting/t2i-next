"""Story interpretation, creative theming, generation, and quality review."""

from __future__ import annotations

import json
import re
from uuid import uuid4

from t2i_story_pipeline.errors import (
    StoryContractError,
    StoryProviderResponseError,
)
from t2i_story_pipeline.models import (
    NarrativeReview,
    NarrativeSequence,
    NarrativeTheme,
    NarrativeThemeBatch,
    NarrativeThemeResult,
    OutputLanguage,
    RenderedNarrative,
    StoryBlueprint,
    StoryRequest,
    StoryResult,
    StoryStage,
    TokenUsage,
    exact_narrative_review_model,
    exact_narrative_sequence_model,
    exact_theme_batch_model,
)
from t2i_story_pipeline.prompts import (
    interpretation_messages,
    narrative_messages,
    review_messages,
    revision_messages,
    theme_messages,
)
from t2i_story_pipeline.provider import ChatMessage, StoryModel
from t2i_story_pipeline.render import render_narratives
from t2i_story_pipeline.safety import (
    validate_generated_story,
    validate_source_story,
)


class StoryStudio:
    """Generate a complete storyboard through one prose-first interface."""

    def __init__(
        self,
        model: StoryModel,
        *,
        max_revisions: int = 2,
        generation_retries: int = 2,
    ) -> None:
        if not 0 <= max_revisions <= 5:
            raise ValueError("max_revisions 必须介于 0 和 5")
        if not 0 <= generation_retries <= 5:
            raise ValueError("generation_retries 必须介于 0 和 5")
        self._model = model
        self._max_revisions = max_revisions
        self._generation_retries = generation_retries

    async def generate(self, request: StoryRequest) -> StoryResult:
        validate_source_story(request.story)
        blueprint, blueprint_usage = await self._interpret(request)
        themes, theme_usage = await self._generate_themes(
            request,
            blueprint,
        )
        usage = blueprint_usage + theme_usage
        theme_results: list[NarrativeThemeResult] = []
        for theme in themes:
            theme_result, theme_result_usage = await self._generate_theme(
                request,
                blueprint,
                theme,
            )
            theme_results.append(theme_result)
            usage += theme_result_usage
        self._validate_portfolio(theme_results)
        return StoryResult(
            run_id=uuid4().hex[:12],
            request=request,
            blueprint=blueprint,
            themes=theme_results,
            usage=usage,
        )

    async def _interpret(
        self,
        request: StoryRequest,
    ) -> tuple[StoryBlueprint, TokenUsage]:
        messages = interpretation_messages(request)
        usage = TokenUsage()
        for attempt in range(self._generation_retries + 1):
            try:
                response = await self._model.generate(
                    stage=StoryStage.INTERPRET,
                    messages=messages,
                    response_model=StoryBlueprint,
                    max_output_tokens=6000,
                )
            except StoryProviderResponseError as exc:
                usage += exc.usage
                if attempt >= self._generation_retries:
                    raise
                messages = self._contract_retry_messages(
                    interpretation_messages(request),
                    exc,
                )
                continue
            usage += response.usage
            blueprint = response.value
            if not isinstance(blueprint, StoryBlueprint):
                raise StoryContractError(
                    "故事模型在 interpret 阶段返回了错误类型"
                )
            try:
                self._normalize_display_names(request, blueprint)
                self._validate_blueprint_fidelity(request, blueprint)
                self._validate_output_language(
                    request,
                    blueprint,
                    stage="故事结构",
                )
                validate_generated_story(
                    blueprint.model_dump_json(ensure_ascii=False)
                )
            except StoryContractError as exc:
                if attempt >= self._generation_retries:
                    raise
                messages = self._contract_retry_messages(
                    interpretation_messages(request),
                    exc,
                )
                continue
            return blueprint, usage
        raise AssertionError("unreachable")

    async def _generate_themes(
        self,
        request: StoryRequest,
        blueprint: StoryBlueprint,
    ) -> tuple[list[NarrativeTheme], TokenUsage]:
        themes: list[NarrativeTheme] = []
        usage = TokenUsage()
        while len(themes) < request.theme_count:
            start_index = len(themes) + 1
            count = min(10, request.theme_count - len(themes))
            base_messages = theme_messages(
                request,
                blueprint,
                start_index=start_index,
                count=count,
                existing_themes=themes,
            )
            messages = base_messages
            for attempt in range(self._generation_retries + 1):
                try:
                    response = await self._model.generate(
                        stage=StoryStage.THEMES,
                        messages=messages,
                        response_model=exact_theme_batch_model(count),
                        max_output_tokens=6000,
                    )
                except StoryProviderResponseError as exc:
                    usage += exc.usage
                    if attempt >= self._generation_retries:
                        raise
                    messages = self._contract_retry_messages(
                        base_messages,
                        exc,
                    )
                    continue
                usage += response.usage
                batch = response.value
                if not isinstance(batch, NarrativeThemeBatch):
                    raise StoryContractError(
                        "故事模型在 themes 阶段返回了错误类型"
                    )
                try:
                    self._validate_theme_batch(
                        request,
                        themes,
                        batch,
                        expected_start=start_index,
                        expected_count=count,
                    )
                    self._validate_output_language(
                        request,
                        batch,
                        stage="叙事主题",
                    )
                    validate_generated_story(
                        batch.model_dump_json(ensure_ascii=False)
                    )
                except StoryContractError as exc:
                    if attempt >= self._generation_retries:
                        raise
                    messages = self._contract_retry_messages(
                        base_messages,
                        exc,
                    )
                    continue
                break
            themes.extend(batch.themes)
        return themes, usage

    async def _generate_theme(
        self,
        request: StoryRequest,
        blueprint: StoryBlueprint,
        theme: NarrativeTheme,
    ) -> tuple[NarrativeThemeResult, TokenUsage]:
        sequence, narratives, usage = await self._generate_sequence(
            request,
            blueprint,
            theme,
        )
        reviews: list[NarrativeReview] = []
        revision_count = 0
        review_scope = sequence
        previous_full_review: NarrativeReview | None = None
        while True:
            review_response = await self._model.generate(
                stage=StoryStage.REVIEW,
                messages=review_messages(
                    request,
                    blueprint,
                    theme,
                    review_scope,
                ),
                response_model=exact_narrative_review_model(
                    len(review_scope.scenes)
                ),
                max_output_tokens=16000,
            )
            scoped_review = review_response.value
            if not isinstance(scoped_review, NarrativeReview):
                raise StoryContractError("故事模型在 review 阶段返回了错误类型")
            self._validate_review(review_scope, scoped_review)
            full_review = (
                scoped_review
                if previous_full_review is None
                else self._merge_review(
                    sequence,
                    previous_full_review,
                    scoped_review,
                )
            )
            reviews.append(full_review)
            usage += review_response.usage
            if full_review.meets_threshold():
                break
            if revision_count >= self._max_revisions:
                raise StoryContractError(
                    f"{theme.theme_id} 叙事评审未达到发布标准，且修订次数已耗尽"
                )
            failed_scene_ids = self._failed_scene_ids(full_review)
            revision_scope = self._select_sequence(
                sequence,
                failed_scene_ids,
            )
            revision_review = self._select_review(
                full_review,
                failed_scene_ids,
            )
            revision_response = await self._model.generate(
                stage=StoryStage.REVISE,
                messages=revision_messages(
                    request,
                    blueprint,
                    theme,
                    revision_scope,
                    revision_review,
                ),
                response_model=exact_narrative_sequence_model(
                    len(revision_scope.scenes)
                ),
                max_output_tokens=10000,
            )
            revised = revision_response.value
            if not isinstance(revised, NarrativeSequence):
                raise StoryContractError("故事模型在 revise 阶段返回了错误类型")
            self._restore_revision_identity(revision_scope, revised)
            sequence = self._merge_sequence(sequence, revised)
            self._validate_sequence(request, blueprint, sequence)
            self._validate_output_language(request, sequence, stage="修订场景")
            validate_generated_story(sequence.model_dump_json(ensure_ascii=False))
            narratives = render_narratives(
                blueprint,
                theme,
                sequence,
                request.output_language,
            )
            previous_full_review = full_review
            review_scope = self._select_sequence(
                sequence,
                failed_scene_ids,
            )
            revision_count += 1
            usage += revision_response.usage
        return (
            NarrativeThemeResult(
                theme=theme,
                sequence=sequence,
                narratives=narratives,
                reviews=reviews,
                revision_count=revision_count,
            ),
            usage,
        )

    async def _generate_sequence(
        self,
        request: StoryRequest,
        blueprint: StoryBlueprint,
        theme: NarrativeTheme,
    ) -> tuple[NarrativeSequence, list[RenderedNarrative], TokenUsage]:
        base_messages = narrative_messages(request, blueprint, theme)
        messages = base_messages
        usage = TokenUsage()
        for attempt in range(self._generation_retries + 1):
            try:
                sequence_response = await self._model.generate(
                    stage=StoryStage.SCENES,
                    messages=messages,
                    response_model=exact_narrative_sequence_model(
                        request.frames_per_theme
                    ),
                    max_output_tokens=10000,
                )
            except StoryProviderResponseError as exc:
                usage += exc.usage
                if attempt >= self._generation_retries:
                    raise
                messages = self._contract_retry_messages(
                    base_messages,
                    exc,
                )
                continue
            usage += sequence_response.usage
            sequence = sequence_response.value
            if not isinstance(sequence, NarrativeSequence):
                raise StoryContractError(
                    "故事模型在 scenes 阶段返回了错误类型"
                )
            try:
                self._validate_sequence(request, blueprint, sequence)
                self._validate_output_language(
                    request,
                    sequence,
                    stage="叙事场景",
                )
                validate_generated_story(
                    sequence.model_dump_json(ensure_ascii=False)
                )
            except StoryContractError as exc:
                if attempt >= self._generation_retries:
                    raise
                messages = self._contract_retry_messages(
                    base_messages,
                    exc,
                )
                continue
            break

        narratives = render_narratives(
            blueprint,
            theme,
            sequence,
            request.output_language,
        )
        return sequence, narratives, usage

    @staticmethod
    def _validate_theme_batch(
        request: StoryRequest,
        existing: list[NarrativeTheme],
        batch: NarrativeThemeBatch,
        *,
        expected_start: int,
        expected_count: int,
    ) -> None:
        expected_ids = [
            f"T{index:03d}"
            for index in range(
                expected_start,
                expected_start + expected_count,
            )
        ]
        actual_ids = [theme.theme_id for theme in batch.themes]
        if actual_ids != expected_ids:
            raise StoryContractError(
                "主题数量或顺序不符合请求："
                f"expected={expected_ids}, actual={actual_ids}"
            )
        if expected_start + expected_count - 1 > request.theme_count:
            raise StoryContractError("主题批次超出请求数量")
        all_themes = [*existing, *batch.themes]
        titles = [StoryStudio._semantic_key(theme.title) for theme in all_themes]
        if len(titles) != len(set(titles)):
            raise StoryContractError("主题标题必须实质不同")
        creative_keys = [
            (
                StoryStudio._semantic_key(theme.creative_intent.decisive_moment),
                StoryStudio._semantic_key(theme.creative_intent.visual_motif),
            )
            for theme in all_themes
        ]
        if len(creative_keys) != len(set(creative_keys)):
            raise StoryContractError("主题的决定性瞬间与视觉母题组合必须实质不同")
        source_material = request.story
        generated_themes = batch.model_dump_json(ensure_ascii=False)
        for unsupported_identity_mark in (
            "疤",
            "胎记",
            "纹身",
            "戒痕",
        ):
            if (
                unsupported_identity_mark in generated_themes
                and unsupported_identity_mark not in source_material
            ):
                raise StoryContractError(
                    "主题新增了故事未提供的身份标记："
                    f"{unsupported_identity_mark}"
                )

    @staticmethod
    def _semantic_key(value: str) -> str:
        return re.sub(r"[\W\d_]+", "", value.casefold())

    @staticmethod
    def _contract_retry_messages(
        base_messages: list[ChatMessage],
        error: StoryContractError | StoryProviderResponseError,
    ) -> list[ChatMessage]:
        return [
            *base_messages,
            ChatMessage(
                role="user",
                content=(
                    "上一份输出违反硬性契约，必须从头重新生成。"
                    f"具体问题：{error}。"
                    "只修正该问题并继续遵守 system 中的全部规则；"
                    "不要解释或输出 schema 之外的内容。"
                ),
            ),
        ]

    @staticmethod
    def _normalize_display_names(
        request: StoryRequest,
        blueprint: StoryBlueprint,
    ) -> None:
        chinese_ordinals = "一二三四五六七八"
        normalized_story = re.sub(r"\s+", "", request.story)
        for index, character in enumerate(blueprint.characters, start=1):
            normalized_name = re.sub(r"\s+", "", character.display_name)
            if normalized_name not in normalized_story:
                character.display_name = (
                    f"人物{chinese_ordinals[index - 1]}"
                    if request.output_language == OutputLanguage.CHINESE
                    else f"Character {index}"
                )

    @staticmethod
    def _validate_blueprint_fidelity(
        request: StoryRequest,
        blueprint: StoryBlueprint,
    ) -> None:
        normalized_story = re.sub(r"\s+", "", request.story)
        story_has_gender = bool(
            re.search(
                r"男性|女性|男人|女人|男子|女子|男士|女士|丈夫|妻子|"
                r"男孩|女孩|少女|少年|父亲|母亲",
                request.story,
            )
        )
        if not story_has_gender:
            for character in blueprint.characters:
                identity_text = (
                    f"{character.display_name}{character.role}"
                    f"{character.appearance}{character.outfit}"
                )
                if re.search(r"男性|女性|男人|女人|男子|女子|旗袍|裙装", identity_text):
                    raise StoryContractError(
                        f"{character.character_id} 新增了原文未提供的性别"
                    )
        for relationship in blueprint.relationships:
            normalized_relationship = re.sub(
                r"\s+",
                "",
                relationship.source_relationship,
            )
            if normalized_relationship not in normalized_story:
                raise StoryContractError(
                    "人物关系没有故事原文依据："
                    f"{relationship.source_relationship}"
                )
            for unsupported_history in (
                "多年",
                "十年前",
                "曾经",
                "旧日",
                "约定",
                "秘密",
            ):
                if (
                    unsupported_history in relationship.relationship
                    and unsupported_history not in request.story
                ):
                    raise StoryContractError(
                        "人物关系新增了原文未提供的经历："
                        f"{unsupported_history}"
                    )
        for beat in blueprint.beats:
            normalized_source_action = re.sub(r"\s+", "", beat.source_action)
            if normalized_source_action not in normalized_story:
                raise StoryContractError(
                    f"{beat.beat_id} 动作没有故事原文依据："
                    f"{beat.source_action}"
                )
            if re.search(
                r"彼此|他们|两人|一起|双方",
                beat.source_action,
            ) and len(
                beat.participant_ids
            ) < 2:
                raise StoryContractError(
                    f"{beat.beat_id} 多人动作缺少参与人物"
                )

    @staticmethod
    def _validate_output_language(
        request: StoryRequest,
        value: object,
        *,
        stage: str,
    ) -> None:
        if request.output_language != OutputLanguage.CHINESE:
            return
        allowed_words = {
            word.casefold()
            for word in re.findall(r"[A-Za-z]{2,}", request.story)
        }

        def text_values(item: object) -> list[str]:
            if isinstance(item, str):
                return [item]
            if isinstance(item, list):
                return [
                    text
                    for child in item
                    for text in text_values(child)
                ]
            if isinstance(item, dict):
                return [
                    text
                    for key, child in item.items()
                    if not key.endswith("_id")
                    and key
                    not in {"mode", "participant_ids", "visible_character_ids"}
                    for text in text_values(child)
                ]
            if hasattr(item, "model_dump"):
                return text_values(item.model_dump(mode="json"))
            return []

        unexpected = sorted(
            {
                word
                for text in text_values(value)
                for word in re.findall(r"[A-Za-z]{2,}", text)
                if word.casefold() not in allowed_words
            }
        )
        if unexpected:
            raise StoryContractError(
                f"{stage}混入原文未提供的英文：{unexpected}"
            )

    @staticmethod
    def _validate_portfolio(
        themes: list[NarrativeThemeResult],
    ) -> None:
        sequence_keys = [
            StoryStudio._semantic_key(
                "\n".join(narrative.prose for narrative in theme.narratives)
            )
            for theme in themes
        ]
        if len(sequence_keys) != len(set(sequence_keys)):
            raise StoryContractError("不同主题的画面序列必须实质不同")

    @staticmethod
    def _validate_sequence(
        request: StoryRequest,
        blueprint: StoryBlueprint,
        sequence: NarrativeSequence,
    ) -> None:
        expected_scene_ids = [
            f"S{index:02d}" for index in range(1, request.frames_per_theme + 1)
        ]
        actual_scene_ids = [scene.scene_id for scene in sequence.scenes]
        if actual_scene_ids != expected_scene_ids:
            raise StoryContractError(
                "场景数量或顺序不符合请求："
                f"expected={expected_scene_ids}, actual={actual_scene_ids}"
            )
        semantic_frames = [
            StoryStudio._semantic_key(
                json.dumps(
                    scene.model_dump(
                        mode="json",
                        exclude={"scene_id"},
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            for scene in sequence.scenes
        ]
        if len(semantic_frames) != len(set(semantic_frames)):
            raise StoryContractError("同一主题中的每个画面必须实质不同")

        known_beats = {beat.beat_id for beat in blueprint.beats}
        known_characters = {
            character.character_id for character in blueprint.characters
        }
        for scene in sequence.scenes:
            if scene.beat_id not in known_beats:
                raise StoryContractError(
                    f"{scene.scene_id} 引用未知故事节拍：{scene.beat_id}"
                )
            unknown_characters = set(scene.visible_character_ids) - known_characters
            if unknown_characters:
                raise StoryContractError(
                    f"{scene.scene_id} 引用未知人物：{sorted(unknown_characters)}"
                )
            expected_order = [
                character.character_id
                for character in blueprint.characters
                if character.character_id in scene.visible_character_ids
            ]
            if scene.visible_character_ids != expected_order:
                raise StoryContractError(
                    f"{scene.scene_id} 人物必须按 StoryBlueprint 顺序排列"
                )
            normalized_story = re.sub(r"\s+", "", request.story)
            for source_text in scene.source_context:
                if re.sub(r"\s+", "", source_text) not in normalized_story:
                    raise StoryContractError(
                        f"{scene.scene_id} 来源片段没有故事原文依据："
                        f"{source_text}"
                    )
            for action in scene.present_actions:
                unknown_action_characters = set(action.participant_ids) - set(
                    scene.visible_character_ids
                )
                if unknown_action_characters:
                    raise StoryContractError(
                        f"{scene.scene_id} 动作引用未入画人物："
                        f"{sorted(unknown_action_characters)}"
                    )

    @staticmethod
    def _validate_review(
        sequence: NarrativeSequence,
        review: NarrativeReview,
    ) -> None:
        expected_ids = [scene.scene_id for scene in sequence.scenes]
        actual_ids = [scene_review.scene_id for scene_review in review.scene_reviews]
        if actual_ids != expected_ids:
            raise StoryContractError(
                "叙事评审没有按顺序覆盖全部场景："
                f"expected={expected_ids}, actual={actual_ids}"
            )
        for scene_review in review.scene_reviews:
            wrong_issue_ids = {
                issue.scene_id
                for issue in scene_review.issues
                if issue.scene_id != scene_review.scene_id
            }
            if wrong_issue_ids:
                raise StoryContractError(
                    f"{scene_review.scene_id} 的评审问题引用其他场景："
                    f"{sorted(wrong_issue_ids)}"
                )
            low_dimensions = {
                dimension
                for dimension, score in (scene_review.scores.model_dump().items())
                if score < 4
            }
            issue_dimensions = {issue.dimension.value for issue in scene_review.issues}
            if low_dimensions != issue_dimensions:
                raise StoryContractError(
                    f"{scene_review.scene_id} 的低分维度与 issues 不一致"
                )

    @staticmethod
    def _failed_scene_ids(review: NarrativeReview) -> list[str]:
        return [
            scene_review.scene_id
            for scene_review in review.scene_reviews
            if not scene_review.scores.meets_threshold()
            or scene_review.issues
        ]

    @staticmethod
    def _select_sequence(
        sequence: NarrativeSequence,
        scene_ids: list[str],
    ) -> NarrativeSequence:
        selected = set(scene_ids)
        return NarrativeSequence(
            scenes=[
                scene
                for scene in sequence.scenes
                if scene.scene_id in selected
            ]
        )

    @staticmethod
    def _select_review(
        review: NarrativeReview,
        scene_ids: list[str],
    ) -> NarrativeReview:
        selected = set(scene_ids)
        return NarrativeReview(
            scene_reviews=[
                scene_review
                for scene_review in review.scene_reviews
                if scene_review.scene_id in selected
            ],
            overall_summary=review.overall_summary,
        )

    @staticmethod
    def _merge_sequence(
        sequence: NarrativeSequence,
        revised: NarrativeSequence,
    ) -> NarrativeSequence:
        replacements = {
            scene.scene_id: scene
            for scene in revised.scenes
        }
        return NarrativeSequence(
            scenes=[
                replacements.get(scene.scene_id, scene)
                for scene in sequence.scenes
            ]
        )

    @staticmethod
    def _merge_review(
        sequence: NarrativeSequence,
        previous: NarrativeReview,
        updated: NarrativeReview,
    ) -> NarrativeReview:
        replacements = {
            scene_review.scene_id: scene_review
            for scene_review in updated.scene_reviews
        }
        previous_by_id = {
            scene_review.scene_id: scene_review
            for scene_review in previous.scene_reviews
        }
        return NarrativeReview(
            scene_reviews=[
                replacements.get(
                    scene.scene_id,
                    previous_by_id[scene.scene_id],
                )
                for scene in sequence.scenes
            ],
            overall_summary=updated.overall_summary,
        )

    @staticmethod
    def _restore_revision_identity(
        previous: NarrativeSequence,
        revised: NarrativeSequence,
    ) -> None:
        for old_scene, new_scene in zip(
            previous.scenes,
            revised.scenes,
            strict=True,
        ):
            if len(old_scene.present_actions) != len(new_scene.present_actions):
                raise StoryContractError(
                    f"{old_scene.scene_id} 修订不得改变动作条目数量"
                )
            if len(old_scene.visible_text) != len(new_scene.visible_text):
                raise StoryContractError(
                    f"{old_scene.scene_id} 修订不得改变画面文字条目数量"
                )
            new_scene.scene_id = old_scene.scene_id
            new_scene.beat_id = old_scene.beat_id
            new_scene.mode = old_scene.mode
            new_scene.visible_character_ids = old_scene.visible_character_ids.copy()
            for old_action, new_action in zip(
                old_scene.present_actions,
                new_scene.present_actions,
                strict=True,
            ):
                new_action.participant_ids = old_action.participant_ids.copy()
            for old_text, new_text in zip(
                old_scene.visible_text,
                new_scene.visible_text,
                strict=True,
            ):
                new_text.content = old_text.content
