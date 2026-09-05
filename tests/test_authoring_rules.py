from __future__ import annotations

import json
from pathlib import Path

import pytest

from t2i_prompt_pipeline.authoring_rules import resolve_rules
from t2i_prompt_pipeline.errors import ConfigurationError
from t2i_prompt_pipeline.models import (
    ContentLevel,
    FrameBatch,
    FrameMode,
    GenerationStage,
    OutputLanguage,
)
from tests.factories import make_spec

SYSTEM_RULES = (
    Path(__file__).parents[1]
    / "src"
    / "t2i_prompt_pipeline"
    / "rule_packs"
    / "system"
)


def test_rules_express_stage_ownership_without_crossing_boundaries() -> None:
    resolved = resolve_rules(make_spec())
    foundation = resolved.text_for(GenerationStage.FOUNDATION)
    themes = resolved.text_for(GenerationStage.THEMES)
    frames = resolved.text_for(GenerationStage.FRAMES)

    for rules in (foundation, themes, frames):
        assert "brief 是事实来源" in rules
        assert "当前 stage 的 ownership" in rules
        assert "只返回 schema 数据" in rules

    assert "CastPlan.members 按人物首次出现顺序展开" in foundation
    assert "StyleConstraints.required_phrases" in foundation
    assert "camera.shot" not in foundation

    assert "Theme 只拥有 title、跨 Frame 稳定的 scene" in themes
    assert "人物位置、表情、动作、接触、遮挡和具体镜头属于 Frame" in themes
    assert "Frame：把一个 Theme 实现" not in themes

    assert "Frame 只拥有 camera、当前可见人物" in frames
    assert "词本身不构成错误" in frames
    assert "明确跨 Frame 引用" in frames
    assert "Theme：为每个 ID 建立" not in frames


def test_system_rule_corpus_stays_concise() -> None:
    rule_files = tuple(SYSTEM_RULES.rglob("*.rules"))
    assert len(rule_files) == 9
    assert sum(len(path.read_bytes()) for path in rule_files) <= 13_000


def test_rule_priorities_preserve_constraints_before_decorative_variation() -> None:
    resolved = resolve_rules(make_spec())
    for stage in (
        GenerationStage.FOUNDATION,
        GenerationStage.THEMES,
        GenerationStage.FRAMES,
    ):
        rules = resolved.text_for(stage)
        assert "示例只说明写法，不给当前 brief 增添要求" in rules
        assert (
            "brief 明示事实与 ownership、单帧物理和可见性、画面差异、修辞细节"
        ) in rules
        assert "先为全部请求 ID 生成最简有效候选，再补可选细节" in rules
        assert "确实无法形成有效候选时才省略该 ID" in rules
        assert "brief 必需事实、人物、路线与因果信息完整保留" in rules

    themes = resolved.text_for(GenerationStage.THEMES)
    assert "scene 用名词短语写活动位置" in themes
    assert "brief 的全部工具与作用对象及材质" in themes
    assert "不靠同义词或仅换时段区分" in themes
    assert "例如“靠窗阅读”" in themes
    assert "活动位置临窗，不是背景存在窗" in themes
    assert "appearance 只写稳定形态，眼神、表情与朝向留给 Frame" in themes
    assert "服饰先满足 brief 的类型、遮盖与材质要求" in themes
    assert "单地点活动省去到达路线" in themes
    assert "当前位置和持握由 Frame 描述" in themes
    assert "request.required_route_points" in themes
    assert "重生成只调整未固定项" in themes
    assert "即使 request.validation_issues 要求新场所" in themes


@pytest.mark.parametrize("mode", list(FrameMode))
@pytest.mark.parametrize("language", list(OutputLanguage))
def test_crop_first_rules_cover_partial_faces_and_natural_actions(
    mode: FrameMode, language: OutputLanguage
) -> None:
    spec = make_spec(output_language=language)
    spec.frame_mode = mode
    rules = resolve_rules(spec).text_for(GenerationStage.FRAMES)

    assert "先定取景边界，再定可见部位与物体" in rules
    assert "眼部可见时写眼神或眉眼" in rules
    assert "仅嘴部、下颌可见时写嘴角或下颌状态" in rules
    assert "面部完全不入画时为 null" in rules
    assert "上边界低于下颌时 expression 为 null" in rules
    assert "营造真实情绪张力" not in rules
    assert "每只手默认一个主要任务" in rules
    assert "如当前帧承担浇水" in rules
    assert "身体细节服从裁切" in rules
    assert "容器内部仅在开口或透明结构位于取景内时描述" in rules
    assert "brief 明示的材质要求约束所有字段" in rules
    assert "逆光只改变衣料表面的明暗" in rules
    assert "camera.composition 正向列出入画区域" in rules
    assert "action 用一个短句" in rules
    assert "details 默认至多两项可选细节" in rules
    assert "只见背面时为 null" in rules
    assert "brief 要求局部面部时才选局部" in rules
    assert "中文40字或英文25词以内" in rules
    assert "中文共30字或英文20词以内" in rules
    assert "短句示例仅示范写法" in rules
    assert "服饰描述只沿用 Theme 原词" in rules


