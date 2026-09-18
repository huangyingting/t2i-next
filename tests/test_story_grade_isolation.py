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
from tests.story_factories import make_theme
from tests.test_story_input_briefs import (
    POLICIES,
    RECIPES,
    REPOSITORY_ROOT,
    bundled_authoring_prose,
)

_ACTION_OPENINGS = (
    "The current fully clothed non-erotic interaction is",
    "The current erotic but non-explicit interaction is",
)
_OUTPUT_LITERALS = {
    "edo-warai-e": _ACTION_OPENINGS,
    "ming-gongbi-mixi-tu": _ACTION_OPENINGS,
}
_VERBATIM_OUTPUT = frozenset(
    literal for literals in _OUTPUT_LITERALS.values() for literal in literals
)
_DRESS_OUTPUT_NAME_BANS = (
    "不得写出“compliant”（合规）、“safety requirement”（安全要求）或"
    "“validation”（验证）等措辞。",
)
_OUTPUT_NAME_BANS = _DRESS_OUTPUT_NAME_BANS
_QUOTED = re.compile(
    r'`[^`]*`|"[^"]*"|“[^”]*”|‘[^’]*’|(?<![A-Za-z])\'[^\'\n]+\'(?![A-Za-z])'
)
_GRADE = re.compile(
    r"(?ai:\b(?:aesthetic|hardcore|(?<!non-)erotic)\b)"
    r"|(?:审美|美学|唯美|情色|露骨|硬核)\s*(?:级别|等级|级)"
    r"|(?ai:\bcontent[- ]level proof\b)"
)


def unexpected_grade_names(
    prose: str, selected: ContentLevel | None
) -> tuple[str, ...]:
    # Selection is internal: neither the selected nor a foreign grade belongs here.
    # Only creative output literals are exempt.
    literal_spans = [
        match.span()
        for match in _QUOTED.finditer(prose)
        if match.group()[1:-1] in _VERBATIM_OUTPUT
    ]
    unexpected = []
    for match in _GRADE.finditer(prose):
        if any(
            start <= match.start() and match.end() <= end
            for start, end in literal_spans
        ):
            continue
        unexpected.append(match.group())
    return tuple(dict.fromkeys(unexpected))


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
def test_only_exact_output_literals_survive_other_grade_mentions(quotes):
    literal = _ACTION_OPENINGS[1]
    prose = f"必须逐字输出 {quotes[0]}{literal}{quotes[1]}。"
    assert unexpected_grade_names(prose, ContentLevel.AESTHETIC) == ()
    changed = prose.replace("interaction is", "interaction must be")
    assert unexpected_grade_names(changed, ContentLevel.AESTHETIC) == ("erotic",)


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


@pytest.mark.parametrize("name", tuple(_OUTPUT_LITERALS))
def test_reviewed_output_literals_are_preserved_verbatim(name):
    quoted = {
        match.group()[1:-1]
        for _, prose in bundled_authoring_prose(RECIPES / f"{name}.yaml")
        for match in _QUOTED.finditer(prose)
    }
    assert set(_OUTPUT_LITERALS[name]) <= quoted


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
def test_dress_preserves_output_name_bans_and_scopes_product_permission(level):
    document = load_story_document(RECIPES / "dress.yaml")
    permission = (
        "若有助于准确指明所设计的物件，可以使用乳夹、口塞、假阳具、"
        "振动器或塞具等直白的标准商业产品名称。"
    )
    assert permission not in document.description
    for stage in StoryStage:
        assert all(
            permission not in rule
            for rule in getattr(document.authoring, stage.value).common
        )
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    restored = ResolvedStoryInput.model_validate_json(resolved.model_dump_json())
    assert restored.fingerprint() == resolved.fingerprint()
    for state in (resolved, restored):
        for stage in StoryStage:
            compiled = state.rules.text_for(stage)
            assert (permission in compiled) == (level != ContentLevel.AESTHETIC)
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
            assert any(permission in value for value in prose) == (
                level != ContentLevel.AESTHETIC
            )
            if stage == StoryStage.FRAMES:
                assert all(
                    clause in messages[0].content for clause in _DRESS_OUTPUT_NAME_BANS
                )


@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_motion_public_production_rule_has_frame_and_grade_scope(level):
    document = load_story_document(RECIPES / "motion-blur-photography.yaml")
    public_production = (
        "背景人群：公共场所拍摄必须采用封闭、出入受控的制作。"
        "前 100 个英文词内，说明对普通公众关闭、临时演员均为知情同意的成年人，"
        "以及人群密度。临时演员绝不成为不知情目击者。"
    )
    for stage in StoryStage:
        assert public_production not in getattr(document.authoring, stage.value).common
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
            assert getattr(state.rules, stage.value).count(public_production) == (
                1 if expected else 0
            )
            assert messages[0].content.count(public_production) == (
                1 if expected else 0
            )


