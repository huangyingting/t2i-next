from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from t2i_prompt_pipeline.errors import (
    ConfigurationError,
    GenerationContractError,
    ProviderTruncatedOutputError,
    RunIncompleteError,
    RunStoreError,
    StructuredOutputError,
)
from t2i_prompt_pipeline.models import (
    AttemptOutcome,
    FrameBatch,
    Gender,
    GenerationStage,
    OutputLanguage,
    ResolvedRuleSet,
    RunStatus,
    Theme,
    ThemeBatch,
    TokenUsage,
)
from t2i_prompt_pipeline.pipeline import PromptStudio
from t2i_prompt_pipeline.providers.base import (
    ChatMessage,
    ModelResponse,
)
from t2i_prompt_pipeline.store import InMemoryRunStore, LocalRunStore
from tests.factories import (
    make_foundation,
    make_frame_batch,
    make_rules,
    make_settings,
    make_spec,
    make_themes,
)


class FakeAuthor:
    def __init__(self, spec: Any) -> None:
        self.spec = spec
        self.foundation = make_foundation(spec)
        self.themes = {
            theme.theme_id: theme for theme in make_themes(spec)
        }
        self.frames = {
            theme_id: {
                frame.frame_id: frame
                for frame in make_frame_batch(spec, theme).frames
            }
            for theme_id, theme in self.themes.items()
        }
        self.calls: list[
            tuple[GenerationStage, tuple[str, ...], int]
        ] = []
        self.system_messages: list[tuple[GenerationStage, str]] = []
        self.requests: list[tuple[GenerationStage, dict[str, Any]]] = []
        self.partial_theme_once = False
        self.partial_frame_themes: set[str] = set()
        self.fail_frame_themes: set[str] = set()
        self.truncate_foundation_once = False
        self.contract_invalid_foundation_once = False
        self.duplicate_invalid_theme_once = False
        self.duplicate_invalid_frame_themes: set[str] = set()
        self.mixed_invalid_theme_once = False
        self.mixed_invalid_frame_themes: set[str] = set()
        self.contract_invalid_theme_once = False
        self.contract_invalid_frame_themes: set[str] = set()
        self.depth_conflict_frame_themes: set[str] = set()
        self.duplicate_scene_theme_once = False
        self.duplicate_title_theme_once = False
        self.duplicate_frame_content_themes: set[str] = set()
        self.raise_unexpected_theme_error = False
        self.usage = TokenUsage(
            prompt_tokens=100,
            cached_prompt_tokens=25,
            completion_tokens=40,
            total_tokens=140,
        )

    async def generate(
        self,
        *,
        stage: GenerationStage,
        messages: list[ChatMessage],
        response_model: type[BaseModel],
        max_output_tokens: int,
    ) -> ModelResponse[Any]:
        request = json.loads(messages[1].content)
        self.requests.append((stage, request))
        self.system_messages.append((stage, messages[0].content))
        requested_ids: tuple[str, ...] = ()
        if stage == GenerationStage.THEMES:
            requested_ids = tuple(request["theme_ids"])
        elif stage == GenerationStage.FRAMES:
            requested_ids = tuple(request["frame_ids"])
        self.calls.append((stage, requested_ids, max_output_tokens))

        if stage == GenerationStage.FOUNDATION:
            if self.truncate_foundation_once:
                self.truncate_foundation_once = False
                raise ProviderTruncatedOutputError(
                    "truncated",
                    raw_content="{}",
                )
            if self.contract_invalid_foundation_once:
                self.contract_invalid_foundation_once = False
                value = self.foundation.model_copy(deep=True)
                value.style_constraints.required_phrases = []
            else:
                value = self.foundation
        elif stage == GenerationStage.THEMES:
            if self.raise_unexpected_theme_error:
                raise TypeError("programming error")
            returned_ids = requested_ids
            if self.mixed_invalid_theme_once:
                self.mixed_invalid_theme_once = False
                payload = {
                    "themes": [
                        self.themes[theme_id].model_dump(mode="json")
                        for theme_id in returned_ids
                    ]
                }
                payload["themes"][-1]["characters"][0]["age"] = 20
                raise StructuredOutputError(
                    "mixed-validity themes",
                    raw_content=json.dumps(payload),
                )
            if self.partial_theme_once and len(returned_ids) > 1:
                self.partial_theme_once = False
                returned_ids = returned_ids[:1]
            if self.contract_invalid_theme_once:
                self.contract_invalid_theme_once = False
                invalid = self.themes[returned_ids[0]].model_copy(
                    update={
                        "style": "电影摄影采用固定机位中景与暖色木纹。"
                    }
                )
                value = ThemeBatch(themes=[invalid])
            else:
                value = ThemeBatch(
                    themes=[
                        self.themes[theme_id] for theme_id in returned_ids
                    ]
                )
            if self.duplicate_scene_theme_once:
                self.duplicate_scene_theme_once = False
                value.themes[1] = value.themes[1].model_copy(
                    update={"scene": value.themes[0].scene}
                )
            if self.duplicate_title_theme_once:
                self.duplicate_title_theme_once = False
                value.themes[1] = value.themes[1].model_copy(
                    update={"title": value.themes[0].title}
                )
            if self.duplicate_invalid_theme_once:
                self.duplicate_invalid_theme_once = False
                valid = value.themes[0]
                invalid_characters = [
                    character.model_copy(
                        update={"gender": Gender.MALE}
                    )
                    for character in valid.characters
                ]
                value = ThemeBatch(
                    themes=[
                        valid.model_copy(
                            update={"characters": invalid_characters}
                        ),
                        *value.themes,
                    ]
                )
        else:
            theme_id = request["theme"]["theme_id"]
            if theme_id in self.fail_frame_themes:
                raise StructuredOutputError(
                    f"{theme_id} failed",
                    raw_content="{}",
                )
            returned_ids = requested_ids
            if theme_id in self.mixed_invalid_frame_themes:
                self.mixed_invalid_frame_themes.remove(theme_id)
                payload = {
                    "theme_id": theme_id,
                    "frames": [
                        self.frames[theme_id][frame_id].model_dump(mode="json")
                        for frame_id in returned_ids
                    ],
                }
                payload["frames"][-1]["details"] = ""
                raise StructuredOutputError(
                    "mixed-validity frames",
                    raw_content=json.dumps(payload),
                )
            if (
                theme_id in self.partial_frame_themes
                and len(returned_ids) > 1
            ):
                self.partial_frame_themes.remove(theme_id)
                returned_ids = returned_ids[:1]
            frames = [
                self.frames[theme_id][frame_id]
                for frame_id in returned_ids
            ]
            if theme_id in self.contract_invalid_frame_themes:
                self.contract_invalid_frame_themes.remove(theme_id)
                frames[0] = frames[0].model_copy(
                    update={
                        "characters": [
                            frames[0].characters[0].model_copy(
                                update={"action": "背对镜头，全身出画不可见"}
                            )
                        ]
                    }
                )
            if theme_id in self.depth_conflict_frame_themes:
                self.depth_conflict_frame_themes.remove(theme_id)
                frames[0] = frames[0].model_copy(
                    update={
                        "camera": frames[0].camera.model_copy(
                            update={"shot": "中景，浅景深聚焦人物"}
                        )
                    }
                )
            value = FrameBatch(theme_id=theme_id, frames=frames)
            if (
                theme_id in self.duplicate_frame_content_themes
                and len(value.frames) > 1
            ):
                self.duplicate_frame_content_themes.remove(theme_id)
                value.frames[1] = value.frames[0].model_copy(
                    update={"frame_id": value.frames[1].frame_id}
                )
            if theme_id in self.duplicate_invalid_frame_themes:
                self.duplicate_invalid_frame_themes.remove(theme_id)
                valid = value.frames[0]
                value = FrameBatch(
                    theme_id=theme_id,
                    frames=[
                        valid.model_copy(
                            update={
                                "characters": valid.characters[:1]
                            }
                        ),
                        *value.frames,
                    ],
                )
        return ModelResponse(value=value, usage=self.usage)


