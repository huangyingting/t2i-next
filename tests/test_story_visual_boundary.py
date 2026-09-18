"""Bundled visual assets must not reintroduce execution or safety policy."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1] / "story-inputs" / "recipes"
CONTROL_PROSE = re.compile(
    r"(?:至少|不超过|最多|最少|不少于|前)\s*"
    r"(?:[1-9]\d{1,3}|[一二三四五六七八九十百千]{2,})\s*"
    r"(?:个)?(?:英文|英语|中文)?(?:词|字|汉字)"
    r"|(?:返回|输出)\s*(?:严格|合法|有效)?\s*JSON"
    r"|(?:违规|不合规|验证失败|校验失败).{0,20}(?:重写|重试|拒绝)"
    r"|(?:必须|须|均为|都).{0,10}(?:清醒|自愿).{0,30}(?:自愿|未成年|停止|退出)"
    r"|不得(?:描述|出现|涉及).{0,10}未成年"
    r"|(?:第[一二三四五]|[四五])句(?:必须|固定|逐字)"
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


@pytest.mark.parametrize("path", sorted(ROOT.rglob("*.yaml")), ids=lambda p: p.stem)
def test_bundled_visual_assets_have_no_execution_or_safety_boilerplate(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert not {"generation", "runtime", "validation", "policy"} & data.keys()
    assert not {"theme_count", "frames_per_theme", "output_languages"} & data.get(
        "requirements", {}
    ).keys()
    violations = [
        match.group()
        for text in strings(data)
        for match in CONTROL_PROSE.finditer(text)
    ]
    assert not violations, f"{path.name}: {violations}"
    if path.parent.name == "_catalogs":
        for entry in data["entries"]:
            if assignment := entry.get("frame_assignment"):
                assert set(assignment) == {"slots"}


@pytest.mark.parametrize(
    "prose",
    [
        "前100英文词建立画面。",
        "每个画面至少600词。",
        "返回JSON。",
        "违规时重写。",
        "所有人物必须清醒自愿且不得未成年。",
        "第一句必须逐字复制模板。",
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
        "人物必须位于构图中央。",
    ],
)
def test_boundary_guard_preserves_visual_measurements_and_visible_copy(prose):
    assert not CONTROL_PROSE.search(prose)
