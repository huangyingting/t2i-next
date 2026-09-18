import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.inputs import (
    CatalogDocument,
    InputOverrides,
    ModuleDocument,
    StoryDocument,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.models import ContentLevel, StoryAuthoring, StoryStage

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECIPES = REPOSITORY_ROOT / "story-inputs" / "recipes"
POLICIES = REPOSITORY_ROOT / "src" / "t2i_story_pipeline" / "rule_packs" / "policies"


def story_contract(document: StoryDocument) -> str:
    """Inspect creative requirements without pretending all levels reach the model."""
    sections = [document.description]
    for stage in (document.authoring.themes, document.authoring.frames):
        sections.extend(stage.common)
        for rules in stage.content_levels.values():
            sections.extend(rules)
    resolved = resolve_story_input(document)
    for source in resolved.sources:
        if source.kind == "module":
            for stage in json.loads(source.content)["authoring"].values():
                sections.extend(stage["common"])
                for rules in stage["content_levels"].values():
                    sections.extend(rules)
        elif source.kind == "catalog":
            for entry in json.loads(source.content)["entries"]:
                sections.extend(entry["themes"])
                sections.extend(entry["frames"])
                if assignment := entry.get("frame_assignment"):
                    for slot in assignment["slots"]:
                        sections.extend(slot["rules"])
    return "\n".join(dict.fromkeys(sections))


def authoring_pool(document, label, *, stage=StoryStage.THEMES):
    authored = getattr(document.authoring, stage.value)
    rules = (*authored.common, *authored.content_levels.get(ContentLevel.HARDCORE, ()))
    prefix = f"{label}: - "
    return [rule.removeprefix(prefix) for rule in rules if rule.startswith(prefix)]


def bundled_authoring_prose(path: Path) -> Iterator[tuple[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if path.parent.name == "_catalogs":
        catalog = CatalogDocument.model_validate(data)
        for entry in catalog.entries:
            for stage in StoryStage:
                for index, rule in enumerate(getattr(entry, stage.value)):
                    yield f"entries.{entry.id}.{stage.value}[{index}]", rule
            if entry.frame_assignment:
                for slot in entry.frame_assignment.slots:
                    for index, rule in enumerate(slot.rules):
                        yield (
                            f"entries.{entry.id}.frame_assignment.{slot.frame_id}"
                            f".rules[{index}]",
                            rule,
                        )
        return
    if path.parent.name == "_modules":
        authoring = ModuleDocument.model_validate(data).authoring
    elif path.parent == POLICIES:
        authoring = StoryAuthoring.model_validate(data["authoring"])
    else:
        document = StoryDocument.model_validate(data)
        yield "description", document.description
        authoring = document.authoring
    for stage in StoryStage:
        authored = getattr(authoring, stage.value)
        for index, rule in enumerate(authored.common):
            yield f"authoring.{stage.value}.common[{index}]", rule
        for level, rules in authored.content_levels.items():
            for index, rule in enumerate(rules):
                yield (
                    f"authoring.{stage.value}.content_levels.{level.value}[{index}]",
                    rule,
                )


def untranslated_authoring(prose: str) -> list[str]:
    # Exact output literals remain English; YAML scalar quoting is already removed.
    unquoted = re.sub(
        r'`[^`]*`|"[^"]*"|“[^”]*”|‘[^’]*’|(?<![A-Za-z])\'[^\'\n]+\'(?![A-Za-z])',
        "",
        " ".join(prose.split()),
    )
    if not unquoted.strip(" \t:;,.，。；：、-"):
        return []
    problems = []
    if not re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", unquoted):
        problems.append("natural-language instruction contains no Chinese")
    english_runs = re.findall(
        r"\b[A-Za-z][A-Za-z'-]*(?:[ \t]+[A-Za-z][A-Za-z'-]*){5,}\b", unquoted
    )
    problems.extend(f"untranslated English prose: {run}" for run in english_runs)
    return problems


@pytest.mark.parametrize(
    ("prose", "valid"),
    [
        ("使用 Blender 制作具有 ASCII 标题的中国场景。", True),
        ('逐字输出 "VIEW DIRECTION LOCK: front view from the rim."，不得翻译。', True),
        ("使用 `left leg` 和 “right leg” 分别描述两条腿。", True),
        ('"VIEW DIRECTION LOCK: front view."', True),
        ("Create an original scene with a coherent adult cast.", False),
        ("完整场景。Create an original scene with a coherent adult cast.", False),
        (
            'Write a scene with "Chinese title" and keep every adult clearly visible.',
            False,
        ),
    ],
)
def test_bundled_language_guard_preserves_literals_not_english_instructions(
    prose: str, valid: bool
) -> None:
    assert (not untranslated_authoring(prose)) is valid


@pytest.mark.parametrize(
    "path",
    sorted((*RECIPES.rglob("*.yaml"), *POLICIES.glob("*.yaml"))),
    ids=lambda path: str(path.relative_to(REPOSITORY_ROOT)),
)
def test_all_bundled_authoring_is_chinese_except_literal_anchors(path: Path) -> None:
    fields = list(bundled_authoring_prose(path))
    assert fields, f"{path.name} must expose natural-language authoring"
    violations = [
        f"{field}: {problem}"
        for field, prose in fields
        for problem in untranslated_authoring(prose)
    ]
    assert not violations, "\n".join(violations)


def test_story_inputs_are_yaml_documents_with_matching_ids() -> None:
    story_inputs_dir = REPOSITORY_ROOT / "story-inputs" / "recipes"
    story_inputs = sorted(story_inputs_dir.glob("*.yaml"))

    assert len(story_inputs) == 48
    assert not list((REPOSITORY_ROOT / "story-inputs").glob("*.yaml"))
    assert not list(story_inputs_dir.glob("*.txt"))
    for story_input in story_inputs:
        document = load_story_document(story_input)
        assert document.id == story_input.stem
        assert document.description.strip()


def test_story_inputs_preserve_description_in_generation_requests() -> None:
    story_inputs = sorted((REPOSITORY_ROOT / "story-inputs" / "recipes").glob("*.yaml"))

    assert story_inputs
    assert not (
        REPOSITORY_ROOT / "story-inputs" / "recipes" / "multi-view-scenes.yaml"
    ).exists()

    for story_input in story_inputs:
        document = load_story_document(story_input)
        assert isinstance(document, StoryDocument), story_input.name
        resolved = resolve_story_input(document)
        request = resolved.request

        assert request.story == document.description, story_input.name
        assert request.source_prompt_stem == document.id, story_input.name
        assert request.theme_count == document.generation.theme_count, story_input.name
        assert request.frames_per_theme == document.generation.frames_per_theme, (
            story_input.name
        )
        assert request.content_level == document.generation.content_level, (
            story_input.name
        )
        assert request.output_language == document.generation.output_language, (
            story_input.name
        )


@pytest.mark.parametrize("path", sorted(RECIPES.glob("*.yaml")), ids=lambda p: p.stem)
def test_recipe_compilation_selects_only_each_stages_active_level(path):
    document = load_story_document(path)
    for level in document.requirements.content_levels or tuple(ContentLevel):
        resolved = resolve_story_input(document, InputOverrides(content_level=level))
        for stage in StoryStage:
            authored = getattr(document.authoring, stage.value)
            compiled = resolved.rules.text_for(stage)
            selected = authored.selected(level)
            assert all(rule in compiled for rule in selected)
            excluded = {
                rule
                for other, rules in authored.content_levels.items()
                if other != level
                for rule in rules
            } - set(selected)
            assert all(rule not in compiled for rule in excluded)
            assert isinstance(
                resolved.context_for(stage, [resolved.plans[0].theme_id]), dict
            )


def test_fixed_couple_catalog_is_one_hundred_ordered_single_frame_plans():
    document = load_story_document(RECIPES / "indoor-couple-pose-aesthetic.yaml")
    resolved = resolve_story_input(document)
    request = resolved.request
    assert request.theme_count == 100
    assert request.frames_per_theme == 1
    assert (request.female_count, request.male_count) == (1, 1)
    assert request.output_language == "english"
    assert len(resolved.plans) == 100
    assert len({plan.entry.id for plan in resolved.plans}) == 100
    catalog = json.loads(
        next(source.content for source in resolved.sources if source.kind == "catalog")
    )
    assert [plan.entry.id for plan in resolved.plans] == catalog["slots"]
    for overrides in (
        InputOverrides(theme_count=99),
        InputOverrides(frames_per_theme=2),
        InputOverrides(female_count=0),
        InputOverrides(male_count=0),
        InputOverrides(output_language="chinese"),
    ):
        with pytest.raises(StoryConfigurationError):
            resolve_story_input(document, overrides)


@pytest.mark.parametrize("filename", ["pose.yaml", "dress.yaml"])
def test_six_internal_views_do_not_force_six_narrative_frames(filename):
    document = load_story_document(RECIPES / filename)
    resolved = resolve_story_input(document, InputOverrides(frames_per_theme=1))
    assert resolved.request.frames_per_theme == 1
    assert (resolved.request.female_count, resolved.request.male_count) == (1, 0)
    layout = next(
        module for module in resolved.modules if module.kind == "layout_multiview"
    )
    assert layout.parameters.min_views == 6
    assert layout.parameters.max_views == 6
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(male_count=1))


def test_human_typography_leaves_cast_unspecified_and_uses_catalog_facts():
    document = load_story_document(RECIPES / "human-typography.yaml")
    resolved = resolve_story_input(document, InputOverrides(theme_count=26))
    assert resolved.request.female_count is None
    assert resolved.request.male_count is None
    assert len({plan.entry.id for plan in resolved.plans[:26]}) == 26
    for plan in resolved.plans:
        assert plan.cast.total == plan.entry.cast.total
        assert plan.cast.min_female == plan.entry.cast.min_female
        assert plan.cast.min_male == plan.entry.cast.min_male
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(female_count=1))


@pytest.mark.parametrize(
    "filename", ["miniature-giant-encounter.yaml", "giant-country-fantasy.yaml"]
)
def test_giant_cast_is_one_extra_role_with_total_at_most_eight(filename):
    document = load_story_document(RECIPES / filename)
    for level in (ContentLevel.EROTIC, ContentLevel.HARDCORE):
        resolved = resolve_story_input(
            document, InputOverrides(content_level=level, female_count=7, male_count=0)
        )
        assert resolved.request.female_count == 7
        for plan in resolved.plans:
            assert plan.cast.scope != "all_people"
            assert len(plan.cast.fixed_roles) == 1
            assert plan.cast.total == 8
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(female_count=8, male_count=0))
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(content_level="aesthetic"))


@pytest.mark.parametrize(
    "level", list(ContentLevel)
)
def test_motion_blur_keeps_finite_background_bands_outside_principal_cap(level):
    document = load_story_document(RECIPES / "motion-blur-photography.yaml")
    resolved = resolve_story_input(
        document,
        InputOverrides(content_level=level, female_count=8, male_count=0),
    )
    for plan in resolved.plans:
        assert plan.cast.scope == "primary_people"
        assert plan.cast.female_count == 8
        assert plan.cast.male_count == 0
        assert plan.cast.principal_total == 8
        assert plan.cast.total is None
        assert (plan.cast.total_min, plan.cast.total_max) == (8, 38)
        assert [
            (band.min, band.max) for band in plan.cast.background_counts
        ] == [(0, 0), (2, 5), (6, 15), (16, 30)]
        permitted = {
            count for band in plan.cast.background_counts
            for count in range(band.min, band.max + 1)
        }
        assert permitted == {0, *range(2, 31)}


@pytest.mark.parametrize("stage", list(StoryStage))
@pytest.mark.parametrize("level", list(ContentLevel))
def test_motion_blur_partitions_removal_and_active_action_rules(stage, level):
    document = load_story_document(RECIPES / "motion-blur-photography.yaml")
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    rules = resolved.rules.text_for(stage)
    assert "载体拖迹从这只手开始" in rules
    assert "保持从手到拖迹再到凝固衣物的一条不间断可见因果链" in rules
    assert "绝不暗示不可见的投掷、画外释放者" in rules

    active_removal = "腾空衣物必须可见地推进当前脱衣"
    explicit_action = "内容等级：在 hardcore 等级中，展示一个明确无误"
    final_release = "照片中的运动只能是最终的手部释放"
    already_cleared = "在接触开始前就已经完全脱离双腿"
    if level == ContentLevel.HARDCORE:
        assert active_removal not in rules
        assert explicit_action in rules
        assert final_release in rules
        assert already_cleared in rules
        assert "主动接触期间，绝不把普通闭环内衣从被占用的腿" in rules
    else:
        assert active_removal in rules
        assert explicit_action not in rules
        assert final_release not in rules
        assert already_cleared not in rules


@pytest.mark.parametrize(
    "filename",
    ["post-layout.yaml", "film-post.yaml", "magazine-cover.yaml", "jav-dvd-wrap.yaml"],
)
def test_visible_copy_language_is_separate_from_recipe_output_requirements(filename):
    recipe = load_story_document(RECIPES / filename)
    reference = next(
        reference for reference in recipe.modules
        if reference.id == "design-visible-copy"
    )
    document = StoryDocument(
        description="An adult presents a printed design on a physical surface.",
        modules=(reference,),
    )
    resolved = resolve_story_input(document, asset_root=RECIPES)
    assert resolved.request.output_language == "chinese"
    assert resolved.quality.frames.checks == ()
    module = next(
        module for module in resolved.modules if module.kind == "visible_copy"
    )
    assert module.parameters.copy_language == "english"
    assert module.parameters.ascii == "required"
    rules = resolved.rules.text_for(StoryStage.FRAMES)
    assert "而不是描述性提示词的语言" in rules
    assert "in precise, fluent Chinese" in rules
    assert "添加字面 ASCII 字符 `: `" in rules
    assert "以字面 ASCII 字符 `;` 结束" in rules
    assert "Frame 的最后一个字符必须是 `;`" in rules
    assert "` ;`" not in rules
    assert "槽位数量、重复出现的位置、允许的载体、排版区域和产品版式均由配方规定" in rules
    assert recipe.requirements.output_languages == ("english",)
    with pytest.raises(StoryConfigurationError, match="output_language"):
        resolve_story_input(recipe, InputOverrides(output_language="chinese"))


@pytest.mark.parametrize(
    "filename,min_words,max_words,requires_ascii",
    [
        ("ming-gongbi-mixi-tu.yaml", 350, 750, False),
        ("tang-guohua-figures.yaml", 450, 1100, False),
        ("edo-warai-e.yaml", 1, 1000, False),
        ("hero-erotic-reinterpretation.yaml", 1, 350, False),
        ("erotic-fantasy.yaml", 1, 1000, False),
        ("surreal-conceptual-portrait.yaml", 600, None, True),
    ],
)
def test_bilingual_recipes_keep_word_and_ascii_checks_english_only(
    filename, min_words, max_words, requires_ascii
):
    document = load_story_document(RECIPES / filename)
    assert resolve_story_input(document).request.output_language == "chinese"
    for language in ("chinese", "english"):
        for level in ContentLevel:
            resolved = resolve_story_input(
                document,
                InputOverrides(output_language=language, content_level=level),
            )
            assert resolved.request.output_language == language
            assert resolved.quality == document.validation
            assert resolved.quality.frames.mode == "report"
            checks = [
                check.model_dump(mode="json")
                for check in resolved.quality.frames.checks
            ]
            assert [check for check in checks if check["type"] == "word_count"] == [
                {
                    "type": "word_count",
                    "when_language": "english",
                    "min_words": min_words,
                    "max_words": max_words,
                }
            ]
            assert [check for check in checks if check["type"] == "ascii"] == (
                [{"type": "ascii", "when_language": "english"}]
                if requires_ascii else []
            )


def test_lifestyle_story_is_social_photography_not_ui() -> None:
    document = load_story_document(RECIPES / "lifestyle-story.yaml")
    brief = story_contract(document)
    normalized = " ".join(brief.split())
    required = (
        "在要求的内容级别下，保留同样精致的社交生活方式摄影语言",
        "独立重述完整人物配置、身份、造型、地点、活动、相机方式、光线",
        "绝不引用其他 画面、前一张图像或之前发生的事",
        "Instagram 和小红书",
        "而非任一应用程序的真实屏幕截图",
        "每日穿搭",
        "咖啡馆探访、城市漫步、周末旅行",
        "严格使用要求数量的成年女性和成年男性",
        "每个人都明确为二十五岁或以上",
        "绝不因受外国启发的服装、活动、建筑、食物、姓名或视觉风格而推断另一种国籍",
        "当指定人物配置为一位女性和零位男性时",
        "使用伸臂自拍、镜面自拍、定时拍摄、三脚架或固定相机",
        "不得虚构附近的朋友、同伴、摄影师、恋人",
        "为每个 主题 选择或创造一个具体场合",
        "地点和活动必须提供具体证据",
        "由附近朋友手持拍摄、眼神接触放松的人像",
        "仅当该朋友属于要求的可见人物配置时可用",
        "仅当该同伴属于要求的可见人物配置时可用",
        "具有一个物理上连贯的倒影且没有额外人物的镜面自拍",
        "定时或固定相机拍摄的全身穿搭人像",
        "当人物配置为一位女性和零位男性时，只能选择伸臂自拍",
        '绝不把视角称作 "nearby-friend"、"companion-taken"',
        "可信的现代手机相机或便携相机光学效果",
        "每条可见手臂或腿必须从肩膀或髋部，经正确关节连续连接",
        "绝不生成脱离、来源不明、重复、融合或多余的肢体",
        "分别描述左腿和右腿",
        '"her legs are parted"（她双腿分开）的整体短语不够',
        "不得在同一姿势中同时组合抬膝、交叉双腿、向前景伸出的腿",
        "绝不能在展示孤立的下肢或脚时隐藏连接关节",
        "避免横跨身体的前景肢体、脚侧极低角度",
        "应简化姿势或移动相机",
        "加入细小的生活痕迹",
        "每个 露骨级 画面 都必须包含明确无误且已经进行中的露骨成年人行为",
        "触碰大腿内侧",
        "当人物配置为一位女性和零位男性时，展示已经进行中的独自自慰",
        "直接刺激她的外生殖器",
        "不得添加伴侣、协助的手、嘴、倒影中的人物",
        "绝不为强化行为而增加参与者",
        "每个 露骨级 画面 都必须直接指明正在动作的手或玩具",
        "被接触的生殖结构，例如阴蒂、外阴",
        "仅有湿润的手指、性唤起、分开的双腿、阴毛",
        "并列的成片备选，而不是按时间顺序排列的步骤",
        "若任一可见肢体无法追溯到其所属身体",
        "应默默剔除并重写",
        "分别描述左腿和右腿后，能确立恰好两条相连的腿",
        '字面短语 "left leg" 和 "right leg"',
        "仅提及脚、膝盖、大腿或笼统的双腿均不满足要求",
        "相机方式自相矛盾",
        "要求英语时，只使用纯英语 ASCII 文字",
        "替代字形、非英语文字和翻译残片",
        '"Instagram" 和 "Xiaohongshu" 这两个词仅用作不可见的艺术指导',
        '绝不在 主题 的标题、情境说明、风格或最终 画面 中写出 '
        '"Instagram" 或 "Xiaohongshu"',
        "应把选定方向转化为可见的摄影、造型、活动、光线、色彩和材料语言",
        "生成字段中不得出现平台名称",
        "每个英语 画面 以 220-300 个单词为目标",
        "保持在 180 至 360 个单词之间，360 为绝对硬上限",
        "统计单词数，若总数超出硬性范围则重写",
    )
    assert not [clause for clause in required if clause not in normalized]
    for forbidden in (
        "应用界面", "个人主页", "用户名", "话题标签", "点赞数", "评论",
        "轮播圆点", "平台标志", "水印", "二维码",
    ):
        assert forbidden in normalized


def test_intimate_liquid_editorial_uses_open_ended_scene_grammar() -> None:
    document = load_story_document(RECIPES / "intimate-liquid-editorial.yaml")
    brief = story_contract(document)
    normalized = " ".join(brief.split())
    compact = "".join(brief.split())
    for obsolete in (
        "overhead-radial-splash-fashion",
        "overhead-intimate-liquid-editorial",
        "high-angle-intimate-liquid-editorial",
    ):
        assert not (RECIPES / f"{obsolete}.yaml").exists()
    pose_ids = [
        token for token in brief.split()
        if len(token) == 4 and token.startswith("P") and token[1:].isdigit()
    ]
    assert pose_ids == [f"P{index:03d}" for index in range(1, 101)]
    # Authored conservation covers every branch, not a selected-level prompt.
    required = """
成人亲密液体动势时尚编辑摄影
多样且符合场景的拍摄视点
固定 高角度俯视 俯拍
高预算、经过完整造型与美术指导的成人 时尚编辑摄影
露骨动作只是画面事件，不得取代时尚叙事
一件 主视觉服装 或一个 主视觉配饰
露骨级 即使下身赤裸
不能只剩 裸体、性玩具和液体
高端成人时尚杂志、奢华美妆大片
业余色情视频截图
不能使用 临床、医疗、法证
时尚感必须在缩略图尺度仍然成立
一个强造型焦点、两个辅助 材质或色彩关系和一项精致美容细节
这是开放式生成语法，不是封闭场景清单
可扩展的创作种子，不是穷举
就可以自由发明未列出的 场景
不把作品限制在固定摄影棚、白色床垫
可控摄影空间
建筑室内
文化与休闲空间
静止交通空间
户外受控场地
水边与浅水空间
物理搭建的幻想空间
场景—液体因果锁
液体不是为了制造喷射效果而额外塞入画面的装饰
优先使用 场所原生且用途明确的来源
器具若不属于该地点的正常设施，就必须改用更合理的器具或更换 地点
不能在温室、街道、屋顶、住宅、雪地、交通工具或文化空间中凭空增加工业雨淋管
只有摄影棚、特效测试间、舞台后场或明确封闭拍摄的布景
储水、低压供水、固定支架、操作或触发方式、防滑承载面和排水路径
如果主要液体来自人物身体或储液式成人玩具，就不要再叠加无关的环境喷水
不要求每张图都有巨大喷射装置或爆炸水冠
自然呈现液体从出现到消失的完整流程
场所用途说明液体为何 存在
合理的私密性、清洁条件和可退出性
不能用“艺术装置”“时尚拍摄”或“定时释放” 作为万能借口
液体来源—地点适配矩阵
默认只选择私人浴室、酒店浴室、独立湿房、私人 水疗套间
完整防水保护层和吸水护理垫的私人卧室床、酒店套房床
此处是严格地点白名单
不得放在中庭、温室、开放广场、街道、稻田或农地、普通屋顶
添加 私人、锁闭、僻静、专用、封闭
不能使其合规
只使用该地点正常存在的一套供水系统
不得让水枪、喷头、 水桶、倾倒板或实验器皿仅因造型新奇
不得在自然场景中加入水枪式成人道具来制造额外喷射
自然雨只能直接落在露天空间、无顶庭院、开启的天窗或明确敞开的屋面缺口下
完整 玻璃顶、封闭车顶、实体屋檐或密闭窗户外侧的雨水
不能同时穿过 屏障落到室内人物或地面
液体的实际落点必须连接到画面可见的地漏
只有普通洗手间而没有地漏时，不能让大量液体在地面聚集
床上人物体液场景必须直接显示一套普通且可信的床面保护
完整包住床垫的防水床笠或 医用级防水保护罩
一至两块大尺寸吸水护理垫、厚浴巾或可清洗防水毯
不得让未保护的床垫、 普通羽绒被、枕头或地毯承接大量液体
不能在床头、床垫或天花凭空安装地漏、喷头阵列
床上的精液只有 在运行请求包含至少一名可见成年男性时才能出现
零男性请求绝不生成精液、画外男性或无来源白色液体
可以在真实来源基础上形成夸张、醒目的弧线
可以跨过受保护床面的较大部分
不能射向天花、越过保护层落到 无关区域
床上可使用手指或一件常规成人玩具完成主要 动作，但不增加喷水器具
第一步固定一个不可更改的“来源—地点”配对
不得先选其他地点再写成 改造、租用、封闭、清空或临时布置后的湿景棚
不能由装卸区、仓库、中庭、温室、舞蹈室、屋顶、 交通工具或其他空间改名而来
任何不在白名单中的地点都必须改选场所原生环境水或 日常清水工具
身体液体允许现实基础上的编辑摄影夸张
更高但仍受重力控制的弧线、密集冻结液滴
戏剧化、 强劲、高弧线、密集、放射状、爆发式喷流
强化弧线、液滴密度、冻结时机、放射状形态
绝不能把体液变成加压管路
夸张重点放在喷射形态、液滴分离、姿势、表情、镜头角度、灯光
人体液体可以承担径向构图的主要视觉动势
不能穿过身体或物体、逆重力改变方向
不得解释自己如何满足 任务说明
不得输出 自检、幕后安排、拍摄后清理计划或规则术语
第一句必须直接从具体地点、人物或相机视点开始
不得先写衣着锁、主题 编号、画面 编号、标题、许可声明
衣着锁放在自然摄影描述之后
露骨级 的主要动作与接触点必须直接可见
不能 被衣摆、身体、手掌、阴影、水花、道具或构图遮住
不得用手臂紧张、衣物下的动作、 水面波纹、表情或文字声明间接暗示
中央水冠、离体高弧、径向 爆发式喷流 或明确 喷流 只用于从两腿之间正确生殖器开口
人物不必躺在床上
拍摄角度是开放变化轴
不把 高角度俯视、正上方俯视 或正俯拍设为默认
垂直高度、俯仰角、绕人物方位、拍摄距离、焦段、裁切尺度和主体落点
70–90 度 正上方俯视 或顶视
25–65 度 高位斜视 高位斜拍
接近水平的 平视 平视
低角度仰视 低机位
侧面轮廓 侧面、前侧四分之三视角 前侧三分之四
近距离 美妆、材质 或 动作细节
场景—姿势—机位匹配矩阵
受保护床面：轮换对角仰卧桥式
不能每次都仰卧张腿
浴缸与水疗床：轮换沿椭圆长轴半躺
必须避开高缸壁 对动作区域的遮挡
淋浴间与独立湿房：轮换墙面单手支撑的站立弓步
湿滑地面禁止无支撑单脚站立
私人泳池与浅水区：轮换仰漂星形
不得让水面反光遮没脸和动作起点
不固定为 50mm 正俯拍
100 种高感官刺激姿势库
每个 画面 只选择一个主姿势
跨 主题 轮换六大姿势家族
相邻 主题 不得重复同一姿势家族
不得连续生成深蹲、仰卧张腿、跪姿后仰或 站立后弯
机位在 正上方俯视 顶视、高位斜视 高位斜拍、平视 平视
低角度仰视 低机位、 侧面轮廓 侧面
水面线 水面高度和近距离 细节
24–35mm 环境广景、40–55mm 全身中景、60–85mm 紧凑人像与动作研究
85–105mm 美妆 或材质细节
不能隔着大腿、缸壁、床头、手臂、水花或反光拍摄
不强制双臂水平展开
不强制人物仰卧
每个 主题 只选择一个主要液体来源家族
环境清水：自然雨水、向下落水、瀑布薄幕
手持清水工具：只用于向下流动或倾倒的低压软水管
储液式成人玩具
女性排尿
从可见尿道口开始
不得把尿液写成来自阴道
女性阴道液体
从可见阴道口或外阴区域开始
主视觉喷射起点锁
喷射起点就必须在镜头中清楚位于该人物两腿之间 的生殖器部位
从可见的正确解剖开口连续连接到液柱或液滴
被闭合、 交叉双腿遮住的位置发出
相机、姿势、水花和道具都不得遮挡这个起点
环境清水、 手持清水工具和储液式成人玩具只能形成下落
不得形成主要 喷流、喷雾、高弧线 或 爆发式喷流
任何人体液体喷射都从镜头中清楚可见、位于两腿之间的正确生殖器解剖开口开始
男性精液
运行请求包含至少一名可见成年男性
从该男性可见生殖器开始
液体形态在 主题 和 画面 间轮换
软水管或手持喷头可在 情色级 或 露骨级 中作为自愿外部自慰工具
不得把高压水流、硬质喷嘴或软管插入身体
性玩具是可选变化轴，不是每个 主题 的强制道具
一件主要性玩具或由多个不可分离部件组成的一套单一系统
不能只写 笼统的性玩具
掌心 子弹型振动器、短柄 棒式振动器、指套 振动器
直形或弯形 硅胶假阴茎
带宽大限位底座的 肛塞
吸盘底座假阴茎
单件 穿戴式假阴茎带
具有可见透明储液腔、挤压球、短导管和明确出液口
只在出液口附近流出或滴落
带可见拉环或回收绳的 跳蛋
不得整批重复透明 假阴茎、银色 子弹型 或黑色 棒式
性玩具—场景匹配
吸盘不能直接粘在柔软床垫、床单或枕头上
不得让市电电线、插线板、充电器或非防水 遥控器接触潮湿区域
浴缸、泳池和浅水区只使用整体防水
全部部件必须属于一个可追踪系统
性玩具—姿势—机位匹配
持玩具的手、 玩具头和外部接触点三者必须同时可见
必须显示玩具底座、进入方向和解剖接触边界
同时显示 吸盘、刚性固定面、玩具轴线、身体承重点和单一接触位置
同时看见储液腔、导管或内部通路、出液口、手部触发和液体落点
不能只靠文字 声明体内藏有看不见的玩具
普通 振动器、假阴茎、塞具、棒式 或 可穿戴玩具 不会自行喷液
普通玩具表面的 润滑剂只能形成贴附薄层、拉丝或滴落
禁止尿道插入、宫颈穿透
肛门玩具必须有清楚可见且大于插入部分的限位底座
审美级 不出现可识别性玩具
情色级 最多使用一件仅作外部接触的玩具
露骨级 可从外部刺激、单一阴道或肛门插入
连续十个包含 性玩具的 主题 至少覆盖五个玩具家族
相邻玩具 主题 不得重复玩具家族、材质、颜色、固定方式和姿势组合
审美级：
情色级：
露骨级：
主表演者必须实际保留一至两件透明、半透明、湿贴、敞开、撩起或 半褪下
主表演者下身必须完全赤裸
当前 内容等级 唯一正确且逐字输出的衣着锁
每个 画面 必须表现明确成人裸露和一个清楚可见的主要露骨动作
裸体、湿衣或 挑逗姿势代替 露骨级 动作
外部自慰、一至两根手指的单一插入
本身也可以独立作为该 画面 唯一的主要 露骨级 液体动作
环境清水、普通倾倒清水和其他安全舞台液本身绝不能替代 露骨级 动作
必须同时清楚显示上述外部自慰、单一插入或单一成人接触之一
仅把玩具靠近身体、让液体流过裸体不算 露骨级 动作
同一解剖中心可有与主要动作直接相关的辅助 手部接触
整张 画面 只描述这一类别的流动
不得同时滴落、喷射、飞溅、形成涟漪或与主要液体混合
不得在 同一 画面 同时出现尿流与阴道液体
不能用 私人、 锁闭、僻静 或 封闭 修饰温室
禁止冷冻舱、冷库、桑拿、高温房、干冰、液氮
各自唯一且前后一致的精确整数年龄
同一 画面 出现两个不同年龄
人物年龄统一保持在 25–34 岁的年轻成年人范围
轮换 25–29 岁和 30–34 岁两个子段
连续十个 主题 至少覆盖六个不同整数年龄
年轻不等于幼态
娇小纤细、修长瘦削、柔软丰满、圆润丰腴
不得默认所有成年人拥有平坦腹部、 细腰、长腿和年轻紧致皮肤
脸部设计轮换椭圆脸、圆脸、方脸、长脸、心形脸
发型必须同时轮换长度、纹理、结构和颜色
不得让每个 主题 都使用黑色波波头
妆容按人物肤色、脸型、服装和地点独立设计
不能只生成 连体衣、紧身练功服 或泳装
每连续十个 主题 至少覆盖六个不同整数年龄、六种体型
发现整套造型相似时，优先改换年龄段、体型、 脸型和发型
相邻 主题 至少改变人物造型档案、地点家族、承载面
只有以场所原生环境水为主的 审美级 或 情色级 批次才要求覆盖五个广义地点家族
露骨级 或任何人物身体液体、玩具储液批次
白名单内至少四种兼容空间子型
受保护私人卧室床和 受保护酒店套房床
允许多个 主题 属于 同一广义湿区家族
人体液体不承担 六种水型配额
不得为 满足多样性配额牺牲地点功能
至少覆盖六种姿势家族、五种视点家族、五种绕人物方位、四档焦段
同一视点家族最多出现两次
规则优先级从高到低依次为：场景功能与物理逻辑
必须舍弃更奇怪的地点、器具、水型或构图
只有一个活动液体来源，且地点本来就适合该来源
单一来源约束：每幅画面只能有一个可见的喷流、流束、喷雾、倾倒或液体运动事件
不得把两个来源的液体组合、交叉、合并、汇合或同步
所有淋浴喷头、软管、水龙头、环境喷雾和储液玩具都应明确处于关闭状态
完整防水床面和吸水层清楚可见时才属于白名单
人体液体可以有强烈、夸张、径向的编辑摄影表现
不变成管道级、工业级或房间级水量
环境水或储液玩具液体单独不能构成 露骨级
仅让储液玩具向裸体流液、让液体落在身体上
必须重写
场景合理性高于地点、水型、器具和构图多样性
宁可重复兼容湿区，也不创造古怪组合
只在正文结尾逐字输出当前 内容等级 的一条衣着锁
内容等级约束：准确采用运行请求的内容等级
露骨级请求的结尾只能使用“HARDCORE WARDROBE LOCK”
绝不能使用“AESTHETIC WARDROBE LOCK”或“EROTIC WARDROBE LOCK”
相邻 主题 不重复姿势 家族、双腿关系、支撑手和相机方位
轮换 正上方俯视、高位、平视、低角度仰视、侧面轮廓、四分之三视角
不把每张 图都拍成 高角度俯视、50mm、人物居中的俯拍全身照
只保留一件主要玩具或一套不可分离系统
普通玩具不主动喷液
湿区玩具防水且 无市电连接
任何玩具都不进行尿道插入
画面都保持高预算成人时尚编辑摄影
不输出临床、医疗、法证、 偷拍、网络摄像头、闭路监控、自拍或普通色情记录美学
人数约束：准确采用请求中的女性和男性人数
请求一名女性和零名男性，就表示恰好只有一名可见成年女性
没有男性、男性身体部位、画外伴侣、暗示存在的男性或精液
不得为了使用某种玩具、动作、液体来源、姿势或相机构图而增加伴侣
在场约束：请求人数是必须准确出现的人数，不是人数上限或可选角色
每名请求成年人都必须在每幅画面中实际可见
请求一名女性和一名男性，就表示每幅画面都恰好有一名可见成年女性和一名可见成年男性
不得漏掉任何一人、将任何一人移至画外
多样性退化为同一白色平台上的换装
把喷嘴、软管、控制器、纸钞、粉色腕带、白色服装
每个 主题 的必选物
"""
    missing = [
        text for text in required.strip().splitlines()
        if "".join(text.split()) not in compact
    ]
    assert not missing, missing
    wardrobe_literals = (
        "“AESTHETIC WARDROBE LOCK: Every visible adult wears one to three "
        "intentional fashion garments whose opaque fabric fully covers all nipples, "
        "external genitals, pubic hair, and anus; no transparent panel, opening, "
        "wet-clinging area, or shifted edge reveals those regions.”",
        "“EROTIC WARDROBE LOCK: The featured adult woman visibly retains one or "
        "two sheer, translucent, open, wet-clinging, lifted, or partially lowered "
        "fashion garments, with each garment and its exact resting position "
        "readable; breasts, nipples, buttocks, pubic hair, and one external genital "
        "region may be visible, while no insertion or explicit partnered sex occurs.”",
        "“HARDCORE WARDROBE LOCK: The featured adult woman's lower body is bare, "
        "with no skirt, trousers, shorts, underwear, opaque bodysuit, or swimwear "
        "covering her vulva, pubic hair, buttocks, anus, or current action area; "
        "only one minimal upper garment plus zero to four accessories, hosiery "
        "pieces, or footwear items may remain away from that area.”",
    )
    for literal in wardrobe_literals:
        assert literal in normalized


