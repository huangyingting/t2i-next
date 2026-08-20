"""Deterministic visual coverage plans for independent Frame variations."""

from __future__ import annotations

import re

_VARIATION_FOCI = (
    "空间关系：使用全景或中全景，突出环境几何、人物与视觉锚点的空间关系。",
    "人物互动：使用中景或近景，突出人物与视觉锚点及真实记录工具的关系。",
    "锚点细节：使用近景或特写，明确命名并呈现视觉锚点，同时保留至少一名可见人物。",
    "非常规机位：采用明显高机位、低机位、俯视或仰视，突出锚点与人物的尺度关系。",
    "间接构图：使用前景遮挡、倒影、框中框或负空间呈现视觉锚点与人物。",
)


def build_variation_plan(
    theme_id: str,
    frame_ids: tuple[str, ...],
) -> dict[str, str]:
    theme_match = re.fullmatch(r"T(\d+)", theme_id)
    if theme_match is None:
        raise ValueError(f"无效 Theme ID：{theme_id}")
    theme_offset = int(theme_match.group(1)) - 1

    plan: dict[str, str] = {}
    frame_pattern = re.compile(rf"{re.escape(theme_id)}-F(\d+)")
    for frame_id in frame_ids:
        frame_match = frame_pattern.fullmatch(frame_id)
        if frame_match is None:
            raise ValueError(
                f"Frame ID {frame_id} 不属于 Theme {theme_id}"
            )
        frame_index = int(frame_match.group(1))
        focus_index = (theme_offset + frame_index - 1) % len(
            _VARIATION_FOCI
        )
        cycle = (frame_index - 1) // len(_VARIATION_FOCI) + 1
        guidance = _VARIATION_FOCI[focus_index]
        if cycle > 1:
            guidance = (
                f"第 {cycle} 轮变化；{guidance}"
                "不得复用前一轮同类焦点的机位、构图或人物调度。"
            )
        plan[frame_id] = guidance
    return plan
