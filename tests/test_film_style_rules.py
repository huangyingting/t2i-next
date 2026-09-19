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
            "把裸露、欲望、身体接近、双向触碰",
            "允许直接呈现自慰、口部性行为、插入",
        ),
        (
            ContentLevel.HARDCORE,
            "高强度无插入 BDSM",
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
    assert "每条可见手臂和腿在该瞬间相互兼容的用途" in text
    assert "谁的哪个部位接触谁的哪个部位或哪件物体" in text
    assert "除共同互动所需动作外不得增加无意义辅助接触" in text
    assert "扶膝、握腕或环颈不能被写成全身支撑" in text
    assert "不得先写该区域完全贴合或没有缝隙" in text
    assert "不得在仍穿上衣或下装时写“完全赤裸”" in text
    assert "每个 Frame 的姿态设计保持开放，不使用固定姿势菜单" in text
    assert "必须为每个人分别写清一条闭合承重链" in text
    assert "为呈现面部而调整摄影机" in text
    assert "不得让衣袖、衣襟或肩带滑落、褪至或堆在手臂" in text
    assert "依次保证支撑与关节合理、接触可达、摄影与自然遮挡协调" in text
    assert "不得把两个方案混入同一画面" in text
    assert "实际存在的接触链或动作链" in text
    assert "画面是动作完成后的一个静态受力瞬间" in text
    assert "每张脸与对方的颈侧、胸前、肩后和头发之间保留可见间隔" in text
    assert "重心投影须落在实际支撑范围内" in text
    assert "不得使用无承托的悬空骨盆、无支点深度俯折" in text
    assert "每条接触链所需的手、手臂、腿或物体必须具有空间上可达的进入路径" in text
    assert "头颈转向须处于自然关节活动范围内" in text
    assert "必须为每个人分别用一句话选定以下一种完整衣物状态" in text
    assert "所有决定性接触部位及其进入路径不得被仍穿着的衣物覆盖" in text
    assert "同一肢体的用途兼容" in text
    assert "人物朝向与高低关系" in text
    assert "theme_anchor_contract 冻结当前 Theme 已选择的原作锚点" in text
    assert "程序会在固定作品来源首句之后确定性插入" in text
    assert "participant_frame_contracts.participants 是逐人物硬约束" in text
    assert "group_frame_contracts" in text
    assert "不得只观察、等待、递物、做表情或充当背景" in text
    assert "hardcore_group_realization" in text
    assert "不得为了完成多人构图而把性部位" in text
    assert "current_frame_diversity_contracts 按 frame_slot" in text
    assert "选择性重试时继续执行原 frame_slot 的同一合同" in text


def test_frame_rules_distinguish_coordinates_supports_and_visibility() -> None:
    text = "\n".join(resolve_film_style_rules(make_prompt_request()).frames)
    for requirement in (
        "人物自身的解剖左右",
        "两人并排同向时",
        "接触必须同时指明两端的人物、部位及左右侧",
        "支撑记录是承重描述的唯一来源",
        "臀部离墙、上背倚墙以及手掌和前臂实际占用的空隙",
        "臀部落地的抱膝坐和臀部离地的蹲姿",
        "侧卧须交代头部支撑和下侧手臂的位置",
        "区分接触边界与被身体压住的接触面",
        "对焦、无遮挡和足够照明",
        "不得同时写成完全逆光剪影",
        "不同距离，应调整机位或景深",
    ):
        assert requirement in text


def test_hardcore_rules_keep_theme_open_and_close_each_frame_topology() -> None:
    rules = resolve_film_style_rules(
        make_prompt_request(ContentLevel.HARDCORE)
    )
    text = "\n".join((*rules.themes, *rules.frames))

    assert "不得固定动作发起者、具体接触部位" in text
    assert "不同 Frame 可以改变行为类别、动作发起者和基础姿态" in text
    assert "每个 Frame 只能有一条带有性动作、器具控制或命令展示含义" in text
    assert "胸部、肩背、大腿或腰部的抓握不能单独充当该路径的核心行为" in text
    assert "批次应同时探索不同的内容路径、姿态类别、核心互动链" in text
    assert "每个 Frame 的内部拓扑必须独立闭合" in text
    assert "可以独立构成本级，不强制同时出现插入" in text
    assert "项圈、牵引链、腕带或绳索不得承担身体重量" in text
    assert "不得让所有 Theme 或 Frame 都收敛为插入、手部刺激或跪姿牵引链" in text
    assert "开放类别而非固定模板或分配表" in text


def test_erotic_and_hardcore_share_sensory_intensity_but_not_evidence() -> None:
    erotic = "\n".join(
        resolve_film_style_rules(
            make_prompt_request(ContentLevel.EROTIC)
        ).frames
    )
    hardcore = "\n".join(
        resolve_film_style_rules(
            make_prompt_request(ContentLevel.HARDCORE)
        ).frames
    )

    assert "同等精细、浓烈的感官描写" in erotic
    assert "必须同时直接呈现四项核心证据" in erotic
    assert "接纳”“放松”“专注”不能替代欲望或愉悦" in erotic
    assert "衣物终态只允许二选一" in erotic
    assert "不得让衣袖、衣襟或肩带从肩头滑落" in erotic
    assert "同等精细、浓烈的皮肤、表情、材质" in hardcore
    assert "不得形成完整的色情控制链" in erotic
    assert "极致感官强度必须来自非生殖器接触" in erotic
    assert "以下是开放式边界例子" in erotic
    assert "松散项圈作为造型" in erotic
    assert "不可误读的明确色情事实" in hardcore
    assert "命令式色情展示" in hardcore
    assert "以下是开放式内容路径例子" in hardcore
    assert "不要把“无插入 BDSM”自动等同于跪姿、狗链" in hardcore
    assert "输出前必须在当前调用内完成路径完整性自检" in hardcore
    assert "不能把无插入当作降低色情强度" in hardcore


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
