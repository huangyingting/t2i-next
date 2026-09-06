"""Deterministic visual coverage plans for independent Frame variations."""

from __future__ import annotations

import re

_VARIATION_FOCI = (
    "空间关系：使用全景或中全景，突出环境几何、人物与视觉锚点的空间关系。",
    "人物互动：使用中景或近景，呈现人物对 brief 核心物体的当前动作；"
    "全部人物以躯干或身体主体入画，工具仅取自 brief 或 Theme。",
    "锚点细节：用中景呈现核心动作和已有工具；"
    "全部人物以躯干或身体主体入画，不用局部肢体代替人物。",
    "非常规机位：采用明显高机位、低机位、俯视或仰视，突出锚点与人物的尺度关系。",
    "间接构图：使用前景遮挡、倒影、框中框或负空间呈现视觉锚点与人物。",
)

_APPEARANCE_FOCI = (
    "发型长度与轮廓",
    "发型质地与颜色",
    "面部稳定特征",
    "整洁或凌乱的造型方向",
    "头发束扎、编发或自然垂落方式",
)
_WARDROBE_FOCI = (
    "利落贴身剪裁",
    "宽松分层穿搭",
    "垂坠或不对称轮廓",
    "功能性结构与扣件",
    "简洁无缝轮廓",
)
_FOOTWEAR_FOCI = (
    "靴类",
    "有跟鞋履",
    "平底鞋履",
    "功能性鞋履",
    "赤足或极简鞋履",
)
_ACCESSORY_FOCI = (
    "无配饰，依靠服装结构",
    "一件细小金属配饰",
    "一件醒目配饰",
    "功能性腰带或腕部配件",
    "耳部或颈部配饰",
)
_SPATIAL_STRUCTURES = (
    "开放式中央焦点，背景沿周边展开",
    "轴向纵深，前中后景连续",
    "分层平台或高差形成上下层",
    "半围合区域与开口形成框景",
    "环形或周边结构包围核心区域",
)
_MATERIAL_DIRECTIONS = (
    "木材与织物为主",
    "混凝土与深色金属为主",
    "玻璃与浅色金属为主",
    "石材与暖色金属为主",
    "陶瓷与哑光涂层为主",
)
_POPULATION_LAYOUTS = (
    "背景人物稀疏分布并留出负空间",
    "背景人物集中于单一纵深层",
    "背景人物分布于前后两层",
    "背景人物沿空间边缘分布",
    "背景人物围绕核心区域分布",
)
_ATMOSPHERE_DIRECTIONS = (
    "暖色、低反差、疏朗",
    "冷色、高反差、克制",
    "中性色、均匀亮度、开放",
    "冷暖分区、局部暗部、紧张",
    "低照度、轮廓高光、私密",
)
_LIGHT_SOURCE_DIRECTIONS = (
    "侧向现场光为主",
    "顶部现场光为主",
    "侧后方轮廓光源为主",
    "前后两种现场光共同作用",
    "低位或近地现场光为主",
)

_SHOT_STRATEGIES = (
    "全景或中全景，建立完整空间关系",
    "中景，突出人物互动",
    "较近中景，全部人物躯干仍入画",
    "全景，强调人物与环境尺度",
    "中全景，利用前景形成层次",
)
_VIEW_STRATEGIES = (
    "平视正面或轻微侧转",
    "高机位三分之四侧视",
    "低机位侧视",
    "明显俯视",
    "后侧三分之四视角",
)
_DEPTH_STRATEGIES = (
    ("deep", "环境与全部人物保持清晰"),
    ("moderate", "核心人物清晰，背景轻微渐虚"),
    ("moderate", "互动接触点清晰，前后层次分离"),
    ("shallow", "仅当全部核心人物处于同一焦平面时使用"),
    ("deep", "前景、人物与环境结构均可辨"),
)
_LIGHT_DIRECTIONS = (
    "侧光形成明确明暗分区",
    "顶光建立人物与地面投影",
    "侧后光勾勒轮廓，正面保留细节",
    "正面主光配轻微侧向阴影",
    "前景较亮，背景逐级转暗",
)
_COLOR_TREATMENTS = (
    "使用所选光源本色",
    "所选光源本色配弱中性填充",
    "仅在可用光源支持时形成冷暖分区",
    "保持人物与背景的色温差",
    "单一主色温，减少杂色",
)