class BlockingThemeAuthor(FakeAuthor):
    def __init__(self, spec) -> None:
        super().__init__(spec)
        self.started = asyncio.Event()
        self.blocker = asyncio.Event()
        self.active = 0

    async def generate(
        self,
        *,
        stage: GenerationStage,
        messages: list[ChatMessage],
        response_model: type[BaseModel],
        max_output_tokens: int | None = None,
    ) -> ModelResponse[Any]:
        if stage is not GenerationStage.THEMES:
            return await super().generate(
                stage=stage,
                messages=messages,
                response_model=response_model,
                max_output_tokens=max_output_tokens,
            )
        self.active += 1
        self.started.set()
        try:
            await self.blocker.wait()
        finally:
            self.active -= 1
        raise AssertionError("blocking call unexpectedly resumed")


class ThemeCheckpointFailingStore(InMemoryRunStore):
    def checkpoint(self, run_id, artifact) -> None:
        if isinstance(artifact, Theme):
            raise RunStoreError("checkpoint disk full")
        super().checkpoint(run_id, artifact)


@pytest.mark.asyncio
async def test_successful_run_journals_stage_attempts_and_usage() -> None:
    spec = make_spec()
    store = InMemoryRunStore()
    author = FakeAuthor(spec)

    result = await PromptStudio(
        author,
        store,
        make_settings(),
    ).run(spec, make_rules(spec))

    attempts = store.attempts(result.run_id)
    assert [attempt.stage for attempt in attempts] == [
        GenerationStage.FOUNDATION,
        GenerationStage.THEMES,
        GenerationStage.FRAMES,
    ]
    assert [attempt.outcome for attempt in attempts] == [
        AttemptOutcome.ACCEPTED,
        AttemptOutcome.ACCEPTED,
        AttemptOutcome.ACCEPTED,
    ]
    assert attempts[1].requested_ids == ["T01"]
    assert attempts[2].accepted_ids == ["T01-F01"]
    assert all(attempt.usage == author.usage for attempt in attempts)
    assert all(attempt.duration_ms >= 0 for attempt in attempts)