def test_indoor_pure_desire_editorial_has_complete_pose_library() -> None:
    document = load_story_document(RECIPES / "indoor-pure-desire-editorial.yaml")
    brief = story_contract(document)
    compact = "".join(brief.split())
    pose_ids = [
        token for token in brief.split()
        if len(token) == 5 and token.startswith("PD") and token[2:].isdigit()
    ]
    assert pose_ids == [f"PD{index:03d}" for index in range(1, 101)]
    required = """
室内纯欲成人时尚摄影 主题
纯欲不是幼态，也不是只使用白色内衣
所有场景必须位于真实、封闭、可进入且可安全退出的室内
服装、服饰、妆容、打扮和发型均为自由变化轴
不把纯欲固定为白色
PD001 仰卧，双膝弯曲，双脚宽距踩稳
PD050 深蹲，双大腿与床面平行
PD100 站姿，躯干直立，一条腿向侧方伸展
每个 画面 只选择一个主姿势
正面视角 正面
侧面视角 纯侧面
背面视角 正后方
前侧四分之三视角 前侧三分之四
后侧四分之三视角 后侧三分之四
正上方俯视 顶视
高位斜视 高位斜拍
平视 平视
低角度仰视 低机位
美妆或动作细节 近景
倾斜机位 荷兰角
相机绕镜头轴有意倾斜约 5–20 度
不得超过约 25 度
过肩视角 肩后视角
头侧或脚侧轴线视角
地面反射 地面反射构图
画中镜面 镜中框构图
前景柔性遮幅
室内环境广景
长焦压缩
侧面轮廓剪影
中央消失点
高低层构图
编辑式裁切
人物必须回头、转为可读侧脸或借可信镜面显示表情
十个 主题 的批次必须至少各出现一次 正面视角、侧面视角、背面视角
任一视角家族最多出现 两次
十个 主题 还必须至少包含一次 倾斜机位、过肩视角
审美级：
情色级：
露骨级：
准确运行人数
运行请求的人数是精确人数，不是上限
每个最终 画面 输出为请求语言的一段自然、连续
不输出标题、主题 编号、画面 编号、 姿势编号
"""
    missing = [
        text for text in required.strip().splitlines()
        if "".join(text.split()) not in compact
    ]
    assert not missing, missing


def test_restroom_brief_requires_forward_leaning_deep_squat() -> None:
    brief = story_contract(load_story_document(
        REPOSITORY_ROOT / "story-inputs" / "recipes" / "piss.yaml"
    ))
    normalized = " ".join(brief.split())

    assert "骨盆居中、双腿紧凑且趋于并拢但不互相接触的低位蹲姿" in normalized
    assert "双膝内缘和双鞋内缘之间形成等宽、狭窄、连续的竖直空隙" in normalized
    assert "躯干从髋关节整体向前折叠到胸腹近乎平行地面" in normalized
    assert "胸腹自然压在大腿上方" in normalized
    assert "肩膀在三维位置中越过膝盖" in normalized
    assert "不能仅低头、弯颈、把头伸向视点或单独伸出手机来假装前倾" in normalized
    assert "禁止抬高臀部变成站立俯身" in normalized
    assert "人物上身直立、后仰或只弯颈低头" in normalized
    assert "just outside the corresponding rim of a Chinese porcelain squat toilet" in normalized
    assert "aimed upward through a rectilinear 35mm perspective" in normalized
    assert "anatomically correct adult proportions" in normalized
    assert "physically plausible low-angle foreshortening" in normalized
    assert "a head visibly smaller than the shoulder span and torso" in normalized
    assert "torso nearly horizontal to the floor" in normalized
    assert "the pelvis centered over the midpoint between the feet" in normalized
    assert "both upper thighs anatomically distinct and closely paired" in normalized
    assert "the thighs descending almost parallel with only a slight medial taper" in normalized
    assert "the inner knee gap and inner shoe gap equal" in normalized
    assert "no wider than one forefoot width" in normalized
    assert "each forward-facing kneecap centered directly above the second toe" in normalized
    assert "both shins forming close vertical parallel columns" in normalized
    assert "with a narrow straight gap between them" in normalized
    assert "both shoe centerlines aimed straight forward and parallel to one another" in normalized
    assert "to the toilet's front-to-rear axis" in normalized
    assert "toe spacing exactly equal to heel spacing" in normalized
    assert "neutral anatomical rotation from hips through ankles" in normalized
    assert "shoulders ahead of the knees" in normalized
    assert "head aligned naturally with the folded spine" in normalized
    assert "without thrusting toward it" in normalized
    assert "the viewpoint is visually absent and leaves the composition unobstructed" in normalized
    assert "禁止写 “unseen camera”、“hidden camera”、“floor camera”" in normalized
    assert "the same adult keeps the exact age, body build, hairstyle, makeup" in normalized
    assert "upper garments, fully lowered lower garments, accessories" in normalized
    assert "matching pair of shoes" in normalized
    assert "and squat-toilet design" in normalized
    assert "胸腹近乎平行地面" in normalized
    assert "骨盆中心位于双脚中点正上方" in normalized
    assert "双腿紧凑、趋于并拢但不互相接触" in normalized
    assert "两条大腿从髋部向下几乎平行" in normalized
    assert "双膝内缘之间与双鞋内缘之间保留同一条狭窄空隙" in normalized
    assert "两条小腿形成彼此靠近的垂直平行柱及窄直缝" in normalized
    assert "每侧髌骨中心必须位于对应鞋第二脚趾正上方" in normalized
    assert "两只鞋的纵向中心线笔直朝前、彼此平行并平行于蹲便器长轴" in normalized
    assert "脚尖间距等于脚跟间距" in normalized
    assert "髋关节、膝关节和踝关节保持中立旋转" in normalized
    assert "英文 画面 不得复述这些错误姿势名称" in normalized
    assert (
        "删除 “M-shaped legs”、“frog squat”、"
        "“diamond-shaped legs”、“wide squat”"
    ) in normalized
    assert (
        "“pigeon-toed”、“inward-pointing toes”、"
        "“turned-in feet” 与 “toe-in stance”"
    ) in normalized
    assert "头发、项链、上衣下摆和松散布料受重力垂向地面视点" in normalized
    assert "正常成人头身比、肩宽、躯干长度及四肢比例" in normalized
    assert "使用 35 mm 等效直线投影，保持自然低角度透视" in normalized
    assert "鞋脚和小腿比臀胯、大腿适度显大" in normalized
    assert "肩膀和胸腹或背部保持主体体量" in normalized
    assert "透视只改变各部位的合理投影大小" in normalized
    assert "正确的视觉层级是下方鞋脚略大" in normalized
    assert "鞋脚占据大半画面、腿异常粗长、躯干塌成短块" in normalized
    assert "真实头高约为完整身高的七分之一至八分之一" in normalized
    assert "投影宽度必须小于可见肩宽和躯干宽度" in normalized
    assert "双肩、胸腹和骨盆必须清楚可见" in normalized
    assert "头部不是距离视点最近的物体" in normalized
    assert "头宽达到或超过肩宽、头遮挡身体、头大身小" in normalized
    assert "25–34 岁的年轻成年人范围内选择一个明确整数年龄" in normalized
    assert "35–49 岁的成熟成年人范围内选择一个明确整数年龄" in normalized
    assert "50–64 岁的年长成年人范围内选择一个明确整数年龄" in normalized
    assert "65–79 岁的老年成年人范围内选择一个明确整数年龄" in normalized
    assert "50 岁以上人物必须显示与具体年龄相符的面部细纹" in normalized
    assert "不得让整批年龄集中在 25–39 岁" in normalized


def test_restroom_brief_varies_interactions_and_uses_ground_camera() -> None:
    brief = story_contract(load_story_document(
        REPOSITORY_ROOT / "story-inputs" / "recipes" / "piss.yaml"
    ))
    normalized = " ".join(brief.split())

    assert "手机不是必需品" in normalized
    assert "已经褪下的裤子、内裤或裙子是静止衣物" in normalized
    assert "低头并用一只手撩起上衣" in normalized
    assert "从卷筒抽取厕纸" in normalized
    assert "进行明确擦拭" in normalized
    assert "整理、梳开或轻拉阴毛" in normalized
    assert "一至两根清楚归属同一只手的手指" in normalized
    assert "进行可见外部自慰" in normalized
    assert "视点位于中国式蹲便器对应外缘的地面高度" in normalized
    assert "从地面向上倾斜 35–55 度" in normalized
    assert "画面底缘必须出现紧邻视点的陶瓷蹲便器边缘" in normalized
    assert "禁止手持、自拍、腰部高度、膝盖高度、眼平、俯拍" in (
        normalized
    )
    assert "画面任何位置都不得出现相机机身、镜头、手机拍摄设备" in normalized
    assert "摄影机遥控器、三脚架或任何会暗示拍摄设备进入画面的道具" in normalized
    assert "所有裤子、短裤、内裤和裙子都必须已经完全离开腰部" in normalized
    assert "统一褪到膝盖以下、小腿或脚踝处并清楚可见" in normalized
    assert "不得只解开、掀起或停留在大腿中段" in normalized
    assert "这些下装保持静止并与双手分离" in normalized
    assert "不得被手提回膝盖或大腿" in normalized
    assert "季节至少轮换盛夏、春秋和寒冬" in normalized
    assert "场合至少轮换都市日常、办公室通勤、正式晚宴、夜店派对" in normalized
    assert "服装颜色不得默认黑色或连续重复单色" in normalized
    assert "每个 主题 写清主色、辅色和材质" in normalized
    assert "发型至少轮换精灵短发、齐耳短发、直长发、自然卷" in normalized
    assert "妆容至少轮换素颜、透明自然妆、办公室柔和妆、复古红唇" in normalized
    assert "表情至少轮换专注、从容、自信、调皮、轻笑、惊喜" in normalized
    assert "鞋履至少轮换平底凉鞋、细带高跟凉鞋、经典尖头高跟鞋" in normalized
    assert "配饰每人选择一至三件" in normalized
    assert "相邻 主题 不得重复相同视角方向、季节、场合、服装类别、主色" in normalized
    assert (
        "不得在 画面 末尾追加以 "
        "“No”、“Without”、“Neither” 或 “Absent” 开头"
    ) in normalized
    assert "发布每个英文 画面 前逐字扫描" in normalized
    assert "确认成对鞋履均穿在双脚上" in normalized
    assert "嵌入地面的中国式陶瓷蹲便器" in normalized
    assert "中央椭圆便池与排污口清楚可见" in normalized
    assert "左右各有带防滑纹的承重脚踏区" in normalized
    assert "不得替换成西式坐便器、独立地漏或长排水沟" in normalized
    assert "左右脚或鞋分别完整踩在中国式蹲便器左右防滑脚踏区" in normalized
    assert "落入正下方中国式蹲便器的中央陶瓷便池和排污口" in normalized
    assert "central oval bowl, visible waste outlet, rear flush channel" in normalized
    assert "two anti-slip foot platforms supporting the complete matching left and right shoes" in normalized
    assert "蹲便器相关内容只使用以下英文词汇" in normalized
    assert "正面、左侧、右侧、背面或三分之四方向中明确选择一个" in normalized
    assert "左侧或右侧视角位于蹲便器对应侧缘 80–100 度" in normalized
    assert "背面视角位于蹲便器后缘和脚跟后方 160–180 度" in normalized
    assert "不得在同一 画面 混合正面、侧面和背面" in normalized
    assert "整批必须均衡覆盖 正面视角、左侧视角、右侧视角" in normalized
    assert "背面视角、前侧四分之三视角 和 后侧四分之三视角" in normalized
    assert "VIEW DIRECTION LOCK: front view from the squat toilet's front rim" in normalized
    assert "VIEW DIRECTION LOCK: left side view from the squat toilet's left rim" in normalized
    assert "VIEW DIRECTION LOCK: right side view from the squat toilet's right rim" in normalized
    assert "VIEW DIRECTION LOCK: rear view from the squat toilet's rear rim" in normalized
    assert "VIEW DIRECTION LOCK: front three-quarter view" in normalized
    assert "VIEW DIRECTION LOCK: rear three-quarter view" in normalized
    assert "最后一句必须正面描述可见的蹲便器陶瓷、脚踏纹、地砖、顶灯" in normalized


def test_restroom_plans_preserve_age_and_two_frame_view_cycles() -> None:
    resolved = resolve_story_input(
        load_story_document(RECIPES / "piss.yaml"),
        InputOverrides(theme_count=13, frames_per_theme=2),
    )
    ages = ("25–34", "35–49", "50–64", "65–79")
    views = (
        ("front view", "left side view"),
        ("right side view", "rear view"),
        ("front three-quarter view", "rear three-quarter view"),
    )

    assert len(resolved.plans) == 13
    for index, plan in enumerate(resolved.plans):
        assert plan.entry is not None
        assert plan.entry.id == f"slot-{index % 12 + 1:02d}"
        age = ages[index % 4]
        assert age in " ".join(plan.entry.themes)
        assert age in " ".join(plan.entry.frames)
        assignment = plan.entry.frame_assignment
        assert assignment is not None
        assert assignment.frames_per_theme == 2
        assert [slot.frame_id for slot in assignment.slots] == ["F01", "F02"]
        for slot, view in zip(assignment.slots, views[index % 3], strict=True):
            assert f"VIEW DIRECTION LOCK: {view} from" in " ".join(slot.rules)


def test_confined_exhibition_fantasy_has_safe_scene_catalog() -> None:
    brief = story_contract(load_story_document(
        REPOSITORY_ROOT
        / "story-inputs" / "recipes"
        / "confined-exhibition-fantasy.yaml"
    ))
    normalized = " ".join(brief.split())
    scenes = re.findall(r"\b\d{3}\. .*?(?=\s\d{3}\. |\n|$)", brief)

    assert len(scenes) == 100
    assert len(set(scenes)) == 100
    assert [int(scene[:3]) for scene in scenes] == list(range(1, 101))
    assert all("围观者" in scene for scene in scenes)
    assert all(
        any(
            pose in scene
            for pose in (
                "折叠",
                "对折",
                "卷曲",
                "收膝",
                "折膝",
                "前倾",
                "翘臀",
                "抬臀",
                "臀部",
                "大字型",
                "四点支撑",
                "四角支撑",
                "四肢撑向",
                "四角伸展",
                "四肢伸展",
            )
        )
        for scene in scenes
    )
    assert "总人数 = female_count + male_count 为 4–8" in normalized
    assert "female_count 至少为 2、male_count 至少为 1" in normalized
    assert "女性围观者人数 = female_count - 1" in normalized
    assert "男性围观者人数 = male_count" in normalized
    assert "保证围观群众同时有女性和男性" in normalized
    assert "不得增加请求之外的人物、背景脸、身体、手脚、镜中人物" in normalized
    assert "站在空间开口或安全边界之外" in normalized
    assert "静止、通风、照明充分且出口保持开启" in normalized
    assert "车辆必须停稳、熄火、钥匙移除" in normalized
    assert "任何箱体、柜体、舱室或隔间都不得上锁" in normalized
    assert "真实摄影师在可控私人场地中拍到的一次高预算编辑摄影" in normalized
    assert "皮肤、织物、金属、木材和软垫各有真实质感" in normalized
    assert "不是不可能的关节、复制粘贴式表情、过度锐化、塑料皮肤或堆砌提示词" in normalized
    assert "400–680 个英文单词" in normalized
    assert "四人场景优先控制在 420–540 个单词" in normalized
    assert "每增加一人最多增加 30 个单词" in normalized
    assert (
        "不得使用 “the same”、“identical”、"
        "“again”、“remains unchanged”"
    ) in normalized
    assert "提交前逐词扫描这些禁用短语" in normalized
    assert "不向前文回指，也不引用另一幅画面" in normalized
    assert "每个围观者最多使用一个简洁句子" in normalized
    assert "不输出 `LOCK`、“schema”、公式、检查步骤" in normalized
    assert "把人数算术留在内部规划中" in normalized
    assert "前两句自然写明准确总人数" in normalized
    assert "逐项写出：上身单品、下身单品或其明确缺席" in normalized
    assert "主色、辅色、材质、鞋履以及一至四件配件" in normalized
    assert "不得连续使用同一件黑色蕾丝内衣" in normalized
    assert "材质轮换哑光棉、丝绸、缎面、雪纺、薄纱、网眼、蕾丝" in normalized
    assert "相邻 主题 的主色、辅色、材质和服装类别均不得重复" in normalized
    assert "细框眼镜、粗框眼镜、无度数彩色镜片、窄丝巾、长丝巾" in normalized
    assert "丝巾只能松系在颈部、头发、手腕或腰侧" in normalized
    assert "至少包含五项同时可见的线索" in normalized
    assert "左右略不对称的眉形" in normalized
    assert "清晰瞳孔和视线目标" in normalized
    assert "不使用风格化啊嘿颜、完全上翻眼睛、失焦瞳孔" in normalized
    assert "衣服数量较少但保持关键部位完全不透明遮盖" in normalized
    assert "一件贴身连体衣，或两至三件组成的极简性感造型" in normalized
    assert "必须保留一至两件透明、半透明、湿贴、敞开或半褪下" in normalized
    assert "必须清楚写出衣物停留位置" in normalized
    assert "表情保持清醒、主动、聚焦和解剖自然" in normalized
    assert "两膝与两前臂形成宽而稳定的四点支撑" in normalized
    assert "骨盆明显高于肩线约半个躯干厚度" in normalized
    assert "肘膝保留自然轻屈" in normalized
    assert "不要求达到关节极限或同时触及最远角点" in normalized
    assert "英文 标题 以 `FOLDED - ` 开头" in normalized
    assert "标题 以 `RAISED HIPS - ` 开头" in normalized
    assert "标题 以 `SPREAD EAGLE - ` 开头" in normalized
    assert "不在正文输出前缀解释或姿势锁" in normalized
    assert "实际距离必须适合所选地点，不写固定米数" in normalized
    assert "3 人可用 2+1 或 1+2" in normalized
    assert "4 人可用 2+2 或 1+2+1" in normalized
    assert "5 人可用 2+2+1" in normalized
    assert "6 人可用 2+2+2 或 3+2+1" in normalized
    assert "7 人可用 3+2+2" in normalized
    assert "每个 画面 的前 180 个英文单词内" in normalized
    assert "完整开口内只出现主表演者、承重垫和内部表面" in normalized
    assert "开口中央、主表演者正后方和四肢间负空间保持为清楚可见的空内部背景" in normalized
    assert (
        "不得只写 “spectators are outside”、"
        "“safe distance” 或 “visible gaps”"
    ) in normalized
    assert "主表演者及其承重垫完整位于开口平面内侧" in normalized
    assert "全部围观者的头、肩、躯干、手臂和双脚完整位于开口平面外侧" in normalized
    assert "不能在投影上出现在黑暗舱体、柜体或箱体内部" in normalized
    assert "一条连续、无遮挡的外部地面或走道隔离带" in normalized
    assert "其投影高度约占画面高度的 8–15%" in normalized
    assert "每名围观者占用一个独立轮廓槽位" in normalized
    assert "头部与相邻头部之间至少保留一个可见头宽" in normalized
    assert "背景包围其轮廓三侧" in normalized
    assert "采用开口外侧 35–45 度的斜向视点" in normalized
    assert "不得把任何围观者安排在主表演者正后方" in normalized
    assert "若所选场景无法在 35–50 mm 视角中同时容纳请求人数" in normalized
    assert "每个 画面 最多一人指点、最多一人手拢嘴边" in normalized
    assert "不得让所有人同时瞪眼、张嘴或摆出相同手势" in normalized
    assert "主表演者占画面高度或宽度约 50–68%" in normalized
    assert "允许离焦随距离自然增加" in normalized
    assert "每名围观者拥有不同的脸、发型、服装辅色、站位" in normalized
    assert "多数视线落在主表演者" in normalized
    assert (
        "允许在英文 画面 中使用 "
        "“camera”、“lens”、“aperture”、“shutter”"
    ) in normalized
    assert "一个主导实景光源、一个克制补光或反射来源" in normalized
    assert "35–50 mm 等效镜头、f/4–f/5.6 光圈" in normalized
    assert "第一层是主表演者的脸、眼神和完整姿势轮廓" in normalized
    assert "第二层是狭小空间边界、受压材质与开启出口" in normalized
    assert "第三层是较小、稍柔但仍可辨识的围观者" in normalized
    assert "细小毛孔、柔软汗毛、轻微色差、局部潮红" in normalized
    assert "高光随皮肤曲面缓慢滚落" in normalized
    assert "构图采用略微偏心的编辑摄影瞬间" in normalized
    assert "每个 画面 至少描写三项材质—身体—空间接触证据" in normalized
    assert "臀部使汽车座垫或床垫产生可信形变" in normalized
    assert "主题标题 前缀与唯一姿势家族一致" in normalized
    assert "最终 画面 只保留可渲染画面正文" in normalized


@pytest.mark.parametrize("batch_size", [1, 2])
def test_confined_requires_three_themes_per_run_not_per_provider_batch(batch_size):
    document = load_story_document(RECIPES / "confined-exhibition-fantasy.yaml")
    resolved = resolve_story_input(
        document, InputOverrides(theme_batch_size=batch_size)
    )
    assert resolved.request.theme_count == 3
    assert resolved.runtime.theme_batch_size == batch_size
    assert document.requirements.theme_count is not None
    assert document.requirements.theme_count.min == 3
    assert [plan.entry.id for plan in resolved.plans] == [
        "folded-emotion-01", "raised-hips-emotion-02", "spread-eagle-emotion-03"
    ]
    for theme_count in (1, 2):
        with pytest.raises(StoryConfigurationError, match="theme_count"):
            resolve_story_input(
                document,
                InputOverrides(
                    theme_count=theme_count, theme_batch_size=batch_size
                ),
            )


def test_confined_plans_preserve_independent_pose_and_emotion_cycles() -> None:
    resolved = resolve_story_input(
        load_story_document(RECIPES / "confined-exhibition-fantasy.yaml"),
        InputOverrides(theme_count=31),
    )
    families = ("folded", "raised-hips", "spread-eagle")
    prefixes = ("FOLDED - ", "RAISED HIPS - ", "SPREAD EAGLE - ")
    emotions = (
        "主动挑逗", "羞耻但享受", "得意炫耀", "从容自信", "调皮邀请",
        "紧张兴奋", "惊讶后微笑", "专注沉浸", "慵懒满足", "大胆直视",
    )

    assert len(resolved.plans) == 31
    for index, plan in enumerate(resolved.plans):
        assert plan.entry is not None
        assert plan.entry.id == (
            f"{families[index % 3]}-emotion-{index % 10 + 1:02d}"
        )
        assert f"`{prefixes[index % 3]}`" in " ".join(plan.entry.themes)
        assert emotions[index % 10] in " ".join(plan.entry.themes)
        assert emotions[index % 10] in " ".join(plan.entry.frames)