def build_theme_variation_plan(
    theme_ids: tuple[str, ...],
    character_count: int,
) -> dict[str, dict[str, object]]:
    plan: dict[str, dict[str, object]] = {}
    for theme_id in theme_ids:
        match = re.fullmatch(r"T(\d+)", theme_id)
        if match is None:
            raise ValueError(f"无效 Theme ID：{theme_id}")
        theme_offset = int(match.group(1)) - 1
        plan[theme_id] = {
            "setting_variation": {
                "spatial_structure": _SPATIAL_STRUCTURES[
                    theme_offset % len(_SPATIAL_STRUCTURES)
                ],
                "material_direction": _MATERIAL_DIRECTIONS[
                    (theme_offset * 2) % len(_MATERIAL_DIRECTIONS)
                ],
                "population_layout": _POPULATION_LAYOUTS[
                    (theme_offset * 3) % len(_POPULATION_LAYOUTS)
                ],
                "atmosphere_direction": _ATMOSPHERE_DIRECTIONS[
                    (theme_offset * 4) % len(_ATMOSPHERE_DIRECTIONS)
                ],
                "light_source_direction": _LIGHT_SOURCE_DIRECTIONS[
                    theme_offset % len(_LIGHT_SOURCE_DIRECTIONS)
                ],
            },
            "character_variations": {
                f"{theme_id}-C{index:02d}": {
                    "appearance_focus": _APPEARANCE_FOCI[
                        (theme_offset + index - 1) % len(_APPEARANCE_FOCI)
                    ],
                    "wardrobe_silhouette": _WARDROBE_FOCI[
                        (theme_offset * 2 + index - 1)
                        % len(_WARDROBE_FOCI)
                    ],
                    "footwear": _FOOTWEAR_FOCI[
                        (theme_offset * 3 + index - 1)
                        % len(_FOOTWEAR_FOCI)
                    ],
                    "accessory_strategy": _ACCESSORY_FOCI[
                        (theme_offset * 4 + index - 1)
                        % len(_ACCESSORY_FOCI)
                    ],
                }
                for index in range(1, character_count + 1)
            }
        }
    return plan


def build_frame_visual_plan(
    theme_id: str,
    frame_ids: tuple[str, ...],
    available_light_sources: tuple[str, ...],
) -> dict[str, dict[str, str]]:
    theme_match = re.fullmatch(r"T(\d+)", theme_id)
    if theme_match is None:
        raise ValueError(f"无效 Theme ID：{theme_id}")
    theme_offset = int(theme_match.group(1)) - 1

    if not available_light_sources:
        raise ValueError("Frame visual plan 至少需要一个可用光源")
    plan: dict[str, dict[str, str]] = {}
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
        strategy_index = (theme_offset + frame_index - 1) % len(
            _SHOT_STRATEGIES
        )
        focus = _VARIATION_FOCI[focus_index]
        if cycle > 1:
            focus = (
                f"第 {cycle} 轮变化；{focus}"
                "不得复用前一轮同类焦点的机位、构图或人物调度。"
            )
        depth_mode, depth_effect = _DEPTH_STRATEGIES[strategy_index]
        plan[frame_id] = {
            "focus": focus,
            "shot_strategy": _SHOT_STRATEGIES[strategy_index],
            "view_strategy": _VIEW_STRATEGIES[strategy_index],
            "depth_mode": depth_mode,
            "depth_effect": depth_effect,
            "light_source": available_light_sources[
                (theme_offset + frame_index - 1)
                % len(available_light_sources)
            ],
            "light_direction": _LIGHT_DIRECTIONS[strategy_index],
            "color_treatment": _COLOR_TREATMENTS[strategy_index],
        }
    return plan