@pytest.mark.asyncio
async def test_five_by_five_uses_batched_calls_and_checkpoints() -> None:
    spec = make_spec(
        theme_count=5,
        frames_per_theme=5,
        female_count=1,
        male_count=1,
    )
    author = FakeAuthor(spec)
    store = InMemoryRunStore()

    result = await PromptStudio(
        author,
        store,
        make_settings(),
    ).run(spec, make_rules(spec))

    stages = [stage for stage, _, _ in author.calls]
    assert stages.count(GenerationStage.FOUNDATION) == 1
    assert stages.count(GenerationStage.THEMES) == 1
    assert stages.count(GenerationStage.FRAMES) == 5
    assert len(result.result.prompts) == 25
    snapshot = store.inspect(result.run_id)
    assert len(snapshot.themes) == 5
    assert len(snapshot.frames) == 25
    assert snapshot.completed is not None


@pytest.mark.asyncio
async def test_unconstrained_run_uses_foundation_cast_plan() -> None:
    spec = make_spec(female_count=None, male_count=None)
    resolved_spec = make_spec(female_count=2, male_count=1)
    author = FakeAuthor(resolved_spec)

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(),
    ).run(spec, make_rules(spec))

    assert result.result.book.cast_plan == author.foundation.cast_plan
    assert len(result.result.book.themes[0].theme.characters) == 3


@pytest.mark.asyncio
async def test_cast_constraint_conflict_stops_before_themes() -> None:
    spec = make_spec(female_count=1, male_count=0)
    author = FakeAuthor(spec)
    author.foundation = make_foundation(
        make_spec(female_count=2, male_count=1)
    )

    with pytest.raises(
        GenerationContractError,
        match=r"brief 解析为女性 2 名.*--female-count 要求 1 名",
    ):
        await PromptStudio(
            author,
            InMemoryRunStore(),
            make_settings(),
        ).run(spec, make_rules(spec))

    assert [stage for stage, _, _ in author.calls] == [
        GenerationStage.FOUNDATION
    ]


@pytest.mark.asyncio
async def test_hundred_by_six_uses_bounded_theme_batches() -> None:
    spec = make_spec(
        theme_count=100,
        frames_per_theme=6,
        female_count=1,
        male_count=1,
    )
    author = FakeAuthor(spec)

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(theme_batch_size=5),
    ).run(spec, make_rules(spec))

    theme_calls = [
        ids
        for stage, ids, _ in author.calls
        if stage == GenerationStage.THEMES
    ]
    assert len(author.calls) == 121
    assert len(theme_calls) == 20
    assert all(1 <= len(ids) <= 5 for ids in theme_calls)
    assert len(result.result.prompts) == 600
    assert all(
        tokens <= 16384 for _, _, tokens in author.calls
    )