def test_rebuilt_inputs_have_explicit_stage_and_level_contracts() -> None:
    for filename in ("avantgarde.yaml", "snofs.yaml", "tentacle.yaml"):
        document = load_story_document(RECIPES / filename)
        assert document.description
        assert document.authoring.themes.common
        assert document.authoring.frames.common
        for level in ContentLevel:
            resolved = resolve_story_input(
                document, InputOverrides(content_level=level)
            )
            assert resolved.request.content_level == level
            for stage in StoryStage:
                authored = getattr(document.authoring, stage.value)
                for rule in authored.selected(level):
                    assert rule in resolved.rules.text_for(stage)


def test_story_inputs_do_not_override_run_level_cast_or_frame_semantics() -> None:
    film_document = load_story_document(RECIPES / "film-post.yaml")
    film_post = story_contract(film_document)
    assert "严格使用指定阵容，不得增加人物" in film_post
    assert "每位指定人物都必须明确出现在每个 Theme 前提和每张海报中" in film_post
    film = resolve_story_input(
        film_document,
        InputOverrides(frames_per_theme=1, female_count=1, male_count=0),
    )
    assert film.request.frames_per_theme == 1
    assert all(plan.cast.total == 1 for plan in film.plans)
    zero_gravity = resolve_story_input(
        load_story_document(RECIPES / "zero-gravity-intimacy.yaml"),
        InputOverrides(content_level=ContentLevel.HARDCORE),
    )
    for stage in StoryStage:
        rules = zero_gravity.rules.text_for(stage)
        assert (
            "每个主题和每幅画面都呈现一种"
            "已经在发生且清晰可见的自愿成人性互动"
        ) in rules
        assert "亲密接触保持非露骨" not in rules


def test_intimate_lifestyle_portrait_matches_reference_photo_grammar() -> None:
    document = load_story_document(RECIPES / "intimate-lifestyle-portrait.yaml")
    normalized = " ".join(story_contract(document).split())
    assert document.generation.output_language == "english"
    assert document.requirements.output_languages == ("english",)
    assert resolve_story_input(document).request.output_language == "english"
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(output_language="chinese"))
    required = (
        "每个 画面 都是一张完成的满版照片",
        "宽高比和画布尺寸由本简述之外的配置控制",
        "不得声明、要求、偏好或拒绝任何宽高比",
        "明亮、精致的东亚社交媒体生活方式魅力美学",
        "清新、温柔、充满阳光、色彩鲜明",
        '"live-action photorealistic location portrait with natural undistorted perspective. '
        "bright high-key East Asian lifestyle beauty portrait, soft feminine "
        "social-media glamour, luminous ivory skin, clear large almond eyes, "
        'clean modern digital-camera realism."',
        "不得缩短、重排、改写、改变大小写或替换任一句",
        "严格使用 `female_count` 位成年女性和 `male_count` 位成年男性",
        "这些运行参数是可见人物数量的唯一依据",
        "推断、添加、移除、替换或复制人物",
        "每位指定人物都明确为 25 岁或以上",
        "指定一位要求中的女性作为主要美妆人像主体",
        "指定同伴也必须同样完整、可辨认、积极参与且清晰呈现",
        "绝不复制、点名或高度近似真实人物",
        "解剖结构连贯、有吸引力的成年人；主要女性可以具有曲线身材和自然丰满的胸部",
        "细微可见毛孔、柔软面部绒毛",
        "描述每位女性完整可见的妆容设计",
        "腮红的确切色相、位置、晕染和质感",
        "位于颧骨高处的蜜桃色膏状腮红",
        "轮换妆容系列，全部尝试后再重复",
        "为每位女性设计视觉上明显不同但和谐的妆容",
        "描述精致的仪容整理",
        "至少三件来自不同类别的协调配饰",
        "宽檐草帽、挺括贝雷帽、丝绸头巾",
        "猫眼、细椭圆、柔和矩形、无框",
        "精细吊坠、珍珠串、天鹅绒颈圈、叠戴链",
        "吊饰手链、叠戴细手镯、宽手镯、精致腕表",
        "绝不能用深色不透明镜片遮住眼睛",
        "构建不同配饰组合，使用不同的中心配饰类别",
        "对于要求中的男性，指定两件或更多协调配饰",
        "同一 主题 的两个 画面 中，每件物品必须保持同一位置",
        "一种不同的地点类别",
        "明亮的社区健身房入口",
        "阳光充足的独立咖啡馆或面包店",
        "明亮公寓的艺术角",
        "户外市场休憩区",
        "复古茶室",
        "砖墙车库",
        "使用原创、无品牌的设计",
        "服装是主要视觉吸引力，而不是普通日常穿着",
        "至少三种奢华时装材料或工艺",
        "使用至少三件协调配饰",
        "普通素面运动服或基础上衣加短裤组合是不够的",
        "装饰束身上衣、刺绣胸衣、镶宝石连体衣",
        "允许深乳沟、侧面镂空、露背、裸肩",
        "乳头和生殖器上的遮盖必须稳定且不透明",
        "在 `aesthetic` 级别",
        "在 `erotic` 级别",
        "在 `hardcore` 级别",
        "允许部分裸露上身、裸露乳房和可见乳头",
        "明确无误、当前可见且适合严格指定人物配置的自愿成年人性行为",
        "单女性配置使用露骨独自行为",
        "一女一男或双女性配置使用双方共同参与的露骨行为",
        "不得添加未要求的伴侣、身体部位、隐藏参与者",
        "一个与所选地点相关、自然且视觉上清晰可辨的活动",
        "活动应服务于人像，而不是主导它",
        "低于画面约百分之二十的面积",
        "将面部朝向、躯干朝向、骨盆朝向和相机位置视为四项独立选择",
        "干净的左侧或右侧面",
        "越过一侧肩膀回头",
        "背部大致朝向相机，脸越过一侧肩膀回望",
        "肩膀和骨盆有意反向旋转",
        "放松重心偏移站姿",
        "坐在地板上，一膝抬起",
        "小腿着地、髋部平衡的直身跪姿",
        "斜躺在沙发或躺椅上",
        "一批有四个或更多 主题 时，至少使用三种面部朝向、三种身体朝向和四种姿势类别",
        "一批有六个或更多 主题 时，至少使用四种面部朝向、五种身体朝向和五种姿势类别",
        "眼睛都是第一焦点",
        "虹膜方向、双眼汇聚程度",
        "自然湿润的下眼睑边缘、分明睫毛和细致虹膜",
        "睁大、清澈且柔和专注的眼睛",
        "绝不能显得具有掠夺性、对抗性或阴郁",
        "眯眼或半垂眼睑仅在",
        "允许聚焦而明亮的半垂眼睑视线",
        "成年人俏皮娇媚",
        "逗趣邀约",
        "慵懒自在",
        "感官满足",
        "梦幻遐想",
        "内心自豪",
        "浪漫期待",
        "自觉展现魅力",
        "惆怅温柔",
        "在 `aesthetic` 级别，优先采用亲切、俏皮、含蓄娇态",
        "在 `erotic` 级别，允许更强的逗趣邀约",
        "先规划整批的表情覆盖",
        "一批有四个或更多 主题 时，以下四条路线每条至少包含一种表情",
        '"COY AND COQUETTISH"',
        '"LANGUID AND SENSORY"',
        '"TEASING AND CONFIDENT"',
        '"WARM AND OPEN"',
        "一批有六个或更多 主题 时，还必须包含",
        '"DREAMY AND TENDER"',
        '"FOCUSED AND PROUD"',
        "以多变的顺序分配这些路线，而不是按 主题 ID 顺序分配",
        "变化直接看镜头、关注手机屏幕、镜中眼神接触",
        "至少四个相互一致的信号",
        '用可见面部证据替代 "beautiful"、"sexy"、"seductive"',
        "一种主要情绪、一种更含蓄的次要情绪",
        "当前场景中的一个具体触发因素",
        "让情绪链在视觉上具有因果关系",
        "观众应能在没有说明文字的情况下推断出两种情绪",
        "保持确切的情绪基线、触发因素、判断和微表情",
        "每个 画面 从不同相机位置捕捉完全相同的情绪瞬间",
        "先在内部构建一个不可变的主体区块",
        "将这一不可变主体区块复制到该 主题 的每个 画面 中",
        "成对变化只能是相机变化",
        "同一 主题 内取景类别和拍摄方式绝不改变",
        "不得在 画面 之间放下、举起、转交、增加或移除手机或相机",
        "连续一致性优先于新颖性",
        "每个 画面 都必须独立成立",
        "把每个稳定事实重述为当前可见事实",
        "逐字段比较成对 画面",
        "清除上述所有跨 画面 比较词",
        "绝不复述指令",
        "发布前删除否定式检查清单短语",
        "要求英语时，不得在 画面 内输出汉字、未翻译片段或混合语言",
        "捕捉动作信息最丰富的一瞬间",
        "一个即时物理后果",
        "每个 画面 都必须包含连贯的微细节层级",
        "让眼睛和驱动动作的手成为最清晰的细节",
        "采用真人实拍般写实的实景人像摄影",
        "不指定焦距，不使用广角、超广角、鱼眼",
        '绝不在最终 画面 中写入 "wide-angle"、"ultra-wide"、"fisheye"、"0.5x"',
        "自拍必须使用自然透视的手机相机模式",
        "变化来自相机位置、高度、侧别、距离",
        "完整展示每位指定人物，从头发顶端直到双脚和鞋履",
        "髋部，以及至少大腿上部或膝盖",
        "在一批中交替使用，之后再重复",
        "为每个 主题 独立选择一种不同的拍摄方式",
        "伸臂前置相机自拍",
        '始终采用 "LARGE HALF BODY"（大半身）取景',
        "镜面自拍，呈现严格指定的人物配置及仅对应这些人物的倒影",
        "从架子、柜台、窗台或稳定迷你三脚架进行定时拍摄",
        "将自拍、镜面自拍、朋友手持相机、定时相机和固定相机视为不同的摄影情境",
        "物理上真实的视线行为",
        "伸臂前置相机自拍绝不能宣称全身取景",
        "一批有三个或更多 主题 时，至少包含一次前置相机自拍或镜面自拍、一次附近朋友拍摄的人像，以及一次定时或固定相机人像",
        "每个 主题 的情境说明都必须以可见语言明确指出其取景类别和拍摄方式",
        "一种本批其他 主题 尚未使用的取景类别和拍摄方式",
        "表情类别、视线模式、眉部模式",
        "面部朝向、身体朝向和姿势类别",
        "构成三个物理纵深层面",
        "保持面部高调明亮且易于辨读",
        "避免低调照明、浓重明暗对照",
        "一种梦幻但能实际拍摄的氛围",
        "柔和黄金时段逆光",
        "小型棱镜折射",
        "明亮雨滴、凝结水珠或起雾玻璃",
        "烛光或暖桌灯，与蓝调时刻窗户的冷色补光平衡",
        "受阳光照亮的花粉、蒸汽或细尘",
        "精巧的实景串灯、咖啡馆灯泡或城市灯光",
        "梦幻氛围必须仍是具有可见物理来源的真实地点摄影",
        "不得使用魔法粒子、超自然光环",
        "四个连续的信息区块",
        '"IDENTITY AND LOOK"',
        '"EYES AND EMOTION"',
        '"POSE AND ACTION"',
        '"CAMERA AND LIGHT"',
        "完整性和定义图像的细节比任意字数更重要",
        "为每位女性写一句明确的 `MAKEUP —` 句子",
        "为每位男性写一句 `GROOMING —` 句子",
        "这些句子和每个人的配饰在每个 画面 中都必须出现",
        "把大部分篇幅用于面部、眼睛、微表情",
        "恰好 `female_count` 位原创成年女性和 `male_count` 位原创成年男性",
        "主要女性的确切腮红色相与位置",
        "严格由参数控制的人物配置",
        "不得增加、移除、替换、合并或裁掉任何指定人物",
    )
    missing = [text for text in required if text not in normalized]
    assert not missing, missing
    aesthetic = resolve_story_input(document, InputOverrides(content_level="aesthetic"))
    assert "性感但不露骨的造型" in aesthetic.rules.text_for(StoryStage.FRAMES)


def test_miniature_giant_encounter_scopes_cast_to_miniature_people() -> None:
    document = load_story_document(RECIPES / "miniature-giant-encounter.yaml")
    brief = story_contract(document)
    normalized = " ".join(brief.split())
    compact = "".join(brief.split())
    assert set(document.requirements.content_levels) == {
        ContentLevel.EROTIC, ContentLevel.HARDCORE,
    }
    cast = document.generation.cast
    assert cast.scope == "miniatures"
    assert [(role.id, role.sex) for role in cast.fixed_roles] == [
        ("giant", "theme_choice"),
    ]
    assert not cast.background_counts
    for level in (ContentLevel.EROTIC, ContentLevel.HARDCORE):
        for female, male in ((1, 0), (0, 1), (1, 1), (7, 0), (0, 7), (3, 4)):
            resolved = resolve_story_input(
                document,
                InputOverrides(
                    female_count=female, male_count=male,
                    theme_count=2, content_level=level,
                ),
            )
            assert resolved.request.content_level == level
            assert (resolved.request.female_count, resolved.request.male_count) == (
                female, male,
            )
            assert len(resolved.plans) == 2
            for plan in resolved.plans:
                assert plan.cast.scope == "miniatures"
                assert (plan.cast.female_count, plan.cast.male_count) == (female, male)
                assert plan.cast.fixed_roles == cast.fixed_roles
                assert not plan.cast.background_counts
                assert plan.cast.principal_total == 1 + female + male <= 8
                assert plan.cast.total == plan.cast.principal_total
                assert plan.cast.total_min == plan.cast.total_max == plan.cast.total
    for female, male in ((8, 0), (0, 8), (4, 4)):
        with pytest.raises(StoryConfigurationError):
            resolve_story_input(
                document, InputOverrides(female_count=female, male_count=male)
            )
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(
            document, InputOverrides(content_level=ContentLevel.AESTHETIC)
        )
    shared = " ".join(
        "\n".join(
            source.content for source in resolve_story_input(document).sources
            if source.kind == "system"
        ).split()
    )
    for text in (
        "female_count and male_count apply only to the named scope",
        "Each fixed role is one additional distinct adult outside the requested group",
        "The requested group plus fixed roles must not exceed eight principal people",
        "A theme_choice role's sex is chosen in its Theme "
        "and remains consistent in every Frame",
        "Every depicted person must be an unmistakable adult",
    ):
        assert text in shared
    required = """
female_count 和 male_count 只约束微型人物
每帧画面总人数严格等于 1 + female_count + male_count
不得出现额外脸、头、躯干、肢体或局部人物
系统为唯一巨大人物自动选择成年男人或成年女人
该 主题 全部 画面 固定此选择
所有人物均为自愿互动的多元东亚成年人
真实成人身体多样性
不是默认年轻、纤瘦、健美、对称、光滑和无瑕
年轻成年、中年或老年年龄层
肥胖厚重、柔软丰满、精瘦、宽壮或肌肉型体态
巨大人物优先轮换明显不同的年龄和体型
皱纹、松弛皮肤、腹部与腰侧脂肪褶皱
下垂胸部、妊娠纹、橘皮组织
静脉、疤痕、痣、色素差异或不对称
年龄与肥胖是正常且可具吸引力的成人特征
不得写成疾病、怪物化、羞辱理由
巨大人物是环境尺度主体
双方均可发起、回应或引导
主题 锁定发起方
专为掌心成年居民建造的室内小人国
真实成年原住民
正常人类世界的成年访客
身体与器官保持普通成人尺寸
除总人数和镜头焦距外，不得输出比例
人物或物体尺寸、长度单位
每个 画面 分开描述
不得把双方简称为同尺寸普通人物
完全相同的头身比、肩宽尺度和四肢长度
不得用高矮、娇小、修长或不同骨架区分
不得让其中一人单独靠近镜头
尺度是每帧最高优先级，必须同时出现三层证据
完整身高短于巨大人物手腕至中指尖
能站在其掌心
头部小于其拇指末节
与巨大手、脚或脸无遮挡并排
广角透视只能强化、不能单独证明尺度
接触处必须同时看见巨大身体、完整微型身体和建筑参照
小人国门框匹配居民身高
巨大访客手大于门洞
身体跨越多个房间
不能由单件小人国家具承托
须由地面、墙体或多组结构支撑
三层尺度证据
不得添加任何不参与主动作的松散小物
所有微型人物投影身高相等
只允许一具解剖连续的巨大成人身体
只允许一个目标性器官可见
目标器官在一个专门句子中只命名一次
相对微型人物的巨大尺度、朝向、自然表面
当前接触造成的可见压力或形变
目标器官保持普通成年人自然尺寸
不得放大成洞穴、房间或建筑
阴茎 保持自然 阴茎体、龟头 与根部
阴道口 保持连续外部褶皱与入口
肛门 保持自然放射褶皱与入口
每名微型人物必须从头顶到双脚全身可见
始终完整位于巨大访客体外
道具、衣物和液体不得遮断其头—躯干—四肢轮廓
任何头、躯干、骨盆、手臂、腿或脚都不得进入体内
独立闭合的头—颈—躯干—骨盆—四肢链
人物轮廓不重叠、不融合、不共享肢体
多个微型人物的头和躯干之间保留可见背景空隙
不同空间槽位和支撑面
每人只用一个固定英文称谓并在全文保持不变
同性交互禁止 “she”、“her”、“he”、“him”、“his” 等代词
不得把同一人改称 “operator”、“worker”、“partner” 或 “figure”
仅有一名微型人物时，它只能二选一
不得同时用身体接触又用手操作控制器
每条手臂和腿只分配一次位置与动作
接触点数量必须与列出的手脚一致
工具只有一个作用面，只连接接触点
每人只握一件工具或控制器
流体仅从接触点流向导流器和单个容器
禁止反向 “toward the contact point”
不得成为第二接触对象或身体支撑
“inward”、“intrusion”、“insert”、“penetration”、“enter”、“inside”
微型人物性器官被服装遮住或位于画外
显示目标部位到所属胸廓或骨盆
巨大人物可以完整出现，也可以只出现
与主要互动相关的局部身体
所属骨盆及一段相连躯干、臀部或大腿
裁切只在画框边缘
全部性行为或性活动只发生在一名或多名微型人物
与唯一巨大人物之间
禁止微型人物彼此、巨大人物独自或第三方性活动
每名微型人物须直接接触巨大人物
或操作由工具、支撑或体液轨迹连接巨大人物的同一动作链
不得旁观或另开动作
每帧只有一个连续主要行为、目标器官和接触中心
微型人物、巨大人物或双方均可发起
须明确发起与回应
除唯一接触点外，每个 画面 只用一只手或一件工具
让唯一接触点主动贴近微型人物
巨大手指不得遮住微型人物头部
非常规活动必须把体型反差转化为可见
每个 画面 只选一个主要行为
围绕同一接触中心形成一条动作链
成人之间明确自愿的暴露、窥视角色扮演
每个人仍须表现出可辨认的发起、同意或回应
并遵守非微距、完整空间和单一身体规则
微型身体或工具压住唯一接触点并造成可见形变
“approaching”、“within reach”、“alignment”、“readiness”
“waiting”、“traverse toward”、“approach”
画外行为、纯观看、纯展示或姿势暗示
想象力与标志性机制
先锁定一个 标志性机制
以下只作灵感参考，不是清单、配额或模板
不得照抄例子或只替换道具名称
空中探险
流体工程
重型机械
巨大访客主动使用完整微型人物的外部身体工具
在内部先构思至少三个候选
交通、剧场、温室、浴场、实验室、厨房
重力、浮力、杠杆、反重、振动、气流
只有巨人—小人尺度差才能成立的角色反转
不输出候选过程
世界系统 + 物理原理 + 装置 + 发起方 + 房间 + 支撑面
主动发起者可为巨大人物或微型人物
机制必须占据清楚画面空间
体液必须来自唯一可见的身体来源
大量且清晰可见的精液、尿液喷射、阴道液体或灌肠喷射
每帧只选一种主要体液效果
“Hardcore” 可使用远大于微型人物体量的强烈喷流
喷口、方向、受力表面、汇流路径
束缚架、滑轮悬吊、束带、项圈、夹具、震动器、泵、扩张器
不得只作装饰、制造伤害、遮住微型完整身体或形成第二性行为
巨大身体也可成为游乐设施地形
环绕胸廓与肩背的安全束带在胸部前搭建秋千
完整微型人物荡过一侧乳房、乳沟上方或躯干
胸前摩天轮、乳沟上方索道或胸骨弹射台
不得把乳头或柔软组织作为唯一锚点
秋千座椅不得遮住微型人物头、躯干和四肢
机械必须完整接地
微型人物采用夸张、舞台化、从头到脚完整设计
每人固定一个强烈轮廓特征
和一个醒目发型、头饰或超大配饰
同一 主题 全部 画面 一致
“Erotic” 和 “Hardcore” 中，巨大人物每个 主题 可选择裸体或部分穿着
并在全部 画面 保持一致
部分穿着可保留一至两件衣物及一件配饰
骨盆、目标部位及其与胸腹、臀部或大腿的连续关系
显示自然可见的阴毛及其与皮肤、骨盆的连续边界
衣物不得覆盖阴毛或接触点
阴毛造型可作为创意和尺度证据
局部修剪成几何边界、分区或渐变
编成短辫，加入轻质环、珠、丝带或金属线
体液形成湿润聚束和导流纹路
每个 主题 只选一种主造型并在全部 画面 固定
不得完全剃除、延伸成触手或额外肢体
不得作为微型人物唯一承重支撑
伪装成肢体或制造额外身体轮廓
夸张造型不能改变人物身高、头身比、肩宽
微型服装按小人国居民的共同尺寸裁制
每名微型人物造型使用 20–30 个英文单词
两种颜色、两种材质、一个轮廓和一个配饰
欧根纱
巨大人物用 12–20 词
不得复制成额外肢体
人物表情必须生动、具体并与发起或回应角色一致
每个 画面 分别为发起者和回应者指定一个简短表情
不得让所有人共享相同的空洞、微笑或惊讶表情
至少一个环境中景或全景必须显示发起者和回应者的脸
“Hardcore” 表现极度性兴奋
潮红面颊、张开的嘴唇、急促呼吸
表情保留自然面部结构
每人表情使用 10–15 个英文单词
不得为表情放大人物、头部或改用贴脸特写
不写导演姓名或模仿在世创作者
采用原创形式主义电影美术
正面中心构图、精确轴线
受控色板选自灰粉、芥末黄、湖蓝、薄荷绿、奶油白与酒红
每场三种主色与一种强调色
家具、门框、壁纸和灯具采用整齐网格
对称只用于建筑、家具、灯光和道具
不得镜像、复制或成对增加人物
人物和唯一接触点可偏离中轴
不能让形式化构图压平成无空间感的平面
最多描述两个建筑特征和三个场景颜色
采用哑光、不反射、不透明表面
禁止微距摄影、微距镜头、极端特写
强制使用 20–32 毫米 等效广角
明显但可信的近大远小、汇聚线和前后景拉伸
不得消除透视变形
禁止鱼眼、正交感、平视平拍
房间尺度广角建立镜头
只有一个 画面 时必须使用该景别
巨大人物完整身体或大段连续身体
贴近微型人物支撑面的低机位仰拍
从巨大访客肩部以上向下的高机位俯拍
不得使用平直眼平视角
低机位广角全景
高机位斜拍全景
局部身体广角环境镜头
局部身体镜头可以让巨大人物超出画框
两个以上 主题 必须同时覆盖一次仰拍和一次俯拍
前景空间锚点、中景互动和背景房间边界三层深度
至少两条强烈汇聚的房间深度线
中等至较深景深
正常人类访客性别
发起方与回应方
多个 画面 是同一个已经发生的主要行为
不是前后发展的连续故事
禁止接近、准备、开始攀爬、驶向、下降前往、等待
每个 画面 严格 700–850 个英文单词
返回前计算词数
超过 850 词删除重复与次要细节
第二句独立以“The single penis...”
只命名目标一次，写自然表面、骨盆连接、形变和动作
后文只称“the contact point”
total = 1 + female_count + male_count
数字均用阿拉伯数字
绝大多数篇幅用于三层尺度证据
每句重复固定称谓；同性人物禁用人物代词
只有一名微型人物时禁用 “first/second” 且只给一个操作动词
造型、表情和场景美术合计不超过 140 个英文单词
句子以“The camera uses a room-scale wide establishing shot”开头
不得为达到 700 词而重复人数、身高、器官名
禁止“previous frame”“as before”
“next phase”等跨帧词
“same”和“identical”仅说明共同尺度
只用自然英文简单现在时
只写画面肯定事实
第三句起的 “penis”、“vaginal opening”、“anus” 替换为 “the contact point”
删除 “no”、“not”、“without”、“unseen”、“uninvolved”
替换 “centimeter”、“inch”、“twentieth”、“pencil”
核对首句身份完整及镜头句精确开头
不附自检报告
总人数不等于 1 + female_count + male_count
出现额外脸、头、躯干、肢体或不止一名巨大人物
人物轮廓在接触点外重叠、融合或共享肢体
出现第二个性器官、第二具骨盆、断开的器官
性活动没有排他地发生在微型—巨大之间
缺少标志性装置
互动只是拥抱、依偎、摆姿与无装置触碰
多个微型人物的实际或投影身高不一致
场景不是小人国
输出焦距外的尺寸单位
画面 少于 700 个英文单词、夹杂中文
镜头句未按指定英文开头
人物缺少夸张造型、造型跨 画面 改变
发起者或回应者没有可辨认表情
微型身体或工具未压住接触点
画面 停在准备状态
输出否定、自检与禁止句
目标器官超出正常成人尺寸、名称出现超过一次
没有显示微型人物完整独立轮廓
单人使用 “first/second”、同一人换称谓
同性用人物代词、一人多任务、肢体变位
流体与支撑错误
任何微型肢体进入巨大访客体内
"""
    missing = [
        text for text in required.strip().splitlines()
        if "".join(text.split()) not in compact
    ]
    assert not missing, missing
    for literal in (
        "“living miniature adult woman/man native”",
        "“normal-human-sized giant visitor”",
        "Exactly [total] separate adult bodies are visible in total inside a "
        "miniature kingdom built for palm-sized adult inhabitants",
        "[female_count] living miniature adult women natives and [male_count] "
        "living miniature adult men natives, plus one normal-human-sized giant "
        "[woman/man] visitor",
        "each miniature adult's entire body is shorter than the giant visitor's "
        "hand from wrist to fingertip, and visible background space separates "
        "every miniature head and torso",
        "the unmistakable cross-scale spectacle is [initiator] using "
        "[invented mechanism] to [active effect at the contact point]",
        "“from the contact point into [channel/container]”",
        "“The camera uses a room-scale wide establishing shot”",
    ):
        assert literal in normalized
    for forbidden in ("铅笔", "硬纱", "和小道具采用", "1:12"):
        assert forbidden not in normalized