def test_frame_example_is_valid_short_output_with_explicit_visibility() -> None:
    rules = resolve_rules(make_spec())
    examples = [rule for rule in rules.frames if rule.startswith('{"theme_id":')]
    assert len(examples) == 1
    example = FrameBatch.model_validate(json.loads(examples[0]))

    assert len(example.frames) == 2
    portrait, detail = example.frames
    assert "完整面部" in portrait.camera.composition
    assert portrait.characters[0].expression is not None
    assert "仅双手" in detail.camera.composition
    assert detail.characters[0].expression is None
    for frame in example.frames:
        assert len(frame.characters[0].action) <= 40
        assert len(frame.details) <= 30


@pytest.mark.parametrize("mode", list(FrameMode))
@pytest.mark.parametrize("language", list(OutputLanguage))
def test_aesthetic_floor_preserves_fixed_clothing_and_activity(
    mode: FrameMode, language: OutputLanguage
) -> None:
    spec = make_spec(output_language=language)
    spec.frame_mode = mode
    spec.content_level = ContentLevel.AESTHETIC
    resolved = resolve_rules(spec)

    for stage in (
        GenerationStage.FOUNDATION,
        GenerationStage.THEMES,
        GenerationStage.FRAMES,
    ):
        rules = resolved.text_for(stage)
        assert "每帧至少呈现裸露程度、贴身轮廓、姿态张力和光影塑形中的两项" in rules
        assert "以相容的姿态与光影满足下限，保留原服饰及活动" in rules
        assert "不写成着装完整的日常记录" not in rules
        assert "所有角色必须外观明确成年" in rules
        assert "尺度上限为不得细致描写或特写聚焦性器官" in rules


def test_style_constraints_preserve_brief_without_inference() -> None:
    foundation = resolve_rules(make_spec()).text_for(
        GenerationStage.FOUNDATION
    )
    themes = resolve_rules(make_spec()).text_for(GenerationStage.THEMES)

    assert "brief 明示的创作者或流派、媒介、视觉技法、时代和地域" in (
        foundation
    )
    assert "brief 中连续、逐字一致的原文片段" in foundation
    assert "不翻译、不概括、不推断关联特征" in foundation
    assert "brief 未明示的角色、职业、时代、地域、媒介、技法和创作者" in (
        foundation
    )
    assert "role 只复制 brief 中明确身份的原词" in foundation
    assert "没有身份原词时用 JSON null" in foundation
    assert "仅年龄、性别、服饰或动作不算身份" in foundation
    assert "摄影或摄像实拍方案" in themes
    assert "非摄影艺术词只能作为被实拍的美术处理" in themes


def test_period_rules_bind_theme_and_frame_to_the_brief() -> None:
    resolved = resolve_rules(make_spec())
    themes = resolved.text_for(GenerationStage.THEMES)
    frames = resolved.text_for(GenerationStage.FRAMES)

    assert "服饰与器物符合 brief 明示的时代、地域、天气和场合" in themes
    assert "沿用 Theme 的时代、地域、颜色和材质逻辑" in frames


def test_every_content_level_states_a_floor_and_ceiling() -> None:
    levels = {}
    for level in ContentLevel:
        spec = make_spec()
        spec.content_level = level
        levels[level] = resolve_rules(spec).text_for(GenerationStage.FRAMES)

    aesthetic = levels[ContentLevel.AESTHETIC]
    erotic = levels[ContentLevel.EROTIC]
    hardcore = levels[ContentLevel.HARDCORE]

    assert "美学级（aesthetic）" in aesthetic
    assert "极致情色级（erotic）" not in aesthetic
    assert "尺度下限是静止画面可见的形体表达" in aesthetic
    assert "依偎、牵手、拥抱、亲吻和抚触" in aesthetic
    assert "接触必须双方可见地互相参与" in aesthetic
    assert "以形体美、光影和构图为主视觉" in aesthetic
    assert "所有角色必须外观明确成年" in aesthetic
    assert "BDSM 题材本身不决定内容等级" in aesthetic
    assert "不得细致描写或特写聚焦性器官" in aesthetic
    assert "极致情色级（erotic）" in erotic
    assert "当前画面直接呈现" in erotic
    assert "替代该等级的可见内容" in erotic
    assert "双方可见地互相参与" in erotic
    assert "单人、双人或多人画面" in erotic
    assert "清醒、回应、主动配合和可退出" in erotic
    assert "不出现性器官特写、插入或口部性行为、自慰、体液和性暴力细节" in erotic
    assert "此上限内的各种性暗示可自由使用" in erotic
    assert "自适应选择符合氛围的服饰" in erotic
    assert "避免单一全裸" in erotic
    assert "有机变化" in erotic
    assert "反射或前景遮挡合计最多占一个 Frame" in erotic
    assert "至少一处双方主动形成的具体身体接触" in erotic
    assert "整组至少一半 Frame 中完成为可见接触" in erotic
    assert "近景不得以胯下、腹股沟或性器官区域为主视觉" in erotic
    assert "BDSM 题材本身不决定内容等级" in erotic
    assert "支配与臣服、主从礼仪与调教仪式" in erotic
    assert "装饰性绳缚或快拆手铐" in erotic
    assert "眼罩或耳罩的感官剥夺" in erotic
    assert "羽毛冰块温蜡等感官刺激" in erotic
    assert "手掌、软拍或软质多尾鞭" in erotic
    assert "束缚余量或快拆结构" in erotic
    assert "悬吊、勒颈、堵塞呼吸" in erotic
    assert "赤裸裸的性描写（hardcore）" not in erotic
    assert "赤裸裸的性描写（hardcore）" in hardcore
    assert "当前画面直接、清晰地呈现" in hardcore
    assert "替代明确行为" in hardcore
    assert "BDSM 题材本身不决定内容等级" in hardcore
    assert "只有在画面另行呈现明确性行为时才归入 hardcore" in hardcore
    assert "器具、束缚或痛感强度本身不能把画面升级" in hardcore
    assert "勒颈窒息、电击、真实武器" in hardcore


