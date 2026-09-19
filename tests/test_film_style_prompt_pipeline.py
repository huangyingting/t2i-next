from __future__ import annotations

import asyncio
import json
from collections import Counter

import pytest

from t2i_film_style_pipeline.compiler import frame_source_sentence
from t2i_film_style_pipeline.diversity import (
    normalize_frame_anchor_prefix,
    normalize_theme_anchor_terms,
)
from t2i_film_style_pipeline.errors import (
    FilmStyleProviderError,
    FilmStyleRunIncompleteError,
)
from t2i_film_style_pipeline.models import FilmCastSource, FilmWorkReference
from t2i_film_style_pipeline.models import TokenUsage as FilmTokenUsage
from t2i_film_style_pipeline.pipeline import (
    FilmStylePipelineSettings,
    FilmStylePromptRequest,
    FilmStylePromptStudio,
    FilmStyleRunStatus,
    LocalFilmStyleRunStore,
)
from t2i_film_style_pipeline.prompt_messages import (
    frame_messages,
    theme_messages,
)
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    FilmPromptRuleSet,
    FilmPromptStage,
    NarrativeFrameSequence,
    NarrativeThemeBatch,
    NarrativeThemeDraftBatch,
    SelectedFilmCharacter,
    TokenUsage,
)
from t2i_film_style_pipeline.prompt_provider import (
    FilmPromptProviderSettings,
    TextModelResponse,
)
from t2i_film_style_pipeline.prompt_provider import (
    ModelResponse as PromptModelResponse,
)
from t2i_film_style_pipeline.prompt_run_store import (
    FilmPromptRunSettings,
    LocalFilmPromptRunStore,
    ThemeOutputMode,
)
from t2i_film_style_pipeline.provider import (
    FilmStyleProviderSettings,
)
from t2i_film_style_pipeline.provider import (
    ModelResponse as FilmModelResponse,
)
from t2i_film_style_pipeline.rules import resolve_film_style_rules
from tests.film_prompt_factories import make_frame_sequence, make_theme_batch
from tests.test_film_style_pipeline import make_profile, make_request


def custom_source_films(
    names: list[str], scenes: list[str]
) -> tuple[FilmCastSource, ...]:
    anchors = make_profile().work_anchors[0]
    return (
        FilmCastSource(
            work=FilmWorkReference(title="测试作品"),
            anchors=anchors.model_copy(update={
                "adult_characters": tuple(
                    anchors.adult_characters[0].model_copy(update={
                        "canonical_name": name,
                        "gender": "female" if index % 2 == 0 else "male",
                    })
                    for index, name in enumerate(names)
                ),
                "scenes": tuple(
                    anchors.scenes[0].model_copy(update={"canonical_name": name})
                    for name in scenes
                ),
            }),
        ),
    )


def custom_selected_cast(names: list[str]) -> tuple[SelectedFilmCharacter, ...]:
    return tuple(
        SelectedFilmCharacter(
            canonical_name=name,
            gender="female" if index % 2 == 0 else "male",
        )
        for index, name in enumerate(names)
    )


class FakeFilmModel:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        return FilmModelResponse(
            value=make_profile(),
            usage=FilmTokenUsage(total_tokens=20),
        )


class FakePromptModel:
    def __init__(self, values: list[object]) -> None:
        self._values = iter(values)
        self.stages: list[FilmPromptStage] = []
        self.messages = []

    async def generate(
        self,
        *,
        stage,
        messages,
        response_model,
        max_output_tokens,
    ):
        self.stages.append(stage)
        self.messages.append(messages)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        if (
            isinstance(value, NarrativeThemeBatch)
            and issubclass(response_model, NarrativeThemeDraftBatch)
        ):
            value = response_model.model_validate(
                {
                    "semantic_name": value.semantic_name,
                    "themes": [
                        theme.model_dump(exclude={"theme_id"})
                        for theme in value.themes
                    ],
                }
            )
        return PromptModelResponse(
            value=value,
            usage=TokenUsage(total_tokens=10),
        )

    async def generate_text(
        self,
        *,
        stage,
        messages,
        max_output_tokens,
    ) -> TextModelResponse:
        self.stages.append(stage)
        self.messages.append(messages)
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        if not isinstance(value, str):
            raise TypeError("fake text response must be a string")
        return TextModelResponse(
            text=value,
            usage=TokenUsage(total_tokens=10),
        )


