from __future__ import annotations

import json

import pytest

from t2i_story_pipeline.models import ContentLevel, OutputLanguage
from t2i_story_pipeline.prompts import (
    ACTION_CHAIN_MARKERS,
    EROTIC_VISIBLE_MARKERS,
    EROTIC_VISIBLE_MARKERS_EN,
    FRAME_TRANSITION_MARKERS,
    HARDCORE_VISIBLE_MARKERS,
    HARDCORE_VISIBLE_MARKERS_EN,
    MODERN_TECH_MARKERS,
    PORTRAIT_ACTION_MARKERS,
    SHOT_ANGLES,
    SHOT_SCALES,
    SOURCE_SENSITIVE_MARKERS,
    STATIC_TRANSITION_MARKERS,
    anachronism_markers_for_story,
    frame_messages,
    theme_messages,
)
from tests.story_factories import make_story_request, make_theme


def test_theme_prompt_requests_story_concepts_not_style_variants() -> None:
    request = make_story_request(theme_count=100, frames_per_theme=6)
    messages = theme_messages(
        request,
        start_index=1,
        count=10,
        existing_themes=[],
    )
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert payload["content_level"] == "aesthetic"
    assert "美学叙事尺度" in payload["content_level_requirement"]
    assert payload["batch_count"] == 10
    assert "微型故事" in messages[0].content
    assert "不能只改变道具、色调或摄影角度" in messages[0].content
    assert "为 story 选择一个明确风格" in messages[0].content
    assert "八十至一百八十个汉字" in messages[0].content
    assert "触发事实、当前目标、期限或失败后果" in messages[0].content
    assert "不要列六帧" in messages[0].content
    assert "不得新增历史人物姓名、具体年号、宫殿名" in messages[0].content


def test_frame_prompt_requests_one_flowing_narrative_paragraph() -> None:
    request = make_story_request(frames_per_theme=6)
    messages = frame_messages(request, make_theme())
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert payload["content_level"] == "aesthetic"
    assert "美学叙事尺度" in payload["content_level_requirement"]
    assert payload["theme"]["theme_id"] == "T001"
    assert "无换行自然段" in messages[0].content
    assert "年代、地点、当前时刻" in messages[0].content
    assert "所有建筑、室内陈设、家具、器物、材料、服装" in messages[0].content
    assert "不确定时使用时代成立的通用描述" in messages[0].content
    assert "一句静态因果" in messages[0].content
    assert "身份与关系、一个触发事实、当前目标" in messages[0].content
    assert "不能复述对话或连续动作" in messages[0].content
    assert "字段标签" in messages[0].content
    assert "每帧重新完整写出每个人" in messages[0].content
    assert "不同的当前情绪、产生该情绪的原因" in messages[0].content
    assert "绝不写其如何到达姿态" in messages[0].content
    assert "每个人只占一个分号分隔的静态分句" in messages[0].content
    assert "放弃站姿蹲身" in messages[0].content
    assert "唯一动作句必须以“此刻，”开头" in messages[0].content
    assert "使用一次“正”或“正在”" in messages[0].content
    assert "使线索、风险、人物判断或关系发生变化" in messages[0].content
    assert "动作句只允许一个主动谓语" in messages[0].content
    assert "另一人物或另一只手再执行动作" in messages[0].content
    assert "五百五十至八百五十个汉字" in messages[0].content
    assert "动作句结束后不得再发生故事" in messages[0].content
    assert "全景、中景、近景或特写" in messages[0].content
    assert "平视、俯拍、仰拍或侧拍" in messages[0].content
    assert "倒数第二句必须以“镜头采用”开头" in messages[0].content
    assert "不能把所有面部裁出画面" in messages[0].content
    assert "最后一句必须以“光线”开头" in messages[0].content
    assert "收束各自情绪、关系和氛围" in messages[0].content
    assert "主动作、发现和情绪转折不得重复" in messages[0].content
    assert "身体、重心、四肢、朝向、遮挡" in messages[0].content
    assert "不得新增姓名、精确年月地点" in messages[0].content
    assert "画面文字必须逐字保留" in messages[0].content
    assert "以 theme.style 原文和逗号开头" in messages[0].content
    assert "StoryBlueprint" not in messages[0].content
    assert "CreativeIntent" not in messages[0].content