@pytest.mark.asyncio
async def test_missing_themes_and_frames_are_supplemented() -> None:
    spec = make_spec(
        theme_count=3,
        frames_per_theme=3,
        female_count=1,
        male_count=1,
    )
    author = FakeAuthor(spec)
    author.partial_theme_once = True
    author.partial_frame_themes = {"T01"}

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(),
    ).run(spec, make_rules(spec))

    theme_requests = [
        ids
        for stage, ids, _ in author.calls
        if stage == GenerationStage.THEMES
    ]
    t01_frame_requests = [
        ids
        for stage, ids, _ in author.calls
        if stage == GenerationStage.FRAMES
        and ids
        and ids[0].startswith("T01-")
    ]
    assert theme_requests == [
        ("T01", "T02", "T03"),
        ("T02", "T03"),
    ]
    assert t01_frame_requests == [
        ("T01-F01", "T01-F02", "T01-F03"),
        ("T01-F02", "T01-F03"),
    ]
    assert len(result.result.prompts) == 9


@pytest.mark.asyncio
async def test_progressing_completion_passes_finish_without_external_resume() -> None:
    spec = make_spec(
        theme_count=3,
        frames_per_theme=2,
        female_count=1,
        male_count=1,
    )
    author = FakeAuthor(spec)
    author.partial_theme_once = True
    author.partial_frame_themes = {"T01"}

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=0),
    ).run(spec, make_rules(spec))

    assert len(result.result.book.themes) == 3
    assert len(result.result.prompts) == 6
    assert [
        ids
        for stage, ids, _ in author.calls
        if stage == GenerationStage.THEMES
    ] == [
        ("T01", "T02", "T03"),
        ("T02", "T03"),
    ]
    assert [
        ids
        for stage, ids, _ in author.calls
        if stage == GenerationStage.FRAMES
        and ids
        and ids[0].startswith("T01-")
    ] == [
        ("T01-F01", "T01-F02"),
        ("T01-F02",),
    ]


@pytest.mark.asyncio
async def test_contract_rejections_are_sent_to_targeted_retries() -> None:
    spec = make_spec()
    author = FakeAuthor(spec)
    author.contract_invalid_theme_once = True
    author.contract_invalid_frame_themes = {"T01"}

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=1),
    ).run(spec, make_rules(spec))

    theme_requests = [
        request
        for stage, request in author.requests
        if stage == GenerationStage.THEMES
    ]
    frame_requests = [
        request
        for stage, request in author.requests
        if stage == GenerationStage.FRAMES
    ]
    assert "validation_issues" not in theme_requests[0]
    assert "Frame 专属具体摄影参数：固定机位" in " ".join(
        theme_requests[1]["validation_issues"]
    )
    assert "validation_issues" not in frame_requests[0]
    assert "action 包含不可见描述：出画" in " ".join(
        frame_requests[1]["validation_issues"]
    )
    assert len(result.result.prompts) == 1


@pytest.mark.asyncio
async def test_depth_conflict_retry_names_required_theme_depth() -> None:
    spec = make_spec()
    author = FakeAuthor(spec)
    author.themes["T01"] = author.themes["T01"].model_copy(
        update={"style": f"{author.themes['T01'].style} 景深偏深。"}
    )
    author.depth_conflict_frame_themes = {"T01"}

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=1),
    ).run(spec, make_rules(spec))

    frame_requests = [
        request
        for stage, request in author.requests
        if stage == GenerationStage.FRAMES
    ]
    assert "validation_issues" not in frame_requests[0]
    assert frame_requests[1]["validation_issues"] == [
        "T01-F01 camera.shot 必须继承 Theme.style 的深景深；"
        "不得使用浅景深。"
    ]
    assert len(result.result.prompts) == 1