def frame_batch_text(sequence: NarrativeFrameSequence) -> str:
    return "\n".join(f"<FRAME>{frame.prose}</FRAME>" for frame in sequence.frames)


def make_pipeline_request() -> FilmStylePromptRequest:
    return FilmStylePromptRequest(
        film_style=make_request(),
        theme_count=1,
        frames_per_theme=2,
    )


def make_film_theme_batch():
    batch = make_theme_batch()
    for theme in batch.themes:
        theme.premise = (
            f"原作成年人物无名与飞雪位于秦宫大殿。{theme.premise}"
        )
    return batch


def make_film_frame_sequence() -> NarrativeFrameSequence:
    sequence = make_frame_sequence()
    source_sentence = frame_source_sentence(make_request())
    for frame in sequence.frames:
        frame.prose = (
            f"{source_sentence}战国秦宫大殿的雨夜，原作成年人物无名与飞雪"
            "站在深远中轴两侧，黑色殿柱与石质地面向后延伸，长剑横放在"
            "两人之间；无名穿深色战国长袍与黑色束冠，飞雪穿单色交领长袍"
            "与宽大衣袖。两人在庭院灯下"
            "相互注视，前景帘幕与背景砖墙建立纵深。摄影机机位设在两人"
            "正面约三米处，以眼平高度和轻微三分之二侧前角度平视，使用"
            "五十毫米标准镜头拍摄中景，自然透视保持人物与庭院尺度，"
            "主焦点落在成熟面容和相触的手部，前景帘幕略微柔化形成框景，"
            "背景砖墙在中等景深内仍清晰可辨。暖灯和冷雨形成清楚反差。"
            "灰砖、旧木和粗布分别"
            "吸收来自左侧的暖色灯光，右后方冷色天光沿人物肩线形成清楚轮廓，"
            "两人都以稳固站姿承担自身重量，手臂保持自然放松，视线持续回应，"
            "门洞、廊柱与后窗组成三层空间，焦点落在成熟面容和相触的手部，"
            "背景纹理仍然可辨。低饱和灰黑环境只以深红"
            "灯笼形成色彩重音，潮湿地面留下有限反光，细密颗粒和柔和高光"
            "保持真实、克制、自然可信且可以直接摄影执行的长片质感。"
        )
    return sequence


def make_settings(
    *,
    generation_retries: int = 0,
    validate_themes: bool = True,
    validate_frames: bool = True,
    concurrency: int = 1,
    theme_batch_size: int = 1,
) -> FilmStylePipelineSettings:
    return FilmStylePipelineSettings(
        film_provider=FilmStyleProviderSettings(model="test-model"),
        prompt=FilmPromptRunSettings(
            provider=FilmPromptProviderSettings(model="test-model"),
            concurrency=concurrency,
            generation_retries=generation_retries,
            theme_batch_size=theme_batch_size,
            theme_output_mode=ThemeOutputMode.STRUCTURED_WITHOUT_IDS,
        ),
        validate_themes=validate_themes,
        validate_frames=validate_frames,
    )


