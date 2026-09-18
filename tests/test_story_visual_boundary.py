"""Bundled visual assets must not reintroduce execution or safety policy."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1] / "recipes"
CONTROL_PROSE = re.compile(
    r"(?:至少|不超过|最多|最少|不少于|前)\s*"
    r"(?:[1-9]\d{1,3}|[一二三四五六七八九十百千]{2,})\s*"
    r"(?:个)?(?:英文|英语|中文)?(?:词|字(?!符)|汉字)"
    r"|(?:正文|提示词|段落|输出).{0,12}(?:至少|最多|不超过)\s*\d+\s*个?字符"
    r"|(?:返回|输出)\s*(?:严格|合法|有效)?\s*JSON"
    r"|(?:违规|不合规|验证失败|校验失败).{0,20}(?:重写|重试|拒绝)"
    r"|(?:必须|须|均为|都).{0,10}(?:清醒|自愿).{0,30}(?:自愿|未成年|停止|退出)"
    r"|(?:每位|每名|每个|所有|全部).{0,35}清醒.{0,35}(?:自愿|自主控制|能够停止)"
    r"|不得(?:描述|出现|涉及).{0,10}未成年"
    r"|(?:第[一二三四五]|[四五])分?句(?:必须|固定|逐字)"
    r"|(?:静默重写|拒绝并重写|最终静默检查|VIEW DIRECTION LOCK)"
)
ROOT_CONTROLS = frozenset(("generation", "runtime", "validation", "policy"))
REQUIREMENT_CONTROLS = frozenset(
    ("theme_count", "frames_per_theme", "output_languages")
)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def control_fields(data):
    violations = sorted(ROOT_CONTROLS & data.keys())
    violations.extend(
        f"requirements.{name}"
        for name in sorted(REQUIREMENT_CONTROLS & data.get("requirements", {}).keys())
    )
    for entry in data.get("entries", []):
        if assignment := entry.get("frame_assignment"):
            violations.extend(
                f"entries.{entry['id']}.frame_assignment.{name}"
                for name in sorted(assignment.keys() - {"slots"})
            )
    return violations


@pytest.mark.parametrize("path", sorted(ROOT.rglob("*.yaml")), ids=lambda p: p.stem)
def test_bundled_visual_assets_have_no_execution_control_fields(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert not control_fields(data), f"{path.name}: {control_fields(data)}"


@pytest.mark.parametrize("path", sorted(ROOT.rglob("*.yaml")), ids=lambda p: p.stem)
def test_bundled_visual_assets_have_no_execution_or_safety_boilerplate(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    violations = [
        match.group()
        for text in strings(data)
        for match in CONTROL_PROSE.finditer(text)
    ]
    assert not violations, f"{path.name}: {violations}"


@pytest.mark.parametrize("name", sorted(ROOT_CONTROLS))
@pytest.mark.parametrize("value", [{}, None])
def test_corpus_guard_rejects_even_empty_root_controls(name, value):
    assert control_fields({"id": "visual", name: value}) == [name]


@pytest.mark.parametrize("name", sorted(REQUIREMENT_CONTROLS))
def test_corpus_guard_rejects_execution_requirements(name):
    assert control_fields({"requirements": {name: None}}) == [f"requirements.{name}"]


@pytest.mark.parametrize("name", ["frames_per_theme", "slot_count"])
def test_corpus_guard_rejects_stored_frame_counts(name):
    assignment = {
        "slots": [{"frame_id": "F01", "rules": ["正面视角。"]}],
        name: 1,
    }
    assert control_fields(
        {
            "entries": [{"id": "front", "frame_assignment": assignment}],
        }
    ) == [f"entries.front.frame_assignment.{name}"]


def test_corpus_guard_preserves_visual_cast_and_applicability():
    assert not control_fields(
        {
            "cast": {"female_count": 1, "male_count": 1},
            "requirements": {
                "female_count": {"min": 1},
                "content_levels": ["aesthetic"],
            },
            "entries": [
                {
                    "id": "front",
                    "frame_assignment": {
                        "slots": [{"frame_id": "F01", "rules": ["正面视角。"]}],
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "prose",
    [
        "前100英文词建立画面。",
        "每个画面至少600词。",
        "提示词最多300个字符。",
        "返回JSON。",
        "违规时重写。",
        "所有人物必须清醒自愿且不得未成年。",
        "第一句必须逐字复制模板。",
        "第一分句必须采用以下语义结构。",
        "所有角色保持清醒警觉且能自主控制。",
        "每个人都必须是外观明确二十五岁以上、清醒、自愿的成年人。",
        "最终静默检查：不合格的结果拒绝并重写。",
        "VIEW DIRECTION LOCK: front view.",
    ],
)
def test_boundary_guard_detects_execution_and_safety_instructions(prose):
    assert CONTROL_PROSE.search(prose)


@pytest.mark.parametrize(
    "prose",
    [
        "人物外观年龄25–79岁。",
        "画布包含6个视图。",
        "双脚支撑于地面，膝盖弯曲90度。",
        "镜头50mm，安全栏杆位于桥边。",
        "画面中的海报标题是“成年人的夏天”。",
        "包装上的品牌名为“JSON”。",
        "画内标语包括空格和标点不超过18个字符。",
        "封套上的文字仅使用无重音拉丁字母和标准 ASCII 标点。",
        "快门时间约为 1/15 至 1/4 秒，固定焦距50mm。",
        "艺术作品分为四个段落般的色块，五行标题位于左上。",
        "人物必须位于构图中央。",
    ],
)
def test_boundary_guard_preserves_visual_measurements_and_visible_copy(prose):
    assert not CONTROL_PROSE.search(prose)