@pytest.mark.asyncio
async def test_foundation_contract_rejection_is_sent_to_retry() -> None:
    phrase = "贝纳尔多·贝托鲁奇（Bernardo Bertolucci）导演风格"
    spec = make_spec(brief=f"{phrase}的两名成年人互动")
    author = FakeAuthor(spec)
    author.foundation.style_constraints.required_phrases = [phrase]
    author.themes = {
        theme_id: theme.model_copy(
            update={"style": f"{phrase}，{theme.style}"}
        )
        for theme_id, theme in author.themes.items()
    }
    author.contract_invalid_foundation_once = True

    await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=1),
    ).run(spec, make_rules(spec))

    foundation_requests = [
        request
        for stage, request in author.requests
        if stage == GenerationStage.FOUNDATION
    ]
    assert "validation_issues" not in foundation_requests[0]
    assert "遗漏 brief 明示风格" in " ".join(
        foundation_requests[1]["validation_issues"]
    )


@pytest.mark.asyncio
async def test_duplicate_theme_scene_is_targeted_with_existing_theme() -> None:
    spec = make_spec(theme_count=2)
    author = FakeAuthor(spec)
    author.duplicate_scene_theme_once = True

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=1),
    ).run(spec, make_rules(spec))

    theme_requests = [
        request
        for stage, request in author.requests
        if stage == GenerationStage.THEMES
    ]
    assert [request["theme_ids"] for request in theme_requests] == [
        ["T01", "T02"],
        ["T02"],
    ]
    assert theme_requests[1]["existing_themes"][0]["theme_id"] == "T01"
    assert "Theme.scene 与已接受 Theme 重复" in " ".join(
        theme_requests[1]["validation_issues"]
    )
    assert len(result.result.book.themes) == 2


@pytest.mark.asyncio
async def test_duplicate_theme_title_is_targeted_with_existing_theme() -> None:
    spec = make_spec(theme_count=2)
    author = FakeAuthor(spec)
    author.duplicate_title_theme_once = True

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=1),
    ).run(spec, make_rules(spec))

    theme_requests = [
        request
        for stage, request in author.requests
        if stage == GenerationStage.THEMES
    ]
    assert [request["theme_ids"] for request in theme_requests] == [
        ["T01", "T02"],
        ["T02"],
    ]
    assert "Theme.title 与已接受 Theme 重复" in " ".join(
        theme_requests[1]["validation_issues"]
    )
    assert len(result.result.book.themes) == 2


@pytest.mark.asyncio
async def test_duplicate_frame_content_is_targeted() -> None:
    spec = make_spec(frames_per_theme=2)
    author = FakeAuthor(spec)
    author.duplicate_frame_content_themes = {"T01"}

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=1),
    ).run(spec, make_rules(spec))

    frame_requests = [
        request
        for stage, request in author.requests
        if stage == GenerationStage.FRAMES
    ]
    assert [request["frame_ids"] for request in frame_requests] == [
        ["T01-F01", "T01-F02"],
        ["T01-F02"],
    ]
    assert "Frame 内容与已接受 Frame 重复" in " ".join(
        frame_requests[1]["validation_issues"]
    )
    assert len(result.result.prompts) == 2


@pytest.mark.asyncio
async def test_schema_invalid_theme_sibling_preserves_valid_theme() -> None:
    spec = make_spec(theme_count=2)
    author = FakeAuthor(spec)
    author.mixed_invalid_theme_once = True

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=1),
    ).run(spec, make_rules(spec))

    theme_requests = [
        ids
        for stage, ids, _ in author.calls
        if stage == GenerationStage.THEMES
    ]
    assert theme_requests == [("T01", "T02"), ("T02",)]
    assert len(result.result.book.themes) == 2


@pytest.mark.asyncio
async def test_schema_invalid_frame_sibling_preserves_valid_frame() -> None:
    spec = make_spec(frames_per_theme=2)
    author = FakeAuthor(spec)
    author.mixed_invalid_frame_themes = {"T01"}

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=1),
    ).run(spec, make_rules(spec))

    frame_requests = [
        ids
        for stage, ids, _ in author.calls
        if stage == GenerationStage.FRAMES
    ]
    assert frame_requests == [
        ("T01-F01", "T01-F02"),
        ("T01-F02",),
    ]
    assert len(result.result.book.themes[0].frames) == 2


@pytest.mark.asyncio
async def test_valid_duplicate_after_invalid_object_is_kept() -> None:
    spec = make_spec(female_count=1, male_count=1)
    author = FakeAuthor(spec)
    author.duplicate_invalid_theme_once = True
    author.duplicate_invalid_frame_themes = {"T01"}

    result = await PromptStudio(
        author,
        InMemoryRunStore(),
        make_settings(generation_retries=0),
    ).run(spec, make_rules(spec))

    assert len(result.result.prompts) == 1