def test_theme_messages_use_compact_global_diversity_ledger() -> None:
    request = make_pipeline_request().prompt_request(
        "BRIEF\n\nDirector scene context.", make_profile()
    )
    existing = make_theme_batch(start=1, count=2).themes
    existing[0].premise = "甲" * 400
    existing[0].style = "乙" * 400
    resolved_rules = resolve_film_style_rules(request)
    rules = FilmPromptRuleSet(
        themes=resolved_rules.themes,
        frames=resolved_rules.frames,
    )

    payload = json.loads(
        theme_messages(
            request,
            rules,
            start_index=3,
            count=2,
            existing_themes=existing,
            semantic_name="film_run",
            program_assigns_ids=True,
        )[1].content
    )

    assert "existing_themes" not in payload
    assert payload["diversity_ledger"]["used_titles"] == [
        theme.title for theme in existing
    ]
    signatures = payload["diversity_ledger"]["used_theme_signatures"]
    assert [item["theme_id"] for item in signatures] == ["T001", "T002"]
    assert len(signatures[0]["premise_excerpt"]) == 180
    assert len(signatures[0]["style_excerpt"]) == 140
    assert "coverage_counts" in payload["diversity_ledger"]
    assert "source_anchor_mentions" in payload["diversity_ledger"]
    contracts = payload["current_batch_diversity_contracts"]
    assert [contract["output_position"] for contract in contracts] == [1, 2]
    assert all(len(contract["novelty_priorities"]) == 2 for contract in contracts)
    assert all(
        contract["cast_size_requirement"] == "选择一至两名原作成年人"
        for contract in contracts
    )
    assert all(
        {
            "content_route_emphasis",
            "cast_size_requirement",
            "relationship_dynamic",
            "spatial_strategy",
            "camera_strategy",
            "lighting_strategy",
        }
        <= contract.keys()
        for contract in contracts
    )
    assert contracts == json.loads(
        theme_messages(
            request,
            rules,
            start_index=3,
            count=2,
            existing_themes=existing,
            semantic_name="film_run",
            program_assigns_ids=True,
        )[1].content
    )["current_batch_diversity_contracts"]

    all_contracts = [
        contract
        for start_index in range(1, 101, 5)
        for contract in json.loads(
            theme_messages(
                request,
                rules,
                start_index=start_index,
                count=5,
                existing_themes=existing,
                semantic_name="film_run",
                program_assigns_ids=True,
            )[1].content
        )["current_batch_diversity_contracts"]
    ]
    for field in (
        "content_route_emphasis",
        "relationship_dynamic",
        "spatial_strategy",
        "camera_strategy",
        "lighting_strategy",
    ):
        counts = Counter(contract[field] for contract in all_contracts)
        assert max(counts.values()) - min(counts.values()) <= 1