def test_frame_modes_are_mutually_exclusive() -> None:
    sequential = resolve_rules(make_spec()).text_for(GenerationStage.FRAMES)
    variation_spec = make_spec()
    variation_spec.frame_mode = FrameMode.VARIATIONS
    variations = resolve_rules(variation_spec).text_for(GenerationStage.FRAMES)

    assert "完整可见因果链" in sequential
    assert "首帧建立未完成状态" in sequential
    assert "终帧在 brief 核心动词的语义上限内" in sequential
    assert "互不依赖的完整候选画面" not in sequential
    assert "request.variation_plan" not in sequential

    assert "互不依赖的完整候选画面" in variations
    assert "request.variation_plan" in variations
    assert "三项差异是满足约束后的目标" in variations
    assert "一致性优先于差异数量" in variations
    assert "任意两帧至少在三项上实质不同" not in variations
    assert "完整可见因果链" not in variations
    assert "终帧" not in variations


def test_output_language_rule_is_selected_for_every_stage() -> None:
    english = resolve_rules(
        make_spec(output_language=OutputLanguage.ENGLISH)
    )
    chinese = resolve_rules(make_spec())

    for stage in GenerationStage:
        english_rules = english.text_for(stage)
        assert "自然、流利、简练的英文" in english_rules
        assert "不得夹杂中文或其他语言" in english_rules

        chinese_rules = chinese.text_for(stage)
        assert "自然、流利、简练的中文" in chinese_rules
        assert "摄影、服饰和材质术语也必须译为中文" in chinese_rules
        assert "其余只用中文、阿拉伯数字和常规标点" in chinese_rules
        assert "brief 原文或规则明确允许的姓名、专有术语可原样保留" in chinese_rules
        assert "schema 规定的机器标识字段不受此限制" in chinese_rules


def test_user_rules_are_appended_in_file_order_and_selected_by_run(
    tmp_path: Path,
) -> None:
    user = tmp_path / "rules"
    (user / "content_levels").mkdir(parents=True)
    (user / "frame_modes").mkdir()
    (user / "common.rules").write_text(
        "# comment\n\n用户通用规则一\n  用户通用规则二  \n",
        encoding="utf-8",
    )
    (user / "themes.rules").write_text("用户主题规则\n", encoding="utf-8")
    (user / "content_levels" / "aesthetic.rules").write_text(
        "不应加载的美学规则\n",
        encoding="utf-8",
    )
    (user / "content_levels" / "erotic.rules").write_text(
        "用户情色规则\n",
        encoding="utf-8",
    )
    (user / "frame_modes" / "sequential.rules").write_text(
        "不应加载的连续规则\n",
        encoding="utf-8",
    )
    (user / "frame_modes" / "variations.rules").write_text(
        "用户变化规则\n",
        encoding="utf-8",
    )
    spec = make_spec()
    spec.content_level = ContentLevel.EROTIC
    spec.frame_mode = FrameMode.VARIATIONS

    resolved = resolve_rules(spec, user_directory=user)

    assert "用户通用规则一" in resolved.themes
    assert "用户通用规则二" in resolved.themes
    assert resolved.themes.index("用户通用规则一") < resolved.themes.index(
        "用户主题规则"
    )
    assert "用户情色规则" in resolved.themes
    assert "不应加载的美学规则" not in resolved.themes
    assert "用户变化规则" in resolved.frames
    assert "不应加载的连续规则" not in resolved.frames
    assert resolved.themes[-1].startswith("输出语言要求")


def test_explicit_user_rule_directory_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="用户规则目录不存在"):
        resolve_rules(make_spec(), user_directory=tmp_path / "missing")


def test_rule_fingerprint_is_stable_and_content_sensitive() -> None:
    resolved = resolve_rules(make_spec())
    changed = resolved.model_copy(update={"frames": (*resolved.frames, "新增规则")})

    assert resolved.fingerprint() == resolved.model_copy().fingerprint()
    assert resolved.fingerprint() != changed.fingerprint()