@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_motion_frames_define_camera_contract_once_and_scope_subject_blur(level):
    document = load_story_document(RECIPES / "motion-blur-photography.yaml")
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    messages = frame_messages(
        resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    prompt = " ".join(messages[0].content.split())
    for literal in (
        "camera body", "camera mounted", "tripod", "gimbal", "flash head",
        "flash unit", "softbox", "light stand", "umbrella", "reflector",
        "capture cable", "shutter trigger", "capture monitor", "production crew",
        "photographer", "lighting assistant", "production personnel",
        "equipment outside the frame",
    ):
        assert prompt.count(f'"{literal}"') == 1, literal
    method = (
        '"Captured from a [height], [distance], [azimuth], [pitch] viewpoint '
        "with a [focal length] lens at [aperture], focused at [distance]; "
        "a [shutter] ambient exposure records [carrier path]; "
        "a [t.1 duration] off-frame pulse from [screen direction] freezes "
        "[selected plane]; [ND strength when needed] controls ambient exposure; "
        'no capture apparatus is visible."'
    )
    assert prompt.count(method) == 1
    for exception in (
        '"Crew cut" 和 "crew-neck" 仍是有效的外观与衣物结构用语',
        "显示器、线缆或设备架仍有效",
        "不要否决自身翻折的腰带",
        "这些是脱下后的物理形状，不是有序收纳",
    ):
        assert exception in prompt
    for instruction in (
        '"SUBJECT MOTION BLUR"',
        "相机不是锁定或固定的",
        "说明摇摄轴心、起始方位角、结束方位角和被追踪平面",
        "摇摄主体的快门时间约为 1/15 至 1/4 秒",
        "将被追踪的最近眼睛或面部平面置于焦点",
    ):
        assert (instruction in prompt) == (level != ContentLevel.HARDCORE)
    forbidden_mode = "多身体露骨接触绝不使用同步摇摄或长曝光主体模糊"
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
        resolved = resolve_story_input(document, InputOverrides(content_level=level))
        assert resolved.request.content_level == level
        for stage in StoryStage:
            for field, prose in selected_asset_prose(resolved, stage):
                if names := unexpected_grade_names(prose, level):
                    violations.append(f"{level}.{stage}.{field}: {', '.join(names)}")
            messages = (
                theme_messages(resolved, count=1, existing_themes=[])
                if stage == StoryStage.THEMES
                else frame_messages(
                    resolved, make_theme(), requested_frame_ids=["F01"],
                    accepted_frames=[],
                )
            )
            payload = json.loads(messages[1].content)
            assert "content_level" not in payload
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
                            "frames_per_theme": 1,
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
                "generation": {"frames_per_theme": 1, "content_level": "erotic"},
                "modules": [
                    {
                        "id": "layout",
                        "parameters": {"layout": "grid", "rows": 1, "columns": 2},
                    }
                ],
                "allocation": {"type": "fixed_slots", "catalog": "slots"},
            }
        ),
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
        ContentLevel.EROTIC: ("consensual and willing", "前一百个英文单词"),
        ContentLevel.HARDCORE: ("当前精确接触、身体朝向、支撑和角色", "前两句"),
    },
    "angel": {
        ContentLevel.AESTHETIC: ("完整的不透明衣物", "雨、浸水、汗、雾和逆光"),
        ContentLevel.EROTIC: ("非露骨的成年人亲密互动", "consensual and willing"),
        ContentLevel.HARDCORE: ("实际可行的翅膀净空", "前两句"),
    },
    "post-layout": {
        ContentLevel.AESTHETIC: ("主导照片必须明确保持非露骨",),
        ContentLevel.EROTIC: (
            "主导照片中明确可见地呈现非露骨",
            "至少一个较小摄影碎片",
        ),
        ContentLevel.HARDCORE: (
            "将直接露骨的成年人互动置于主导照片中",
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
                "公共场所拍摄必须采用封闭、出入受控的制作",
                "前 100 个英文词内，说明对普通公众关闭",
                "临时演员均为知情同意的成年人，以及人群密度",
                "临时演员绝不成为不知情目击者",
            ):
                assert any(clause in value for value in prose) == (
                    stage == StoryStage.FRAMES and level != ContentLevel.AESTHETIC
                )
        if stage == StoryStage.FRAMES:
            compiled = messages[0].content
            assert all(marker in compiled for marker in _FRAME_FEATURES[name][level])
            if name in ("demon-lord", "angel") and level != ContentLevel.AESTHETIC:
                assert "不高于脚踝" in compiled
                assert "任何面孔、胸部、骨盆、性接触或呼吸通道都不得浸没" in compiled