def test_frame_messages_freeze_anchors_and_balance_content_routes() -> None:
    request = FilmPromptRequest(
        frame_source_sentence="这是固定来源句。",
        source_films=custom_source_films(
            ["林岚", "陈默"], ["木构内厅", "河岸长廊"]
        ),
        context=(
            "原作人物与场景锚点\n"
            "- 林岚：成年人物\n"
            "- 陈默：成年人物\n"
            "- 木构内厅：实际场景\n"
            "- 河岸长廊：实际场景\n\n"
            "色彩\n低饱和综合色。"
        ),
        frames_per_theme=5,
        content_level=ContentLevel.HARDCORE,
    )
    theme = make_theme_batch().themes[0].model_copy(
        update={
            "selected_cast": custom_selected_cast(["林岚", "陈默"]),
            "premise": "原作成年人物林岚与陈默位于木构内厅。"
        }
    )
    rules = FilmPromptRuleSet(
        themes=("Theme rule.",),
        frames=("Frame rule.",),
    )
    frame_ids = [f"F{index:02d}" for index in range(1, 6)]

    payload = json.loads(
        frame_messages(
            request,
            theme,
            rules,
            requested_frame_ids=frame_ids,
            accepted_frames=[],
        )[1].content
    )

    assert payload["theme_anchor_contract"] == {
        "source_work_index": 0,
        "selected_cast": [
            {"canonical_name": "林岚", "gender": "female"},
            {"canonical_name": "陈默", "gender": "male"},
        ],
        "required_characters": ["林岚", "陈默"],
        "required_scene": "木构内厅",
        "required_exact_terms": ["林岚", "陈默", "木构内厅"],
        "forbidden_other_anchor_terms_in_body": ["河岸长廊"],
        "deterministic_anchor_sentence": (
            "原作人物林岚、陈默位于原作场景“木构内厅”。"
        ),
    }
    participant_contract = payload["participant_frame_contracts"]
    assert [
        item["canonical_name"]
        for item in participant_contract["participants"]
    ] == ["林岚", "陈默"]
    assert participant_contract["group_frame_contracts"] == []
    contracts = payload["current_frame_diversity_contracts"]
    assert [contract["frame_slot"] for contract in contracts] == frame_ids
    assert len({contract["content_route"] for contract in contracts}) == 1
    assert all(
        contract["required_level_evidence"] == []
        for contract in contracts
    )
    assert all(contract["required_route_evidence"] for contract in contracts)

    retry_payload = json.loads(
        frame_messages(
            request,
            theme,
            rules,
            requested_frame_ids=["F03"],
            accepted_frames=[],
        )[1].content
    )
    assert retry_payload["current_frame_diversity_contracts"][0] == contracts[2]

    routes = {
        json.loads(
            frame_messages(
                request,
                theme.model_copy(update={"theme_id": f"T{index:03d}"}),
                rules,
                requested_frame_ids=["F01"],
                accepted_frames=[],
            )[1].content
        )["current_frame_diversity_contracts"][0]["content_route"]
        for index in range(1, 5)
    }
    assert routes == {
        "明确性行为",
        "器具形成的无插入 BDSM 控制链",
        "命令式开放展示",
        "外部器具或受控自我刺激",
    }


def test_three_person_frame_contract_requires_everyone_to_participate() -> None:
    request = FilmPromptRequest(
        frame_source_sentence="这是固定来源句。",
        source_films=custom_source_films(
            ["林岚", "陈默", "周遥"], ["公寓阳台"]
        ),
        context=(
            "原作人物与场景锚点\n"
            "### 《测试作品》\n"
            "原作成年人物\n"
            "- 林岚：成年女性\n"
            "- 陈默：成年男性\n"
            "- 周遥：成年女性\n"
            "原作场景\n"
            "- 公寓阳台：夜间场景\n\n"
            "色彩\n低饱和综合色。"
        ),
        frames_per_theme=4,
    )
    theme = make_theme_batch().themes[0].model_copy(
        update={
            "selected_cast": custom_selected_cast(["林岚", "陈默", "周遥"]),
            "premise": (
                "林岚、陈默与周遥三名原作成年人位于公寓阳台。"
            )
        }
    )
    payload = json.loads(
        frame_messages(
            request,
            theme,
            FilmPromptRuleSet(
                themes=("Theme rule.",),
                frames=("Frame rule.",),
            ),
            requested_frame_ids=["F01", "F02", "F03", "F04"],
            accepted_frames=[],
        )[1].content
    )

    participant_contract = payload["participant_frame_contracts"]
    assert [
        item["canonical_name"]
        for item in participant_contract["participants"]
    ] == ["林岚", "陈默", "周遥"]
    contracts = participant_contract["group_frame_contracts"]
    assert [contract["frame_slot"] for contract in contracts] == [
        "F01",
        "F02",
        "F03",
        "F04",
    ]
    assert all(
        contract["required_active_participants"]
        == ["林岚", "陈默", "周遥"]
        for contract in contracts
    )
    assert all(contract["participant_count"] == 3 for contract in contracts)
    assert all(
        "core_interaction_pair" not in contract
        and "independent_participants" not in contract
        for contract in contracts
    )

    normalized = normalize_frame_anchor_prefix(
        request,
        theme,
        "这是固定来源句。三人在狭小水泥阳台上纳凉。",
    )
    assert normalized == (
        "这是固定来源句。"
        "原作人物林岚、陈默、周遥位于原作场景“公寓阳台”。"
        "三人在狭小水泥阳台上纳凉。"
    )
    assert (
        normalize_frame_anchor_prefix(request, theme, normalized)
        == normalized
    )
    modified_scene_theme = theme.model_copy(
        update={
            "premise": (
                "林岚、陈默与周遥三名原作成年人位于狭小公寓的水泥阳台。"
            )
        }
    )
    normalized_theme = normalize_theme_anchor_terms(
        request,
        modified_scene_theme,
    )
    assert normalized_theme.premise.endswith("原作场景为“公寓阳台”。")

    hardcore_request = request.model_copy(
        update={"content_level": ContentLevel.HARDCORE}
    )
    hardcore_payload = json.loads(
        frame_messages(
            hardcore_request,
            theme,
            FilmPromptRuleSet(
                themes=("Theme rule.",),
                frames=("Frame rule.",),
            ),
            requested_frame_ids=["F01", "F02", "F03"],
            accepted_frames=[],
        )[1].content
    )
    hardcore_contracts = hardcore_payload["participant_frame_contracts"][
        "group_frame_contracts"
    ]
    assert all(
        contract["hardcore_group_realization"]["participants"]
        == ["林岚", "陈默", "周遥"]
        for contract in hardcore_contracts
    )
    assert all(
        "role_assignment"
        not in contract["hardcore_group_realization"]
        for contract in hardcore_contracts
    )