@pytest.mark.asyncio
async def test_pipeline_renders_selected_english_output_language() -> None:
    spec = make_spec(output_language=OutputLanguage.ENGLISH)

    result = await PromptStudio(
        FakeAuthor(spec),
        InMemoryRunStore(),
        make_settings(),
    ).run(spec, make_rules(spec))

    assert "Theme:" in result.result.prompts[0].text
    assert "主题：" not in result.result.prompts[0].text


@pytest.mark.asyncio
async def test_cancelling_run_cleans_up_parallel_generation_tasks() -> None:
    spec = make_spec(theme_count=2)
    author = BlockingThemeAuthor(spec)
    operation = asyncio.create_task(
        PromptStudio(
            author,
            InMemoryRunStore(),
            make_settings(theme_batch_size=1),
        ).run(spec, make_rules(spec))
    )
    await asyncio.wait_for(author.started.wait(), timeout=1)

    operation.cancel()

    with pytest.raises(asyncio.CancelledError):
        await operation
    assert author.active == 0


@pytest.mark.asyncio
async def test_checkpoint_store_error_aborts_generation() -> None:
    spec = make_spec()
    author = FakeAuthor(spec)

    with pytest.raises(RunStoreError, match="checkpoint disk full"):
        await PromptStudio(
            author,
            ThemeCheckpointFailingStore(),
            make_settings(),
        ).run(spec, make_rules(spec))

    assert [stage for stage, _, _ in author.calls] == [
        GenerationStage.FOUNDATION,
        GenerationStage.THEMES,
    ]


@pytest.mark.asyncio
async def test_unexpected_parallel_error_is_not_treated_as_incomplete() -> None:
    spec = make_spec()
    author = FakeAuthor(spec)
    author.raise_unexpected_theme_error = True

    with pytest.raises(TypeError, match="programming error"):
        await PromptStudio(
            author,
            InMemoryRunStore(),
            make_settings(),
        ).run(spec, make_rules(spec))


@pytest.mark.asyncio
async def test_resume_only_generates_missing_frames() -> None:
    spec = make_spec(
        theme_count=3,
        frames_per_theme=2,
        female_count=1,
        male_count=1,
        output_language=OutputLanguage.ENGLISH,
    )
    store = InMemoryRunStore()
    failing = FakeAuthor(spec)
    failing.fail_frame_themes = {"T02"}
    settings = make_settings(generation_retries=0)

    with pytest.raises(RunIncompleteError) as error:
        await PromptStudio(failing, store, settings).run(
            spec,
            make_rules(spec),
        )

    run_id = error.value.run_id
    failed_snapshot = store.inspect(run_id)
    assert len(failed_snapshot.themes) == 3
    assert sorted(failed_snapshot.frames) == [
        "T01-F01",
        "T01-F02",
        "T03-F01",
        "T03-F02",
    ]
    assert failed_snapshot.completed is None

    resumed_author = FakeAuthor(spec)
    result = await PromptStudio(
        resumed_author,
        store,
        settings,
    ).resume(run_id)

    assert [stage for stage, _, _ in resumed_author.calls] == [
        GenerationStage.FRAMES
    ]
    assert resumed_author.calls[0][1] == ("T02-F01", "T02-F02")
    assert len(result.result.prompts) == 6


@pytest.mark.asyncio
async def test_resume_uses_frozen_rules() -> None:
    spec = make_spec()
    original = ResolvedRuleSet(
        foundation=("原始基础规则",),
        themes=("原始主题规则",),
        frames=("原始镜头规则",),
    )
    store = InMemoryRunStore()
    failing = FakeAuthor(spec)
    failing.fail_frame_themes = {"T01"}
    settings = make_settings(generation_retries=0)

    with pytest.raises(RunIncompleteError) as error:
        await PromptStudio(
            failing,
            store,
            settings,
        ).run(spec, original)

    resumed = FakeAuthor(spec)
    await PromptStudio(
        resumed,
        store,
        settings,
    ).resume(error.value.run_id)

    assert resumed.system_messages == [
        (GenerationStage.FRAMES, "原始镜头规则")
    ]
    assert store.inspect(error.value.run_id).rules == original


