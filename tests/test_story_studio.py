from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

from t2i_story_pipeline.errors import (
    StoryContractError,
    StoryProviderResponseError,
)
from t2i_story_pipeline.models import (
    CreativeIntent,
    NarrativeSequence,
    NarrativeTheme,
    NarrativeThemeBatch,
    OutputLanguage,
    ReviewDimension,
    ReviewIssue,
    StoryStage,
    TokenUsage,
)
from t2i_story_pipeline.provider import ModelResponse
from t2i_story_pipeline.studio import StoryStudio
from tests.story_factories import (
    make_narrative_review,
    make_narrative_sequence,
    make_narrative_theme_batch,
    make_story_blueprint,
    make_story_request,
)


class FakeStoryModel:
    def __init__(self, values: Iterable[object]) -> None:
        self._values = iter(values)
        self.stages: list[StoryStage] = []
        self.messages = []
        self.output_budgets: list[int] = []
        self.response_models = []

    async def generate(
        self,
        *,
        stage,
        messages,
        response_model,
        max_output_tokens,
    ) -> ModelResponse:
        self.stages.append(stage)
        self.messages.append(messages)
        self.output_budgets.append(max_output_tokens)
        self.response_models.append(response_model)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        return ModelResponse(
            value=value,
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )


@pytest.mark.asyncio
async def test_studio_generates_six_frames_from_one_creative_theme() -> None:
    theme = NarrativeTheme(
        theme_id="T001",
        title="汇合的轨道",
        creative_intent=CreativeIntent(
            emotional_core="迟来的信任恢复",
            narrative_tension="即将离站的列车与终于停下来的旧友",
            decisive_moment="两只手同时握住旧皮箱提手",
            visual_motif="分离的铁轨与汇合的手",
            motif_progression="铁轨从分隔人物转为引向共同握住的皮箱",
            restraint="舍弃无关旅客与装饰性雨伞",
        ),
    )
    sequence = make_narrative_sequence(
        frame_count=6,
        theme=theme,
    )
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            NarrativeThemeBatch(themes=[theme]),
            sequence,
            make_narrative_review(passing=True, frame_count=6),
        ]
    )

    result = await StoryStudio(model).generate(
        make_story_request(theme_count=1, frames_per_theme=6)
    )

    assert result.themes[0].theme == theme
    assert len(result.themes[0].narratives) == 6
    assert "汇合的手" in result.themes[0].theme.creative_intent.visual_motif


@pytest.mark.asyncio
async def test_studio_allocates_full_budget_to_ten_dimension_review() -> None:
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            make_narrative_sequence(),
            make_narrative_review(passing=True),
        ]
    )

    await StoryStudio(model, generation_retries=0).generate(
        make_story_request()
    )

    review_index = model.stages.index(StoryStage.REVIEW)
    assert model.output_budgets[review_index] == 16000


@pytest.mark.asyncio
async def test_studio_reviews_sequence_without_render_duplicates() -> None:
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            make_narrative_sequence(),
            make_narrative_review(passing=True),
        ]
    )

    await StoryStudio(model).generate(make_story_request())

    review_index = model.stages.index(StoryStage.REVIEW)
    review_payload = json.loads(model.messages[review_index][1].content)
    assert "narrative_sequence" in review_payload
    assert "rendered_narratives" not in review_payload


@pytest.mark.asyncio
async def test_studio_requests_exact_theme_and_frame_collection_sizes() -> None:
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            make_narrative_sequence(),
            make_narrative_review(passing=True),
        ]
    )

    await StoryStudio(model, generation_retries=0).generate(
        make_story_request()
    )

    theme_index = model.stages.index(StoryStage.THEMES)
    scene_index = model.stages.index(StoryStage.SCENES)
    theme_schema = model.response_models[theme_index].model_json_schema()
    scene_schema = model.response_models[scene_index].model_json_schema()
    assert theme_schema["properties"]["themes"]["minItems"] == 1
    assert theme_schema["properties"]["themes"]["maxItems"] == 1
    assert scene_schema["properties"]["scenes"]["minItems"] == 2
    assert scene_schema["properties"]["scenes"]["maxItems"] == 2


@pytest.mark.asyncio
async def test_studio_generates_one_hundred_themes_with_six_frames_each() -> None:
    values: list[object] = [make_story_blueprint()]
    values.extend(
        make_narrative_theme_batch(start=start, count=10) for start in range(1, 101, 10)
    )
    for index in range(1, 101):
        theme = make_narrative_theme_batch(
            start=index,
            count=1,
        ).themes[0]
        values.extend(
            (
                make_narrative_sequence(
                    frame_count=6,
                    theme=theme,
                ),
                make_narrative_review(passing=True, frame_count=6),
            )
        )
    model = FakeStoryModel(values)

    result = await StoryStudio(model).generate(
        make_story_request(theme_count=100, frames_per_theme=6)
    )

    assert len(result.themes) == 100
    assert sum(len(theme.narratives) for theme in result.themes) == 600
    assert result.themes[0].theme.theme_id == "T001"
    assert result.themes[-1].theme.theme_id == "T100"
    assert model.stages.count(StoryStage.THEMES) == 10
    assert model.stages.count(StoryStage.SCENES) == 100
    assert model.stages.count(StoryStage.REVIEW) == 100


