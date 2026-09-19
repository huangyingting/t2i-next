from __future__ import annotations

import json

import pytest

from t2i_film_style_pipeline.prompt_messages import frame_messages, theme_messages
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    FilmPromptRuleSet,
    NarrativeFrame,
    NarrativeTheme,
    OutputLanguage,
)
from t2i_film_style_pipeline.rules import resolve_film_style_rules

_REQUIRED_EXPRESSION_GUIDANCE = (
    "当前可见事件、人物关系、当前动作和关注对象",
    "不得用心理独白、不可见的秘密或新编身世解释情绪",
    "至少用眉眼、眼睑、嘴角、嘴唇、下颌、面颊或额头中的两项",
    "面部状态必须共同表现同一个冻结瞬间",
    "同一张嘴同时写成紧闭和张开",
    "同一瞬间凝视两个不同目标",
    "混合情绪或局部不对称",
    "视线落点须在既定头部朝向和眼球自然转向下可达",
    "与编译上下文中已有的作品表现依据一致",
    "不得只凭导演署名推定统一表情",
    "克制不等于面无表情",
    "不得为了远景可读性刻意夸张表情",
    "多人可以共享同一种主要情绪",
    "不得按性别、名单顺序或固定角色模板分配反应",
    "当前批次和 accepted_frame_prose",
    "至少在反应强弱、面部状态组合、关注对象或回应方式中的一项形成可见差异",
    "不强制每帧使用不同情绪标签",
    "不是按时间发展的连续情节",
    "情绪有可见情境依据、面部状态相容且视线可达",
)
_REQUIRED_PARTICIPANT_GUIDANCE = (
    "当前可见事件与人物关系的依据",
    "面部状态相互协调",
    "唯一且自然可达的视线落点",
    "表演幅度符合当前情境与已有作品依据",
    "可共享主要情绪",
    "不得复制其他人物或其他 Frame 的整套表情方案",
    "不得改变已确定的位置、朝向与支点",
)


@pytest.mark.parametrize("level", list(ContentLevel))
@pytest.mark.parametrize("language", list(OutputLanguage))
@pytest.mark.parametrize(
    ("female_count", "male_count"),
    [(1, 0), (0, 1), (1, 1), (2, 2)],
    ids=["female-solo", "male-solo", "pair", "group"],
)
def test_expression_guidance_reaches_theme_frames_and_selective_retry(
    level: ContentLevel,
    language: OutputLanguage,
    female_count: int,
    male_count: int,
) -> None:
    names = ["林岚", "周宁", "陈安", "沈云"][: female_count + male_count]
    characters = [
        f"- {name}：成年{'女性' if index < female_count else '男性'}\n"
        for index, name in enumerate(names)
    ]
    request = FilmPromptRequest(
        context=(
            "原作人物与场景锚点\n### 《图书馆》\n原作成年人物\n"
            + "".join(characters)
            + "原作场景\n- 阅览室：明亮的室内空间\n\n色彩\n自然色彩。"
        ),
        female_count=female_count,
        male_count=male_count,
        content_level=level,
        output_language=language,
        frames_per_theme=2,
    )
    theme = NarrativeTheme(
        theme_id="T001",
        title="查找书中线索",
        premise=f"{'、'.join(names)}在阅览室查找书中的线索。",
        style="自然窗光，清楚的人物轮廓。",
    )
    resolved = resolve_film_style_rules(request)
    rules = FilmPromptRuleSet(themes=resolved.themes, frames=resolved.frames)
    themes = theme_messages(
        request, rules, start_index=1, count=1, existing_themes=[]
    )
    assert (
        "不预先固定每个 Frame 的表情、反应强度或视线落点"
        in themes[0].content
    )
    assert "不把情绪升级写成必须逐帧发展的情节" in themes[0].content

    initial = frame_messages(
        request, theme, rules, requested_frame_ids=["F01", "F02"], accepted_frames=[]
    )
    expressions = (
        (
            "眉间收紧，嘴角平直，视线落在书页的批注上",
            "眼睑舒展，嘴唇微合，视线落在书脊上",
            "眉梢略扬，下颌放松，视线落在桌面地图上",
            "眼角微弯，嘴角轻扬，视线落在对面的同伴脸上",
        )
        if language == OutputLanguage.CHINESE
        else (
            "has drawn brows and a straight mouth, looking at a note in the book",
            "has relaxed eyelids and lightly closed lips, looking at a book spine",
            "has slightly raised brows and a relaxed jaw, looking at the desk map",
            "has soft eye corners and a small smile, looking at the person opposite",
        )
    )
    accepted = NarrativeFrame(
        frame_id="F01",
        prose="; ".join(
            f"{name} {expression}"
            for name, expression in zip(names, expressions, strict=False)
        ),
    )
    retry = frame_messages(
        request,
        theme,
        rules,
        requested_frame_ids=["F02"],
        accepted_frames=[accepted],
    )
    for messages in (initial, retry):
        for requirement in _REQUIRED_EXPRESSION_GUIDANCE:
            assert requirement in messages[0].content
        payload = json.loads(messages[1].content)
        assert payload["output_language"] == language.value
        assert payload["theme_cast_requirement"] == {
            "participant_count": len(names),
            "female_count": female_count,
            "male_count": male_count,
        }
        participants = payload["participant_frame_contracts"]["participants"]
        assert [participant["canonical_name"] for participant in participants] == names
        for participant in participants:
            for requirement in _REQUIRED_PARTICIPANT_GUIDANCE:
                assert requirement in participant["description_requirement"]
    initial_payload = json.loads(initial[1].content)
    retry_payload = json.loads(retry[1].content)
    assert retry[0] == initial[0]
    assert initial_payload["accepted_frame_prose"] == []
    assert initial_payload["requested_frame_slots"] == ["F01", "F02"]
    assert retry_payload["accepted_frame_prose"] == [accepted.prose]
    assert retry_payload["requested_frame_slots"] == ["F02"]
    assert (
        retry_payload["participant_frame_contracts"]["participants"]
        == initial_payload["participant_frame_contracts"]["participants"]
    )
    assert (
        retry_payload["current_frame_diversity_contracts"]
        == initial_payload["current_frame_diversity_contracts"][1:]
    )