@pytest.mark.asyncio
async def test_resume_reuses_journaled_validation_issues() -> None:
    spec = make_spec()
    store = InMemoryRunStore()
    failing = FakeAuthor(spec)
    failing.contract_invalid_frame_themes = {"T01"}
    settings = make_settings(generation_retries=0)
    rules = make_rules(spec)
    snapshot = store.create(spec, settings, rules)
    store.checkpoint(snapshot.run_id, failing.foundation)
    store.checkpoint(snapshot.run_id, failing.themes["T01"])

    with pytest.raises(RunIncompleteError) as error:
        await PromptStudio(failing, store, settings).resume(snapshot.run_id)

    resumed = FakeAuthor(spec)
    await PromptStudio(resumed, store, settings).resume(error.value.run_id)

    frame_requests = [
        request
        for stage, request in resumed.requests
        if stage == GenerationStage.FRAMES
    ]
    assert "action 包含不可见描述：出画" in " ".join(
        frame_requests[0]["validation_issues"]
    )


@pytest.mark.asyncio
async def test_new_store_instance_resumes_files_after_process_loss(
    tmp_path,
) -> None:
    spec = make_spec(
        theme_count=3,
        frames_per_theme=2,
        female_count=1,
        male_count=1,
        output_language=OutputLanguage.ENGLISH,
    )
    runs = tmp_path / "runs"
    prompts = tmp_path / "prompts"
    settings = make_settings(generation_retries=0)
    failing = FakeAuthor(spec)
    failing.fail_frame_themes = {"T02"}

    with pytest.raises(RunIncompleteError) as error:
        await PromptStudio(
            failing,
            LocalRunStore(runs, prompts),
            settings,
        ).run(spec, make_rules(spec))

    run_id = error.value.run_id
    assert not list(prompts.rglob("*.txt"))
    assert len(list((runs / run_id / "themes").glob("*.json"))) == 3
    assert len(list((runs / run_id / "frames").glob("*.json"))) == 4

    resumed_author = FakeAuthor(spec)
    result = await PromptStudio(
        resumed_author,
        LocalRunStore(runs, tmp_path / "ignored-prompts"),
        settings,
    ).resume(run_id)

    assert [stage for stage, _, _ in resumed_author.calls] == [
        GenerationStage.FRAMES
    ]
    assert Path(result.prompt_file).parent == prompts / "aesthetic"
    assert len(result.result.prompts) == 6
    assert "Theme:" in result.result.prompts[0].text


@pytest.mark.asyncio
async def test_completed_resume_is_idempotent() -> None:
    spec = make_spec()
    store = InMemoryRunStore()
    first_author = FakeAuthor(spec)
    first = await PromptStudio(
        first_author,
        store,
        make_settings(),
    ).run(spec, make_rules(spec))
    second_author = FakeAuthor(spec)

    second = await PromptStudio(
        second_author,
        store,
        make_settings(),
    ).resume(first.run_id)

    assert second.prompt_file == first.prompt_file
    assert first.prompt_file == (
        "memory://prompts/aesthetic/quiet_cafe_conversation_0001.txt"
    )
    assert second_author.calls == []


@pytest.mark.asyncio
async def test_truncation_retry_escalates_to_hard_cap() -> None:
    spec = make_spec()
    author = FakeAuthor(spec)
    author.truncate_foundation_once = True
    settings = make_settings(output_token_limit=12000)

    await PromptStudio(
        author,
        InMemoryRunStore(),
        settings,
    ).run(spec, make_rules(spec))

    foundation_budgets = [
        tokens
        for stage, _, tokens in author.calls
        if stage == GenerationStage.FOUNDATION
    ]
    assert foundation_budgets == [1536, 12000]


@pytest.mark.asyncio
async def test_resume_rejects_a_different_provider_signature() -> None:
    spec = make_spec()
    store = InMemoryRunStore()
    snapshot = store.create(spec, make_settings(), make_rules(spec))

    with pytest.raises(ConfigurationError, match="不一致"):
        await PromptStudio(
            FakeAuthor(spec),
            store,
            make_settings(provider_signature="another-provider"),
        ).resume(snapshot.run_id)
    assert store.inspect(snapshot.run_id).manifest.status == RunStatus.RUNNING