def test_frame_prompt_keeps_adult_consent_safety() -> None:
    messages = frame_messages(make_story_request(), make_theme())

    assert "二十一岁以上成年人" in messages[0].content
    assert "清醒、自愿" in messages[0].content


def test_frame_prompt_exposes_every_local_quality_gate() -> None:
    prompt = frame_messages(make_story_request(), make_theme())[0].content

    for marker in (
        *FRAME_TRANSITION_MARKERS,
        *STATIC_TRANSITION_MARKERS,
        *PORTRAIT_ACTION_MARKERS,
        *ACTION_CHAIN_MARKERS,
        *SOURCE_SENSITIVE_MARKERS,
        *SHOT_SCALES,
        *SHOT_ANGLES,
    ):
        assert f"“{marker}”" in prompt
    assert "不得同时出现“又”和“再”" in prompt
    assert "使用一次“正”或“正在”" in prompt
    assert "必须精确以“此刻，”开头" in prompt
    assert "倒数第二句必须以“镜头采用”开头" in prompt
    assert "最后一句必须以“光线”开头" in prompt
    assert "原文已有的英文字词" in prompt


@pytest.mark.parametrize(
    ("level", "required", "excluded"),
    (
        (
            ContentLevel.AESTHETIC,
            "本次使用美学叙事尺度",
            ("本次使用成人情色尺度", "本次使用仅限二十一岁以上成年人的露骨情色尺度"),
        ),
        (
            ContentLevel.EROTIC,
            "本次使用成人情色尺度",
            ("本次使用美学叙事尺度", "本次使用仅限二十一岁以上成年人的露骨情色尺度"),
        ),
        (
            ContentLevel.HARDCORE,
            "本次使用仅限二十一岁以上成年人的露骨情色尺度",
            ("本次使用美学叙事尺度", "本次使用成人情色尺度"),
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
        assert "不得把内容等级名称、英文值或合规说明写入" in prompt


def test_explicit_content_prompts_expose_visible_level_markers() -> None:
    erotic = frame_messages(
        make_story_request(content_level=ContentLevel.EROTIC),
        make_theme(),
    )[0].content
    hardcore = frame_messages(
        make_story_request(content_level=ContentLevel.HARDCORE),
        make_theme(),
    )[0].content

    assert all(f"“{marker}”" in erotic for marker in EROTIC_VISIBLE_MARKERS)
    assert all(
        f"“{marker}”" in hardcore for marker in HARDCORE_VISIBLE_MARKERS
    )


@pytest.mark.parametrize(
    ("level", "markers"),
    (
        (ContentLevel.EROTIC, EROTIC_VISIBLE_MARKERS_EN),
        (ContentLevel.HARDCORE, HARDCORE_VISIBLE_MARKERS_EN),
    ),
)
def test_english_content_prompts_expose_visible_level_markers(
    level: ContentLevel,
    markers: tuple[str, ...],
) -> None:
    request = make_story_request(content_level=level)
    request.output_language = OutputLanguage.ENGLISH

    prompt = frame_messages(request, make_theme())[0].content

    assert all(marker in prompt for marker in markers)


def test_historical_prompt_exposes_high_confidence_anachronisms() -> None:
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
        assert "当前 story 具有明确的历史或季节锚点" in prompt
        assert all(f"“{marker}”" in prompt for marker in MODERN_TECH_MARKERS)


def test_story_can_explicitly_request_intentional_anachronism() -> None:
    request = make_story_request()
    request.story += "这是有意的时代错置，画面中保留智能手机。"

    assert anachronism_markers_for_story(request) == ()
    assert "只有 story 明确要求穿越" in frame_messages(
        request,
        make_theme(),
    )[0].content


def test_qing_cold_season_prompt_rejects_summer_court_hat() -> None:
    request = make_story_request()
    request.story = "清代深秋，一名三十岁的成年人站在王府书房。"

    assert "凉帽" in anachronism_markers_for_story(request)
    assert "服装冷暖、植物状态和取暖降温方式必须符合季节" in frame_messages(
        request,
        make_theme(),
    )[0].content