def test_giant_country_fantasy_scopes_cast_to_visiting_people() -> None:
    document = load_story_document(RECIPES / "giant-country-fantasy.yaml")
    brief = story_contract(document)
    normalized = " ".join(brief.split())
    compact = "".join(brief.split())
    assert set(document.requirements.content_levels) == {
        ContentLevel.EROTIC, ContentLevel.HARDCORE,
    }
    cast = document.generation.cast
    assert cast.scope == "visitors"
    assert [(role.id, role.sex) for role in cast.fixed_roles] == [
        ("giant", "theme_choice"),
    ]
    assert not cast.background_counts
    for level in (ContentLevel.EROTIC, ContentLevel.HARDCORE):
        for female, male in ((1, 0), (0, 1), (2, 1), (7, 0), (0, 7), (3, 4)):
            resolved = resolve_story_input(
                document,
                InputOverrides(
                    female_count=female, male_count=male,
                    theme_count=2, content_level=level,
                ),
            )
            assert resolved.request.content_level == level
            assert (resolved.request.female_count, resolved.request.male_count) == (
                female, male,
            )
            assert len(resolved.plans) == 2
            for plan in resolved.plans:
                assert plan.cast.scope == "visitors"
                assert (plan.cast.female_count, plan.cast.male_count) == (female, male)
                assert plan.cast.fixed_roles == cast.fixed_roles
                assert not plan.cast.background_counts
                assert plan.cast.principal_total == 1 + female + male <= 8
                assert plan.cast.total == plan.cast.principal_total
                assert plan.cast.total_min == plan.cast.total_max == plan.cast.total
    for female, male in ((8, 0), (0, 8), (4, 4)):
        with pytest.raises(StoryConfigurationError):
            resolve_story_input(
                document, InputOverrides(female_count=female, male_count=male)
            )
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(
            document, InputOverrides(content_level=ContentLevel.AESTHETIC)
        )
    shared = " ".join(
        "\n".join(
            source.content for source in resolve_story_input(document).sources
            if source.kind == "system"
        ).split()
    )
    for text in (
        "female_count and male_count apply only to the named scope",
        "Each fixed role is one additional distinct adult outside the requested group",
        "The requested group plus fixed roles must not exceed eight principal people",
        "A theme_choice role's sex is chosen in its Theme "
        "and remains consistent in every Frame",
        "Every depicted person must be an unmistakable adult",
    ):
        assert text in shared
    required = """
female_count 和 male_count 只约束从正常人类世界来到巨人国的成年访客
每帧画面总人数严格等于 1 + female_count + male_count
加一名巨人国原住民
禁止输出 “normal-human-sized”
不得写成天生微型种族、玩偶、模型、克隆人或儿童
巨人不得拥有年轻、健美、无瑕或模特化的完美身材
肥胖并有自然腹部与皮肤褶皱
苍老并有皱纹、松弛皮肤与老年斑
瘦削并有突出的锁骨、肋骨与关节
疤痕、静脉、妊娠纹、色斑和左右轻微不对称
同一 主题 全部 画面 固定年龄层、体型和皮肤特征
访客层
日用品层
身体层
世界层
所有属于巨人国原住民、巨人国建筑或当地环境的可见物件都必须按巨人居民的统一日常比例制造
常用容器、鞋、手机、工具、家具、机器、车辆和建筑构件必须至少达到访客完整身体的高度
较小部件可以低于访客身高，但必须以异常厚度、宽度或重量继续显出巨人尺度
英文名称前必须明确写“giant-scale”或“colossal giant-country”
禁止只写普通 “cup”、“chair”、“door”、“rope”、“lever”、“bucket” 或 “platform”
每个 主题 使用一个具体、可理解、可拍摄的巨人国日常地点
城市室内、城市户外和半开放空间只是默认方向，不是硬边界
园林和自然边缘地点都可使用，只要环境、人物身份和互动具有生活逻辑
场景只需选择足以让地点一眼可辨的两至四种环境线索
不强制固定基础设施清单
除指定访客与唯一巨人外不得出现额外人物
优先避免连续重复同一地点和同一装置
住宅与家务、零售与餐饮、办公室与医疗、交通与停车
市政与公共休闲、文化与娱乐、酒店与度假、运动与健康
不要求先用完固定类别，也不强制工业场景占比
只是启发性例子，不是允许列表、固定菜单、配额或轮换表
所有巨人国原生建筑、家具、车辆、机器和日用品仍按巨人居民的统一日常比例制造
对巨人保持普通日用比例，对访客形成可操作的巨大结构
至少两件额外 巨人尺度 原生物件和一个最低台阶、门槛或底座与访客同焦
只允许 “travel mug”、“coffee mug”、“beverage can”、\
“beverage bottle”、“smartphone” 或 “remote control”
这是封闭列表
禁止鞋、安全帽、衣物、梯子、椅子、手电筒、工具
“finger-length” 是访客的唯一文字尺度等级
每名访客从头到脚只有巨人普通一根食指那么长
该比较只用于生成器理解尺寸，不在画面中安排测量动作
禁止把巨人手掌或手指伸到访客旁边作标尺
它只证明巨人国物件而不是人物身高
“finger-length miniature-scale” 是整段最高频尺度词
不得达到巨人的手掌、前臂、膝盖、大腿、腰、胸或肩部高度
两只巨人手处于同一深度、具有相同自然尺寸并分别连续连接双肩
禁止手掌或手指朝镜头、指向访客、单独放大、复制或断开
巨人的头、双肩、胸腹、骨盆、双大腿、双膝和至少一只完整脚
不能出现为普通人制造的椅子、梯子、控制台或平台
“ordinary stepladder”、“office chair”、“rolling chair”、\
“full-size ladder”、“full-size platform”
禁止前景放大访客、巨人在远处、极端仰俯拍、鱼眼、超广角、微距、器官特写、手脚伸向镜头或裁掉巨人头脚
每名访客必须从头顶到双脚全身可见
完整位于巨人身体外部
访客的头部、胸廓、腹部和骨盆四周
可见空气、背景空隙或刚性平台边界
除一个明确命名的局部接触面外
禁止整名访客横跨、趴伏或贴伏在巨人的胸部、腹部、阴阜、骨盆或大腿表面
全部访客位于同一个 微型访客互动台 的独立编号工位
“Erotic” 只允许 标志性机制 的单一软垫末端、气流、水流或织物到达接触点
“Hardcore” 允许被明确分配的访客嘴、一只手或单一玩具直接到达同一目标器官
禁止 “visitor against giant torso”
禁止 “full-body direct contact”、“body-weight contact”
耻骨弓 上的 根部、大腿内侧上部 之间连续的 阴茎体、清楚 龟头
龟头 下方唯一 阴囊 和相对骨盆的轴向
下骨盆 正中连续的 大阴唇、小阴唇、阴蒂包皮
位于 阴阜 下方、会阴 前方和 大腿内侧上部 之间
臀沟 正中的 外部肛门口，位于 骶骨 下方
会阴 后方和两侧 臀部 之间
下半身目标 使用 下腹部与大腿 固定定位
乳头目标 使用 颈部、胸廓与腹部 固定定位
男性巨人 只选 “penis” 或 “anus”
女性巨人 只选 “vaginal opening”、“anus” 或 “selected nipple”
下半身目标 位于两腿之间，所选 乳头 属于连续胸部
均不得代替肢体或形成额外身体
先按巨人姿势选择最能表现压倒体量的构图并在 主题 内锁定
不得从工具或他人长出、消失进物件、互相承重或共享肢体，并保留背景缝隙
访客身体之间始终有空气间隙，手脚不得触碰另一访客
每只手保持独立可见
画面显示目标部位到所属巨人骨盆，再到胸腹、左右大腿、双膝
至少一只完整脚的连续轮廓
空间词必须以 巨人耻骨弓、腹部、会阴、臀沟、大腿
乳头目标 的 胸骨、胸廓、乳房隆起 为参照
全部性行为只发生在一个或多个正常人类访客
与唯一巨人国原住民之间
每个 主题 必须先建立一条不可替代的 必要性链
画面显示结果、巨人对指定访客的回应和访客间反馈
反事实必要性检验
触发来源路径
需求与目标同一性锁定
每名访客承担一个前后相接且不可省略的角色
禁止 工具性暴露
目标暴露是最小充分访问
地点必须具有画面内可见的隐私条件
限制必须临时、无伤害且不影响同意能力
当且仅当 request.content_level 为 “erotic”：选择一种明确非插入式亲密行为
当且仅当 request.content_level 为 “hardcore”：选择口交、手交、玩具插入
至少一名访客以 嘴、一只手 或 一个玩具 已接触目标
其他人负责承重、衣物牵引、定位、润滑、节奏、观察或承接
直接参与者不操作控制器
不得旁观、另开动作或重复占据同一解剖位置
“Hardcore” 每帧最多一种主要体液，显示唯一 来源、轨迹、表面 和 落点
未选择 释放 时不得出现喷射、液滴或湿痕
它可以是简单日用品、柔性材料、家具、服务设施或机械系统
不得用皮肤、阴毛或柔软组织承重，也不得遮住访客
下半身目标 显示连续阴毛边界
所有人物穿衣或半裸，不得全裸
巨人穿两至四件正常衣物及一件配饰
乳头目标 则 长裤 扣好且只掀一件上衣
禁止替代下装、第二条 长裤、裤子消失或单腿穿裤
写了 “shoes”、“boots” 或 “sandals” 就必须保持穿在对应双脚
访客各穿高对比纯色连体工作服和鞋
服装、长发和配饰不得伪装成额外肢体或遮住脸、手、承重点和接触中心
巨人需要完整人物造型
微型尺度访客 不描述眼妆品牌、首饰、精细材质或复杂时装剪裁
必须拥有海报级可读的夸张成人表情
巨人拥有与互动一致的明确表情和视线
每名访客必须同时用脸、头部朝向和全身姿态表达不同情绪
不得放大访客身体或改成卡通脸
每人的动作必须是一个稳定、可拍摄的当前动作
躯干朝向、重心、主要支撑面、双手唯一任务
固定每人的造型、妆容、表情角色、动作、支撑与四肢位置
巨人体毛匹配年龄体型
另显示至少两处自然体毛，保持真实密度、方向
灰白变化和皮肤连接
不能只写 “generic interior”、“outdoors” 或 “giant country”
每个 主题 选择并轮换一种开放摄影风格
真人实拍的照片级写实实景或搭景摄影
真实成年演员、皮肤毛孔与体毛、布料、实体道具、可信光学和一致阴影
允许广告级布光、粉彩、奢华材质与彩色灯光
禁止 “magic”、“levitation”、“illustration”、“painting”、\
“anime”、“comic”、“CGI look”、“3D render”
塑料皮肤和镜像、复制或融合身体
使用痕迹表现世界有人生活
风格可改变对称性、色彩、布景、光比和留白
不得改变尺度、解剖、接触或因果
同一 主题 的全部 画面 锁定巨人的支撑姿势、骨盆旋转
不能把站、坐、跪、躺互换
不可变的 S2–S6 主体文本块
再复制到全部 画面
配对 画面 只改变相机方位和最终镜头句
严格按以下物理句序写，任何顺序变化都重写
必须逐字套用以下单句骨架
在 “perspective” 之前不得出现句号或分号
这里命名的接触者、身体部位或 玩具 必须在 S5 和 S6 完全相同
禁止透视假尺度、测量手指或第二巨人
不得在 S3 使用 “held”、“worn”、“lying”、“resting”、“remains” 或其他位置状态词
不得增加 “extended”、“pointing”、“dangling” 或 “measuring finger”
标志性机制 必须是地点原生设施或其合理延伸
禁止无法解释来源的临时专业设备
全部承重、锚点和传力部件属于同一功能链并固定在地面、家具或其他硬结构上
“Erotic” 中，S1 命名的 标志性机制 必须直接作用于接触点
“Hardcore” 中，S1 命名的 标志性机制 必须直接承托、定位、稳定、驱动节奏或承接体液
这属于装饰性假机制
互动台严格分成与访客人数相等的独立工位，从画面左到右编号
每个工位只有一人并以栏杆和背景缝隙分隔
U+2019 改为 ASCII 撇号
一个物理句子先详细写巨人造型
一件衣物只有一个 所有者、一个 腰头、一个 开合部件
一个 道具 不能同时在手中、桌上和背景
父级链规则
单槽位规则
一个物理句子写巨人姿势和全部访客工位
逐人写完整四肢；两只巨人手同深度、自然等大并连接手臂
禁止因果句临时新增持物、工作或受限动作
巨人随后必须执行一个会改变接触压力、角度、节奏、流量或位置的可见动作
至少四次写 “the contact point itself”；禁止被动回应或目标漂移
物理第一句必须点名具体 现实世界式巨人国场景
紧接句号后的第二句以
只命名目标一次并完成对应身体定位；第三句起只称“the contact point”
U+2010、U+2011 和 U+2012 改为 ASCII 连字符
克制的纪实实景摄影
高端 商业海报、奢华时尚专题摄影
夜生活色片灯光摄影、明亮生活方式广告
材料、家具、标识、植物、天气、道路、设备和使用痕迹按地点自然选择
人物、绳索、工具和机械不得悬浮、穿透或融合
使用足够拍下完整巨人的 35–50 毫米 正常视角和中深景深
互动台、访客、完整日用品证明与巨人处于同一登记平面
完整头脚跨度沿画面最长轴接近两端但保留边缘空间
超自然地点仅在输入主题明确要求时使用
"""
    missing = [
        text for text in required.strip().splitlines()
        if "".join(text.split()) not in compact
    ]
    assert not missing, missing
    # Output literals remain English; translated instructions are checked above.
    for literal in (
        "“finger-length miniature-scale normal-world adult woman/man visitor”",
        "“giant-country native giant woman/man”",
        "“finger-length miniature-scale normal-world adult visitor”",
        "single miniature visitor interaction deck",
        "“Every visitor has an unmistakable finger-length miniature scale from "
        "head to foot, while both fully connected giant hands stay in natural "
        "task or support poses away from the visitor group, with relaxed "
        "fingers and no measuring gesture.”",
        "the finger-length miniature-scale normal-world adult visitors "
        "occupy one separated interaction-deck bay each",
        "“a visible air gap separates the visitor's head, torso, abdomen, "
        "and pelvis from the giant's skin”",
        "“a visible air gap separates each visitor's torso, abdomen, pelvis, "
        "arms, and legs from the giant's skin, with only the assigned mouth, "
        "hand, or toy reaching the contact point”",
        "“the lower abdomen is visibly above the target”",
        "“both thighs continue toward the knees”",
        "“Both giant shoulders visibly connect through two separate arms to "
        "two naturally equal-sized hands at one depth, the giant pelvis visibly "
        "connects to two separate thighs, knees, lower legs, and feet, and the "
        "contact point lies between rather than replacing the thighs; every "
        "visitor has two independently traceable arms, hands, legs, and feet "
        "with a background gap around each limb.”",
        "Because [trigger at TARGET_ID] creates [need at the contact point itself]",
        "“The giant's trousers are fully lowered as one continuous garment, "
        "with one waistband, one [zipper, button, drawstring, or elastic] closure, "
        "and both pant legs visibly bunched around both upper thighs.”",
        "“At [specific real-world giant-country setting], exactly [total] "
        "separate adult bodies are visible in total: [visitor count and "
        "finger-length miniature-scale normal-world adult identities] occupy "
        "one separated bay each on a single miniature visitor interaction deck, "
        "every complete visitor having an unmistakable finger-length scale "
        "from head to foot, plus one giant-country native giant [woman/man], "
        "while the visitors carry out [one content-level interaction] using "
        "[location-native Signature Mechanism], viewed in a [pose-appropriate "
        "scale-dominance camera and portrait or landscape orientation] with a "
        "35–50 mm normal perspective in [selected photographic style].”",
        "“Four simultaneous scale proofs share one clear focal plane:”",
        "“the selected giant-scale everyday anchor functions as an ordinary "
        "everyday object for the giant”",
        "“The fully visible giant-scale [whole object] stands beside the "
        "interaction deck on the same picture plane, its full height clearly "
        "towering over every visitor, and its [recognizable feature] alone "
        "larger than one visitor.”",
        "“The sole giant is the frame's overwhelmingly largest visual mass "
        "from head to feet along its longest axis, the complete visitor group "
        "and interaction deck form a secondary cluster smaller than the giant's "
        "head, and each visitor's full height is visibly shorter than the "
        "giant's face from chin to hairline.”",
        "visitor-scale control input → giant-scale force transmission",
        "assigned visitor mouth, hand, or toy at the contact point",
        "“The giant has one unbroken body silhouette from head through torso "
        "and a single pelvis into two thighs, knees, lower legs, and feet; "
        "no counter, table, bed edge, cart, interaction deck, machine panel, "
        "wall opening, or frame crosses, hides, encloses, or duplicates the "
        "waist, pelvis, or legs.”",
        "“live-action photorealistic location photography captured from "
        "sufficient distance with a real 35–50 mm camera”",
        "previous frame, same, identical, unchanged, still, again, now, remains, "
        "then, afterward, next, about to, will, normal-human-sized",
        "The visitors retain an unmistakable finger-length miniature scale "
        "without any measuring hand or finger in the composition",
        "both giant hands share one natural size and depth plane",
        "“The camera uses a full-body scale-dominance composition”",
    ):
        assert literal in normalized
    for forbidden in ("1:15", "11-centimeter", "14-centimeter"):
        assert forbidden not in normalized


def test_furry_mythic_interactions_uses_original_live_action_characters() -> None:
    from t2i_story_pipeline.models import AsciiCheck, WordCountCheck

    document = load_story_document(RECIPES / "furry-mythic-interactions.yaml")
    normalized = " ".join(story_contract(document).split())
    assert document.generation.output_language == "chinese"
    assert document.requirements.output_languages is None
    for language in ("chinese", "english"):
        assert resolve_story_input(
            document, InputOverrides(output_language=language)
        ).request.output_language == language
    assert document.validation.frames.mode == "report"
    assert document.validation.frames.checks == (
        AsciiCheck(type="ascii", when_language="english"),
        WordCountCheck(type="word_count", when_language="english", min_words=600),
    )
    required = (
        "`total_count` = `female_count` + `male_count`",
        "每个 主题 都设置 `furry_count` = 1 及 `human_count` = `total_count` - 1",
        "由较小的正数所对应性别提供兽人名额",
        "若两个正数相等，则男性名额为兽人",
        "两名女性及一名男性对应两名人类女性及一名男性兽人",
        "一名女性及两名男性对应一名女性兽人及两名人类男性",
        "human_count = 2, furry_count = 1, zero other bodies",
        "two named human women and one named adult male anthropomorphic",
        '禁止出现短语 "human man" 和 "female furry"',
        "第一句中，先命名两名人类女性及男性兽人，再说明行为",
        "在同一句中让第二名人类女性与其余两位之一直接接触",
        "阵容声明必须在同一句中继续使用以下明确接触语法",
        '"the male furry\'s penis is inside the first human woman\'s vagina, '
        "while the second human woman's hand directly contacts either the first "
        'woman\'s clitoris or the male furry\'s penis or scrotum"',
        "严格保留 `female_count` 个女性名额及 `male_count` 个男性名额",
        "exactly one requested adult woman and zero adult men, allocated as",
        "exactly one visible adult body",
        "with zero humans and zero other furry beings",
        "绝不添加请求指定名额以外的角色",
        "清醒、聪慧、能够说话或明显具备推理能力的成年人",
        "兽人角色继承按确定性规则选出的请求指定名额的性别",
        "若仅 `female_count` 非零，每名兽人都是女性",
        "若仅 `male_count` 非零，每名兽人都是男性",
        "保持姓名、性别、代词及性解剖结构一致",
        '不得切换性别、使用 "it" 或 "they" 来回避说明性别',
        "一名女性及零名男性，意味着一名成年女性兽人及零名人类",
        "全女性运行不包含阴茎、阴囊、睾丸",
        "仅选择与已锁定解剖结构相容的行为",
        "被拍摄的成年表演者",
        "真实在场的电影生物",
        "每名兽人至少穿戴一件清晰可见",
        "不得将固定服装或服装类别绑定到物种",
        "绝不让兽人变成完全没有衣着、仅有毛皮的身体",
        "公版神话",
        "《西游记》人物",
        "八仙",
        "完全原创的高幻想角色",
        "完全原创的英雄、义警、宇宙或超人原型",
        "不得复制来自《魔兽》、漫威、DC",
        "不得点名、模仿、唤起、组合或移用任何真实导演",
        "不得使用公众人物、宗教领袖、历史名人、演员或其他真实人物的姓名、头衔、别名、面孔、生平或可识别的特征组合",
        "不得把 `T001`、`T002` 或任何其他 主题 ID 分配给预先确定的来源",
        "一个可见且有后果的决定，其效果在所描绘的瞬间已经发生",
        '绝不写 "must choose,"、"must decide,"',
        "每个 主题 前提都以两个简洁的证明分句结束",
        '"Decision: [protagonist name] [completed physical action that enacts the choice]. '
        "Immediate response: [every other participant's current physical reaction, "
        'or the solo protagonist\'s visible bodily response]."',
        '前提必须在 "Immediate response" 分句之后结束',
        "视觉风格只能放在独立的 主题 `style` 值中",
        "在 审美级 和 情色级 级别，每个 画面 开头都要独立说明精确地点",
        "不使用任何回指",
        "重新安排一个等效的决定性瞬间",
        "`F02` 不晚于 `F01`",
        "每种变化都必须看起来是对共同决定性瞬间的全新调度",
        "展示主角已经完成的决定",
        "不得取代主角在叙事及视觉上的优先地位",
        "不得提及创作简报、提示词、请求、模型、生成器",
        '"the image reads first as,"、"only afterward,"',
        "当请求语言为英语时，每个 主题 和 画面 仅使用 U+0020 至 U+007E 的 ASCII 码点",
        "把人名及地名音译为合理的 ASCII 拉丁字母拼写",
        "扫描每个标题、前提、`style` 及正文值",
        "排除任何引用另一 画面、自称延续内容，或推进固定时间窗口的 画面",
        "不得使用动画、漫画",
        "在 `aesthetic` 级别",
        "在 `erotic` 级别",
        "在 `hardcore` 级别",
        "展示一种已经发生的明确成年人自愿性行为",
        "前一百个英文词内",
        '精确短语 "consensual and willing"',
        "`total_count` 等于一时，在第一句中写明兽人主角明确的独自手部接触",
        "对于更大阵容，在前两句内让每位参与者都置于同一直接生殖器、口部或手部性行为链中",
        "明确说明谁的阴茎在谁的阴道或肛门内",
        '"intimate contact"、"joined bodies"、"explicit interaction"',
        '该句开头须把图像称为 "live-action fantasy photograph"',
        "说明请求指定的精确成人性别总数、精确 `human_count`、精确 `furry_count`",
        "在同一个第一句中写入直接解剖接触",
        "第一句绝对优先",
        "所有性解剖结构都是适合该角色的普通成年类人解剖结构",
        "绝不使用吻部形态、喙、角、利爪、尾巴、翅膀、爪垫",
        "没有成年人仅在背景旁观",
        "说明可见成年身体的精确总数",
        "第一句中逐一命名每个人类及兽人",
        "前两句必须为每位兽人及人类参与者赋予同一性行为链中一个当前",
        "第二位或之后的参与者不得在其他人互动时站在旁边",
        "自我触碰可以补充但绝不能取代与另一位参与者的接触",
        "为每位参与者提供一个独立、无遮挡的身体位置",
        "硬性下限为 600 个由空白分隔的词",
        "目标为 750-950 个词",
        "绝不在最终文字中提及词数或长度检查",
        "使用强制的阵容与接触首句",
        "宽阔、干燥、水平、室温、防滑",
        "不得从固定的具名姿势目录中选择或重复",
        "创造一种新的、物理上合理的姿势",
        "不存在强制姿势顺序、配额或四姿势循环",
        "不得使用站立插入、压墙身体",
        "骨盆在不相容高度相接",
        "先为每位参与者默默完成肢体清单",
        "左大腿、左膝、左小腿及左脚",
        "右大腿、右膝、右小腿及右脚",
        "在前 300 个英文词内",
        '字面侧别标签 "left arm"、"left hand"、"right arm"、"right hand"、'
        '"left thigh"、"left knee"、"left lower leg"、"left foot"、"right thigh"、'
        '"right knee"、"right lower leg" 和 "right foot"',
        "绝不能替代分侧图谱",
        "在强制的 露骨级 阵容与接触句及单独一个地点句之后，立即描述骨盆支撑",
        "完整的人类肢体图谱，再描述完整的兽人肢体图谱",
        "不得在地点句与这两份肢体图谱之间插入面孔、头发、生平、神话、衣着",
        "让人类手臂与兽人前肢在视觉上分离",
        "让每只手、手指、前爪、利爪、物件、衣物边缘及尾巴都位于人类及兽人的嘴外",
        "不得在嘴唇附近托、遮、压、拉或抚摸面孔",
        "改将支撑手放在锁骨下方，或共同支撑面",
        "每名兽人恰好有两条手臂及两条腿",
        "绝不添加第三条腿、重复膝盖",
        "亲密接触时尾巴绝不承重",
        "不得让尾巴缠绕建筑、家具、肢体或另一身体",
        "让性行为匹配可见的头部解剖结构",
        "具有喙、扁喙、僵硬吻部、獠牙、大型尖牙",
        "绝不进行口部与生殖器接触",
        "使用 35mm 至 65mm 的四分之三身或全身相机视图",
        "相机须足够斜置，以分开重叠肢体",
        "露骨级 画面 未在前两句及前一百个英文词内清楚指明成人性行为",
        '露骨级 画面 用 "explicit interaction" 指代非性仪式',
        "英文 画面 少于 600 个由空白分隔的词",
    )
    missing = [text for text in required if text not in normalized]
    assert not missing, missing
    assert re.search(r"(?:^|\n)\s*-\s*T\d{3}:", story_contract(document)) is None
    assert "Follow each input_context plan's cast facts exactly" in (
        resolve_story_input(document).rules.text_for(StoryStage.THEMES)
    )


def test_dress_board_region_names_are_layout_only() -> None:
    dress = load_story_document(RECIPES / "dress.yaml")
    brief = story_contract(dress)
    normalized = " ".join(brief.split())

    for requirement in (
        "不得将主题标题或区域名称呈现为可见文字",
        "区域名称仅作为内部版式参考",
        "将强度尺度的起点设为明显性感但不露骨的时尚",
        "要求一名女性、零名男性",
        "允许零至一件视觉克制、对身体安全的成人产品",
        "具有明确成人属性的产品与穿戴物时尚体系",
        "包含一至三件设计明确、对身体安全的成人产品",
        "发型、服装设计、穿搭造型和可见面部表情",
        "绝不能只靠明亮灯光",
        "后续选择绝不能削弱前面的要求",
        "有限高彩度配色",
        "“BDSM”器具与服装设计板",
        "总共包含三至六个“BDSM”专属设计元素",
        "至少包含两件外部可穿戴部件",
        "不承重、低压力，并具有可见的释放方式",
        "即使缩成缩略图仍然强烈",
        "至少使用以下三个对比维度",
        "一个主导重点、两个次级结构",
        "乳夹",
        "球形口塞",
        "衔杆式口塞",
        "中空口塞",
        "所选的任何硬核级产品都可在人物视图中以佩戴状态出现",
        "可见的低张力限制器",
        "可见呼吸通道",
        "放松的下颌",
        "贞操带灵感腰带",
        "通气皮革半面具",
        "宽姿态颈圈",
        "束缚连指手套",
        "环绕乳房构成框架的皮革束带",
        "轻质衬垫分腿杆",
        "柔软绒面革多尾鞭",
        "宽幅衬垫皮革拍板",
        "所必需的有限身体区域",
        "外部可穿戴性玩具可在人物视图中装配",
        "可以命名和展示插入式产品类别",
        "必须完全位于体外",
        "全尺寸棒式按摩器",
        "承载可拆卸硅胶假阳具的穿戴式固定带",
        "经典硅胶假阳具",
        "兔形振动器",
        "嵌有宝石的硅胶肛塞",
        "按大小渐变的肛珠",
        "带纹理的自慰套",
        "除“BDSM”器具体系之外，使用一至三件性玩具",
        "夹在乳头上",
        "夹在蕾丝",
        "不得称为乳夹",
        "不得说颈圈无缝延伸成手套",
        "材质平铺图必须展示两只鞋、两只手套",
        "每个画面都必须是实质不同的呈现",
        "至少改变以下四项",
        "不得写出内部级别名称",
        "“BDSM”在必要时最多出现一次",
        "未翻译的英语工作流程词汇",
        "合规式否定措辞填充最终文字",
        "不满足产品强调要求",
        "不得使用“futuristic”",
        "普通的中灰墙面",
        "平淡、无阴影的商品目录照明",
        "每件被命名的产品都有真实形状和预定贴合方式",
        "每个画面都在至少四个允许变化的呈现维度上区别于同主题的其他画面",
        "最终文字绝不陈述内部内容级别",
        "不得使用机械改造身体部件",
        "共用的身份、服装、配色和物品清单事实只陈述一次",
        "科技造型服装部件",
        "区域数量表示一幅图像的内部划分，不是叙事画面数量",
    ):
        assert requirement in normalized, requirement
    for excluded in (
        "实用未来主义",
        "呈现一套完整、不透明、非情色的服装",
        "唯美级不包含任何成人产品",
        "主题标题恰好出现一次，六个区域标签各出现一次",
    ):
        assert excluded not in normalized, excluded
    assert dress.authoring.themes.content_levels[ContentLevel.AESTHETIC]
    assert dress.authoring.themes.content_levels[ContentLevel.HARDCORE]
    layout = next(module for module in dress.modules if module.id == "layout-multiview")
    assert layout.parameters == {"layout": "grid", "min_views": 6, "max_views": 6}

    def pool(label):
        rules = (
            *dress.authoring.themes.common,
            *dress.authoring.themes.content_levels[ContentLevel.HARDCORE],
        )
        prefix = f"{label}：- "
        return [rule.removeprefix(prefix) for rule in rules if rule.startswith(prefix)]

    for label, minimum in (
        ("精选硬核级服装原型", 8),
        ("精选硬核级器具体系", 8),
        ("精选明确“BDSM”产品类别", 12),
        ("精选性玩具产品类别", 10),
        ("精选硬核级材质与配色体系", 8),
    ):
        entries = pool(label)
        assert len(entries) >= minimum, label
        assert len(entries) == len(set(entries)), label


