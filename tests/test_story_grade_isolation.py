"""Check authored prose, not just which refinement keys the compiler selects."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from t2i_story_pipeline.inputs import (
    InputOverrides,
    ResolvedStoryInput,
    StoryDocument,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.models import ContentLevel, StoryStage
from t2i_story_pipeline.prompts import frame_messages, theme_messages
from tests.story_factories import make_frame_sequence, make_theme
from tests.test_story_input_briefs import (
    POLICIES,
    RECIPES,
    REPOSITORY_ROOT,
    audit_run_configuration,
    bundled_authoring_prose,
)

_RETIRED_ACTION_PRELUDES = (
    "The current fully clothed non-erotic interaction is",
    "The current erotic but non-explicit interaction is",
    "The current explicit consensual adult sexual act is",
)
_DRESS_OUTPUT_NAME_BANS = (
    "不得写出“compliant”（合规）、“safety requirement”（安全要求）或"
    "“validation”（验证）等措辞。",
)
_OUTPUT_NAME_BANS = _DRESS_OUTPUT_NAME_BANS
_PROVIDER_CONTROL_FIELDS = frozenset(
    (
        "content_level",
        "program_assigns_theme_ids",
        "program_assigns_frame_ids",
        "validation",
        "quality",
        "quality_mode",
        "mode",
        "checks",
    )
)
_GRADE = re.compile(
    r"(?ai:\b(?:aesthetic|hardcore|(?<!non-)erotic)\b)"
    r"|(?:审美|美学|唯美|情色|露骨|硬核)\s*(?:级别|等级|级)"
    r"|(?ai:\bcontent[- ]level proof\b)"
    r"|(?i:" + "|".join(re.escape(value) for value in _RETIRED_ACTION_PRELUDES) + ")"
)


def unexpected_grade_names(
    prose: str, selected: ContentLevel | None
) -> tuple[str, ...]:
    # Selection is internal: neither the selected nor a foreign grade belongs here.
    return tuple(dict.fromkeys(match.group() for match in _GRADE.finditer(prose)))


def selected_asset_prose(
    resolved: ResolvedStoryInput, stage: StoryStage
) -> Iterator[tuple[str, str]]:
    for source in resolved.sources:
        if source.kind == "module":
            for index, rule in enumerate(getattr(source, stage.value)):
                yield f"module.{source.id}.{stage.value}[{index}]", rule
    frame_ids = (
        [f"F{index:02d}" for index in range(1, resolved.request.frames_per_theme + 1)]
        if stage == StoryStage.FRAMES
        else None
    )
    context = resolved.context_for(
        stage, [plan.theme_id for plan in resolved.plans], frame_ids=frame_ids
    )
    for plan in context["plans"]:
        if plan["entry"] is not None:
            for index, rule in enumerate(plan["entry"]["rules"]):
                yield f"{plan['theme_id']}.entry.rules[{index}]", rule
        for slot in plan["frame_slots"]:
            for index, rule in enumerate(slot["rules"]):
                yield f"{plan['theme_id']}.{slot['frame_id']}.rules[{index}]", rule


def string_values(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from string_values(item)


@pytest.mark.parametrize(
    ("selected", "prose", "unexpected"),
    [
        (ContentLevel.EROTIC, "保留非露骨边界，禁止露骨性行为。", ()),
        (ContentLevel.EROTIC, "情色级保留非露骨边界。", ("情色级",)),
        (ContentLevel.EROTIC, "eRoTiC 只使用当前规则。", ("eRoTiC",)),
        (ContentLevel.HARDCORE, "HaRdCoRe 当前接触。", ("HaRdCoRe",)),
        (
            ContentLevel.AESTHETIC,
            "审美级、美学级和唯美级的同一范围。",
            ("审美级", "美学级", "唯美级"),
        ),
        (
            ContentLevel.EROTIC,
            "情色级和/或露骨级使用此规则。",
            ("情色级", "露骨级"),
        ),
        (
            ContentLevel.HARDCORE,
            "情色级和露骨级都使用此规则。",
            ("情色级", "露骨级"),
        ),
        (
            ContentLevel.EROTIC,
            "在 aesthetic 或 hardcore 中选择。",
            ("aesthetic", "hardcore"),
        ),
        (ContentLevel.EROTIC, "比硬核级更克制。", ("硬核级",)),
        (ContentLevel.EROTIC, "在HaRdCoRe级别使用此规则。", ("HaRdCoRe",)),
        (ContentLevel.HARDCORE, "情色　级的其他规则。", ("情色　级",)),
        (ContentLevel.EROTIC, "“露骨级”", ("露骨级",)),
        (ContentLevel.EROTIC, "`hardcore`", ("hardcore",)),
        (ContentLevel.EROTIC, "'HARDCORE'", ("HARDCORE",)),
        (ContentLevel.EROTIC, "“审美级别”", ("审美级别",)),
        (ContentLevel.EROTIC, '"HARDCORE WARDROBE LOCK"', ("HARDCORE",)),
        (ContentLevel.HARDCORE, '"HARDCORE WARDROBE LOCK"', ("HARDCORE",)),
        (ContentLevel.HARDCORE, '"Hardcore proof: current contact."', ("Hardcore",)),
        (
            ContentLevel.AESTHETIC,
            '"Content-level proof: covered."',
            ("Content-level proof",),
        ),
        (ContentLevel.AESTHETIC, '"non-erotic"', ()),
        (ContentLevel.HARDCORE, '"An ordinary non-erotic portrait."', ()),
        (ContentLevel.EROTIC, "'NON-EROTIC interaction'", ()),
        (
            ContentLevel.EROTIC,
            '"For hardcore scenes apply these many specific instructions instead."',
            ("hardcore",),
        ),
        (
            ContentLevel.EROTIC,
            "“在露骨级使用这段很长的普通指令，不得将引号当成输出契约。”",
            ("露骨级",),
        ),
        (None, "采用当前选中级别，保留动作与安全边界。", ()),
        (None, "如果是情色级，就选择另一条规则。", ("情色级",)),
        (None, "hardcore_mode 是内部标识符。", ()),
    ],
)
def test_grade_guard_checks_prose_without_banning_adjectives(
    selected, prose, unexpected
):
    assert unexpected_grade_names(prose, selected) == unexpected


@pytest.mark.parametrize(
    "quotes", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("`", "`")]
)
@pytest.mark.parametrize("literal", _RETIRED_ACTION_PRELUDES)
def test_retired_action_preludes_are_not_exempt_when_quoted(quotes, literal):
    prose = f"必须逐字输出 {quotes[0]}{literal}{quotes[1]}。"
    for level in ContentLevel:
        assert unexpected_grade_names(prose, level) == (literal,)


@pytest.mark.parametrize("selected", tuple(ContentLevel))
@pytest.mark.parametrize(
    "quotes", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("`", "`")]
)
def test_quoted_current_grade_selectors_are_not_output_literals(selected, quotes):
    prose = f"采用 {quotes[0]}{selected.value}{quotes[1]} 的规则。"
    assert unexpected_grade_names(prose, selected) == (selected.value,)


def test_yaml_delimiters_do_not_turn_dispatch_into_output_literals():
    value = yaml.safe_load('rule: "Use hardcore rules instead."')
    assert unexpected_grade_names(value["rule"], ContentLevel.EROTIC) == ("hardcore",)


@pytest.mark.parametrize("selected", (None, *ContentLevel))
@pytest.mark.parametrize("clause", _OUTPUT_NAME_BANS)
def test_explicit_output_name_bans_do_not_dispatch_other_grades(selected, clause):
    assert unexpected_grade_names(clause, selected) == ()


def test_output_name_ban_exception_does_not_hide_grade_routing():
    ban = "".join(_OUTPUT_NAME_BANS)
    prose = ban + "但在“hardcore”中改用另一种规则。"
    assert unexpected_grade_names(prose, ContentLevel.EROTIC) == ("hardcore",)
    for clause in _OUTPUT_NAME_BANS:
        assert unexpected_grade_names(
            clause + "但在“hardcore”中改用另一种规则。", ContentLevel.EROTIC
        ) == ("hardcore",)
        disguised_dispatch = clause[:-1] + "时改用“hardcore”的规则" + clause[-1]
        assert "hardcore" in unexpected_grade_names(
            disguised_dispatch, ContentLevel.EROTIC
        )


@pytest.mark.parametrize(
    "name", ("edo-warai-e", "ming-gongbi-mixi-tu", "tang-guohua-figures")
)
@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_painting_messages_keep_visible_action_and_medium_without_templates(
    name, level
):
    document = load_story_document(RECIPES / f"{name}.yaml")
    resolved = resolve_story_input(
        document,
        run_configuration=audit_run_configuration(document, content_level=level),
    )
    messages = frame_messages(
        resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    prompt = " ".join(messages[0].content.split())
    action_constraints = {
        ContentLevel.AESTHETIC: "画面直接呈现完整穿着的人物正在进行的非情色互动。",
        ContentLevel.EROTIC: "画面直接呈现可见的感官亲密互动，保持非露骨边界。",
        ContentLevel.HARDCORE: "画面直接呈现正在发生的明确性行为。",
    }
    for owner, constraint in action_constraints.items():
        assert prompt.count(constraint) == (1 if owner == level else 0)
    assert unexpected_grade_names(prompt, level) == ()
    assert "空间" in prompt
    assert "轮廓" in prompt
    if name == "edo-warai-e":
        assert "nishiki-e" in prompt
        assert "平面" in prompt
    else:
        assert "绢" in prompt
        assert "矿物" in prompt
    assert "句原文开头" not in prompt
    assert "英文单词的空间位置图" not in prompt


@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_provider_controls_stay_internal_without_losing_ids_or_retry_contracts(level):
    resolved = resolve_story_input(
        StoryDocument.model_validate(
            {
                "description": "中性的成年人物画面。",
            }
        ),
        InputOverrides(content_level=level, theme_count=3, frames_per_theme=4),
    )
    restored = ResolvedStoryInput.model_validate_json(resolved.model_dump_json())
    assert restored.fingerprint() == resolved.fingerprint()
    accepted = make_frame_sequence(frame_count=4, theme_index=2).frames[::2]
    for state in (resolved, restored):
        assert state.request.content_level == level
        assert [plan.theme_id for plan in state.plans] == ["T001", "T002", "T003"]
        themes = theme_messages(state, count=2, existing_themes=[make_theme()])
        theme_payload = json.loads(themes[1].content)
        assert _PROVIDER_CONTROL_FIELDS.isdisjoint(theme_payload)
        assert theme_payload["theme_count"] == 2
        assert theme_payload["existing_themes"][0]["theme_id"] == "T001"
        assert [
            plan["theme_id"] for plan in theme_payload["input_context"]["plans"]
        ] == ["T002", "T003"]
        assert (
            "Submit only semantic_name and each Theme's "
            "title, premise, style, and diversity; "
            "the program assigns all Theme IDs."
        ) in themes[0].content

        frames = frame_messages(
            state,
            make_theme(2),
            requested_frame_ids=["F02", "F04"],
            accepted_frames=accepted,
        )
        frame_payload = json.loads(frames[1].content)
        assert _PROVIDER_CONTROL_FIELDS.isdisjoint(frame_payload)
        assert frame_payload["theme"]["theme_id"] == "T002"
        assert frame_payload["requested_frame_slots"] == ["F02", "F04"]
        assert frame_payload["frames_per_theme"] == 4
        assert [frame["frame_id"] for frame in frame_payload["accepted_frames"]] == [
            "F01",
            "F03",
        ]
        assert frame_payload["frame_batch_format"] == (
            "Return exactly one <FRAME>...</FRAME> block per requested "
            "slot, in order. Tags delimit prose; do not output IDs or JSON."
        )
        for contract in (
            "Return exactly one <FRAME>...</FRAME> block per "
            "requested_frame_slots item, in the listed order.",
            "The program assigns all Frame IDs.",
            "Complete only requested_frame_slots, even when retrying a subset.",
        ):
            assert contract in frames[0].content


@pytest.mark.parametrize("level", tuple(ContentLevel))
@pytest.mark.parametrize("stage", tuple(StoryStage))
def test_relationship_messages_keep_visual_contact_and_carriers_without_templates(
    level, stage
):
    document = load_story_document(RECIPES / "relationship-caricature.yaml")
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    messages = (
        theme_messages(resolved, count=1, existing_themes=[])
        if stage == StoryStage.THEMES
        else frame_messages(
            resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
        )
    )
    prompt = " ".join(messages[0].content.split())
    bounds = {
        ContentLevel.AESTHETIC: ("不透明", "普通动作", "劳动"),
        ContentLevel.EROTIC: (
            "非露骨",
            "自我接触",
            "相互感官接触",
        ),
        ContentLevel.HARDCORE: ("生殖器", "口部", "手部", "接触"),
    }
    assert all(bound in prompt for bound in bounds[level])
    assert unexpected_grade_names(prompt, level) == ()
    for fact in ("主导", "高饱和", "隐喻", "载体", "支撑", "关系"):
        assert fact in prompt
    assert all(
        rule in messages[0].content
        for rule in document.authoring.selected(stage, level)
    )
    payload = json.loads(messages[1].content)
    assert _PROVIDER_CONTROL_FIELDS.isdisjoint(payload)


@pytest.mark.parametrize(
    ("level", "requirements"),
    [
        (
            ContentLevel.AESTHETIC,
            (
                "每位可见成年人穿一至三件",
                "乳头、外部生殖器、阴毛和肛门必须由不透明布料完整覆盖",
                "不得用湿贴、透视、开口或滑移暴露",
            ),
        ),
        (
            ContentLevel.EROTIC,
            (
                "主要成年女性表演者必须实际保留一至两件",
                "逐件写明可见的准确停留位置",
                "不能直接完全裸体",
                "不得出现插入或明确伴侣性行为",
            ),
        ),
        (
            ContentLevel.HARDCORE,
            (
                "主要成年女性表演者下身必须完全赤裸",
                "不得遮住外阴、阴毛、臀部、肛门或当前动作区域",
                "动作区域之外保留一件极少量上身单品",
                "零至四件配饰、袜类或鞋履",
            ),
        ),
    ],
)
def test_liquid_messages_keep_concrete_wardrobe_constraints_without_proofs(
    level, requirements
):
    document = load_story_document(RECIPES / "intimate-liquid-editorial.yaml")
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    messages = frame_messages(
        resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    prompt = messages[0].content
    assert unexpected_grade_names(prompt, level) == ()
    assert all(requirement in "".join(prompt.split()) for requirement in requirements)
    assert "WARDROBE LOCK" not in prompt
    assert "衣着锁" not in prompt


@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_dress_preserves_selected_product_design_without_word_blacklists(level):
    document = load_story_document(RECIPES / "dress.yaml")
    visual_features = {
        ContentLevel.AESTHETIC: ("内衣", "连体衣", "轻透叠穿"),
        ContentLevel.EROTIC: ("身体首饰", "敞开式服装", "束带结构"),
        ContentLevel.HARDCORE: ("快拆束环", "身体链饰", "五金件"),
    }
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    restored = ResolvedStoryInput.model_validate_json(resolved.model_dump_json())
    assert restored.fingerprint() == resolved.fingerprint()
    for state in (resolved, restored):
        for stage in StoryStage:
            compiled = state.rules.text_for(stage)
            assert all(feature in compiled for feature in visual_features[level])
            assert unexpected_grade_names(compiled, level) == ()
            messages = (
                theme_messages(state, count=1, existing_themes=[])
                if stage == StoryStage.THEMES
                else frame_messages(
                    state, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
                )
            )
            prose = [
                messages[0].content,
                *string_values(json.loads(messages[1].content)),
            ]
            assert all(
                any(feature in value for value in prose)
                for feature in visual_features[level]
            )
            if stage == StoryStage.FRAMES:
                assert all(
                    clause not in messages[0].content
                    for clause in _DRESS_OUTPUT_NAME_BANS
                )


@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_motion_public_setting_is_visual_and_safety_is_always_system_owned(level):
    document = load_story_document(RECIPES / "motion-blur-photography.yaml")
    public_production = "公共场所呈现封闭片场的空间状态及明确背景人群密度"
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    restored = ResolvedStoryInput.model_validate_json(resolved.model_dump_json())
    assert restored.fingerprint() == resolved.fingerprint()
    for state in (resolved, restored):
        for stage, messages in (
            (StoryStage.THEMES, theme_messages(state, count=1, existing_themes=[])),
            (
                StoryStage.FRAMES,
                frame_messages(
                    state, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
                ),
            ),
        ):
            expected = stage == StoryStage.FRAMES and level in (
                ContentLevel.EROTIC,
                ContentLevel.HARDCORE,
            )
            assert state.rules.text_for(stage).count(public_production) == (
                1 if expected else 0
            )
            assert messages[0].content.count(public_production) == (
                1 if expected else 0
            )
            assert "前 100 个英文词" not in messages[0].content
            safety = next(
                source
                for source in state.sources
                if source.kind == "system" and source.id.endswith("safety.rules")
            )
            assert all(
                rule in messages[0].content for rule in getattr(safety, stage.value)
            )


@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_motion_frames_define_camera_contract_once_and_scope_subject_blur(level):
    document = load_story_document(RECIPES / "motion-blur-photography.yaml")
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    messages = frame_messages(
        resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    prompt = " ".join(messages[0].content.split())
    for visual_fact in (
        "拍摄系统不进入图像",
        "设备、人员、轮廓、阴影或反射",
        "快门时间和闪光时长不同",
        "1/2000",
        "1/10000",
        "焦平面",
        "前景过渡",
        "背景过渡",
    ):
        assert visual_fact in prompt
    assert "Captured from a [height]" not in prompt
    assert '"camera body"' not in prompt
    for instruction in (
        "主体运动模糊采用摇摄而非锁定机位",
        "静止环境反向拖成条纹",
        "摇摄轴心、起止方位角和被追踪平面一致",
        "摇摄主体的快门时间约为 1/15 至 1/4 秒",
        "主体运动模糊对焦最近眼睛或面部平面",
    ):
        assert (instruction in prompt) == (level != ContentLevel.HARDCORE)
    forbidden_mode = "不用同步摇摄或长曝光主体模糊表现多身体露骨接触"
    assert (forbidden_mode in prompt) == (level == ContentLevel.HARDCORE)


@pytest.mark.parametrize(
    ("level", "bounds"),
    [
        (
            ContentLevel.AESTHETIC,
            ("服装尺度为完整尺寸", "全部六种姿势中始终稳固就位"),
        ),
        (
            ContentLevel.EROTIC,
            (
                "服装尺度缩减至内衣尺寸",
                "不透明罩杯或布片须遮盖乳头",
                "每种姿势中遮盖生殖器、肛门及臀沟",
                "既不得恢复为常规完整遮盖，也不得缩减为微型遮盖",
            ),
        ),
        (
            ContentLevel.HARDCORE,
            (
                "服装尺度为极简或微型",
                "仅占据很少的身体表面",
                "不得采用常规完整尺寸或内衣尺寸的遮盖",
            ),
        ),
    ],
)
def test_pose_messages_preserve_absolute_coverage_and_six_internal_views(level, bounds):
    document = load_story_document(RECIPES / "pose.yaml")
    resolved = resolve_story_input(
        document, InputOverrides(content_level=level, frames_per_theme=1)
    )
    messages = frame_messages(
        resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    assert all(bound in messages[0].content for bound in bounds)
    assert unexpected_grade_names(messages[0].content, level) == ()
    payload = json.loads(messages[1].content)
    assert payload["frames_per_theme"] == 1
    assert payload["requested_frame_slots"] == ["F01"]
    assert payload["input_context"]["plans"][0]["cast"]["total"] == 1
    layout = next(
        item["parameters"]
        for item in payload["input_context"]["modules"]
        if item["id"] == "layout-multiview"
    )
    assert (layout["min_views"], layout["max_views"]) == (6, 6)


@pytest.mark.parametrize(
    "path",
    sorted((*RECIPES.rglob("*.yaml"), *POLICIES.glob("*.yaml"))),
    ids=lambda path: str(path.relative_to(REPOSITORY_ROOT)),
)
def test_bundled_prose_has_no_grade_announcements_or_dispatch(path: Path):
    violations = []
    for field, prose in bundled_authoring_prose(path):
        parts = field.split(".")
        selected = (
            ContentLevel(parts[2])
            if parts[:2] == ["authoring", "level_refinements"]
            else None
        )
        if names := unexpected_grade_names(prose, selected):
            violations.append(f"{field}: {', '.join(names)}")
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize("path", sorted(RECIPES.glob("*.yaml")), ids=lambda p: p.stem)
def test_selected_messages_and_assets_have_no_grade_announcements_or_dispatch(path):
    document = load_story_document(path)
    violations = []
    for level in document.requirements.content_levels or tuple(ContentLevel):
        resolved = resolve_story_input(
            document,
            InputOverrides(content_level=level),
            run_configuration=audit_run_configuration(document),
        )
        assert resolved.request.content_level == level
        for stage in StoryStage:
            for field, prose in selected_asset_prose(resolved, stage):
                if names := unexpected_grade_names(prose, level):
                    violations.append(f"{level}.{stage}.{field}: {', '.join(names)}")
            messages = (
                theme_messages(resolved, count=1, existing_themes=[])
                if stage == StoryStage.THEMES
                else frame_messages(
                    resolved,
                    make_theme(),
                    requested_frame_ids=["F01"],
                    accepted_frames=[],
                )
            )
            payload = json.loads(messages[1].content)
            assert _PROVIDER_CONTROL_FIELDS.isdisjoint(payload)
            for index, prose in enumerate(
                [messages[0].content, *string_values(payload)]
            ):
                if names := unexpected_grade_names(prose, level):
                    violations.append(
                        f"{level}.{stage}.messages[{index}]: {', '.join(names)}"
                    )
    assert not violations, "\n".join(violations)


def test_selected_asset_audit_catches_module_catalog_and_frame_slot_prose(tmp_path):
    bad = "Use hardcore instructions in this erotic request."
    for directory in ("_modules", "_catalogs"):
        (tmp_path / directory).mkdir()
    (tmp_path / "_modules" / "layout.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "layout",
                "kind": "layout_multiview",
                "authoring": {"frames": {"common": [bad]}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "_catalogs" / "slots.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "slots",
                "slots": ["one"],
                "entries": [
                    {
                        "id": "one",
                        "themes": ["A neutral layout."],
                        "frames": [bad],
                        "frame_assignment": {
                            "slots": [{"frame_id": "F01", "rules": [bad]}],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    resolved = resolve_story_input(
        StoryDocument.model_validate(
            {
                "description": "A neutral layout.",
                "modules": [
                    {
                        "id": "layout",
                        "parameters": {"layout": "grid", "rows": 1, "columns": 2},
                    }
                ],
                "allocation": {"type": "fixed_slots", "catalog": "slots"},
            }
        ),
        InputOverrides(frames_per_theme=1, content_level="erotic"),
        asset_root=tmp_path,
    )
    violations = {
        field: unexpected_grade_names(prose, ContentLevel.EROTIC)
        for field, prose in selected_asset_prose(resolved, StoryStage.FRAMES)
    }
    assert violations == {
        "module.layout.frames[0]": ("hardcore", "erotic"),
        "T001.entry.rules[0]": ("hardcore", "erotic"),
        "T001.F01.rules[0]": ("hardcore", "erotic"),
    }
    assert all(
        not unexpected_grade_names(prose, ContentLevel.EROTIC)
        for _, prose in selected_asset_prose(resolved, StoryStage.THEMES)
    )


_FRAME_FEATURES = {
    "demon-lord": {
        ContentLevel.AESTHETIC: ("所有成年人穿完整不透明衣物", "王座"),
        ContentLevel.EROTIC: ("触碰的可见相互回应", "衣物必须遵循当前姿势与重力"),
        ContentLevel.HARDCORE: ("当前精确接触、身体朝向、支撑和角色", "具体连接"),
    },
    "angel": {
        ContentLevel.AESTHETIC: ("完整的不透明衣物", "雨、浸水、汗、雾和逆光"),
        ContentLevel.EROTIC: (
            "清楚可见且非露骨的成年人情色状态",
            "相互回应可见",
            "至少让一位主要参与者的面部表情清楚可读",
            "不用相同的半闭眼、张嘴、仰头",
        ),
        ContentLevel.HARDCORE: (
            "实际可行的翅膀净空",
            "参与动作的普通人类解剖结构",
            "身体内部结构始终不可见",
            "具体参与者、具体动作和具体接触部位",
            "每幅画面逐字写明一种当前动作",
            "性姿势与动作布局采用开放集合",
            "身体朝向、跪立坐卧层级、承重点",
            "抱举或抬起姿势必须说明承重者双脚所在的稳定表面",
            "器具保持一个连续形体和一条可见接触路径",
            "至少让一位主要参与者的面部表情清楚可读",
            "执行、承受、支撑或使用器具的人不复制同一表情",
        ),
    },
    "post-layout": {
        ContentLevel.AESTHETIC: ("主导照片必须明确保持非露骨",),
        ContentLevel.EROTIC: (
            "主导照片中呈现非露骨的亲密互动",
            "至少一个较小摄影碎片",
        ),
        ContentLevel.HARDCORE: (
            "将直接露骨的互动置于主导照片中",
            "至少一个较小摄影碎片",
        ),
    },
    "motion-blur-photography": {
        ContentLevel.AESTHETIC: ("腾空衣物必须可见地推进当前脱衣", "不进行性化裸露"),
        ContentLevel.EROTIC: ("不要展示直接生殖器刺激或露骨玩具使用",),
        ContentLevel.HARDCORE: (
            "在接触开始前就已经完全脱离双腿",
            "照片中的运动只能是最终的手部释放",
            "不要为弱化当前行为的可见性而添加衣物",
        ),
    },
}


@pytest.mark.parametrize("name", tuple(_FRAME_FEATURES))
@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_real_messages_keep_current_features_without_other_grade_prose(name, level):
    document = load_story_document(RECIPES / f"{name}.yaml")
    resolved = resolve_story_input(
        document,
        InputOverrides(
            content_level=level, frames_per_theme=1, female_count=1, male_count=1
        ),
    )
    for stage, messages in (
        (StoryStage.THEMES, theme_messages(resolved, count=1, existing_themes=[])),
        (
            StoryStage.FRAMES,
            frame_messages(
                resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
            ),
        ),
    ):
        payload = json.loads(messages[1].content)
        assert resolved.request.content_level == level
        assert "content_level" not in payload
        prose = [messages[0].content, *string_values(payload)]
        violations = [
            names for value in prose if (names := unexpected_grade_names(value, level))
        ]
        assert not violations, violations
        assert all(
            rule in messages[0].content
            for rule in document.authoring.selected(stage, level)
        )
        if name == "motion-blur-photography":
            for clause in (
                "公共场所呈现封闭片场的空间状态",
                "背景成年人保持次要位置",
            ):
                assert any(clause in value for value in prose) == (
                    stage == StoryStage.FRAMES and level != ContentLevel.AESTHETIC
                )
        if stage == StoryStage.FRAMES:
            compiled = messages[0].content
            assert all(marker in compiled for marker in _FRAME_FEATURES[name][level])
            assert "前 100 个英文词" not in compiled
            assert "前一百个英文单词" not in compiled
            if name == "demon-lord" and level != ContentLevel.AESTHETIC:
                assert "不高于脚踝" in compiled
                assert "任何面孔、胸部、骨盆、性接触或呼吸通道都不得浸没" in compiled


@pytest.mark.parametrize("level", tuple(ContentLevel))
@pytest.mark.parametrize("stage", tuple(StoryStage))
def test_angel_visual_choices_reach_each_stage_without_fixed_style_locks(level, stage):
    document = load_story_document(RECIPES / "angel.yaml")
    resolved = resolve_story_input(
        document,
        InputOverrides(content_level=level, female_count=1, male_count=1),
    )
    messages = (
        theme_messages(resolved, count=1, existing_themes=[])
        if stage == StoryStage.THEMES
        else frame_messages(
            resolved,
            make_theme(),
            requested_frame_ids=["F01", "F02"],
            accepted_frames=[],
        )
    )
    compiled = "\n".join(message.content for message in messages)
    payload = json.loads(messages[1].content)
    assert payload["story"] == document.description
    assert resolved.plans[0].cast.total == 2
    for identity in ("恰好有一位核心天使", "恰好一对翅膀", "无翼人类"):
        assert identity in compiled
    assert "Safety is an immutable instruction contract" in messages[0].content
    assert all(
        rule in messages[0].content
        for rule in document.authoring.selected(stage, level)
    )
    choices = {
        StoryStage.THEMES: (
            "姿态、双翼开合、具体接触布局、景别、机位、焦点和局部照明留给各 Frame",
            "人物目的、关系结构、空间用途、环境状态、羽翼形态、服装体系与视觉语言",
            "已经接受的 Theme",
            "当前目标、阻碍或异常状态",
            "不把其中任何一项或其组合当作默认天使母题",
            "不要求每个主题都有大型场面事件",
            "明亮、中间调或暗调曝光均可成立",
            "普通居所、狭窄工作间",
            "地点具有可见用途并影响人物活动、姿态与羽翼净空",
            "不是封闭职业清单",
        ),
        StoryStage.FRAMES: (
            "同一时间窗口中的平行画面方案",
            "任意两个 Frame 至少在景别、机位高度",
            "至少生成三个 Frame 时",
            "一个头部、一个躯干、一个骨盆",
            "每条可见的手臂和腿",
            "每条肢体只有一个位置、一个关节状态和一个主要职责",
            "表情由当前动作阶段、人物角色、身体受力、呼吸节奏和彼此关系共同决定",
            "用视线方向、眼睑张力、眉形、嘴唇或下颌状态",
            "折翼不要求场地能够容纳完全展开的翼展",
            "分别从对应翼根连续延伸至翼尖",
            "羽翼不是人体的第三支点",
            "侧身、背身、局部裁切与自然遮挡都可使用",
            "不要求每幅同时展示面孔、两个翼根、双手和全部羽毛",
            "单一不透明二维投影",
            "改变机位或姿势",
            "没有视线通路时不声称双方对视",
            "不为面向摄影机而反向扭颈",
            "为每个承重的手、膝、脚、背部或骨盆",
            "每件衣物只有一个明确位置",
            "不限定为一组固定数值",
            "不强行添加奇观",
            "不混入 intensity、mood、cinematic",
        ),
    }
    for choice in choices[stage]:
        assert choice in messages[0].content
    level_choices = {
        ContentLevel.EROTIC: {
            StoryStage.THEMES: (
                "每个 Theme 和每幅画面都通过部分或完整裸体",
                "Theme 阶段直接建立上述清楚可见且非露骨的成年人感官状态",
                "移除当前亲密接触后",
            ),
            StoryStage.FRAMES: (
                "每个 Theme 和每幅画面都通过部分或完整裸体",
                "每幅画面的冻结瞬间已经建立一项明确的双向亲密互动",
                "不执行取水、绘画、劳作、观察环境等独立任务",
                "至少让一位主要参与者的面部表情清楚可读",
                "不用相同的半闭眼、张嘴、仰头",
            ),
        },
        ContentLevel.HARDCORE: {
            StoryStage.THEMES: (
                "每个 Theme 和每幅画面都呈现一项清晰可见",
                "性姿势与动作布局采用开放集合",
                "Theme 阶段直接建立上述已经发生且正在进行的成年人性行为",
                "premise 用具体解剖词明确指定一项主要性行为",
                "不能只用“成年人性行为”“亲密结合”或其他泛称占位",
                "不重复“主要行为、姿势类别、双方朝向、承重表面与器具使用”组合",
                "请求不少于六个 Theme 时",
            ),
            StoryStage.FRAMES: (
                "每个 Theme 和每幅画面都呈现一项清晰可见",
                "性姿势与动作布局采用开放集合",
                "每幅画面的性行为已经建立并占据视觉中心",
                "与性行为并行的环境任务代替",
                "闭环下装在行为开始前已经完全脱离双腿",
                "身体内部结构始终不可见",
                "每幅画面逐字写明一种当前动作",
                "不能只写“性行为正在持续”",
                "不只改变机位或措辞",
                "抱举或抬起姿势必须说明承重者双脚所在的稳定表面",
                "器具保持一个连续形体和一条可见接触路径",
                "至少让一位主要参与者的面部表情清楚可读",
                "不复制同一表情",
            ),
        },
    }
    for choice in level_choices.get(level, {}).get(stage, ()):
        assert choice in messages[0].content
    for retired in (
        "百分之八十五",
        "百分之六十至七十五",
        "百分之五",
        "不超过两个柔和色相族",
        "恰好选择一个在可见瞬间已发生的主导大型场面事件",
        "每幅图像构建三个清晰可辨的层次",
        "清晰可辨的双手与面孔",
        "24mm 至 135mm 范围内一个精确焦距",
        "整个身体占据区域都干燥、处于室温",
        "不高于脚踝",
    ):
        assert retired not in compiled