def test_eight_person_frame_contract_remains_role_agnostic() -> None:
    names = [
        "林岚",
        "陈默",
        "周遥",
        "沈青",
        "许安",
        "赵川",
        "苏明",
        "顾宁",
    ]
    request = FilmPromptRequest(
        frame_source_sentence="这是固定来源句。",
        source_films=custom_source_films(names, ["公寓客厅"]),
        context=(
            "原作人物与场景锚点\n"
            "### 《测试作品》\n"
            "原作成年人物\n"
            + "".join(f"- {name}：成年人物\n" for name in names)
            + "原作场景\n"
            "- 公寓客厅：夜间场景\n\n"
            "色彩\n低饱和综合色。"
        ),
        frames_per_theme=5,
        content_level=ContentLevel.HARDCORE,
    )
    theme = make_theme_batch().themes[0].model_copy(
        update={
            "selected_cast": custom_selected_cast(names),
            "premise": (
                f"{'、'.join(names)}八名原作成年人位于公寓客厅。"
            )
        }
    )
    rules = FilmPromptRuleSet(
        themes=("Theme rule.",),
        frames=("Frame rule.",),
    )
    frame_ids = [f"F{index:02d}" for index in range(1, 6)]
    payload = json.loads(
        frame_messages(
            request,
            theme,
            rules,
            requested_frame_ids=frame_ids,
            accepted_frames=[],
        )[1].content
    )

    participant_contract = payload["participant_frame_contracts"]
    contracts = participant_contract[
        "group_frame_contracts"
    ]
    assert participant_contract["selected_participant_count"] == 8
    assert len(contracts) == 5
    for contract in contracts:
        assert contract["participant_count"] == 8
        assert contract["required_active_participants"] == names
        assert "core_interaction_pair" not in contract
        assert "independent_participants" not in contract
        assert "participant_spatial_assignments" not in contract
        realization = contract["hardcore_group_realization"]
        assert realization["participants"] == names
        assert "role_assignment" not in realization

    retry_payload = json.loads(
        frame_messages(
            request,
            theme,
            rules,
            requested_frame_ids=["F03"],
            accepted_frames=[],
        )[1].content
    )
    assert retry_payload["participant_frame_contracts"][
        "group_frame_contracts"
    ][0] == contracts[2]


