from __future__ import annotations

import re

import pytest

from t2i_film_style_pipeline.errors import FilmStyleConfigurationError
from t2i_film_style_pipeline.prompt_models import ContentLevel, FilmPromptRequest
from t2i_film_style_pipeline.rules import resolve_film_style_rules


def make_prompt_request(
    content_level: ContentLevel = ContentLevel.AESTHETIC,
) -> FilmPromptRequest:
    return FilmPromptRequest(
        context="BRIEF\n\nDirector-work film scene generation.",
        content_level=content_level,
    )


def test_film_style_rules_select_only_the_requested_content_level() -> None:
    rules = resolve_film_style_rules(
        make_prompt_request(ContentLevel.EROTIC),
    )

    for stage_rules in (rules.themes, rules.frames):
        text = "\n".join(stage_rules)
        assert "内容级别：极致情色级" in text
        assert "内容级别：美学级" not in text
        assert "内容级别：赤裸明确级" not in text


@pytest.mark.parametrize(
    ("content_level", "required_rule", "forbidden_rule"),
    [
        (
            ContentLevel.AESTHETIC,
            "不出现明确性行为",
            "允许直接呈现自慰、口部性行为、插入",
        ),
        (
            ContentLevel.EROTIC,
            "把裸露、欲望、身体接近和双向触碰推到最高可见强度",
            "允许直接呈现自慰、口部性行为、插入",
        ),
        (
            ContentLevel.HARDCORE,
            "正在发生的具体性行为、性器官及其接触方式",
            "不得出现明确性行为",
        ),
    ],
)
def test_film_style_content_levels_define_clear_visual_bounds(
    content_level,
    required_rule,
    forbidden_rule,
) -> None:
    rules = resolve_film_style_rules(
        make_prompt_request(content_level),
    )
    text = "\n".join(rules.frames)

    assert required_rule in text
    assert forbidden_rule not in text
    assert "最大化感官表现时" in text
    assert "主动" in text
    assert "自愿" in text


def test_frame_rules_require_specific_expression_for_every_character() -> None:
    rules = resolve_film_style_rules(make_prompt_request())
    text = "\n".join(rules.frames)

    assert "每个入画人物都必须分别写出一个具体、可见" in text
    assert "至少用眉眼、眼睑、嘴角、嘴唇、下颌、面颊或额头中的两项" in text
    assert "明确其视线落点" in text
    assert "不得只为群体提供一个共同表情" in text
    assert "不得让不同人物复制相同表情" in text


def test_frame_rules_define_low_complexity_body_topology() -> None:
    rules = resolve_film_style_rules(make_prompt_request())
    text = "\n".join(rules.frames)

    assert "主要支撑面和承重部位" in text
    assert "骨盆、躯干和头部各自唯一的朝向与高度" in text
    assert "每条可见手臂和腿分配一个且仅一个作用" in text
    assert "谁的哪个部位接触谁的哪个部位或哪件物体" in text
    assert "每个人最多增加一个无动作含义的辅助接触" in text
    assert "扶膝、握腕或环颈不能被写成全身支撑" in text
    assert "不得先写该区域完全贴合或没有缝隙" in text
    assert "不得在仍穿上衣或下装时写“完全赤裸”" in text
    assert "每个 Frame 的姿态设计保持开放，不使用固定姿势菜单" in text
    assert "必须为每个人分别写清一条闭合承重链" in text
    assert "为呈现面部而调整摄影机" in text
    assert "不得让衣袖、衣襟或肩带滑落、褪至或堆在手臂" in text
    assert "身体拓扑和动作可读性优先于" in text
    assert "不得把两个方案混入同一画面" in text
    assert "当前 Frame 专属的“核心接触链”句" in text
    assert "画面是动作完成后的一个静态受力瞬间" in text
    assert "每张脸与对方的颈侧、胸前、肩后和头发之间保留可见间隔" in text
    assert "每人的重心落在自己的支撑多边形内" in text
    assert "不得使用悬空骨盆、无支点深度俯折" in text
    assert "其他手臂必须放在自己的身体或主要支撑面上" in text
    assert "核心接触所需的手、手臂、腿或物体必须具有可见的进入路径" in text
    assert "头颈方向必须与胸骨朝向自然一致" in text
    assert "必须为每个人分别用一句话选定以下一种完整衣物状态" in text
    assert "核心接触部位及其进入路径不得被仍穿着的衣物覆盖" in text
    assert "每人至多一只手接触对方" in text
    assert "人物朝向与高低关系" in text


def test_hardcore_rules_keep_theme_open_and_close_each_frame_topology() -> None:
    rules = resolve_film_style_rules(
        make_prompt_request(ContentLevel.HARDCORE)
    )
    text = "\n".join((*rules.themes, *rules.frames))

    assert "不得固定动作发起者、具体接触部位" in text
    assert "不同 Frame 可以改变行为类别、动作发起者和基础姿态" in text
    assert "每个 Frame 只能有一处带有性动作含义的主动接触" in text
    assert "胸部、肩背、大腿或腰部的抓握不能单独充当本级核心行为" in text
    assert "批次应同时探索不同的姿态类别、核心接触链" in text
    assert "每个 Frame 的内部拓扑必须独立闭合" in text


@pytest.mark.parametrize("output_language", ["chinese", "english"])
def test_every_builtin_film_style_rule_is_written_in_chinese(
    output_language,
) -> None:
    rules = resolve_film_style_rules(
        FilmPromptRequest(
            context="BRIEF\n\nDirector-work film scene generation.",
            output_language=output_language,
        )
    )

    for rule in (*rules.profile, *rules.themes, *rules.frames):
        assert re.search(r"[\u4e00-\u9fff]", rule), rule


def test_film_style_rules_append_optional_user_files_in_stage_order(
    tmp_path,
) -> None:
    (tmp_path / "content_levels").mkdir()
    (tmp_path / "profile.rules").write_text(
        "Film user profile rule.\n",
        encoding="utf-8",
    )
    (tmp_path / "common.rules").write_text(
        "# ignored\nFilm user common rule.\n\n",
        encoding="utf-8",
    )
    (tmp_path / "themes.rules").write_text(
        "Film user Theme rule.\n",
        encoding="utf-8",
    )
    (tmp_path / "frames.rules").write_text(
        "Film user Frame rule.\n",
        encoding="utf-8",
    )
    (tmp_path / "content_levels" / "aesthetic.rules").write_text(
        "Film user aesthetic rule.\n",
        encoding="utf-8",
    )

    rules = resolve_film_style_rules(
        make_prompt_request(),
        user_directory=tmp_path,
    )

    assert rules.profile[-1] == "Film user profile rule."
    assert rules.themes[-4:-1] == (
        "Film user common rule.",
        "Film user Theme rule.",
        "Film user aesthetic rule.",
    )
    assert rules.frames[-4:-1] == (
        "Film user common rule.",
        "Film user Frame rule.",
        "Film user aesthetic rule.",
    )
    assert "电影场景上下文" in rules.themes[-1]
    assert "电影场景上下文" in rules.frames[-1]


def test_film_style_rules_reject_missing_user_directory(tmp_path) -> None:
    with pytest.raises(
        FilmStyleConfigurationError,
        match="film-style user rules directory does not exist",
    ):
        resolve_film_style_rules(
            make_prompt_request(),
            user_directory=tmp_path / "missing",
        )