@pytest.mark.asyncio
async def test_studio_rejects_theme_variations_that_only_add_numbers() -> None:
    first = make_narrative_theme_batch(start=1, count=1).themes[0]
    second = first.model_copy(deep=True)
    second.theme_id = "T002"
    second.title += " 2"
    second.creative_intent.decisive_moment += " 2"
    second.creative_intent.visual_motif += " 2"
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            NarrativeThemeBatch(themes=[first, second]),
        ]
    )

    with pytest.raises(StoryContractError, match="实质不同"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request(theme_count=2, frames_per_theme=6)
        )


@pytest.mark.asyncio
async def test_studio_rejects_duplicate_frame_sequences_across_themes() -> None:
    first_theme = make_narrative_theme_batch(start=1, count=1).themes[0]
    repeated_sequence = make_narrative_sequence(
        frame_count=6,
        theme=first_theme,
    )
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(start=1, count=2),
            repeated_sequence,
            make_narrative_review(passing=True, frame_count=6),
            repeated_sequence,
            make_narrative_review(passing=True, frame_count=6),
        ]
    )

    with pytest.raises(StoryContractError, match="画面序列必须实质不同"):
        await StoryStudio(model).generate(
            make_story_request(theme_count=2, frames_per_theme=6)
        )


@pytest.mark.asyncio
async def test_studio_rejects_repeated_frames_within_one_theme() -> None:
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            make_narrative_sequence(frame_count=6),
        ]
    )

    with pytest.raises(StoryContractError, match="每个画面必须实质不同"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request(theme_count=1, frames_per_theme=6)
        )


@pytest.mark.asyncio
async def test_studio_renders_english_prompt_labels_when_requested() -> None:
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            make_narrative_sequence(),
            make_narrative_review(passing=True),
        ]
    )

    result = await StoryStudio(model).generate(
        make_story_request(output_language=OutputLanguage.ENGLISH)
    )

    narratives = result.themes[0].narratives
    assert narratives[0].prompt.startswith("Creative direction:")
    assert "Interaction and action:" in narratives[0].prompt
    assert "时间与地点：" not in narratives[0].prompt


@pytest.mark.asyncio
async def test_studio_replaces_machine_ids_used_as_display_names() -> None:
    blueprint = make_story_blueprint()
    blueprint.characters[0].display_name = "王强"
    blueprint.characters[1].display_name = "Alice"
    sequence = make_narrative_sequence()
    sequence.scenes[0].character_entry = "C01从站牌旁走向C02。"
    model = FakeStoryModel(
        [
            blueprint,
            make_narrative_theme_batch(),
            sequence,
            make_narrative_review(passing=True),
        ]
    )

    result = await StoryStudio(model).generate(make_story_request())

    prose = result.themes[0].narratives[0].prose
    assert "C01" not in prose
    assert "C02" not in prose
    assert "人物一" in prose
    assert "人物二" in prose


@pytest.mark.asyncio
async def test_studio_rejects_blueprint_actions_without_source_evidence() -> None:
    blueprint = make_story_blueprint()
    blueprint.beats[1].source_action = "陈川把早已找到的皮箱交还给林岚"
    model = FakeStoryModel([blueprint])

    with pytest.raises(StoryContractError, match="没有故事原文依据"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request()
        )


@pytest.mark.asyncio
async def test_studio_rejects_gender_invented_for_unspecified_people() -> None:
    blueprint = make_story_blueprint()
    blueprint.characters[0].appearance = "三十余岁的成年男子"
    model = FakeStoryModel([blueprint])

    with pytest.raises(StoryContractError, match="原文未提供的性别"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request()
        )


@pytest.mark.asyncio
async def test_studio_rejects_invented_identity_mark_in_theme() -> None:
    batch = make_narrative_theme_batch()
    batch.themes[0].creative_intent.decisive_moment = "人物露出旧疤确认身份"
    model = FakeStoryModel([make_story_blueprint(), batch])

    with pytest.raises(StoryContractError, match="未提供的身份标记"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request()
        )