@pytest.mark.asyncio
async def test_pipeline_can_disable_all_semantic_validation(tmp_path) -> None:
    request = make_pipeline_request()
    theme_batch = make_film_theme_batch()
    theme_batch.themes[0].premise = (
        "无名与飞雪两名成年人。这是一段不包含场景或内容证据的普通主题描述。"
    )
    sequence = make_film_frame_sequence()
    for index, frame in enumerate(sequence.frames, start=1):
        frame.prose = f"无名与飞雪。第 {index} 个没有来源或摄影证据的未验证画面正文。"
    prompt_model = FakePromptModel(
        [theme_batch, frame_batch_text(sequence)]
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")

    completed = await FilmStylePromptStudio(
        FakeFilmModel(),
        prompt_model,
        store,
        make_settings(
            validate_themes=False,
            validate_frames=False,
        ),
        resolve_film_style_rules(
            request.prompt_request("BRIEF\n\nDirector scene context.", make_profile())
        ),
    ).run(request, prompts_directory=tmp_path / "prompts")

    snapshot = store.inspect(completed.run_id)
    assert completed.prompt_file.exists()
    assert completed.diversity_report_file.exists()
    report = json.loads(completed.diversity_report_file.read_text())
    assert report["theme_count"] == 1
    assert report["frame_count"] == 2
    assert report["unique_theme_titles"] == 1
    assert report["same_theme_frame_similarity"]["pair_count"] == 1
    assert (
        report["content_evidence_complete_frames"]
        + report["content_evidence_incomplete_frames"]
        == 2
    )
    assert (
        report["anchor_complete_frames"]
        + report["anchor_missing_required_frames"]
        >= 2
    )
    assert report["character_anchor_complete_frames"] == 2
    assert report["scene_anchor_complete_frames"] == 0
    assert report["participant_slot_count"] == 4
    assert report["participant_description_complete_slots"] == 0
    assert report["participant_face_complete_slots"] == 0
    assert report["participant_gaze_complete_slots"] == 0
    assert report["participant_support_complete_slots"] == 0
    assert report["clothing_state_conflict_frames"] >= 0
    assert snapshot.settings.validate_themes is False
    assert snapshot.settings.validate_frames is False
    assert prompt_model.stages == [
        FilmPromptStage.THEMES,
        FilmPromptStage.FRAMES,
    ]


@pytest.mark.asyncio
async def test_pipeline_generates_frames_while_next_theme_is_in_flight(
    tmp_path,
) -> None:
    request = FilmStylePromptRequest(
        film_style=make_request(),
        theme_count=4,
        frames_per_theme=1,
    )

    class PipelinedPromptModel:
        def __init__(self) -> None:
            self.theme_calls = 0
            self.active_calls = 0
            self.max_active_calls = 0
            self.second_theme_started = asyncio.Event()
            self.first_frame_started = asyncio.Event()
            self.overlap_recorded = asyncio.Event()
            self.overlap_observed = False

        def _start_call(self) -> None:
            self.active_calls += 1
            self.max_active_calls = max(
                self.max_active_calls,
                self.active_calls,
            )

        def _finish_call(self) -> None:
            self.active_calls -= 1

        async def generate(
            self,
            *,
            stage,
            messages,
            response_model,
            max_output_tokens,
        ):
            assert stage == FilmPromptStage.THEMES
            self._start_call()
            try:
                self.theme_calls += 1
                index = self.theme_calls
                if index == 2:
                    self.second_theme_started.set()
                    await asyncio.wait_for(
                        self.first_frame_started.wait(),
                        timeout=1,
                    )
                    self.overlap_observed = self.active_calls == 2
                    self.overlap_recorded.set()
                start = 1 if index == 1 else 3
                batch = make_theme_batch(start=start, count=2)
                for theme in batch.themes:
                    theme.premise = (
                        f"原作成年人物无名与飞雪位于秦宫大殿。"
                        f"{theme.premise}"
                    )
                value = response_model.model_validate(
                    {
                        "semantic_name": batch.semantic_name,
                        "themes": [
                            theme.model_dump(exclude={"theme_id"})
                            for theme in batch.themes
                        ],
                    }
                )
                return PromptModelResponse(
                    value=value,
                    usage=TokenUsage(total_tokens=10),
                )
            finally:
                self._finish_call()

        async def generate_text(
            self,
            *,
            stage,
            messages,
            max_output_tokens,
        ) -> TextModelResponse:
            assert stage == FilmPromptStage.FRAMES
            self._start_call()
            try:
                await asyncio.wait_for(
                    self.second_theme_started.wait(),
                    timeout=1,
                )
                if not self.first_frame_started.is_set():
                    self.first_frame_started.set()
                    await asyncio.wait_for(
                        self.overlap_recorded.wait(),
                        timeout=1,
                    )
                sequence = make_film_frame_sequence()
                return TextModelResponse(
                    text=frame_batch_text(
                        NarrativeFrameSequence(
                            frames=[sequence.frames[0]]
                        )
                    ),
                    usage=TokenUsage(total_tokens=10),
                )
            finally:
                self._finish_call()

    prompt_model = PipelinedPromptModel()
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    completed = await FilmStylePromptStudio(
        FakeFilmModel(),
        prompt_model,
        store,
        make_settings(
            concurrency=2,
            theme_batch_size=2,
            validate_themes=False,
            validate_frames=False,
        ),
        resolve_film_style_rules(
            request.prompt_request("BRIEF\n\nDirector scene context.", make_profile())
        ),
    ).run(request, prompts_directory=tmp_path / "prompts")

    assert completed.prompt_file.exists()
    assert prompt_model.overlap_observed is True
    assert prompt_model.max_active_calls == 2
    snapshot = LocalFilmPromptRunStore(
        store.prompt_runs_directory(completed.run_id)
    ).inspect(completed.prompt_run_id)
    assert len(snapshot.themes) == 4
    assert set(snapshot.frames) == {"T001", "T002", "T003", "T004"}
    assert all(len(sequence.frames) == 1 for sequence in snapshot.frames.values())


@pytest.mark.asyncio
async def test_pipeline_retries_rejected_film_frame_content(tmp_path) -> None:
    request = make_pipeline_request()
    bad_sequence = make_film_frame_sequence()
    bad_sequence.frames[0].prose = (
        f"{frame_source_sentence(make_request())}抱歉，我无法协助创作这个画面。"
    )
    prompt_model = FakePromptModel(
        [
            make_film_theme_batch(),
            frame_batch_text(bad_sequence),
            frame_batch_text(
                NarrativeFrameSequence(
                    frames=[make_film_frame_sequence().frames[0]]
                )
            ),
        ]
    )

    completed = await FilmStylePromptStudio(
        FakeFilmModel(),
        prompt_model,
        LocalFilmStyleRunStore(tmp_path / "runs"),
        make_settings(generation_retries=1),
        resolve_film_style_rules(
            request.prompt_request("BRIEF\n\nDirector scene context.", make_profile())
        ),
    ).run(request, prompts_directory=tmp_path / "prompts")

    assert completed.prompt_file.exists()
    assert prompt_model.stages == [
        FilmPromptStage.THEMES,
        FilmPromptStage.FRAMES,
        FilmPromptStage.FRAMES,
    ]
    initial_payload = json.loads(prompt_model.messages[1][1].content)
    retry_payload = json.loads(prompt_model.messages[2][1].content)
    assert initial_payload["requested_frame_slots"] == ["F01", "F02"]
    assert initial_payload["accepted_frame_prose"] == []
    assert retry_payload["requested_frame_slots"] == ["F01"]
    source_sentence = frame_source_sentence(make_request())
    anchor_sentence = retry_payload["theme_anchor_contract"][
        "deterministic_anchor_sentence"
    ]
    expected_accepted = make_film_frame_sequence().frames[1].prose.replace(
        source_sentence,
        source_sentence + anchor_sentence,
        1,
    )
    assert retry_payload["accepted_frame_prose"] == [
        expected_accepted
    ]


@pytest.mark.asyncio
async def test_pipeline_resumes_prompt_without_regenerating_profile(tmp_path) -> None:
    request = make_pipeline_request()
    settings = make_settings()
    rules = resolve_film_style_rules(
        request.prompt_request("BRIEF\n\nDirector scene context.", make_profile())
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")
    film_model = FakeFilmModel()
    partial_sequence = make_film_frame_sequence()
    partial_sequence.frames[1].prose = (
        f"{frame_source_sentence(make_request())}抱歉，我无法协助创作这个画面。"
    )
    first_prompt_model = FakePromptModel(
        [make_film_theme_batch(), frame_batch_text(partial_sequence)]
    )
    studio = FilmStylePromptStudio(
        film_model,
        first_prompt_model,
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
    assert failed.manifest.prompt_run_id is not None
    assert film_model.calls == 1
    prompt_run = next(
        (tmp_path / "runs" / run_id / "prompt-runs").iterdir()
    )
    assert (prompt_run / "frames/T001/F01.json").is_file()
    assert not (prompt_run / "frames/T001/F02.json").exists()

    resumed_sequence = make_film_frame_sequence()
    resumed_prompt_model = FakePromptModel(
        [
            frame_batch_text(
                NarrativeFrameSequence(frames=[resumed_sequence.frames[1]])
            )
        ]
    )
    completed = await FilmStylePromptStudio(
        film_model,
        resumed_prompt_model,
        store,
        settings,
        rules,
    ).resume(run_id)

    assert completed.run_id == run_id
    assert completed.prompt_file.exists()
    assert completed.prompt_file.name == "张艺谋_0001.txt"
    assert completed.compiled_context_file.name == "compiled-context.txt"
    assert completed.compiled_context_file.is_file()
    assert film_model.calls == 1
    assert resumed_prompt_model.stages == [
        FilmPromptStage.FRAMES,
    ]
    resumed_payload = json.loads(resumed_prompt_model.messages[0][1].content)
    assert resumed_payload["requested_frame_slots"] == ["F02"]
    source_sentence = frame_source_sentence(make_request())
    anchor_sentence = resumed_payload["theme_anchor_contract"][
        "deterministic_anchor_sentence"
    ]
    expected_accepted = resumed_sequence.frames[0].prose.replace(
        source_sentence,
        source_sentence + anchor_sentence,
        1,
    )
    assert resumed_payload["accepted_frame_prose"] == [
        expected_accepted
    ]
    assert store.inspect(run_id).manifest.status == FilmStyleRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_pipeline_can_resume_after_profile_provider_failure(tmp_path) -> None:
    request = make_pipeline_request()
    settings = make_settings()
    rules = resolve_film_style_rules(
        request.prompt_request("BRIEF\n\nDirector scene context.", make_profile())
    )
    store = LocalFilmStyleRunStore(tmp_path / "runs")

    class FailingFilmModel:
        async def generate(self, **_kwargs):
            raise FilmStyleProviderError("temporary profile failure")

    with pytest.raises(FilmStyleRunIncompleteError) as caught:
        await FilmStylePromptStudio(
            FailingFilmModel(),
            FakePromptModel([]),
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
        FakePromptModel(
            [
                make_film_theme_batch(),
                frame_batch_text(make_film_frame_sequence()),
            ]
        ),
        store,
        settings,
        rules,
    ).resume(run_id)

    assert completed.run_id == run_id
    assert completed.prompt_file.exists()
    assert store.inspect(run_id).manifest.status == FilmStyleRunStatus.COMPLETED
