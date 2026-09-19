from __future__ import annotations

import json

import pytest

from t2i_film_style_pipeline.prompt_messages import frame_messages
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    FilmPromptRuleSet,
    NarrativeTheme,
    OutputLanguage,
)
from t2i_film_style_pipeline.rules import resolve_film_style_rules

_REQUIRED_PHYSICAL_GUIDANCE = (
    "单脚主要承重、另一脚轻触",
    "手掌撑住桌沿，同时手指抓紧同一处桌沿可以成立",
    "同一只手不能既撑桌又伸到另一处拿杯",
    "同一人物、解剖侧、接触部位与空间位置",
    "发力与受力方向须相互对应",
    "高度差和距离必须在既定姿态及自然关节活动范围内可达",
    "不得靠未写出的转身、迈步、伸长肢体或反向关节补足",
    "进入路径必须物理可达，但不要求从镜头全程可见",
    "不得为了展示接触面而挪开承重物、穿透身体或增加肢体",
    "位置、朝向、支点和肢体用途在正文中集中说明一次",
    "后续摄影、表情和材质描写只能补充",
    "必须同步修正相关人物与物体的描述",
    "指定人数、人物身份和当前内容等级要求保持不变",
    "依次保证支撑与关节合理、接触可达、摄影与自然遮挡协调",
    "不得靠减少人物、暗中增加支点、强扭关节或凭空增加肢体补救",
)
_SUPERSEDED_PHYSICAL_GUIDANCE = (
    "每条可见肢体的唯一职责",
    "每条可见手臂和腿分配一个且仅一个作用",
    "每条肢体只有一个职责",
    "站姿由双脚和地面承重",
    "显示所有决定性接触点",
    "必须具有可见的进入路径",
    "requested_cast_counts",
)


@pytest.mark.parametrize("level", list(ContentLevel))
@pytest.mark.parametrize("language", list(OutputLanguage))
@pytest.mark.parametrize("cast_size", [1, 2, 4])
def test_frame_payload_and_rules_agree_on_physical_consistency(
    level, language, cast_size
):
    names = ["林岚", "周宁", "陈安", "沈云"][:cast_size]
    request = FilmPromptRequest(
        context=(
            "原作人物与场景锚点\n### 《图书馆》\n原作成年人物\n"
            + "".join(f"- {name}：成年女性\n" for name in names)
            + "原作场景\n- 阅览室：明亮的室内空间\n\n色彩\n自然色彩。"
        ),
        female_count=cast_size,
        male_count=0,
        content_level=level,
        output_language=language,
        frames_per_theme=2,
    )
    theme = NarrativeTheme(
        theme_id="T001",
        title="午后阅读",
        premise=f"{'、'.join(names)}在阅览室阅读。",
        style="自然窗光，清楚的人物轮廓。",
    )
    resolved = resolve_film_style_rules(request)
    rules = FilmPromptRuleSet(themes=resolved.themes, frames=resolved.frames)
    messages = frame_messages(
        request, theme, rules, requested_frame_ids=["F01", "F02"], accepted_frames=[]
    )
    payload = json.loads(messages[1].content)
    for requirement in _REQUIRED_PHYSICAL_GUIDANCE:
        assert requirement in messages[0].content
    for requirement in _SUPERSEDED_PHYSICAL_GUIDANCE:
        assert requirement not in messages[0].content
        assert requirement not in messages[1].content
    assert payload["theme_cast_requirement"] == {
        "participant_count": cast_size,
        "female_count": cast_size,
        "male_count": 0,
    }
    contracts = payload["participant_frame_contracts"]
    assert [p["canonical_name"] for p in contracts["participants"]] == names
    for participant in contracts["participants"]:
        description = participant["description_requirement"]
        assert "前后一致且相互兼容的肢体用途" in description
        assert "不得改变已确定的位置、朝向与支点" in description
    groups = contracts["group_frame_contracts"]
    if cast_size < 3:
        assert not groups
    else:
        assert len(groups) == 2
        for group in groups:
            assert group["required_active_participants"] == names
            assert "相互对应的受力方向" in group["topology_safety_requirement"]
            assert "距离和高度差" in group["topology_safety_requirement"]
            assert (
                "保留指定人数、身份和内容等级要求"
                in group["topology_safety_requirement"]
            )
            assert "允许接触面自然遮挡" in group["spatial_requirement"]
            assert "不要求全部支撑面毫无遮挡" in group["spatial_requirement"]
            assert "先调整机位" in group["camera_requirement"]
            assert "挪开承重物" in group["camera_requirement"]
    retry = json.loads(
        frame_messages(
            request, theme, rules, requested_frame_ids=["F02"], accepted_frames=[]
        )[1].content
    )
    assert (
        retry["participant_frame_contracts"]["participants"]
        == contracts["participants"]
    )
    assert retry["participant_frame_contracts"]["group_frame_contracts"] == groups[1:]
