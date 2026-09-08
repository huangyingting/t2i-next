from __future__ import annotations

import json

import pytest

from t2i_story_pipeline.models import ContentLevel
from t2i_story_pipeline.prompts import frame_messages, theme_messages
from tests.story_factories import make_story_request, make_theme


def test_theme_prompt_requests_distinct_coherent_story_concepts() -> None:
    request = make_story_request(theme_count=100, frames_per_theme=6)
    messages = theme_messages(
        request,
        start_index=1,
        count=10,
        existing_themes=[],
    )
    prompt = messages[0].content
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert payload["batch_count"] == 10
    assert payload["content_level"] == "aesthetic"
    assert "premise 最多两句" in prompt
    assert "不写具体姿态、绳路、器具" in prompt
    assert "把这些留给各个 frame 独立发挥" in prompt
    assert "人物关系、场景用途、决定或冲突上真正不同" in prompt


def test_frame_prompt_prioritizes_coherent_standalone_prose() -> None:
    request = make_story_request(frames_per_theme=6)
    messages = frame_messages(request, make_theme())
    prompt = messages[0].content
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert payload["theme"]["theme_id"] == "T001"
    assert payload["frame_ids"] == [
        "F01",
        "F02",
        "F03",
        "F04",
        "F05",
        "F06",
    ]
    assert "整体叙事的自然、通顺和画面成立优先于逐项填表" in prompt
    assert "把每帧当作这组图片中唯一存在的一张来写" in prompt
    assert "每帧重新完整描写所有可见人物" in prompt
    assert "只写当前可见状态和直接物理结果" in prompt
    assert "镜头与光线必须明确而专业" in prompt
    assert "每一帧都直接呈现已经完成、可被拍摄的核心造型" in prompt
    assert "整段不得夹入英文" in prompt
    assert "平行画面方案，不是一件事按时间先后展开的镜头序列" in prompt
    assert "篇幅由人物数量和画面复杂度决定" in prompt
    assert "严格依次写六部分" not in prompt
    assert "因玉扣遗失" not in prompt
    assert "必须精确以“此刻，”开头" not in prompt
    assert "倒数第二句必须以“镜头采用”开头" not in prompt
    assert "以下是提交前必须满足的精确质量门" not in prompt


def test_frame_prompt_keeps_adult_consent_safety() -> None:
    prompt = frame_messages(make_story_request(), make_theme())[0].content

    assert "二十一岁以上成年人" in prompt
    assert "清醒、自愿" in prompt


@pytest.mark.parametrize(
    ("level", "required", "excluded"),
    (
        (
            ContentLevel.AESTHETIC,
            "采用美学叙事尺度",
            ("采用成人情色尺度", "采用仅限二十一岁以上成年人的露骨情色尺度"),
        ),
        (
            ContentLevel.EROTIC,
            "采用成人情色尺度",
            ("采用美学叙事尺度", "采用仅限二十一岁以上成年人的露骨情色尺度"),
        ),
        (
            ContentLevel.HARDCORE,
            "采用仅限二十一岁以上成年人的露骨情色尺度",
            ("采用美学叙事尺度", "采用成人情色尺度"),
        ),
    ),
)
def test_prompts_compile_only_selected_content_level(
    level: ContentLevel,
    required: str,
    excluded: tuple[str, str],
) -> None:
    request = make_story_request(content_level=level)

    for messages in (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content
        assert required in prompt
        assert all(item not in prompt for item in excluded)


def test_prompts_express_era_consistency_holistically() -> None:
    request = make_story_request()

    for messages in (
        theme_messages(
            request,
            start_index=1,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content
        assert "建筑、陈设、器物、材料、服装、发型" in prompt
        assert "时代、地域、季节、时辰和社会环境" in prompt
        assert "不确定史实时使用可信的通用描述" in prompt
        assert "穿越、架空或时代错置" in prompt