@pytest.mark.asyncio
async def test_studio_rejects_scene_backstory_without_source_evidence() -> None:
    sequence = make_narrative_sequence()
    sequence.scenes[0].source_context = ["两人履行十年前的秘密约定"]
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            sequence,
        ]
    )

    with pytest.raises(StoryContractError, match="来源片段没有故事原文依据"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request()
        )


@pytest.mark.asyncio
async def test_studio_rejects_unrequested_english_in_chinese_scene() -> None:
    sequence = make_narrative_sequence()
    sequence.scenes[0].environmental_evidence = ["长椅有 rats 啃咬痕迹。"]
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            sequence,
        ]
    )

    with pytest.raises(StoryContractError, match="混入原文未提供的英文"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request()
        )


@pytest.mark.asyncio
async def test_studio_retries_interpretation_with_contract_feedback() -> None:
    invalid_blueprint = make_story_blueprint()
    invalid_blueprint.beats[0].source_action = "两人履行秘密约定"
    model = FakeStoryModel(
        [
            invalid_blueprint,
            make_story_blueprint(),
            make_narrative_theme_batch(),
            make_narrative_sequence(),
            make_narrative_review(passing=True),
        ]
    )

    result = await StoryStudio(model).generate(make_story_request())

    assert len(result.themes) == 1
    assert model.stages[:2] == [StoryStage.INTERPRET, StoryStage.INTERPRET]
    assert "没有故事原文依据" in model.messages[1][-1].content


@pytest.mark.asyncio
async def test_studio_retries_provider_schema_failure_for_scenes() -> None:
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            StoryProviderResponseError(
                "场景内容必须能够直接成像",
                usage=TokenUsage(
                    prompt_tokens=20,
                    completion_tokens=10,
                    total_tokens=30,
                ),
            ),
            make_narrative_sequence(),
            make_narrative_review(passing=True),
        ]
    )

    result = await StoryStudio(model).generate(make_story_request())

    assert len(result.themes[0].narratives) == 2
    assert model.stages.count(StoryStage.SCENES) == 2
    second_scene_call = model.stages.index(StoryStage.SCENES) + 1
    assert "必须能够直接成像" in model.messages[second_scene_call][-1].content
    assert result.usage.total_tokens == 90


@pytest.mark.asyncio
async def test_studio_revises_narrative_from_typed_review_feedback() -> None:
    initial = make_narrative_sequence()
    initial.scenes[0].present_actions[0].visible_response = "皮箱没有立即移动。"
    revised = initial.model_copy(deep=True)
    revised.scenes[0].present_actions[
        0
    ].visible_response = "车轮轻晃，积水沿铁轨荡开细小波纹。"
    revised = NarrativeSequence(scenes=[revised.scenes[0]])
    passing_rereview = make_narrative_review(passing=True)
    passing_rereview.scene_reviews = passing_rereview.scene_reviews[:1]
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            initial,
            make_narrative_review(passing=False),
            revised,
            passing_rereview,
        ]
    )

    result = await StoryStudio(model, max_revisions=2).generate(make_story_request())

    assert model.stages == [
        StoryStage.INTERPRET,
        StoryStage.THEMES,
        StoryStage.SCENES,
        StoryStage.REVIEW,
        StoryStage.REVISE,
        StoryStage.REVIEW,
    ]
    theme_result = result.themes[0]
    assert theme_result.revision_count == 1
    assert len(theme_result.reviews) == 2
    assert "积水沿铁轨荡开细小波纹" in theme_result.narratives[0].prose
    revise_index = model.stages.index(StoryStage.REVISE)
    assert "补充行李车晃动和积水波纹" in (model.messages[revise_index][1].content)


@pytest.mark.asyncio
async def test_studio_revises_and_rereviews_only_failed_scenes() -> None:
    initial = make_narrative_sequence()
    initial.scenes[0].present_actions[0].visible_response = "皮箱没有立即移动。"
    revised_scene = initial.scenes[0].model_copy(deep=True)
    revised_scene.present_actions[
        0
    ].visible_response = "车轮轻晃，积水沿铁轨荡开细小波纹。"
    revised = NarrativeSequence(scenes=[revised_scene])
    passing_rereview = make_narrative_review(passing=True)
    passing_rereview.scene_reviews = passing_rereview.scene_reviews[:1]
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            initial,
            make_narrative_review(passing=False),
            revised,
            passing_rereview,
        ]
    )

    result = await StoryStudio(model).generate(make_story_request())

    final = result.themes[0]
    assert len(final.sequence.scenes) == 2
    assert final.sequence.scenes[1] == initial.scenes[1]
    assert len(final.reviews[1].scene_reviews) == 2
    revise_index = model.stages.index(StoryStage.REVISE)
    revise_payload = json.loads(model.messages[revise_index][1].content)
    assert len(revise_payload["current_sequence"]["scenes"]) == 1
    second_review_index = len(model.stages) - 1
    rereview_payload = json.loads(model.messages[second_review_index][1].content)
    assert len(rereview_payload["narrative_sequence"]["scenes"]) == 1