def test_post_layout_brief_builds_one_analog_collage_poster() -> None:
    brief = story_contract(load_story_document(RECIPES / "post-layout.yaml"))
    normalized = " ".join(brief.split())

    for marker in (
        "具有触感的二十世纪中叶电影式摄影蒙太奇",
        "一张主导的单色摄影主图",
        "两至四个较小的纪实、环境、物体、剪影或胶片条图像碎片",
        "一个超大的窄体标题，拼装于撕裂纸块上",
        "重叠的撕纸，具有不规则毛边",
        "半色调网点、复印颗粒、粗糙新闻纸",
        "必须进行有意识的拼贴，但须形成一个完整海报提案",
        "竖版 4:5 海报",
        "同一主角的重复摄影裁切可以作为印刷来源碎片使用，不算增加人物",
        "不得偏向整洁的企业极简风",
        "参考仅确立这套设计语法",
        "将主体、场景、构图、风格、文字、细节及输出作为七项内部规划关注点",
        "而非逐字输出格式",
        "不得输出这些关注点名称、字段标签、前缀",
        "它们的名称仅供内部创作提示",
        "写成一个紧凑流畅的段落，而非七行带标签文字",
        "专用画内文字片段是所有可见画内文案的唯一来源",
        "准确的物理载体、画内位置和排版方式",
        "添加字面 ASCII 字符 `: `",
        "以字面 ASCII 字符 `;` 结束",
        "不得用引号包围文案",
        "不得呈现非英文文字系统",
        "人物、地点、年代和物件均不构成使用当地语言文字的许可",
        "可见文案外围无引号",
        "若某个词未在该段落中明确声明，则不得在图像任何位置可读",
        "生成海报任何位置都没有非英语字形",
        "定义裁切或拍摄距离、拼贴结构、焦点层级、位置、阅读路径和受保护的留白，不得重复宽高比",
        "不指定输出尺寸或宽高比",
        "构图及最终输出质量措辞不含重复宽高比或尺寸要求",
        "不得在海报中呈现备选布局",
    ):
        assert marker in normalized, marker
    for label in (
        "Subject:",
        "Scene:",
        "Composition:",
        "Style:",
        "Text:",
        "Details:",
        "Output:",
    ):
        assert label not in brief


def test_post_briefs_isolate_text_without_removing_poster_copy() -> None:
    briefs = {}
    for filename in ("film-post.yaml", "post-layout.yaml"):
        document = load_story_document(RECIPES / filename)
        resolved = resolve_story_input(document)
        normalized = " ".join(story_contract(document).split())
        briefs[filename] = normalized
        assert document.generation.output_language == "english"
        assert document.requirements.output_languages == ("english",)
        assert resolved.request.output_language == "english"
        assert any(check.type == "ascii" for check in document.validation.frames.checks)
        with pytest.raises(StoryConfigurationError):
            resolve_story_input(document, InputOverrides(output_language="chinese"))
        visible_copy = next(
            module for module in resolved.modules if module.kind == "visible_copy"
        )
        assert visible_copy.parameters.product == "poster"
        assert visible_copy.parameters.copy_language == "english"
        assert visible_copy.parameters.ascii == "required"
        for marker in (
            "Frame 全文必须使用英语",
            "生成 Theme 时，标题、前提和风格也必须使用仅含 ASCII 字符的英语",
            "完整 Frame 的每个字符都必须位于 ASCII 码点 0 至 127",
            "将 U+2018 和 U+2019 替换为直撇号",
            "专用画内文字片段是所有可见画内文案的唯一来源",
            "添加字面 ASCII 字符 `: `",
            "以字面 ASCII 字符 `;` 结束",
            "不得写出单词 `colon` 或 `semicolon`",
            "Frame 的最后一个字符必须是 `;`",
            "乱码",
            "不可读微小文字",
            "字符串数量和排版区域数量不固定",
            "槽位数量、重复出现的位置、允许的载体、排版区域和产品版式均由配方规定",
            "文案语言与字符集约束的是可见画内文字，而不是描述性提示词的语言",
        ):
            assert marker in normalized, (filename, marker)
        assert "恰好三个可读英语字符串" not in normalized, filename
        assert "恰好三个受控排版区域" not in normalized, filename

    for marker in (
        "保留原有院线文案组合和排版自由",
        "片名、宣传语、上映信息、演职员表、署名",
        "为该设计原创的英语宣传语",
        "紧凑的虚构英语演职员表",
        "证据与档案：收据、信件、地图",
        "手写证据",
    ):
        assert marker in briefs["film-post.yaml"], marker
    for marker in (
        "可见文案的序列化不得改变海报设计",
        "不得删除或简化编辑碎片、署名、引文、日期、场地细节",
        "少量简短英语编辑片段、署名、引文块、日期或场地细节",
        "票券、照片边缘、署名条、徽章、标牌",
    ):
        assert marker in briefs["post-layout.yaml"], marker


def test_jav_dvd_wrap_has_complete_ascii_packaging_contract() -> None:
    document = load_story_document(RECIPES / "jav-dvd-wrap.yaml")
    normalized = " ".join(story_contract(document).split())
    resolved = resolve_story_input(document)
    assert document.generation.output_language == "english"
    assert document.requirements.output_languages == ("english",)
    assert resolved.request.output_language == "english"
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(output_language="chinese"))
    checks = document.validation.frames.checks
    assert any(check.type == "ascii" for check in checks)
    word_count = next(check for check in checks if check.type == "word_count")
    assert (word_count.min_words, word_count.max_words) == (500, 1300)
    visible_copy = next(
        module for module in resolved.modules if module.kind == "visible_copy"
    )
    assert visible_copy.parameters.product == "sleeve"
    assert visible_copy.parameters.copy_language == "english"
    assert visible_copy.parameters.ascii == "required"
    for marker in (
        "左侧封底、中央窄书脊、右侧封面",
        "Frame 全文必须使用合乎语法的英语",
        "生成 Theme 时，标题、前提和风格也必须使用仅含 ASCII 字符的英语",
        "完整 Frame 的每个字符都必须位于 ASCII 码点 0 至 127",
        "Frame 的最后一个字符必须是 `;`",
        "添加字面 ASCII 字符 `: `",
        "以字面 ASCII 字符 `;` 结束",
        "封底约占宽度的百分之 43 至 46",
        "书脊占百分之 6 至 8",
        "封面占百分之 47 至 50",
        "六至九张有边框的嵌入剧照",
        "任何身体、面容、手、肢体、道具、体液或衣物都不得从一张剧照跨入另一张",
        "严格使用指定人物阵容，不得增加任何人",
        "明显是成熟的中国成年人",
        "当请求阵容是一名女性、零名男性时",
        "所有封面、封底及嵌入照片都严格为单人",
        "镜头外参与者、第二具身体、多余手部、局部头部",
        "前提都必须描述单人自主行为",
        "在 aesthetic 级别",
        "在 erotic 级别",
        "在 hardcore 级别",
        "所有插入物都必须是明确为生殖器或肛门使用设计、对身体安全的性玩具",
        "绝不插入瓶子、食物、家居物品",
        "各 Frame 是并行宣传变体",
        "一个精确虚构的 13 位数字条码编号",
        "目标为 700 至 1000 词",
        "严格限定为 500 至 1300 词",
        "每张嵌入图描述少于 40 词",
        "共享照明、身份、边框和印刷行为只说明一次",
        "拒绝并改写任何少于 500 词或多于 1300 词的 Frame",
        "任何缺少最终专用图中文字段落",
        "一张完整平面封套",
        "每个实体出现位置都须声明一次精确可读字符串，包括重复的标题和产品代码位置",
        "槽位数量、重复出现的位置、允许的载体、排版区域和产品版式均由配方规定",
    ):
        assert marker in normalized, marker


def _legacy_everyday_social_caricature_contract() -> None:
    brief = story_contract(load_story_document(
        REPOSITORY_ROOT / "story-inputs" / "recipes" / "everyday-social-caricature.yaml"
    ))
    normalized = " ".join(brief.split())

    assert "Every visible person is a fictional East Asian adult" in normalized
    assert (
        "mainland Chinese, Taiwanese, Hong Kong Chinese, Japanese, South Korean, "
        "and Singaporean Chinese"
        in normalized
    )
    assert "Set every Theme and Frame in mainland China, Taiwan, Hong Kong" in normalized
    assert "Use plausible local names in ASCII Latin letters" in normalized
    assert "Every Theme premise must explicitly identify each person's allowed identity" in (
        normalized
    )
    assert "Every Frame must identify every adult as an East Asian woman or East Asian man" in normalized
    assert "At least one adult woman is the unmistakable narrative" in normalized
    assert "Use exactly the requested cast and add no bystanders" in normalized
    assert "complete Frame in English, regardless of the requested output language" in (
        normalized
    )
    assert "Use English-only ASCII characters" in normalized
    assert "Reject any code point outside ASCII U+0020 through U+007E" in normalized
    assert "Write personal names in normal Title Case" in normalized
    assert "reserve uppercase words exclusively for exact visible copy" in normalized
    assert (
        "Flat satirical photomontage assembled from photographs of real adult "
        "performers:"
        in normalized
    )
    assert "exact cast supplied by the generation request" in normalized
    assert "Exactly [requested total] East Asian adults fill the image" in normalized
    assert "Omit a gender phrase when its requested count is zero" in normalized
    assert "Never infer, default, or hard-code any count in this brief" in normalized
    assert "two East Asian women and one East Asian man" not in normalized
    assert "repeat the complete opening cast declaration verbatim" in normalized
    assert "final two-entry text passage" in normalized
    assert "Every visible person must remain unmistakably photographic and human" in (
        normalized
    )
    assert "Do not use illustration, drawing, painting" in normalized
    assert "anime, manga, chibi" in normalized
    assert "real photographic adult cutouts" in normalized
    assert "The final style sentence must positively restate" in normalized
    assert "invisible domestic labor" in normalized
    assert "friendship rituals" in normalized
    assert "dating, courtship, commitment" in normalized
    assert "workplace meetings" in normalized
    assert "attention, imitation, approval, self-presentation" in normalized
    assert "Exaggerate decisively" in normalized
    assert "one controlled caricatural exaggeration" in normalized
    assert "thirty to forty percent of the image" in normalized
    assert "Exactly one physical supporting object" in normalized
    assert "Every adult appears as one intact photographic person" in normalized
    assert "Use no more than one anatomical or silhouette exaggeration" in normalized
    assert "Never cut, paste, duplicate, float, detach, fold, splice" in normalized
    assert "Do not exaggerate breasts, buttocks, genitals, tongue" in normalized
    assert "Do not use exact body-part canvas percentages" in normalized
    assert "Branch immediately after the cast sentence" in normalized
    assert "For hardcore, the second sentence must begin with the explicit act" in (
        normalized
    )
    assert "All requested adults are already joined in one consensual explicit act:" in (
        normalized
    )
    assert "This sentence contains only names, involved anatomy, present contact" in (
        normalized
    )
    assert "within the first eighty English words after the fixed opening phrase" in (
        normalized
    )
    assert "Only after this early content proof" in normalized
    assert "complete head-to-foot outfit" in normalized
    assert "including top, bottom or one-piece garment, and footwear" in normalized
    assert "describe each adult's remaining or displaced clothing" in normalized
    assert "Clothing must not cover or contradict required contact" in normalized
    assert "Immediately after the selected-level proof" in normalized
    assert "All figures are frontal whole-person photographic cutouts" in normalized
    assert "before faces, metaphor, setting, or props" in normalized
    assert "Never mention instructions, sentence numbers, requirements" in normalized
    assert "Exaggerate decisively, but select exactly one item" in normalized
    assert "Never assign a second item from the list to the same person" in normalized
    assert "These choices are mutually exclusive" in normalized
    assert "whole-body scaling leaves hair, garments, limbs, and face unaltered" in (
        normalized
    )
    assert "scaled between seventy and one hundred thirty percent" in normalized
    assert "without changing the size or shape of any facial organ" in normalized
    assert "Never resize or paste a face or isolated organ" in normalized
    assert "All faces must remain unmistakably mature" in normalized
    assert "Reject smooth doll faces, huge sparkling eyes" in normalized
    assert "silently draw at least three radically different thumbnail" in normalized
    assert "using only black shapes and one accent color" in normalized
    assert "silently assemble one complete final photomontage" in normalized
    assert "separately photographed real adult performers" in normalized
    assert "following the viewer's scan order from dominant icon" in normalized
    assert "If a symbol requires explanation, redesign it before writing" in normalized
    assert "fill thirty-five to fifty percent of the entire image area" in normalized
    assert "Give each side a concrete visual label" in normalized
    assert "Use one blunt visual contest that survives without context" in normalized
    assert "If the scene can be mistaken for an ordinary lifestyle illustration" in (
        normalized
    )
    assert "Use an animal, object, garment, or emblem as a visual label" in normalized
    assert "Every symbol must have one clear referent" in normalized
    assert "one closed causal force chain" in normalized
    assert "central woman's intimate movement applies one visible directional force" in (
        normalized
    )
    assert "another participant's body transmits that same force" in normalized
    assert "primary metaphor visibly changes mechanical state because of the bodies" in (
        normalized
    )
    assert "changed mechanism redirects pressure into every remaining participant" in (
        normalized
    )
    assert "At least two adults must directly touch, load, grip, brace, block" in normalized
    assert "If removing the explicit interaction leaves the metaphor unchanged" in (
        normalized
    )
    assert "Because [central woman] [physical verb]" in normalized
    assert "At aesthetic level" in normalized
    assert "name one complete opaque outfit for each adult" in normalized
    assert "Show no bare torso, transparent garment, lingerie" in normalized
    assert "At erotic level" in normalized
    assert "At hardcore level" in normalized
    assert "Every requested participant must make direct intimate physical contact" in (
        normalized
    )
    assert "through penetration, oral-genital contact, or direct genital stimulation" in (
        normalized
    )
    assert "Looking, kissing, touching shoulders or hips" in normalized
    assert "Include no clothed spectator or queued participant" in normalized
    assert "Do not pin, trap, force, dominate, restrain" in normalized
    assert "include no loose props or debris" in normalized
    assert "everyone awake, alert, willing" in normalized
    assert "Every Theme must choose one meaningful pair of opposed English labels" in (
        normalized
    )
    assert "Each label contains one or two short words" in normalized
    assert "Lock the exact pair during Theme generation" in normalized
    assert "Locked image labels: FIRST LABEL | SECOND LABEL." in normalized
    assert "The Frame must preserve this exact pair" in normalized
    assert "Give each label one large, simple physical carrier" in normalized
    assert "No other readable or pseudo-readable content may appear" in normalized
    assert "The two clean label carriers are the only text-bearing surfaces" in (
        normalized
    )
    assert "Do not use any of these English words or their plurals" in normalized
    assert "Replace any candidate containing one of these words" in normalized
    assert "microtext, card, pass, knife, cleaver, blade" in normalized
    assert "weapon, pin, pinned, trap, trapped, force, forced" in normalized
    assert "The Theme premise itself must contain the complete visible proof" in (
        normalized
    )
    assert "Do not substitute vague phrases such as sexual activity" in normalized
    assert "Hardcore does not imply BDSM" in normalized
    assert "one Theme sentence must account for every requested participant" in normalized
    assert "Touching only oneself, clothing, furniture, or a prop does not qualify" in (
        normalized
    )
    assert "Never describe any participant as preparing, approaching" in normalized
    assert "Every erotic Frame must include at least one" in normalized
    assert "Bare shoulders, cleavage, exposed thighs, sleepwear" in normalized
    assert "the explicit interaction is the sole ongoing human action" in normalized
    assert "No participant simultaneously reads, types, calculates" in normalized
    assert "The humor comes from desire, etiquette, attention" in normalized
    assert "understandable without text" in normalized
    assert "Use a poster-like hierarchy" in normalized
    assert "at least four fifths of the composition" in normalized
    assert "Photograph each real performer frontally or in a shallow side pose" in (
        normalized
    )
    assert "one exact orthographic poster plane" in normalized
    assert "must not resemble people photographed together in a real room" in normalized
    assert "single matte field with no floor line, wall corner, ceiling" in normalized
    assert "Every Frame must visibly include the Theme's exact pair" in normalized
    assert "Every letter must be at least one twentieth of the image height" in (
        normalized
    )
    assert "each complete label must occupy at least one eighth" in normalized
    assert "inside the central eighty percent of the canvas" in normalized
    assert "minimum ten-percent safety margin" in normalized
    assert "inside ten-percent safety margin: WORK;" in normalized
    assert "Spell each locked label exactly twice in the complete Frame" in normalized
    assert "Repetition reinforces correct image rendering" in normalized
    assert "dedicated image-text passage at the absolute end" in normalized
    assert "Write exactly two entries" in normalized
    assert "minimum letter height, horizontal orientation, type weight" in normalized
    assert "Use the literal ASCII characters `: `" in normalized
    assert "Do not add an IMAGE-TEXT heading" in normalized
    assert "The Frame's final character" in normalized
    assert "Write this dedicated passage once only" in normalized
    assert "never restart or duplicate either carrier-copy entry" in normalized
    assert "Use this serialization grammar exactly" in normalized
    assert "After each colon, write only the exact locked label" in normalized
    assert "Every other surface must contain zero letters" in normalized
    assert "its entire visible typographic content must be one of the two" in normalized
    assert "If removing the words makes the satire unintelligible" in normalized
    assert "Do not use interpretive phrases such as symbolizes" in normalized
    assert "do not hard-code a sentence count" in normalized
    assert "one stable anchor sentence per adult when needed" in normalized
    assert "verbatim opening cast declaration" in normalized
    assert "The only supporting object is one [singular object]" in normalized
    assert "Name no other loose object, debris, food scatter" in normalized
    assert "Perform a final character scan on every Theme and Frame" in normalized
    assert "premium physical editorial photomontage" in normalized
    assert "full natural color and photographic tonal variation" in normalized
    assert "names, allowed identities, ages, facial anchors, hair" in normalized
    assert "base garments, chosen exaggerations, primary metaphor, and label pair" in (
        normalized
    )
    assert "Clothing may shift only as required by the selected interaction" in normalized
    assert "requested women and men visually unambiguous" in normalized
    assert "No generic shocked open mouths" in normalized


@pytest.mark.parametrize("level", list(ContentLevel))
def test_everyday_social_caricature_requires_multiple_adults_and_a_woman(level):
    document = load_story_document(RECIPES / "everyday-social-caricature.yaml")
    default = resolve_story_input(document, InputOverrides(content_level=level))
    assert (default.request.female_count, default.request.male_count) == (1, 1)

    expected = {
        (female, male)
        for female in range(1, 9)
        for male in range(9 - female)
        if 2 <= female + male <= 8
    }
    assert document.requirements.allowed_casts is not None
    assert {
        (cast.female_count, cast.male_count)
        for cast in document.requirements.allowed_casts
    } == expected
    assert len(expected) == 35
    for female, male in sorted(expected):
        resolved = resolve_story_input(
            document,
            InputOverrides(
                content_level=level, female_count=female, male_count=male
            ),
        )
        assert resolved.request.female_count == female
        assert resolved.request.male_count == male
        assert resolved.plans[0].cast.total == female + male
    for female, male in ((1, 0), (0, 1), (0, 2)):
        with pytest.raises(StoryConfigurationError, match="cast|female"):
            resolve_story_input(
                document,
                InputOverrides(
                    content_level=level, female_count=female, male_count=male
                ),
            )


def test_everyday_social_caricature_centers_women_and_lived_interaction() -> None:
    document = load_story_document(RECIPES / "everyday-social-caricature.yaml")
    brief = story_contract(document)
    normalized = " ".join(brief.split())
    assert len(brief.splitlines()) <= 150
    assert len(brief) <= 17_000
    assert document.generation.output_language == "english"
    assert document.requirements.output_languages == ("english",)
    assert any(check.type == "ascii" for check in document.validation.frames.checks)
    assert re.search(r"[\u4e00-\u9fff]", document.description)
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(output_language="chinese"))

    required_contract = (
        "创作原创、以女性为中心的社论式夸张讽刺画",
        "初看幽默、细想苦涩",
        "讽刺行为和关系，绝不讽刺身份本身",
        "请求的确切阵容",
        "动作与隐喻的因果关系",
        "严格采用脚本请求的女性和男性数量",
        "每位可见人物都是虚构、自愿、清醒、年满二十五岁的东亚成年人",
        "场景设在中国大陆、台湾、香港、日本、韩国或新加坡",
        "为每人从此列表逐字选用恰好一个身份短语",
        '"mainland Chinese"、"Taiwanese"、"Hong Kong Chinese"、"Japanese"、'
        '"South Korean" 或 "Singaporean Chinese"',
        "不得添加第二个国籍、公民身份、侨民身份、混合身份或矛盾身份",
        "明确写出每人的性别",
        "绝不用全大写姓氏",
        "每个主题和画面都只用英文 ASCII 编写",
        "将智能标点、乘号及非英文字符替换为普通 ASCII",
        "在 aesthetic 级",
        "在 erotic 级",
        "在 hardcore 级",
        "写明每位参与者的人体部位与接触角色",
        "拿无关物品、指导姿势或触碰衣物均不算",
        "按 A > B > C 并继续排列阵容",
        "仅允许相邻配对的性接触",
        "C 绝不接触 A",
        "一个专属目标",
        "行为是独立选择的娱乐",
        "绝不是证据、付款、入门仪式、惩罚、要挟手段",
        "无人索要、要求、强迫、购买、交换、奖赏或记录该行为",
        "从头到脚醒目的社论式造型",
        "一种大胆服装轮廓",
        "高对比色块",
        "不能变成另一种变形、标签、符号或隐喻",
        "拒绝通用默认办公服",
        "一片宽广哑光色域，加至多两个指示地点的简单几何线索",
        "不得有房间陈设清单、杂乱装饰",
        "阵容、主要结构和成对母题主导图像",
        "恰好两个协调的变形层次",
        "一组连贯的面部夸张，至少改变眼睛、眉毛、脸颊、嘴、下颌、鼻子和发型中的两项",
        "沿纵向拉长、沿横向加宽或均匀放大",
        "正常尺度的二到四倍",
        "沿纵向缩短、沿横向收窄或均匀缩小",
        "正常尺度的二分之一到四分之一",
        "明确写出两项面部改变",
        "只能采用一个允许的动词与轴向组合及一个数值尺度",
        "绝不能混合相反的尺寸动词或改变第二条轴",
        "泛化表情或未量化形容词不合格",
        "对应肢体和相邻部位保持普通",
        "均不能满足所需的非面部层次",
        "画面不得创造、扩散、加强或转移其主题未包含的变形",
        "其余每位成年人恰好获得一种不同的次级面部、身体或肢体变形",
        "只能选择一组面部特征或一项身体或肢体改变，不可兼有",
        "若选身体或肢体，面部保持普通",
        "若选面部，所有身体比例保持普通",
        "尺度改变在指定关节处明确停止",
        "面部、身体、手势和动作必须传达同一种特质",
        "一个闭合反应回路",
        "占画布百分之三十五到五十",
        "写明每个接触点、力的方向、即时物理变化",
        "为每位具名成年人提供一个可见的接触—力—结果分句",
        "露骨行为是唯一正在进行的人类动作",
        "描述一个定格瞬间",
        "左右及遮叠位置、朝向、承重支撑",
        "每次接触须写明两个解剖上可相互到达的表面",
        "保持一致的空间占用图",
        "无肢体穿过身体或结构",
        "无无支撑悬浮",
        "任何身体不得穿串、环绕、包缠、编织穿过开口、框架、栏杆、网、家具或结构，也不得被它们横切",
        "反光道具只显示抽象眩光，绝不重复人物或人体部位",
        "不改变连接、平衡、伸达路径、碰撞或载荷传递",
        "硬边只能接触脚、膝、手或前臂",
        "宽阔平面可无压迫地支撑背部或坐部",
        "任何结构都不得挤压、楔住、困住或横切头",
        "B 必须位于实际空间中央，并直接邻接两个端点",
        "左右顺序必须是 A-B-C 或 C-B-A",
        "任何人或肢体均不得越过第三个人，或从其后方、周围、上方、下方或体内绕行来接触",
        "若场面无法在物理上重建，须重新设计",
        "先建立完整物理场面图，再描述",
        "只使用一个辅助母题，以两个相关实体呈现",
        "分别拍摄的真实成年表演者",
        "大胆的成人报纸丝网印刷",
        "每个变形剪贴内的人体皮肤、眼睛、头发、手和布料均保留摄影纹理",
        "在自然皮肤和头发之外恰好四种主导平面专色色域",
        "受控的图形透视缩短",
        "必须不依赖镜头远近而仍不可能",
        '"Locked image labels: FIRST LABEL | SECOND LABEL."',
        "每个锁定标签只拼写一次，且仅在末尾序列化中出现",
        "绝不选本来就带文字的物品作主要结构或辅助母题",
        "参与者接触图、空间占用图",
        "丢弃整份草稿并重建",
        '"Cast:" 列出每个人首字母大写的姓名、至少二十五岁的年龄',
        '"Deformations:" 使用格式 "CENTRAL NAME',
        "明确的女性或男性",
        "feature plus alteration; feature plus alteration",
        "one nonfacial part, allowed verb-axis pair, and valid scale",
        '"Consent:" 声明每位成年人都自由选择了与社会利害无关的娱乐',
        '"Staging:" 固定 A-B-C 或 C-B-A 空间顺序、B 居中',
        '"Hardcore proof: Chain A > B > C.',
        "No other sexual contact.",
        "统一的真人报纸照片蒙太奇媒介",
        '"Hybrid real-person newspaper photomontage with biting anatomical caricature:"',
        '"Exactly [requested total] East Asian adults fill the image',
        "严格保留主题中的每个年龄、身份、服装、变形、链条顺序",
        "媒介混杂",
        "可互换衣装",
        "杂乱背景",
        "非相邻或重复的接触配对",
        "接触数不是人数减一",
        "链条中点不在空间中央",
        "接触跨越第三位成年人",
        "共用人体目标",
        "辅助成年人同时有面部和身体改变",
        "相反的尺度动词",
        "变形扩散至相邻部位",
        "身体穿过结构",
        "硬边抵住身体核心部位",
        "结构挤压或困住身体",
        "非 ASCII 字符",
        "无支撑、相交或无法重建的场面",
    )
    for marker in required_contract:
        assert marker in normalized, marker

    for conflict in (
        "立即接续完整的主导视觉图标",
        "不得使用摄影",
        "选择一种连贯的原创媒介",
        "约占图像三分之一",
        "每个主题选择一种主导变形语法",
        "两位成年人各自不同的主导变形",
        "五至八个完整句子",
        "前提不得超过两句话",
        "前景、中景、背景",
        "强制透视",
        "视点、距离或透视",
    ):
        assert conflict not in normalized, conflict


def test_creative_brief_uses_open_ended_high_concept_ideation() -> None:
    document = load_story_document(RECIPES / "creative.yaml")
    brief = story_contract(document)
    normalized = " ".join(brief.split())
    for marker in (
        "候选概念数量至少为所需数量的两倍，且不得少于十二个",
        "明显混合单物件主题与多物件组合主题",
        "力求两者各占约一半",
        "由两到五个熟悉物件构成的协调组合",
        "真实日常环境中的小居民",
        "在物件之间移动",
        "用一个物件改变另一个",
        "不要散放无关的巨型道具",
        "至少八种明显不同的日常用途类别",
        "至少五个常规尺寸区间",
        "选择至少三个通常比成年人手掌更大的物件",
        "能完全握在成年人合拢手掌中的物件不得超过三个",
        "如果移除人物后只剩材质演示",
        "至少六种实质不同的主要驱动机制",
        "受规则支配的制度为核心的主题不得超过两个",
        "采用同一种关系模式的主题不得超过两个",
        "六种真正不同的图像表现机会",
        "六幅图像只是依次展示六个部件",
        "竞赛、市场、许可制度或亲密经济体系",
        "在六个区域中的至少两个区域里",
        "以一眼就能认出是日常使用的方式使用该物件",
        "符合设计用途的方式使用物件",
        "绝不将任何身体置于物件内部",
        "日常使用绝不构成进入内部的许可",
        "一次来自外部常规尺度、且贴合物件的日常使用碰撞",
        "至少四个视觉巧招必须改变人物的目标",
        "即使移除全部性感内容，至少两个仍须具有吸引力",
        "恰好五个分号",
        '无论 "frames_per_theme" 的值为何，每个叙事画帧都是一个完整的竖幅 2 列 3 行网格',
        "绝不将一张概念板分散到多个画帧、为每个区域各用一个画帧",
        '原文提示词 "Region 1:" 至 "Region 6:"',
        "每个都必须能够独立作为广告主视觉",
        '不要将 "erotic" 或 "hardcore" 淡化成中性图像',
        "受控的移轴或微距式选择性对焦",
        "首先确保它在缩略图尺寸下清晰可读",
        "至少使用四个远景或中景，展示完整的成年身体",
        "用于近距离细节的区域不得超过两个",
        "一个完整物件或物件组合的主视觉",
        "避免将宽大而无特征的侧面当作墙壁",
        "掩盖人物与物件的比例",
        "其他表面图形体系",
        "也可以强化尺度感",
        "沿物件表面的微缩人物眼平视角",
        "以完整轮廓衬托微小身体的高位斜视角",
        "这是清晰利落的编辑式广告摄影，而不是电影剧照",
        "不要使用电影化调色",
        "使用明亮、洁净的高调色彩",
        "有意设计的互补色对比",
        "一眼可读的主导色彩关系",
        "大胆的周围色块",
        "避免让不锈钢灰",
        "不要让浅色皮肤、浅色服装、浅色物件和浅色背景处于同一色调区间",
        "精心制作的商业桌面广告",
        "保留可见细节的通透暗部",
        "并非硬性质量门槛",
        "这些优先项用于指导筛选和修订",
        "不可妥协的网格、人物构成、仅限外部、内容级别和数据模式契约仍属强制要求",
    ):
        assert marker in normalized, marker
    assert (
        '"A portrait 2-column by 3-row grid forms one image with six cleanly '
        "separated regions. Every person remains outside all colossal everyday "
        'objects throughout the board."'
    ) in normalized
    for conflict in (
        "当 frames_per_theme 为 1 时",
        "满足以下情况时淘汰候选方案",
        "满足以下情况时拒绝主题",
        "- T001:",
    ):
        assert conflict not in brief, conflict
    assert document.generation.output_language == "chinese"
    for frames_per_theme in (1, 6):
        resolved = resolve_story_input(
            document, InputOverrides(frames_per_theme=frames_per_theme)
        )
        assert resolved.request.frames_per_theme == frames_per_theme
        layout = next(
            module for module in resolved.modules if module.kind == "layout_multiview"
        )
        assert layout.parameters.layout == "grid"
        assert (layout.parameters.rows, layout.parameters.columns) == (3, 2)
        assert (layout.parameters.min_views, layout.parameters.max_views) == (6, 6)


def test_edo_warai_e_brief_respects_all_content_levels() -> None:
    document = load_story_document(RECIPES / "edo-warai-e.yaml")
    brief = story_contract(document)
    normalized = " ".join(brief.split())

    assert document.authoring.frames.content_levels
    assert "aesthetic：让每位成年人完整穿着多层时代服饰" in normalized
    assert "呈现毫不含糊的成年性感" in normalized
    assert "明确色情但非露骨的互动" in normalized
    assert "hardcore：在每个主题与画面中呈现已经发生的露骨、自愿成年性行为" in normalized
    assert "不得用屏风、扇子、被褥、衣袖、家具、策略性裁切、遥远剪影或喜剧插曲隐藏定义性内容" in normalized
    assert "在 erotic 等级，衣袍可以敞开" in normalized
    assert "在 hardcore 等级，成年人可部分或完全裸体" in normalized
    assert "直接确立所要求内容等级的身体遮盖、衣物状态、当前互动" in normalized
    assert "每个画面开头即须使所选等级的定义性状态已经可见" in normalized
    assert "在每个画面中保留主题的露骨行为" in normalized
    aesthetic = document.authoring.frames.content_levels[ContentLevel.AESTHETIC]
    for level in (ContentLevel.EROTIC, ContentLevel.HARDCORE):
        resolved = resolve_story_input(document, InputOverrides(content_level=level))
        frames = resolved.rules.text_for(StoryStage.FRAMES)
        assert all(rule not in frames for rule in aesthetic)


def test_edo_warai_e_requires_live_action_ukiyo_e_evidence() -> None:
    document = load_story_document(RECIPES / "edo-warai-e.yaml")
    normalized = " ".join(story_contract(document).split())
    for marker in (
        "由成年表演者演绎的平面、无边框 nishiki-e 戏剧画面",
        "由真实成年表演者演绎",
        "而非真正的木版画",
        "类似主版线条的轮廓分隔",
        "江户 nishiki-e 配色",
        "平坦、分隔的色块",
        "恰好一道限于上方条带的 bokashi 风格渐变",
        "在缩略图尺寸和正常观看距离下，每个画面都必须先读作平面 nishiki-e 构图",
        "恰好组织为三条与画面平面平行的浅叠画带",
        "主导性的平面剪影",
        "不使用体积明暗塑形",
        "Bokashi 仅限一个背景平面",
        "近看时，可通过个性化的成熟脸型",
        "辨认真人表演者",
        "这些近看线索绝不能推翻远看的平面印象",
        "所有成年人都留在中央画带",
        "不得以远近尺度变化或向外伸出的透视缩短肢体打破平面",
        "当前动作句后立即重复此确切平面媒介锁定句",
        "恰好两种近看表演者线索，仅可从成熟脸型、连贯外侧关节轮廓、"
        "可见手部归属、服装接缝或套准织物图案中选择",
        "目标为 700 至 900 个英文单词",
        "绝不超过 1000 个英文单词",
        "三至五种具体的日常老化与使用迹象",
        "受保护接缝处仍较浓",
        "按触摸、摩擦、烟、湿气与日晒分配磨损",
        "不得使整幅图像变成棕色、米色、灰色或去饱和",
        "成年人的皮肤须保持为暖色、有界哑光色域",
        "不得使用全局棕褐或泛黄偏色、摄影颗粒",
        "扫描版画损坏",
        "仅返回正面描述所描绘场景的正文",
        "默默执行所有规则",
        "每个词都必须属于图像生成描述",
        "直接说出正在发生的行为",
        "普鲁士蓝仅限于 1820 年代及之后的场景",
        "不得添加技术拍摄规格",
        "光学景深模糊",
    ):
        assert marker in normalized, marker
    opening = (
        "Flat, borderless nishiki-e theatrical picture plane in a "
        "[chūban-like or ōban-like] [vertical or horizontal] proportion, enacted "
        "by real adult performers. Exactly three shallow stacked picture bands: "
        "a lower prop strip, a central adult tableau, and an upper architectural "
        "strip, all parallel to the image surface. Adult faces, limbs, garments, "
        "and furniture read as contour-enclosed matte color shapes with crisp "
        "overlaps and two-step values; contour and flat shadow shapes carry all "
        "form. Edo-period material patina appears only as bounded wear on physical "
        "costumes, props, and set surfaces."
    )
    assert f'"{opening}"' in normalized
    assert (
        '"All visible bodies, garments, props, and room planes return immediately '
        "to contour-enclosed matte color shapes on the same flat three-band "
        'nishiki-e surface."'
    ) in normalized
    for level, literal in (
        (ContentLevel.AESTHETIC, "The current fully clothed non-erotic interaction is"),
        (ContentLevel.EROTIC, "The current erotic but non-explicit interaction is"),
        (ContentLevel.HARDCORE, "The current explicit consensual adult sexual act is"),
    ):
        assert f"“{literal}”" in "\n".join(
            document.authoring.frames.content_levels[level]
        )
    for conflict in (
        "一个可解的三维布局",
        "前景、中景和背景",
        "真实成年表演者的实拍图像",
        "单根毛发",
        "细微皮肤变化",
        "全画幅或中画幅相机",
        "毫米等效",
        "光圈行为",
    ):
        assert conflict not in normalized, conflict
    assert "而非圆润光照、皮肤纹理或光学纵深" in normalized
    word_count = next(
        check for check in document.validation.frames.checks
        if check.type == "word_count"
    )
    assert word_count.when_language == "english"
    assert word_count.max_words == 1000


def test_ming_gongbi_mixi_tu_owns_historical_painting_contract() -> None:
    document = load_story_document(RECIPES / "ming-gongbi-mixi-tu.yaml")
    normalized = " ".join(story_contract(document).split())
    for marker in (
        "匿名晚明江南画坊册页",
        "1573至1644年间",
        "在熟绢上绘制的历史册页画",
        "皮肤与五官采用游丝般细腻的线条",
        "衣物与家具采用铁线般稳定的线条",
        "以界画的规整线法描绘",
        "使用三矾九染的视觉逻辑",
        "五至七个主要色系",
        "使用散点透视",
        "平面画幅必须主导第一印象",
        "最少的色调塑形",
        "不得使用体积光影塑形",
        "岁月痕迹必须在第一眼及缩略图尺寸下可见",
        "绘画与工笔技法约贡献三分之二的印象",
        "可见的材料老化贡献三分之一",
        "二至四条浅层、叠置、重叠的带状区域",
        "轮廓封闭的色域",
        "一处断续的深茶褐边缘氧化斑",
        "一道浅旧折痕",
        "古旧熟绢画面连续延伸至画布的每一条边",
        "不得出现可见的装裱留边、卡纸、画框、边框或矩形边带",
        "边缘旧痕必须断续、变化并不规则地向内消散",
        "每个人物、衣物、物件和建筑平面都只以绢上的墨线轮廓与颜料存在",
        "成年人是具有个体特征的工笔肖像，成熟面部线条各有差别",
        "细微不对称",
        "严格使用三种克制肤色",
        "每一笔都仍明显是绢上的墨或矿物色",
        "手绘古绢册页的平面档案摹本",
        "使用无边框的满幅出血构图",
        "紧接当下动作句后重复以下紧凑的媒介锁定原文",
        "严格使用四句描述",
        "固定五句开头之后，任何一句都不得超过60个英语单词",
        '必须逐字保留的短语 "three shallow stacked bands"',
        "硬性限制为350至750个英语单词",
        "返回前计数",
        "三至五处局部且物理合理的岁月线索",
        "日本浮世绘",
        "现代国潮插画",
        "不得生成可读汉字",
        "不直接命名或描述男性生殖解剖结构",
        "主题或画面中提及的每个人都必须属于所要求的人物阵容",
        "不得将不在场的配偶",
    ):
        assert marker in normalized, marker
    opening = (
        "Full-canvas continuous-silk flat archival facsimile of a hand-painted "
        "antique late-Ming Jiangnan gongbi mixi-tu album leaf. The aged prepared-silk "
        "painting extends continuously to every canvas edge as an uninterrupted "
        "uneven warm-tea field. Every person, garment, object, and architectural "
        "plane exists only as ink contour and pigment on silk; adult figures use "
        "individualized mature facial lines, plausible adult proportions, clear "
        "joints, and exactly three bounded skin tones in the same silk plane. "
        "Flat gongbi picture plane with shallow stacked spaces, contour-enclosed "
        "color fields, dominant flat silhouettes, no volumetric light-and-shadow "
        "modeling or cast shadows. Fine gossamer-line and iron-wire contours, thin "
        "layered mineral-color washes, ruled-line jiehua interior, visible silk "
        "weave, softened outer pigments, rubbed silk fibers at one isolated edge, "
        "and small age creases."
    )
    assert f'"{opening}"' in normalized
    assert (
        '"Every person, garment, object, and architectural plane exists only as ink '
        "contour and pigment on visibly aged silk; adults remain contour-defined "
        'gongbi figures with mature facial specificity and plausible proportions."'
    ) in normalized
    assert (
        '"The entire image remains a visibly aged, flat, hand-painted gongbi silk '
        "album leaf made from ink contours and mineral pigment, with individualized "
        'mature adult faces defined by fine line."'
    ) in normalized
    assert '"The current explicit consensual adult sexual act is"' in "\n".join(
        document.authoring.frames.content_levels[ContentLevel.HARDCORE]
    )
    assert "熟绢或施胶宣纸" not in normalized
    frame_contract = "\n".join(document.authoring.frames.common)
    for photography_trigger in (
        "从生活中观察",
        "栩栩如生",
        "活生生的成年模特",
        "细微肌肤变化",
        "可信重量",
        "根据观察绘制",
    ):
        assert photography_trigger not in frame_contract, photography_trigger
    word_count = next(
        check for check in document.validation.frames.checks
        if check.type == "word_count"
    )
    assert word_count.when_language == "english"
    assert (word_count.min_words, word_count.max_words) == (350, 750)


def test_pose_brief_selects_a_varied_text_free_six_pose_group() -> None:
    document = load_story_document(RECIPES / "pose.yaml")
    normalized = " ".join(story_contract(document).split())
    for requirement in (
        "可辨认的、双方自愿的成人性姿势",
        "中性的舞蹈、瑜伽、健身、康养、时装",
        "身体力学本身必须承载性意图",
        "不得把库中的条目中性化",
        "独立、多样化地选取恰好六种姿势蓝图",
        "不得选取六个相邻条目",
        "从至少四个不同的姿势类别标题下，不按顺序选取六种姿势",
        "分配恰好六种不同的镜头角度蓝图",
        "使用至少四种不同的方位类别",
        "至少三个机位高度或俯仰角度带",
        "即使左右镜像也不行",
        "全画幅50-85毫米",
        "姿势与镜头蓝图",
        "从左侧髋部高度取前侧四分之三视角",
        "一个主导区域和五个辅助区域",
        "每个内容级别都必须选择具体可穿戴的造型",
        "一个具体的成人场合",
        "该画面内的全部六个区域必须共享",
        "不同画面和不同主题",
        "先用尽未使用的环境类别",
        "而不是一个固定房间",
        "共享背景仅指在同一幅画面内共享",
        "不要求不同画面或主题重复使用相同场合",
        "每幅画面都点明六个区域共享的一个具体场合与地点",
        "须明确具体服装与配饰单品",
        "主题设定必须点明完整的所选造型",
        "每幅画面都必须在描述区域之前，用可见图像语言完整重述所选造型",
        "至少包含一件真实服装或可穿戴配饰",
        "服装绝不隐含、不泛化",
        "恰好占一个物理行",
        "全部六个区域的完整描述放在该画面的一个连续自然语言段落中",
        "绝不可将一张参考板分散到多幅画面",
        "每个区域单占一幅画面",
        "没有任何画面只是一个区域、参考板片段",
        "完成的参考板没有可见标题、姿势名称",
        "区域数量表示一幅图像的内部划分，不是叙事画面数量",
    ):
        assert requirement in normalized, requirement
    for level, garment_scale in (
        (ContentLevel.AESTHETIC, "服装尺度为完整尺寸"),
        (ContentLevel.EROTIC, "服装尺度缩减至内衣尺寸"),
        (ContentLevel.HARDCORE, "服装尺度为极简或微型"),
    ):
        resolved = resolve_story_input(document, InputOverrides(content_level=level))
        assert garment_scale in resolved.rules.text_for(StoryStage.FRAMES)
    layout = next(
        module for module in document.modules if module.id == "layout-multiview"
    )
    assert layout.parameters == {"layout": "grid", "min_views": 6, "max_views": 6}

    def pool(label, *, stage=StoryStage.THEMES):
        authored = getattr(document.authoring, stage.value)
        rules = (*authored.common, *authored.content_levels[ContentLevel.HARDCORE])
        prefix = f"{label}：- "
        return [rule.removeprefix(prefix) for rule in rules if rule.startswith(prefix)]

    occasion_entries = []
    for family in (
        "专业影像创作",
        "私人住宅",
        "旅宿与休憩",
        "艺术、设计与表演",
        "私密康养与休闲",
        "建筑展示",
        "幽静户外环境",
        "季节与氛围场合",
    ):
        entries = pool(family, stage=StoryStage.FRAMES)
        assert entries, family
        occasion_entries.extend(entries)
    assert len(occasion_entries) >= 40
    assert len(occasion_entries) == len(set(occasion_entries))
    camera_entries = pool("精选镜头角度库")
    assert len(camera_entries) >= 15
    assert len(camera_entries) == len(set(camera_entries))
    for direction in ("正面", "侧面", "后方"):
        assert any(direction in entry for entry in camera_entries), direction
    pose_entries = []
    for family in (
        "正向展示站姿",
        "后向展示站姿与髋折叠姿势",
        "坐姿与跨坐",
        "跪姿与脚跟支撑",
        "蹲伏与深蹲",
        "仰卧与骨盆抬高",
        "侧卧与扭转",
        "俯卧与胸部支撑",
        "手膝与前臂支撑",
    ):
        entries = pool(family)
        assert entries, family
        pose_entries.extend(entries)
    assert len(pose_entries) >= 81
    assert len(pose_entries) == len(set(pose_entries))
    pool_text = "\n".join(pose_entries)
    for excluded in ("隐形墙", "不可见的墙", "诱惑地", "缓慢"):
        assert excluded not in pool_text, excluded


def test_threshold_emergence_brief_locks_cast_geometry_and_batch_variety() -> None:
    document = load_story_document(RECIPES / "threshold-emergence.yaml")
    normalized = " ".join(story_contract(document).split())
    required = (
        "绝不把请求中的人物全部当作目击者后，再添加穿出者",
        "每个可见或暗示存在的人都计入人物数量",
        "源内侧身体必须仍是可辨认的人体结构",
        "源平面恰好在腰、髋部或大腿上部与身体相交一次",
        "身体约百分之四十至六十处于每一侧",
        "骨盆加至少一条完整相连的腿位于内侧",
        "成年人头朝前、垂直于屏幕爬出",
        "腰部周围的边框保持完整可见",
        "一个相机、一个连续外侧地点",
        "源内部只出现在电视屏幕、影院银幕、画框、镜框、窗户、舱口或开口的精确限定区域内",
        "每个画帧以一个简洁的几何锁定句结尾",
        "没有分屏、第二套布景、反射复制体",
        "不要把内侧半身压平、绘画化、像素化、溶解",
        "没有全身波纹、半透明叠层",
        "相同的自然皮肤、服装、体积",
        "不要先承诺有文字，再在别处否定",
        "五主题批次中，每种类别恰好使用一次",
        "一个家庭、晚餐、聚会或其他私人社交场景",
        "一个影院、剧院、音乐会、体育、游戏或其他集体休闲场景",
        "一个花园、公园、海滩、山地、农场",
        "一个列车、车站、渡轮、机场、公路停靠点",
        "一个商店、办公室、工作室、实验室、作坊、服务柜台、专业厨房或其他工作场所",
    )
    missing = [text for text in required if text not in normalized]
    assert not missing, missing


def test_magazine_cover_brief_builds_a_finished_newsstand_cover() -> None:
    document = load_story_document(RECIPES / "magazine-cover.yaml")
    normalized = " ".join(story_contract(document).split())
    resolved = resolve_story_input(document)
    assert document.generation.output_language == "english"
    assert document.requirements.output_languages == ("english",)
    assert resolved.request.output_language == "english"
    assert any(check.type == "ascii" for check in document.validation.frames.checks)
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(output_language="chinese"))
    visible_copy = next(
        module for module in resolved.modules if module.kind == "visible_copy"
    )
    assert visible_copy.parameters.product == "magazine_cover"
    assert visible_copy.parameters.copy_language == "english"
    assert visible_copy.parameters.ascii == "required"
    for marker in (
        "顶部一个原创且持续使用的刊头",
        "恰好两条简短次要封面标题",
        "不得使用电影海报信号",
        "不得使用社交帖子信号",
        "不得展示实体样机",
        "平面、满版出血的竖版 3:4 正面封面",
        "可见文案总量须少于二十四个英语单词",
        "字母高度至少约为封面高度的百分之四",
        "不得渲染条码、二维码、ISBN、ISSN",
        "可见文案不得使用小写字母、数字、标点",
        "每个精确字符串必须匹配 `[A-Z]+( [A-Z]+)*`",
        "绝不使用 `&`，改写为原样文字 `AND`",
        "绝非日期、月份、年份、卷、版本",
        "商标符号、注册标记、上标",
        "Frame 全文必须使用英语",
        "完整 Frame 的每个字符都必须位于 ASCII 码点 0 至 127",
        "单个非 ASCII 字符即可使 Frame 无效",
        "恰好使用三个受控排版区域",
        "一个对齐的信息块",
        "所有精确可见文案都隔离到最后段落",
        "任何连续两个及以上的大写字母序列",
        "五个精确字符串各出现且仅出现一次",
        "Frame 最后一个字符是结束季节标记条目的分号",
        "专用图中文字段落是可见文案的唯一来源",
        "恰好包含五个条目，顺序为刊头、主要专题标题、第一条次要标题、第二条次要标题、季节标记",
        "加冒号，再写精确大写文字，以分号结尾",
        "绝不以引号、括号、框、代码格式或装饰标记包围可见文字",
        "添加字面 ASCII 字符 `: `",
        "以字面 ASCII 字符 `;` 结束",
        "Frame 的最后一个字符必须是 `;`",
        "占封面约百分之六十至八十的主导主图",
        "在 hardcore 级别",
        "结果是一张平面竖版 3:4 杂志正面封面",
        "槽位数量、重复出现的位置、允许的载体、排版区域和产品版式均由配方规定",
    ):
        assert marker in normalized, marker
    for literal in (
        "The cover contains exactly five readable English strings and zero other "
        "letters, words, numbers, symbols, pseudo-letters, or glyph-like marks.",
        "The five declared English strings are the complete typographic layer; "
        "all remaining cover areas are pure photography, uninterrupted color, "
        "or blank negative space.",
    ):
        assert f'"{literal}"' in normalized
    frame_contract = "\n".join(document.authoring.frames.common)
    for season in ("SPRING", "SUMMER", "AUTUMN", "WINTER", "SPECIAL"):
        assert f'"{season}"' in frame_contract


def test_extreme_absurdity_requires_visible_human_prop_contact_chain() -> None:
    normalized = " ".join(
        story_contract(load_story_document(RECIPES / "extreme-absurdity.yaml")).split()
    )
    required = (
        "明确具体参与者、具体身体部位、具体道具表面、接触方向及持续施力",
        "仅在近旁、隐含、自动或未被触碰的道具无效",
        "从人体接触点到道具当前状态，追踪一条不中断、可见的力传递路径",
        "在前两句内说明人与道具接触点",
        "为每位成年人提供可见的身高和体型",
        "承重面积、关节及其他人周围的空隙",
        "整个画面保持同一尺度",
        "像摄影师正看着一张完成的静帧并只描述眼前可见内容那样写作",
        "说明面部朝向、目光目标、通过眉毛、眼睑、嘴、下颌及面颊张力呈现的可见表情",
        "将最终效果描述为当前可见几何",
        "等抽象因果动词替代可见接触、力路径与最终物理结果",
        "为每位参与者提供独特、稳定且可拍摄的完整造型",
        "不得有人呈现为没有造型的普通裸体",
        "夸张但物理可信的发型",
        "为每位参与者明确可见妆容",
        "分配互补颜色与不同剪影",
    )
    missing = [text for text in required if text not in normalized]
    assert not missing, missing


def test_near_future_plans_preserve_world_seed_and_action_cycles() -> None:
    resolved = resolve_story_input(
        load_story_document(RECIPES / "near-future-intimacy-realism.yaml"),
        InputOverrides(theme_count=31),
    )
    solo_actions = []
    group_actions = []
    seeds = []

    assert len(resolved.plans) == 31
    for instruction in (
        resolved.request.story,
        *resolved.rules.themes,
        *resolved.rules.frames,
    ):
        assert re.search(r"\bT\d{3}\b", instruction) is None
    for index, plan in enumerate(resolved.plans):
        assert plan.entry is not None
        assert plan.entry.id == f"seed-{index % 30 + 1:02d}"
        bucket = "ABCDEFGHIJ"[index % 10]
        for rules in (plan.entry.themes, plan.entry.frames):
            assert all(re.search(r"\bT\d{3}\b", rule) is None for rule in rules)
            assert any(
                rule.startswith(f"已选场景世界分桶 {bucket}：")
                for rule in rules
            )
        seeds.append(
            next(
                rule for rule in plan.entry.themes
                if rule.startswith("已选场景种子：")
            )
        )
        solo_actions.append(
            next(
                rule for rule in plan.entry.themes
                if rule.startswith("当请求的总人数为一名成年人时，")
            )
        )
        group_actions.append(
            next(
                rule for rule in plan.entry.themes
                if rule.startswith(
                    "当请求的总人物构成包含两名或更多成年人时，"
                )
            )
        )
        assert seeds[-1] in plan.entry.frames
        assert solo_actions[-1] in plan.entry.frames
        assert group_actions[-1] in plan.entry.frames

    assert len(set(seeds[:30])) == 30
    assert seeds[30] == seeds[0]
    for actions in (solo_actions, group_actions):
        assert len(set(actions[:10])) == 10
        assert all(
            action == actions[index % 10] for index, action in enumerate(actions)
        )
    assert sum("自慰" in action for action in group_actions[:10]) >= 2
    bdsm_families = ("束缚", "拍打", "蒙眼", "支配", "捆绑")
    assert sum(
        any(family in action for family in bdsm_families)
        for action in group_actions[:10]
    ) >= 4
    assert sum("插入" in action for action in group_actions[:10]) <= 3
    for stage in StoryStage:
        context = resolved.context_for(stage, ["T009", "T011", "T030", "T031"])
        assert [plan["theme_id"] for plan in context["plans"]] == [
            "T009", "T011", "T030", "T031"
        ]
        assert [plan["entry"]["id"] for plan in context["plans"]] == [
            "seed-09", "seed-11", "seed-30", "seed-01"
        ]
        assert all(
            re.search(r"\bT\d{3}\b", rule) is None
            for plan in context["plans"]
            for rule in plan["entry"]["rules"]
        )


def test_near_future_intimacy_uses_compact_conditional_contract() -> None:
    document = load_story_document(RECIPES / "near-future-intimacy-realism.yaml")
    brief = story_contract(document)
    normalized = " ".join(brief.split())
    assert len(brief) < 54_000
    assert document.generation.output_language == "english"
    assert set(document.requirements.output_languages) == {"english"}
    checks = {check.type: check for check in document.validation.frames.checks}
    assert checks["ascii"].when_language == "english"
    assert checks["word_count"].when_language == "english"
    assert checks["word_count"].min_words == 600
    assert checks["word_count"].max_words is None

    for requirement in (
        "冷峻、带生活痕迹的写实",
        "精确可见身体数",
        "每个成年人都有独特完整造型",
        "完整的周围环境，包含至少八个紧凑现实锚点",
        "分布在所有纵深层的至少六件独立道具",
        "同时呈现房间尺度、身体尺度和性接触尺度",
        "完整受力路径、重心、投影",
        "获准的全息成年人形态",
        "获准的冷却悬吊形态",
        "获准的轨道龙门架形态",
        "精确遵循批次路由，使场景世界和性动作各不相同",
        "仅写正向、可见的指令",
        "绝不将规则、排除项、警告",
        "返回前",
        "每个画面至少写 600 个英语单词",
        "只要具体视觉细节仍然有用，就不设固定上限",
        "600 词的最低要求是硬性限制",
        "将人物构成、动作、解剖结构和技术放在前半段",
        "图像不包含说明文字、字幕、标志",
        "请求的完整人物构成",
        '"Exactly N adults and N complete bodies occupy the entire image."',
        '"Exactly two adults and two complete bodies occupy the entire image, '
        'one 38-year-old Chinese woman named Mei and one 42-year-old Chinese man named Jun."',
        "这一对伴侣始终是唯一的人体轮廓组",
        '"a 38-year-old Chinese woman named Mei and a 42-year-old Chinese man named Jun"',
        '始终在每个姓名旁写出 "woman" 或 "man"',
        "将 female_count 和 male_count 视为不可更改的性别名额",
        '仍须使用与请求名额对应的词语 "woman" 或 "man"',
        '两名女性和一名男性："one NN-year-old woman named A, '
        'one NN-year-old woman named B, and one NN-year-old man named C"',
        '一名女性和两名男性："one NN-year-old woman named A, '
        'one NN-year-old man named B, and one NN-year-old man named C"',
        "在每个画面中独立重述请求的完整性别构成",
        "每个请求的人呈现一个可见身体和一张脸",
        "女性有一个外阴，男性有一根与其骨盆连续相连的阴茎",
        "双方耻部直接接触",
        "外部仅可见相连的根部",
        "在前 120 个词内描述完整接触几何",
        "双方耻部裸露且直接相压",
        "所有下装均从双腿完全脱除",
        '"Both bare pubic regions press directly together; the man\'s single penis '
        "is rooted continuously in his fully unclothed pelvis, most of its shaft "
        "is visibly enveloped by the woman's vagina, and only its attached base "
        'remains visible at their touching pubic skin."',
        "仅有躯干的代理体",
        "呈现抽象光线或空房间的建筑结构",
        "从一侧边缘到另一侧边缘都明显无人",
        "所有活动均由具有知情同意能力的成年人自愿进行",
        "将专业服务与性活动分开",
        "分别描述每个人",
        "体型、身高印象、肤色",
        "脸型和可见五官",
        "发型的颜色、长度、质感、剪裁、分缝",
        "可见的仪容修整或妆容",
        "通过视线方向、眼睑、眉毛、嘴部、下颌、面颊紧张程度呈现当前表情",
        "每一件衣物和鞋履",
        "一至三件个人配饰",
        "裸体不取消造型要求",
        "脱下衣物的精确位置",
        "一个清楚可见且正在进行的明确性动作",
        "独自自慰、伴侣引导的自慰、双方各自自慰",
        "双方同意的 BDSM",
        "本规则覆盖下文所有场景种子、技术类别、模块",
        "恰好呈现一名成年人、一个完整身体、一张脸和一个轮廓",
        "唯一的成年人进行独自自慰",
        "另一只手自由操作释放装置",
        "小型非阴茎形振动器",
        "由一名伴侣清楚可见地握在手中",
        "从肩部经过肘部、手腕、手掌和手指，连续追踪主动手",
        "为每名成年人安排独立的手对身体动作",
        "明确自愿角色",
        "展示双向同意",
        "每处束缚均有可见快速释放装置",
        "拍打仅落在肉厚的臀部或大腿外侧",
        "在前 120 个词内确立一个裸露且无遮挡的接触中心",
        "将长裤、内裤、裙子和其他下装从双腿上完全脱除",
        "支撑硬件须完全位于双方耻部之外",
        "处于通电、穿戴、连接",
        "同一主题下的画面是同一设定的备选照片",
        "每个主题恰好选择一项主要推想发展",
        "房间尺度：",
        "身体尺度：",
        "接触尺度：",
        "至少包含六个连贯的未来信号",
        "改装的巨型都市家居",
        "粗野主义栖居舱设施",
        "适应气候的室内",
        "光谱远程临场房间",
        "至多两个使用常规卧室、床垫、铺位或旅馆房间",
        "绝不重复地点类型、主要技术类别",
        "在改变造型之前，先让场景轮廓明显不同",
        "通过微划痕、清洁条纹",
        "展现安全的使用磨损",
        "在结构上保持洁净完好",
        "35-50 mm 的直线投影镜头",
        "f/5.6-f/11",
        "5200K-6500K",
        "前景、中景和背景",
        "配色以冷色为主",
        "四个主动叙事系统",
        "至少包含八个紧凑现实锚点",
        "完整的有人使用的空间，而非通用背景",
        "房间类型、地板、墙壁、天花板、入口",
        "至少包含六件独立且视觉可辨的道具",
        "具体物品身份、材质、颜色、大小印象",
        "将它们分布在前景、中景和背景",
        "以分号分隔的环境句子",
        "55-70% 的光学密度",
        "平滑的光密度",
        "半透明单色体积光成年人",
        "将所有外部身体结构描述为由同一青色、青紫或冷淡紫体积形成的连续光",
        "宽石墨色胸廓衬垫和大腿外侧翼",
        "所有缆线和织带均置于腹股沟及身体间接触区之外",
        "宽、平、深色，且明显连到支撑垫",
        "完整空床表面须始终可见",
        "家用家具，而非医疗椅",
        "双方伴侣都保持清醒、相互投入",
        "主动参与",
        "侧卧后入的卧铺",
        "裸露髋部紧贴接受方骨盆",
        "完全远离双方腿部",
        "以抽象倒影呈现雨、交通光线或空的建筑结构",
        "四片物理上分离的柔性支撑翼",
        "30-40 厘米的椭圆接触开口",
        "上方 50-80 厘米处",
        "淡青色冷却液",
        "前方伴侣侧卧，脊柱朝向后方伴侣",
        "后方伴侣平行地朝同一侧侧卧",
        "骨盆高度的后侧四分之三视角",
        "两条独立配重平衡的身体轴线",
        "30-40 度后倾",
        "35-50 度前倾",
        "两台可见天花板滑车",
        "安全织带使用柔和紫或石墨色",
        '"directly joined pelvises" 和 "touching pubic skin"',
        "空白纯色租赁箱",
        "个人造型：分别为每名成年人",
        "未来房间和道具：完整房间边界",
        "青色、冰蓝或柔和紫弧形",
        "脸、头、躯干、骨盆、身体或人体轮廓总数错误",
        "插入器官穿过衣物出现、脱离骨盆",
        "自慰出现无归属的手",
        "BDSM 使颈部或气道承重",
        "阴茎形玩具安装在男性骨盆上",
        "形似第二根阴茎",
        "单一成年人的请求中出现第二个身体",
        "改变 female_count 或 male_count",
        "将请求的性别名额变为未指定性别",
        "前 120 个词内的所选动作几何",
        "下装仍堆在大腿、膝盖或脚踝处",
        "交通工具窗户出现人体倒影",
        "面板开裂、损坏或不安全",
        "肉色支撑硬件",
        "锈蚀、腐蚀、剥落灰泥",
        "雨中延迟全息汽车旅馆",
        "热量配给冷却悬吊",
        "循环空气旅馆悬吊",
        "默默使用这些检查",
        "其词汇绝不出现在返回的画面中",
        "仅返回一段正向的英语 ASCII 段落",
        "确认至少 600 个英语单词",
        "对应的直形 ASCII 字符",
    ):
        assert requirement in normalized, requirement
    family_section = next(
        rule for rule in brief.splitlines() if rule.startswith("1. 家用合成伴侣：")
    )
    for number in range(1, 24):
        assert re.search(rf"\b{number}\. ", family_section), number
    assert document.allocation.type == "cyclic_slots"
    assert document.allocation.catalog == "near-future-intimacy-realism"
    resolved = resolve_story_input(document)
    catalogs = [
        json.loads(source.content)
        for source in resolved.sources
        if source.kind == "catalog"
    ]
    assert len(catalogs) == 1
    assert catalogs[0]["id"] == "near-future-intimacy-realism"
    assert len(catalogs[0]["entries"]) == 30
    seeds = {
        rule
        for entry in catalogs[0]["entries"]
        for rule in entry["themes"]
        if rule.startswith("已选场景种子：")
    }
    assert len(seeds) == 30
    assert seeds == {
        rule
        for entry in catalogs[0]["entries"]
        for rule in entry["frames"]
        if rule.startswith("已选场景种子：")
    }
    assert seeds <= set(brief.splitlines())
    for excluded in ("五至七个句子", "最多 320 词", "2000 个 ASCII 字符"):
        assert excluded not in normalized, excluded