@pytest.mark.asyncio
async def test_studio_revises_frames_from_creative_unity_feedback() -> None:
    initial = make_narrative_sequence()
    revised = initial.model_copy(deep=True)
    revised.scenes[
        0
    ].lighting_and_color = "站灯沿铁轨形成两条分离光带，在共同握住的提手处汇合。"
    revised = NarrativeSequence(scenes=[revised.scenes[0]])
    failing_review = make_narrative_review(passing=True)
    failing_review.scene_reviews[0].scores.creative_unity = 2
    failing_review.scene_reviews[0].issues = [
        ReviewIssue(
            scene_id="S01",
            dimension=ReviewDimension.CREATIVE_UNITY,
            problem="光线没有服务分离铁轨与汇合双手的视觉母题。",
            required_change="让两条分离光带在共同握住的提手处汇合。",
        )
    ]
    passing_rereview = make_narrative_review(passing=True)
    passing_rereview.scene_reviews = passing_rereview.scene_reviews[:1]
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            initial,
            failing_review,
            revised,
            passing_rereview,
        ]
    )

    result = await StoryStudio(model).generate(make_story_request())

    assert result.themes[0].revision_count == 1
    assert "两条分离光带" in result.themes[0].narratives[0].prose
    revise_index = model.stages.index(StoryStage.REVISE)
    assert "共同握住的提手处汇合" in model.messages[revise_index][1].content


@pytest.mark.asyncio
async def test_studio_restores_identity_changed_by_revision_model() -> None:
    initial = make_narrative_sequence()
    revised = initial.model_copy(deep=True)
    revised.scenes[0].mode = revised.scenes[1].mode
    revised.scenes[0].beat_id = "B02"
    revised.scenes[0].visible_character_ids = ["C02"]
    revised.scenes[0].present_actions[0].participant_ids = ["C02"]
    revised = NarrativeSequence(scenes=[revised.scenes[0]])
    passing_rereview = make_narrative_review(passing=True)
    passing_rereview.scene_reviews = passing_rereview.scene_reviews[:1]
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            initial,
            make_narrative_review(passing=False),
            revised,
            passing_rereview,
        ]
    )

    result = await StoryStudio(model).generate(make_story_request())

    final_scene = result.themes[0].sequence.scenes[0]
    assert final_scene.mode == initial.scenes[0].mode
    assert final_scene.beat_id == initial.scenes[0].beat_id
    assert final_scene.visible_character_ids == ["C01", "C02"]
    assert final_scene.present_actions[0].participant_ids == ["C01", "C02"]


@pytest.mark.asyncio
async def test_studio_fails_closed_when_revision_budget_is_exhausted() -> None:
    sequence = make_narrative_sequence()
    revision = NarrativeSequence(scenes=[sequence.scenes[0]])
    failing_rereview = make_narrative_review(passing=False)
    failing_rereview.scene_reviews = failing_rereview.scene_reviews[:1]
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            sequence,
            make_narrative_review(passing=False),
            revision,
            failing_rereview,
        ]
    )

    with pytest.raises(StoryContractError, match="修订次数已耗尽"):
        await StoryStudio(model, max_revisions=1).generate(make_story_request())


@pytest.mark.asyncio
async def test_studio_returns_cinematic_prose_and_image_prompts() -> None:
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            make_narrative_sequence(),
            make_narrative_review(passing=True),
        ]
    )

    result = await StoryStudio(model).generate(make_story_request())

    narratives = result.themes[0].narratives
    assert [item.scene_id for item in narratives] == ["S01", "S02"]
    assert narratives[0].prose.startswith("1930年代秋夜")
    assert "时间与地点：" not in narratives[0].prose
    assert "互动与动作：" in narratives[0].prompt


@pytest.mark.asyncio
async def test_studio_rejects_wrong_frame_count() -> None:
    sequence = make_narrative_sequence()
    sequence.scenes.pop()
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            sequence,
        ]
    )

    with pytest.raises(StoryContractError, match="场景数量或顺序"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request(frames_per_theme=2)
        )


@pytest.mark.asyncio
async def test_studio_rejects_unknown_shot_character() -> None:
    sequence = make_narrative_sequence()
    sequence.scenes[0].visible_character_ids = ["C99"]
    model = FakeStoryModel(
        [
            make_story_blueprint(),
            make_narrative_theme_batch(),
            sequence,
        ]
    )

    with pytest.raises(StoryContractError, match="引用未知人物"):
        await StoryStudio(model, generation_retries=0).generate(
            make_story_request()
        )