def test_precise_intimate_activity_geometry_has_explicit_spatial_contract() -> None:
    document = load_story_document(RECIPES / "precise-intimate-activity-geometry.yaml")
    normalized = " ".join(story_contract(document).split())
    assert document.generation.output_language == "english"
    assert set(document.requirements.output_languages) == {"english"}
    assert any(
        check.type == "ascii" for check in document.validation.frames.checks
    )
    for requirement in (
        '"Exactly N adults belong to N coherent bodies in this image."',
        "每个主题的标题和设定只定义人物、房间、主要活动",
        "主题绝不定义相机位于哪一侧、镜头、取景、裁切",
        "画帧独自负责相机和可见性",
        "忽略这些表述，在画帧中重新建立一个相机场景图",
        "编写每个主题前，建立不可变的性别名额",
        "恰好 female_count 个成年女性名额",
        "恰好 male_count 个成年男性名额",
        "每个主题设定和每个画帧都必须指名恰好一名成年女性和恰好一名成年男性",
        "绝不把请求中的男性换成女性",
        "每个可见的面部、头部、躯干、骨盆、手臂、手、腿、脚",
        "身体完整性是拓扑要求，不是全身取景要求",
        "只描述执行动作、承重或决定姿势的可见肢体",
        "从其可见的身体连接处连续追踪",
        "隐藏肢体和画外部位不需要清点",
        "只选择一名中心人物",
        "在一个人物描述块中",
        "画面位置：画面中央、偏左中央、偏右中央",
        "每条可见身体链和每个指名的遮挡体积",
        "仅在面部可见时描述表情和视线",
        "每条可见肢体的位置、支撑职责和主动接触，都只在其指名所属者的人物描述块中写一次",
        "不要先分配被动位置",
        "用独立句子描述每名其他成年人",
        "只描述可见肢体链、可见支撑点",
        "仅在面部可见时说明头部角度、视线和表情",
        "平放的脚，其脚跟、前脚掌和脚趾都接触表面",
        "抬起脚跟时，只有前脚掌和脚趾接触表面",
        "伸直的肘部也不能同时落在表面上充当支撑",
        "单一不透明二维投影",
        "只描述无遮挡视线能到达的身体结构和接触",
        "在第二句中锁定相机",
        "取景尺度和近侧可见表面",
        "指明遮挡主要接触的任何体积",
        "绝不把相机描述拖到段落末尾",
        "全段使用的唯一可见性场景图",
        "仅纳入其边界内可见的身体结构、接触边界、支撑点和道具",
        "画外部位不在图中",
        "姿势、动作、造型、光线和焦点均使用这张图",
        "将可见性分配给表面小片，而非整个身体部位",
        "为主要接触边界指定一种状态：可见，或被某个指名的近侧身体体积遮挡",
        "插入边界可以保持被遮挡",
        "此时通过身体对齐关系让动作可读",
        "可见性状态不可变",
        "之后不得被描述、对焦、描述为在视野内受到接触或称为可见",
        '比较每处 "visible"、"occluded" 和 "hidden" 的用法',
        "正面视角中，胸部和躯干前侧可以可见",
        "完整臀部和臀沟不可见",
        "背面视角中，背部和臀部可以可见",
        "双乳、乳头、腹部和前侧生殖器不能完整可见",
        "严格侧面视角中，只展示侧面轮廓",
        "绝不把完整正面胸部和双臀完整后视图结合起来",
        "转头会改变面部可见性，但不会让躯干",
        "明确说明近侧与远侧的遮挡顺序",
        "移动相机或改变姿势",
        "透明身体、不可能的扭转、第二视角",
        "一个物理一致的反射",
        "接触边界可见时",
        "不要只声称其视线畅通",
        "通过指明观看窗口来证明",
        "对于阴茎口腔插入，使用侧后方或后侧四分之三相机视角",
        "头部或近侧大腿遮住口部与生殖器的接触边界",
        "只提及一次吮阴茎以确立动作",
        "省略局部阴茎、阴茎体、龟头、嘴唇、舌头和口腔几何关系",
        "对于外部生殖器舔舐",
        "为每处接触分配且只分配一种拓扑状态",
        "分离：两个结构之间存在可见间隙",
        "外部接触：两个外表面在一个可见边界相接",
        "插入：接受方边界环绕主动结构",
        "同一接触不能在同一画帧中处于两种状态",
        "省略该边界以外的所有远端结构",
        "不要为嘴内或身体开口内的身体结构命名、定位、布光、对焦或赋予运动",
        "每个接触边界的两侧共享同一画面位置和同一深度平面",
        "必须能由其相连关节到达",
        "写正文前改变姿势或支撑",
        "对于阴茎口部活动，只能在两种方案中选择一种",
        "口腔插入只提及一次吮阴茎",
        "将其接触边界指定为被遮挡状态",
        "省略该处局部身体结构",
        "这两种方案绝不共存",
        "任何手部接触都是独立动作链",
        "对于口乳接触",
        "嘴部遮住唇下的中央区域",
        "对于插入，使用侧向或四分之三侧向视角",
        "在该交界处结束可见链条，省略内部部分",
        "对于托举插入，要么选择偏正面视角",
        "远侧臀部和远侧支撑接触仍被遮挡",
        "绝不声称双臀、两个臀下接触点",
        "对于手部或玩具接触",
        "正面相机看不到后方成年人的骨盆",
        "夹在两个躯干或骨盆之间的任何接触",
        "将两人错开并使用侧向四分之三相机视角",
        "执行者 -> 其所属身体部位或手持物 -> 目标成年人",
        "根据接触边界在相机场景图中的状态，选择一种动作链形式",
        "只在动作执行者的人物描述块中写一次该链",
        "不重复接触身体结构，也不重新分配执行动作的肢体",
        "对于可见边界",
        "对于被遮挡边界",
        "活动名称 -> 执行者与目标的身体对齐关系",
        "省略隐藏的接触身体结构、接触运动和内部状态",
        "绝不对同一动作混用可见和被遮挡两种形式",
        "Mina 的舌头从 Mina 的嘴中可见地伸出",
        "被遮挡的口腔插入：An 跪在 Bo 张开的大腿之间",
        "侧后方相机使 An 的头部轮廓与 Bo 的耻部重叠",
        "Bo 的近侧大腿遮住他们的接触边界",
        "Jun 的右肩连续连接到他弯曲的右肘",
        "插入部位与其所属者的骨盆保持可见连续",
        "接受方的耻部在同一接触平面与之相接",
        "外部插入交界",
        "在接受方边界处结束可见描述",
        "省略内部部分",
        "绝不让插入部位终止于腹部",
        "一条肢体在全段中只承担一个物理职责",
        "当另一名成年人托举中心人物时",
        "哪个部位承重：上背部、胸廓、腰部",
        "双脚均离地",
        "对于托举插入，使用力学相容的轴向",
        "不要将被托举者描述为水平或横躺在托举者身上",
        "将承重路径从指名的身体部位",
        "每名可见成年人都通过动作",
        "仅使用相机场景图中的可见元素，为每名成年人写一个简洁的造型分句",
        "仅在脚可见时描述鞋履",
        "造型绝不重新引入被遮挡或画外部位",
        "不要重述或改变第二句中确立的相机",
        "按动作可读性选择取景",
        "让每处主动接触和每条支撑链保持在画面内",
        "省略选定取景之外的所有身体结构",
        "仍有非 ASCII 字符",
        "不改变锁定的相机",
        "每个画帧写成一个自然的英文段落，仅使用可打印 ASCII 字符",
        "只返回正向的可见描述",
    ):
        assert requirement in normalized, requirement
    for excluded in (
        "最高优先级人物构成与相机锁定",
        "可见未来技术特征",
        "未来视觉世界锁定",
        "高未来视觉强度锁定",
        "反科幻视觉门槛",
    ):
        assert excluded not in normalized, excluded


def test_surreal_conceptual_portrait_has_safe_minimal_installation_contract() -> None:
    from t2i_story_pipeline.models import AsciiCheck, WordCountCheck

    document = load_story_document(RECIPES / "surreal-conceptual-portrait.yaml")
    normalized = " ".join(story_contract(document).split())
    assert document.policy == "standard-story"
    assert document.generation.output_language == "chinese"
    assert document.requirements.output_languages is None
    for language in ("chinese", "english"):
        resolved = resolve_story_input(document, InputOverrides(output_language=language))
        assert resolved.request.output_language == language
        for stage in StoryStage:
            compiled = resolved.rules.text_for(stage)
            assert "未指定时，每个人物分别默认为中国籍" in compiled
            assert "否则场景国家默认为中国" in compiled
    assert document.validation.frames.mode == "report"
    assert document.validation.frames.checks == (
        AsciiCheck(type="ascii", when_language="english"),
        WordCountCheck(
            type="word_count", when_language="english", min_words=600, max_words=None
        ),
    )
    required = (
        "结合克制的时尚摄影、实体装置艺术、面无表情的戏剧布置",
        "安静、精确、诡异且情感可读，而非壮观",
        "博物馆级的超现实观念肖像",
        "一个不可能但视觉连贯的隐喻",
        "不得复制任何参考构图",
        "一个主导隐喻",
        "严格使用所要求数量的成年女性和成年男性",
        "场景中只有这组确切可见人物，没有额外人物或人体部位",
        "为每个要求的人物赋予不可或缺的构图作用",
        "可信的支撑线向上延伸至画外天花网架",
        "每件重物都有自己的可信承重路径",
        "不得通过人的头发、皮肤、颈部、生殖器或衣物悬挂任何东西",
        "可见衣架或平面非人形支撑",
        "衣橱档案只包含成人尺寸衣物",
        "不含婴儿服、儿童尺寸衣物、校服",
        "超轻空心戏剧复制道具",
        "其他刚性或沉重物件须位于人物旁边",
        "围绕一个现有人物真实头部的可穿戴雕塑头饰",
        "绝非斩首、漂浮替代头、第二个头",
        "鼻口须不受实体压迫",
        "绝不使用紧塑料、粘性包裹、勒颈绳",
        "巴拉克拉法面罩、封闭头罩、麻袋",
        "宽敞的下半脸呼吸间隙",
        "绕过颈部的独立承重路径",
        "轻质防碎亚克力",
        "真实玻璃、陶瓷、脆性材料",
        "绝不反射、重复、切碎或增殖人物的脸、眼、头、身体或肢体",
        "约保留画面的百分之四十至七十",
        "最多使用两种主导色相加一种点缀",
        "通常为等效 40-105 毫米",
        "每条可见肢体连续连接到一个人的躯干",
        "不得通过物件重叠、黑暗、镜子、画框、屏幕、影子或悬挂衣物创造额外、脱离、重复、融合或无来源的解剖",
        "在 Hardcore 等级，装置可为行为构框、呼应、计数",
        "但不得插入、束缚、悬挂、击打",
        "肩、胸、骨盆、臀部和生殖器均由不透光织物完全覆盖",
        "同一主题中的画面是平行的完成肖像",
        "三个悬挂系统、两个落地物件布局",
        "每个最终画面都明确重申所渲染场景不含可读文字、标志、界面、水印或人物图像",
        "绝不描述为手写、印刷、写有地址",
        "至少包含 600 个以空白分隔的单词",
        "目标为 650-900 个单词的具体可成像细节",
        "此最低限度优先于后文任何简洁要求",
        "英文画面至少 600 个单词，或在所要求的其他语言中使用等量细节",
        "起草以 650-900 个单词为工作范围",
        "英文画面约使用十二至十六句",
        "将这六个方面展开至完整句数预算",
        '"Only the specified cast is present"',
        '"negative space"',
        '"no readable text, logo, interface, watermark, or human image"',
        "英文画面只使用 ASCII 字符，包括直引号和普通连字符，而非智能标点",
        "发布前扫描英文画面每个字符",
        "把所有汉字、带重音字母、智能标点或其他非 ASCII 符号替换为纯英文 ASCII",
        "英文画面包含任何非 ASCII 字符",
        "返回每个英文画面前，按空白分隔计算单词数；若不足 600",
        "不得附加材料清单、象征阐释",
    )
    missing = [text for text in required if text not in normalized]
    assert not missing, missing


def test_demon_lord_brief_has_gendered_sovereign_dark_fantasy_contract() -> None:
    from t2i_story_pipeline.models import AsciiCheck, WordCountCheck

    document = load_story_document(RECIPES / "demon-lord.yaml")
    normalized = " ".join(story_contract(document).split())
    assert document.policy == "standard-story"
    assert document.generation.output_language == "chinese"
    assert document.requirements.output_languages is None
    for language in ("chinese", "english"):
        assert resolve_story_input(
            document, InputOverrides(output_language=language)
        ).request.output_language == language
    assert document.validation.frames.mode == "report"
    assert document.validation.frames.checks == (
        AsciiCheck(type="ascii", when_language="english"),
        WordCountCheck(type="word_count", when_language="english", min_words=600),
    )
    required = (
        "每个主题恰好包含一位核心恶魔君主",
        "一位成年女性魔王或一位成年男性魔王",
        "绝不在同一主题中同时安排女性和男性恶魔君主",
        "至少含 600 个以空白分隔的单词",
        "以 650-900 个词的具体可成像细节为目标",
        "原创真人实拍黑暗奇幻长片图像",
        "真实的成年演员，具有自然皮肤纹理",
        "可实际穿戴的角、翅膀、盔甲",
        "大制作真人实拍黑暗奇幻长片中的完成版画面",
        "而非油画、插画、概念美术",
        "克制且不可察觉的视觉特效延展",
        "有意采用低饱和度、暗调、高明度反差、窄色域配色",
        "低饱和蓝灰与失去光泽的柔和琥珀色",
        "不得复制参考中的恶魔设计",
        "严格使用所要求的成年女性和成年男性人数",
        "恶魔君主计入所要求的一位女性或一位男性",
        "在内部为所要求的精确成年女性和精确成年男性分别建立人物记录",
        "绝不将所要求的女性变为男性",
        "在每个最终画面的前六十个英文单词内",
        "图像必须恰好包含一位成年女性和一位成年男性",
        "每个混合阵容的第一句在描述个人之前，先一并说明所有所要求性别人数",
        '这两个精确的 "only" 句式只保留给真正的单人请求',
        "创作严格单人肖像，仅包含这一位恶魔君主",
        '第一句必须写 "one adult Chinese man only"',
        '第一句必须写 "one adult Chinese woman only"',
        "单人主题中绝不使用复数人物、暗示另一个主人的成对物件",
        "有女性而无男性时",
        "有男性而无女性时",
        "混合阵容时，恰好选择所要求的一位成年人",
        "平衡女性和男性君主",
        "二十五至七十九岁之间的人类等效外观年龄",
        "绝不能取代它",
        "为每个人使用一个精确整数年龄",
        "绝不写三十五岁上下、四十出头、接近六十岁",
        "清醒、能力未受损、自愿、会作出回应",
        "明确描述互动为双方同意且自愿",
        "在每个 情色级 或 露骨级 画面的前一百个英文单词内",
        '包含精确短语 "consensual and willing"',
        "在每个 露骨级 画面的前一百个英文单词内",
        "说明谁的勃起阴茎在谁的阴道或肛门内",
        "将该直接 露骨级 接触放在第一句或第二句中",
        "不得在说出参与动作的解剖结构前，用面孔、角、服装",
        "所有词语位置检查在内部进行",
        "绝不提及开头词语、前一百词、词语位置",
        "绝不使用囚犯、奴隶、祭品、贡品",
        "衡量不可能争端的地狱法官",
        "宫廷天文学家、炼金术士、档案管理员",
        "仅当所要求阵容包含额外成年人时",
        "不要让每位女性君主都是魅惑女王",
        "一个头、一条颈、一个躯干、两条手臂",
        "角为可选，但通常值得采用",
        "恰好使用一对匹配翅膀，连接于上背部",
        "可选尾巴从骶骨连续伸出",
        "不得添加过大的奇幻生殖器",
        "所有性解剖结构保持为与君主所声明性别相符的成年类人解剖结构",
        "轮换不同场景类型",
        "竖向神圣空间",
        "私密王室内景",
        "运作中的权力中心",
        "户外领地",
        "原创过渡空间",
        "不要默认每个场景都有烟、余烬",
        "每个主题恰好选择一个在可见瞬间已发生的主导大型场面事件",
        "巨大闸门开启",
        "悬吊锻炉坩埚在水道上方旋转",
        "风暴观测台的实体环架围绕开放圆形天窗转动",
        "机械日食光圈在浅色天窗前闭合",
        "选择清晰可辨的高潮瞬间",
        "使用一个主导事件，最多再有一个从属环境反应",
        "整个身体占据区域都干燥、处于室温、稳定",
        "水可形成不高于脚踝的浅薄反光层",
        "绝不在水下、完全淹没的室内",
        "灰烬、尘土、淤泥、火星、雨、烟、蒸汽",
        "应保持数个身长距离，位于可见路缘、墙、栏杆、水道或其他物理隔离之后",
        "不得重复参考中的近距离正面膝上布局",
        "三个清晰可辨的空间层次",
        "一种主导图形结构",
        "添加一种尺度对比和一种材料对比",
        "选择一个运动向量",
        "开放式姿态创作思路，不是固定菜单或主题编号映射",
        "在 审美级 级别，变化以下动作",
        "在 情色级 级别，变化非露骨的成年人布局",
        "在 露骨级 级别，轮换物理上可信的露骨布局",
        "面对面坐姿阴道或肛门性交",
        "有支撑的站立性交",
        "侧卧性交",
        "从后方进入的阴道或肛门性交",
        "相互自慰、相互口部接触",
        "每个画面中使用一种主导身体布局",
        "24-135mm 等效透视",
        "24-28mm 用于环境广角",
        "轮换摄影机方案类型：正面视线高度对称",
        "沿反光表面的地面高度视图",
        "选择一个决定性电影瞬间",
        "每个最终画面说明一个 24-135mm 范围内以毫米为单位的精确焦距",
        "电影式视图、戏剧性角度、广阔构图或近景肖像等模糊说法绝不能替代数字焦距",
        "以真人实拍电影摄影呈现",
        "实体假体通过可信基部、压力、妆容过渡与阴影衔接皮肤",
        "细腻电影颗粒",
        "避免油画、可见笔触、插画",
        "它是完成版虚构电影本身中的一帧",
        "抑制色彩对比，同时保留强烈亮度对比",
        "可见画面至少百分之八十五",
        "画面约百分之六十至七十五保留在深沉但可辨读的阴影中",
        "小范围骨白或金属高光",
        "保留黑色内部细节",
        "任何彩色点缀最多占画面的百分之五",
        "不超过两个柔和色相族，另加中性材料",
        "不得使用饱和绿松石色、电光青",
        "电影青橙调色",
        "避免平板灰雾、仅有混浊中间调的表现",
        "每条可见肢体都通过自然关节连续连接",
        "在 审美级 级别，每个人始终被不透明成人衣物完全遮盖",
        "不呈现插入、露骨口部与生殖器接触",
        "一项清晰可见、已在进行的自愿成年人性行为",
        "单人阵容使用可见的成年人自慰",
        "多位成年人时，保持精确阵容可见",
        "普通成年类人性解剖结构",
        "绝不使用角、爪、尾巴、触手、武器",
        "使用朝向远离所有面孔和身体的钝角",
        "任何参与者都不抓握、拉扯、骑乘或借力于角",
        "不得使用针尖、刀刃尾尖",
        "同一主题中的画面是平行的完成版图像",
        "每个连续滚动的十二主题组内",
        "在一百个主题的生成中",
        "至少八种不同主导大型场面事件",
        "至少六种不同三层纵深设计",
        "不重复相同环境类型、主导事件",
        "占比均不得超过主题总数的十分之一",
        "英文画面仅使用 ASCII 字符",
        "这是绝对发布要求",
        "在内部重新扫描每个字符",
        "结尾重申在场成年女性和成年男性的精确人数",
        "词数统计是内部写作检查",
        '不得写 "six hundred words"',
        '"zero adult women" 或 "zero adult men"',
        "对单人请求添加任何第二个人、姓名、主人、目光交流对象",
        "少于 600 个英文单词",
        "使用鲜艳、霓虹、宝石色、高饱和",
        "环境保持静态，没有一个可见的当前事件",
        "组合多于一个主导灾难",
        "缺少精确的 24-135mm 焦距",
        "将确切 露骨级 解剖结构或直接接触推迟到前两句或前一百个英文单词之后",
        "将 情色级 或 露骨级 亲密互动安排在水下",
        "将灰烬、尘土、淤泥、火星、雨、烟",
        '缺少 "live-action dark-fantasy feature-film frame"',
    )
    missing = [text for text in required if text not in normalized]
    assert not missing, missing


def test_angel_brief_has_dark_cinematic_exact_cast_contract() -> None:
    from t2i_story_pipeline.models import AsciiCheck, WordCountCheck

    document = load_story_document(RECIPES / "angel.yaml")
    normalized = " ".join(story_contract(document).split())
    assert document.policy == "standard-story"
    assert document.generation.output_language == "chinese"
    assert document.requirements.output_languages is None
    for language in ("chinese", "english"):
        assert resolve_story_input(
            document, InputOverrides(output_language=language)
        ).request.output_language == language
    assert document.validation.frames.mode == "report"
    assert document.validation.frames.checks == (
        AsciiCheck(type="ascii", when_language="english"),
        WordCountCheck(type="word_count", when_language="english", min_words=600),
    )
    required = (
        "原创真人实拍黑暗奇幻长片图像",
        "高品质长片中的完成版画面，具有真实的成年演员",
        "每个主题恰好包含一位核心天使",
        "一位成年女性天使或一位成年男性天使",
        "绝不在同一主题中同时安排女性和男性核心天使",
        "所要求的成年人中恰好一位是天使",
        "其余每位所要求的成年人都是普通的无翼人类",
        "一位有翼天使和一位无翼人类",
        "至少含 600 个以空白分隔的单词",
        "以 650-900 个词的具体、可见、可成像细节为目标",
        "ASCII 是绝对的发布要求",
        "返回英文画面前，最后逐字符执行 ASCII 检查",
        '在每个最终画面的前六十个英文单词内，明确将图像称为 "live-action dark-fantasy feature-film frame"',
        "真实的成年演员，具有自然皮肤纹理",
        "实体制作的翅膀",
        "宏伟的地点、受控的美术设计",
        "真实长片镜头的光学表现",
        "摄影式黑暗奇幻电影真实感",
        "不得使用油画用语",
        "合成 CGI 光泽",
        "克制且不可察觉的视觉特效延展",
        "创作完全原创的成年角色与场景",
        "不得复制参考中的面孔、身体、姿势",
        "严格使用所要求的成年女性和成年男性人数",
        "在内部为每位所要求的成年人分别建立一条人物记录",
        "在前六十个英文单词内",
        "在前一百个英文单词内明确将每位非核心的所要求成年人标明为无翼人类",
        "严格的单人肖像，仅包含该核心天使",
        '第一句必须写 "one adult Chinese man only"',
        '第一句必须写 "one adult Chinese woman only"',
        "二十五至七十九岁之间的一个精确外观年龄",
        "说明一个精确的整数年龄",
        "清醒、能力未受损、自愿、会作出回应",
        '精确短语 "consensual and willing"',
        "不得出现酒精、烈酒、葡萄酒、啤酒、鸡尾酒",
        "检查遭受风暴侵袭的山间关门的天界统帅",
        "调节实体环架的日食导航员",
        "在灰暗温室照料浅色植物的夜间园丁",
        "外加恰好一对匹配的翅膀",
        "将双翼连接在上背部和肩胛骨区域",
        "恰好有一对匹配翅膀，由一只左翼和一只右翼组成",
        "修长风化象牙色鹰式飞羽",
        "氧化银色隼式翅膀",
        "不得创造六只翅膀、布满眼睛的翅膀、脱离身体的翅膀",
        "带磨旧古金镶嵌的发黑活动板甲",
        "失去光泽的浅金色札甲",
        "欢迎使用金色盔甲",
        "狭窄受控的高光、较暗关节凹槽",
        "破损圆形天窗下的巨石玄武岩大教堂",
        "由深层矿物水透光照明的淹水钟墓",
        "实体环架围绕开放屋顶的风暴观测台",
        "每个主题恰好选择一个在可见瞬间已发生的主导大型场面事件",
        "机械日食光圈在浅色天窗前闭合",
        "恰好使用一个主导事件，最多再有一个从属物理反应",
        "整个身体占据区域都干燥、处于室温、稳定",
        "充满可呼吸空气",
        "任何面孔、胸部、骨盆、性接触或呼吸通道都不得浸没",
        "灰烬、尘土、淤泥、火星、雨、烟、蒸汽",
        "应距人物数个身长，并与人物实际隔离",
        "每幅图像构建三个清晰可辨的层次",
        "以前景台阶边缘",
        "中景包含完整人物阵容",
        "背景承载宏伟建筑",
        "每幅图像选择一种强有力的图形结构",
        "一个清晰可辨的运动向量",
        "穿过圆形天窗下射光束",
        "在 情色级 级别，采用非露骨的成年人亲密互动",
        "一项清晰可见、已在进行的自愿成年人性行为",
        "在每个 露骨级 画面的前一百个英文单词内",
        "将确切性行为和当前解剖接触放在前两句中",
        "哪位成年人的阴茎位于哪位成年人的阴道或肛门内",
        '泛化的 "point of contact" 不满足 露骨级 要求',
        "一百词和前两句的位置检查在内部进行",
        "绝不提及词语位置、词数门槛",
        "暗调、低饱和度、高反差和窄色域",
        "可见图像至少百分之八十五",
        "图像约百分之六十至七十五",
        "任何彩色点缀最多占图像的百分之五",
        "不得使用饱和绿松石色、电光青",
        "24mm 或 28mm 环境广角",
        "视线高度的 35mm 环境肖像",
        "50mm 中距离全身镜头",
        "100mm 或 135mm 压缩建筑构图",
        "说明 24mm 至 135mm 范围内一个精确焦距",
        "细微电影颗粒和自然微反差",
        "每十个主题中",
        "至少八种不同主导大型场面事件",
        "至少六种不同三层纵深设计",
        "每个连续滚动的十二主题组内",
        "在一百个主题的生成中",
        "任何单一正面白翼姿势",
        "占比均不得超过主题总数的十分之一",
        "词数统计是内部写作检查",
        "英文画面仅使用 ASCII 字符",
        "少于 600 个英文单词",
        "将任何非核心人物称为天使",
        "多于一个有翼人物或多于一对匹配翅膀",
        "使用酒精、烈酒、葡萄酒、啤酒、鸡尾酒",
        "环境保持静态，没有一个可见的当前事件",
        "缺少清晰可辨的前景、中景和背景纵深",
        "将亲密互动安排在深水中、潮湿或湿滑的支撑面上",
        "一幅已完成、可见的真人实拍电影图像",
    )
    missing = [text for text in required if text not in normalized]
    assert not missing, missing


def _legacy_motion_blur_photography_contract() -> None:
    brief = story_contract(load_story_document(
        REPOSITORY_ROOT
        / "story-inputs" / "recipes"
        / "motion-blur-photography.yaml"
    ))
    normalized = " ".join(brief.split())

    assert "one self-contained English paragraph of at least 700 words" in normalized
    assert "Target 850-1200 words" in normalized
    assert "Apply a final lexical render gate to the Frame" in normalized
    assert "must contain zero instances of camera body, camera mounted, tripod" in normalized
    assert "production crew, photographer, lighting assistant, production personnel" in normalized
    assert "capture cable, shutter trigger, capture monitor" in normalized
    assert "Rewrite them as locked viewpoint, panned viewpoint, off-frame pulse" in normalized
    assert "Do not output a negative inventory of absent gear" in normalized
    assert "Crew cut and crew-neck remain valid appearance and garment-construction terms" in normalized
    assert "A monitor, cable, or equipment rack remains valid when the visible location's ordinary current function genuinely requires it" in normalized
    assert "silently rewrite it if it falls below 700" in normalized
    assert "Do not pad the paragraph with repetition" in normalized
    assert "Write with maximum information density" in normalized
    assert "make every sentence add new, concrete, visible, renderable information" in normalized
    assert "prefer exact nouns and measurements over decorative adjectives" in normalized
    assert "Concision means removing redundancy, never removing required information" in normalized
    assert "Do not shorten by omitting, generalizing, or merely implying" in normalized
    assert "background population, setting, camera, light, exposure" in normalized
    assert "compact, telegraphic image-prompt prose instead of literary narration" in normalized
    assert "short subject-verb-object clauses joined by semicolons" in normalized
    assert "Order visible facts first" in normalized
    assert "Put the photographic explanation in the final portion" in normalized
    assert "invisible viewpoint geometry, lens and focus, off-frame illumination" in normalized
    assert "State each fact once" in normalized
    assert "remove conversational transitions, scene-setting filler" in normalized
    assert "Order information once in this sequence" in normalized
    assert "Do not circle back to restate an earlier section" in normalized
    assert "one continuous paragraph without headings" in normalized
    assert "compressed syntax and zero ornament, not missing facts" in normalized
    assert "requested female and male counts apply exactly to the primary adult subjects" in normalized
    assert "Contextual background adults are governed only by" in normalized
    assert "lock one complete visual dossier for each requested person" in normalized
    assert "exact adult age, exact height, body proportions" in normalized
    assert "chest and breast proportions as applicable" in normalized
    assert "Repeat that complete dossier independently in every Frame" in normalized
    assert "exact height in centimeters" in normalized
    assert "natural breast size, shape, projection" in normalized
    assert "face shape and mature facial anatomy" in normalized
    assert "precise skin color and undertone" in normalized
    assert "every visible garment from inner visible layer to outer layer" in normalized
    assert "complete footwear, including shoe type" in normalized
    assert "every piece of jewelry and every accessory" in normalized
    assert "one specific facial expression" in normalized
    assert "one complete current action or held pose" in normalized
    assert "one distinct, stable expression" in normalized
    assert "exact gaze target; eye openness and focus" in normalized
    assert "upper and lower eyelid tension" in normalized
    assert "brow height, angle, and asymmetry" in normalized
    assert "jaw tension; cheek tension" in normalized
    assert "visible evidence of alertness, agency, response, and consent" in normalized
    assert "complementary but non-identical expressions" in normalized
    assert "Lock one expression for the entire exposure" in normalized
    assert "one fixed wardrobe inventory for every primary adult" in normalized
    assert "eyeglasses or sunglasses, scarf or neckwear, jewelry" in normalized
    assert "every primary adult exactly one complete pair of footwear" in normalized
    assert "If the person is barefoot, describe both removed shoes" in normalized
    assert "never write only that the person wears no shoes" in normalized
    assert "every primary adult at least two distinctive accessories" in normalized
    assert "at least one jewelry item" in normalized
    assert "one signature non-jewelry item chosen from eyeglasses, sunglasses" in normalized
    assert "cannot replace the required eyeglasses, sunglasses, or silk scarf" in normalized
    assert "Do not satisfy this rule with two jewelry items" in normalized
    assert "Every Frame must account for every inventoried item" in normalized
    assert "partly removed, naming which limb or body region remains inside it" in normalized
    assert "fully removed and visibly placed at one exact location" in normalized
    assert "Never make clothing, shoes, glasses, a scarf, jewelry" in normalized
    assert "where every removed garment, underwear piece, shoe" in normalized
    assert "Place and describe every item separately" in normalized
    assert "never use the words pile, cluster, heap, bundle" in normalized
    assert "A fully nude adult may deliberately retain jewelry, glasses, a scarf" in normalized
    assert "Lay a removed garment flat" in normalized
    assert "never roll it into a bundle" in normalized
    assert "one person's garment on top of another person's garment" in normalized
    assert "at least twenty centimeters apart with no overlap" in normalized
    assert "No garment may be simultaneously worn and lying elsewhere" in normalized
    assert "Audit garment construction before accepting the Frame" in normalized
    assert "A pullover T-shirt has no front opening, buttons, placket, or shirt cuffs" in normalized
    assert "A button-front dress shirt may open along its placket" in normalized
    assert "A slip dress uses straps rather than sleeves" in normalized
    assert "at least three of those five signals" in normalized
    assert "Bare breasts and nipples, cleavage, back, abdomen" in normalized
    assert "use a self-possessed held pose with deliberate adult self-touch" in normalized
    assert "every requested adult must participate in reciprocal contact" in normalized
    assert "Erotic Frames do not show genital close-ups" in normalized
    assert "State the act near the beginning of the Frame" in normalized
    assert "Partial clothing is the default Hardcore styling" in normalized
    assert "Do not choose full nudity merely because" in normalized
    assert "Plan the wardrobe distribution from the requested Hardcore Theme count" in normalized
    assert "At least seventy-five percent of the requested Themes" in normalized
    assert "round this minimum upward to a whole Theme" in normalized
    assert "At most twenty-five percent may show all primary adults fully nude" in normalized
    assert "round this maximum downward to a whole Theme" in normalized
    assert "When the rounded all-nude maximum is zero" in normalized
    assert "Every requested Frame inherits its Theme's" in normalized
    assert "each primary adult retains at least two worn clothing categories" in normalized
    assert "roughly thirty-five to seventy percent" in normalized
    assert "Open, lift, lower, loosen, or displace only the specific garment area" in normalized
    assert "Do not remove an upper garment when only lower anatomy needs access" in normalized
    assert "For a one-person cast, show explicit solo masturbation already in progress" in normalized
    assert "every requested adult must have one active, unmistakable role" in normalized
    assert "An inserted structure enters once at one receiving boundary" in normalized
    assert "For standing penetration, separate and bend the receiving adult's legs" in normalized
    assert "align both pelvises at the same height and depth plane" in normalized
    assert "Do not combine closed or touching legs with visible vaginal" in normalized
    assert "trace only the externally visible portion" in normalized
    assert "end the description at that boundary" in normalized
    assert "fully inserted while also calling its entire length fully visible" in normalized
    assert "Never describe the glans or any internal segment as visible" in normalized
    assert "the external shaft leads continuously from its owner's pelvis" in normalized
    assert "everything beyond the boundary is internal and omitted" in normalized
    assert '"fully inserted," "visibly inserted," "fully visible penis,"' in normalized
    assert "Do not describe the glans in an inserted act" in normalized
    assert "sexual fluid remains a small, localized, sharp surface detail" in normalized
    assert "The modes are mutually exclusive" in normalized
    assert "do not add independently moving crowds, weather, liquid, or thrown props" in normalized
    assert "Never write \"secondary motion,\" \"additional motion evidence,\"" in normalized
    assert "Build the believable scene and current activity first" in normalized
    assert "Never add a moving object, weather condition, crowd behavior" in normalized
    assert "Because this visible current activity is happening" in normalized
    assert "Do not add a scarf, jacket, shirt, or stocking solely so it can fly" in normalized
    assert "never introduce a bucket, glass, hose, splash, or spray only for motion" in normalized
    assert "do not give extras flashlights, lanterns, fabric, or choreographed gestures" in normalized
    assert "If deleting the moving element leaves the scene's activity unchanged" in normalized
    assert "Close three causal loops before writing" in normalized
    assert "Scene loop: location, operating state, weather, population" in normalized
    assert "Mechanics loop: every force must have a visible source" in normalized
    assert "Imaging loop: camera movement, shutter time, flash duration" in normalized
    assert "a camera setting that cannot create the claimed result" in normalized
    assert "Never make one hand throw ten liters of water" in normalized
    assert "Every released object follows a ballistic arc" in normalized
    assert "Rain outside glass stays outside" in normalized
    assert "casual conversation, cleanup, equipment handling, or walking extras as sharp" in normalized
    assert "This is the only mode in which every primary adult remains completely motionless" in normalized
    assert "synchronized panning or flash" in normalized
    assert "Never blur the entire person into an unreadable silhouette" in normalized
    assert "Synchronized panning can keep only one tracked plane and velocity" in normalized
    assert "At Hardcore level, do not use synchronized panning" in normalized
    assert "a just-thrown garment flies open above or beside its owner" in normalized
    assert "a longer ambient exposure leaves one coherent trailing path" in normalized
    assert "one of the image's two largest visual masses" in normalized
    assert "roughly thirty to seventy percent of the visible frame" in normalized
    assert "The viewer must recognize motion before reading facial or wardrobe detail" in normalized
    assert "Choose one dominant motion-evidence carrier per Frame" in normalized
    assert "A subject action and its directly caused garment" in normalized
    assert "background adult group that translates, rotates, falls" in normalized
    assert "When background adults carry the blur" in normalized
    assert "A dense crowd field requires multiple parallel walking lanes" in normalized
    assert "a single-file line cannot fill a broad region" in normalized
    assert "never a top-to-bottom vertical curtain" in normalized
    assert "Choose one dominant motion system, never unrelated competing systems" in normalized
    assert "render background adults as sharp secondary figures" in normalized
    assert "They do not walk, walk in place, gesture, turn" in normalized
    assert "Changing pixels, refreshing data, scrolling screen content" in normalized
    assert "does not count as physical motion" in normalized
    assert "must be visibly active during the current exposure" in normalized
    assert "a boat that already passed, residual wake, aftermath" in normalized
    assert "Describe motion direction in the image plane" in normalized
    assert "a river seen from its bank blurs along its downstream course" in normalized
    assert "Rain in calm air produces vertical trails" in normalized
    assert "Wind-driven rain produces diagonal trails" in normalized
    assert "Choose exactly one of those states per Frame" in normalized
    assert "Gravity-driven water travels downward" in normalized
    assert "Pump-driven water may travel upward" in normalized
    assert "Never describe upward water as gravity-driven" in normalized
    assert "Choose camera movement according to the motion mode" in normalized
    assert "permit one smooth horizontal, vertical, or diagonal pan" in normalized
    assert "the environment streaks in the opposite screen direction" in normalized
    assert "Never combine panning with zooming, rotation, random shake" in normalized
    assert "roughly 1/15 to 1/4 second for panned subject motion" in normalized
    assert "roughly 1/15 to 1/2 second for a frozen action peak" in normalized
    assert "roughly 1/4 to 1 second for a still anchor" in normalized
    assert "Separate shutter time from flash duration" in normalized
    assert "Use a plausible t.1 flash duration around 1/2000 to 1/10000 second" in normalized
    assert "Never call 1/200 or 1/250 second the flash pulse" in normalized
    assert "Flash freezes only surfaces receiving enough flash illumination" in normalized
    assert "at least three stops below the flash exposure" in normalized
    assert "First-curtain flash places the crisp image at the beginning" in normalized
    assert "rear-curtain flash places the crisp image at the end" in normalized
    assert "Estimate the photographed displacement during the open shutter" in normalized
    assert "Do not pair a two-second exposure with a tiny three-centimeter trail" in normalized
    assert "Do not use camera flash to freeze distant rain or a crowd" in normalized
    assert "Claim sharpness only within depth of field" in normalized
    assert "airborne immediately after its owner releases or throws it" in normalized
    assert "An airborne garment is not worn, held, or placed elsewhere" in normalized
    assert "show that hand open immediately after release" in normalized
    assert "Repeat the same owner and same releasing hand" in normalized
    assert "The garment owner must be the person who releases it" in normalized
    assert "may not simultaneously grip a partner, brace on a surface" in normalized
    assert "A panning camera is not locked off" in normalized
    assert "a lean, facial reaction, braced stationary act" in normalized
    assert "Every stationary background object and stationary background adult streaks opposite" in normalized
    assert "Do not claim that fixed architecture blurs while stationary extras" in normalized
    assert "Hardcore motion must be visually consequential" in normalized
    assert "a free hand may release a shirt, blouse, scarf, stocking, jacket" in normalized
    assert "dense informed adult extra crowd follows ordinary routes" in normalized
    assert "Do not reduce Hardcore motion to a distant train" in normalized
    assert "only when removing that item is a natural current part of undressing" in normalized
    assert "Do not add rain, a bucket, thrown liquid, a fan, loose paper" in normalized
    assert "must be visibly moved clear of that exact junction" in normalized
    assert "Never show penetration through intact, normally worn" in normalized
    assert "If a skirt is fastened and worn at normal height" in normalized
    assert '"fully visible externally," "entire visible length,"' in normalized
    assert "A fully nude adult still has a complete removed-clothing inventory" in normalized
    assert "kneeling footwear may contact through toes, uppers, or side edges" in normalized
    assert "glasses cannot be both on the face or head and described as removed" in normalized
    assert "Count physical emitting fixtures, not lighting roles" in normalized
    assert "A bank of four uplights counts as four sources" in normalized
    assert "Every Theme and Frame must explicitly state the background population" in normalized
    assert "private, residential, secured, closed, or after-hours location" in normalized
    assert "quiet public location: two to five background adults" in normalized
    assert "ordinarily active public location: six to fifteen background adults" in normalized
    assert "sixteen to thirty background adults" in normalized
    assert "A normally operating public place must look inhabited" in normalized
    assert "A Beijing subway platform, high-speed rail concourse" in normalized
    assert "must never be empty" in normalized
    assert "Do not write a deserted Beijing public location" in normalized
    assert "informed, consenting adult extra" in normalized
    assert "closed to the public and operating as a controlled adult film set" in normalized
    assert "within the first one hundred English words" in normalized
    assert "closure to ordinary public access" in normalized
    assert "informed consenting adult extras is invalid" in normalized
    assert "Render no legible sign, label, advertisement" in normalized
    assert "exact number of active light sources" in normalized
    assert "exact position and height relative to the primary subjects" in normalized
    assert "approximate color temperature or precise hue" in normalized
    assert "apparent size, hardness or diffusion, relative intensity" in normalized
    assert "which source is the key, fill, rim, background practical" in normalized
    assert "resulting catchlight shape and position" in normalized
    assert "shadow direction, edge hardness, density" in normalized
    assert "Use a short-duration flash to freeze a moving primary subject" in normalized
    assert "A continuous key may resolve the primary cast without blur only when" in normalized
    assert "Ambient light accumulated during the slow shutter records the selected motion carrier" in normalized
    assert "Keep one Theme's exact location, architectural identity" in normalized
    assert "completely self-contained prompt for isolated rendering" in normalized
    assert "Silently reject and rewrite any Frame that fails" in normalized


def test_motion_blur_photography_locks_cast_and_physical_motion() -> None:
    document = load_story_document(RECIPES / "motion-blur-photography.yaml")
    normalized = " ".join(story_contract(document).split())
    assert document.generation.output_language == "english"
    assert set(document.requirements.output_languages) == {"english"}
    checks = {check.type: check for check in document.validation.frames.checks}
    assert "ascii" in checks
    assert checks["word_count"].min_words == 700
    assert checks["word_count"].max_words is None
    for requirement in (
        "每个运动元素都必须是地点与当前活动的必然结果",
        "绝不只为让图像显得有动感而添加载体、道具、人物、光线或手势",
        "若所述相机设置无法产生描述的最终图像",
        "每个画帧返回为一个自足的英文段落，不少于 700 词",
        "目标为 850-1200 词",
        "优先用分号连接简短主谓宾分句",
        "主题数、画帧数、女性数、男性数",
        "请求中的主要人物数量",
        "明显成熟、年龄不低于 25 岁的成年人",
        "请求超过两名主要成年人时，在写主题或画帧前建立内部角色台账",
        "记录一个当前明确角色、精确的一名或多名搭档",
        "每名请求中的主要成年人都必须在拍摄瞬间直接执行或接受一个指名的露骨行为",
        "本身都不能满足该角色",
        "三人时，使用一个相连的露骨接触拓扑",
        "四人或更多时，使用一个相连拓扑或明确分开的露骨配对",
        "没有主要成年人仅是助手、旁观者或只承担支撑的参与者",
        "一个身体部位只在一个画面位置接触一个接受方边界",
        "指明从左到右及由近到远的顺序",
        "把所有必需面部和关键边界放在声明的主体深度层内",
        "不要把一对放在另一对后方数米处",
        "三名或更多成年人时，通常使用 35-50mm 镜头",
        "闪光凝固运动，绝不扩展景深",
        "精确年龄和以厘米为单位的身高",
        "自然乳房大小、形状、前突程度",
        "脸型；眉部、眼睛及其颜色、鼻子、脸颊",
        "精确肤色与底色",
        "一个精确表情，通过视线目标",
        "一整双鞋",
        "至少一件从眼镜、太阳镜或丝巾中选取的非首饰标志物",
        "清单中每件物品都要有其精确可见颜色",
        "指明底色、辅色、饰边以及存在时的图案位置",
        "鞋面、鞋底、鞋跟、五金件、鞋带或系带颜色",
        "对首饰，指明金属色、宝石色和表面质感",
        "对眼镜或太阳镜，指明镜框、镜腿、五金件和镜片颜色",
        "对围巾，指明底色、纹样颜色、边框颜色和织物光泽",
        "这些颜色在穿戴、移位、脱下、手持和腾空状态中保持不变",
        '绝不以 "matching"、"coordinated"、"dark"、"light"、"neutral"、'
        '"colorful"、"metallic" 或 "same color" 代替实际颜色名称',
        "每件物品恰好具有一种可见当前状态",
        "裸体成年人仍有完整的已脱衣物和鞋履清单",
        "脱下的衣物必须看起来是画中脱衣动作刚刚自然丢下的",
        "而非为陈列折叠或刻意布置",
        "为每件物品给出精确占地范围、朝向、重力支撑形状、褶皱",
        "只有每件参与物品和重叠边界都仍明确可辨时，才允许有限的局部重叠",
        '绝不默认采用 "neatly folded"、"laid flat"、"stacked"、"aligned"',
        "鞋不必整齐成双",
        "只有整理打包本身是可见当前活动时才允许有序收纳",
        "一只手只执行一个任务",
        "自然适配优先于多样性",
        "在内部补全这句话：“因为这个可见的当前活动正在发生，"
        "所以这个载体必须以这种方式运动。”",
        "若删除载体后活动不变",
        "不要混合载体类别",
        "绝不把动作引起的载体与独立环境载体配对",
        "只有所属者刚刚脱完同一件衣物",
        "不要只为让它飞起而添加围巾、衬衫、夹克、内衣或长袜",
        "不要仅因必需的标志性眼镜、太阳镜或丝巾已在清单中，就把它们用作腾空物",
        "只露出颈部、锁骨或配饰位置并不足够",
        "在同一图像中，将此人的松手呈现为可见当前动作",
        "载体拖迹从这只手开始",
        "若没有主要成年人可见地松开衣物，就不能有腾空物",
        "绝不暗示不可见的投掷、画外释放者",
        "从手到拖迹再到凝固衣物的一条不间断可见因果链",
        "中间没有无法解释的清晰空气间隙",
        "短拖迹不能解释离手远得多的物体",
        "必须使用真实侧系带、侧按扣",
        "绝不把普通闭环内衣从被占用的腿",
        "必须已将衣物移开当前露骨行为所用的精确身体部位、接触边界或支撑边界",
        "下半身接触期间，仅为露出躯干而脱上装并不合格",
        "绝不抛掷装满的水桶、十升水",
        "优先使用其运行已属必要的固定淋浴头、水龙头或浴缸出水口",
        "不要只为形成液体弧线而添加便携水壶、水桶或漂浮陶瓷容器",
        "不要为制造拖迹而给他们手持物件或编排手势",
        "单列队伍不能填满宽阔区域",
        "而非合并不相容的地点",
        "占画面约 30-70%",
        "先建立场景，再选择运动载体",
        "生成约束，不是地点菜单",
        "尽量实现有意义的场景多样性",
        "相邻主题避免同一类型",
        "绝不将地点类别分配给固定主题 ID",
        "自然适配仍优先于多样性",
        "编写单个主题前规划完整主题批次",
        "任意两个主题之间，以下方面至少三项实质不同",
        "普通私人住宅内的多个房间仍属同一住宅类型",
        "只要还有其他物理可信场景类型未使用，就不要重复该类型",
        "若选择地点仅为容纳方便的模糊效果",
        "场景回路：地点、运行状态、时间、天气",
        "力学回路：力有可见来源",
        "湿滑支撑需要可见防滑纹理",
        "每个关键接触边界都保持在不透明或扰动水面之上",
        "拍摄技术是非渲染元数据，绝不是可见场景内容",
        "先描述完整可见场景",
        "用一个紧凑的方法句，只解释图像如何拍成",
        '"Captured from a [height], [distance], [azimuth], [pitch] viewpoint '
        "with a [focal length] lens at [aperture], focused at [distance]; "
        "a [shutter] ambient exposure records [carrier path]; "
        "a [t.1 duration] off-frame pulse from [screen direction] freezes "
        "[selected plane]; [ND strength when needed] controls ambient exposure; "
        'no capture apparatus is visible."',
        "绝不赋予拍摄装置可见位置、材质、支撑",
        '不要写 "camera body"、"camera mounted"、"tripod"、"gimbal"、"flash head"',
        "解释视点和入射光，而非硬件立在哪里",
        "封闭制作并不能成为图像中出现制作器材的理由",
        "每个画帧说明一个精确虚拟视点",
        "传感器距支撑地板高度",
        "到最近主要人物的距离、围绕人物的水平方位角",
        "横幅或竖幅、镜头轴线目标",
        "这描述图像几何，而非可见物体",
        "运动起点、完整可见载体路径和落区或目的区域",
        "避免压缩手到载体距离",
        "不可见视点必须对应画外一个真实、安全、可到达的空间和稳定支撑表面",
        "锁定相机相对于一个声明的参照系锁定",
        "将不可见拍摄系统安全安装在同一结构上，使主体距离和取景保持恒定",
        "外部静止视点会记录人物平移",
        "焦距、画幅方向和裁切必须在几何上符合",
        "使视点匹配运动模式",
        "说明摇摄轴心、起始方位角、结束方位角",
        "从清晰侧面或斜角观看释放路径",
        "将稳定人物安排在一个主导深度层",
        "不要默认每幅图像都是站立眼高的正面相机",
        "快门时间和闪光时长不同",
        "1/2000 至 1/10000 秒的合理 t.1 闪光时长",
        "至少比闪光曝光低三档",
        "三脚架防止相机抖动，但不能凝固人物",
        "快门时间慢于 1/4 秒时",
        "静止锚点模式快门慢于 1/4 秒时，必须对每名主要成年人使用短闪光",
        "没有该闪光时，将快门时间上限设为 1/4 秒",
        "前帘闪光把清晰影像放在拖迹开端",
        "后帘闪光把清晰影像放在先前拖迹末端",
        "静止灯映在静止地板上，不会仅因快门慢就产生拖迹",
        '在 "STILL ANCHOR" 中，每名主要成年人在整个环境曝光期间保持所述唯一姿势',
        '不要使用 "rocking"、"grinding"、"thrusting"、"pumping"、"bouncing"',
        "只有选定环境载体运动",
        "合理景深内声称清晰",
        "默认视觉语言为大光圈和明显浅景深",
        "优先约 f/1.4-f/2.8",
        "只有必要主体平面无法以其他方式保持可读时才使用 f/3.2-f/4",
        "不要仅为把每个细节都列为清晰，就默认 f/5.6、f/8 或更深景深",
        "说明所需中性密度滤镜",
        "每个画帧必须说明一个浅景深设计",
        "指明精确焦平面、最近和最远可接受清晰的主体特征",
        "使最近主要眼睛或共享面部平面极致清晰",
        "可以进入轻柔对焦过渡，而非被虚称为刀锐般清晰",
        "至少一个实质性的前景或背景平面必须明显光学柔化",
        "将光学失焦与载体运动分开描述",
        "景深必须主动组织运动结果",
        "将被追踪的最近眼睛或面部平面置于焦点",
        "使释放手、轨迹起点和凝固载体位置处于或非常靠近焦平面",
        "环境载体可以远在景深之外",
        '绝不将失焦环境载体称为 "crisp"',
        "说明相机到载体的距离，并与声明的景深近界和远界比较",
        "声称被闪光凝固的动作载体必须与可接受对焦范围相交",
        "描述为光学柔化的方向性运动，绝不是清晰解析的结构",
        "整幅宽度约 36 毫米的全画幅传感器",
        "照明：",
        "对于可见实景灯，说明真实发光灯具的精确数量",
        "一组四盏灯算四个光源",
        "将非渲染拍摄照明描述为入射光",
        "宽广或狭窄照明形态",
        "不要命名或定位硬件、控光附件或等效装置",
        "可见实景发光体属于环境；拍摄照明不属于环境",
        "北京或任何其他指定城市中正常营业的公共场所",
        "封闭、出入受控的制作",
        "以可见动作边界区分 erotic 与 hardcore",
        "全裸也可以属于 erotic",
        "部分着装也可以属于 hardcore",
        "让成年人的性张力明确且强烈",
        "erotic 可使用连贯的挑逗性服装、局部裸体或全裸",
        "边界是所描绘的动作，而非衣物覆盖程度",
        'hardcore 只使用 "FLASH-FROZEN ACTION PEAK" 或 "STILL ANCHOR, MOVING WORLD"',
        "已经进行中的露骨行为是强制要求",
        "不构成 hardcore",
        "为未来行为脱衣、准备接触通道、靠近身体部位",
        "必须描绘此刻的露骨接触，而非仅作承诺",
        "hardcore 等级不强制服装配额或默认服装",
        "完全根据场景和当前行为选择全裸、部分着装或正在脱衣",
        "不要为弱化 hardcore 内容或将其与 erotic 内容区分而添加衣物",
        "在生成任何画帧前否决主题",
        "标题、设定和风格都指向同一个唯一模式与载体",
        "否决设定未将露骨行为描述为当前接触",
        "除非每人都有指名的直接露骨角色",
        "服装清单若使用堆、垛、捆、散乱物品",
        "整齐折叠衣物、陈列式对齐、无法解释的重叠",
        "静止锚点模式快门慢于 1/4 秒却省略必需短闪光",
        "没有具体对焦几何理由却默认 f/5.6 或更小光圈",
        "闪光凝固载体完全位于声明的景深界限外",
        "把失焦环境载体称为清晰",
        '标题只命名一个运动创意，而非 "X and Y"',
        '对于 "FLASH-FROZEN" 主题',
        '对于 "STILL ANCHOR" 主题',
        "每条次要通路、天气效果、流体系统、动力系统",
        "不要把私人室内与正常运行的公共室外混合",
        "不要把搭建的复制布景称为具有真实运行的在用公共基础设施",
        "场景回路和力学回路通过日常生活逻辑检验",
        '最后在草稿中搜索 "pile"、"heap"、"bundle"、"scattered"',
        '对于脱下物品的摆放，还要搜索 "neatly folded"、"folded into a rectangle"',
        "不要否决自身翻折的腰带",
        "这些是脱下后的物理形状，不是有序收纳",
        "任何画帧只要有一项未通过，就静默否决并重写",
    ):
        assert requirement in normalized, requirement
    for excluded in (
        "至少 75% 的主题",
        "至少百分之七十五的主题",
        "至多 25% 可以让所有主要成年人全裸",
        "至多百分之二十五可以让所有主要成年人全裸",
    ):
        assert excluded not in normalized, excluded
