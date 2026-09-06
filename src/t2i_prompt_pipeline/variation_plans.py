"""Deterministic visual coverage plans for Theme and Frame generation."""

from __future__ import annotations

import re

from t2i_prompt_pipeline.models import FrameMode

_VARIATION_BLOCK_SIZE = 10

_VARIATION_FOCI = (
    "空间关系：使用全景或中全景，突出环境几何、人物与视觉锚点的空间关系。",
    "人物互动：使用中景或近景，呈现人物对 brief 核心物体的当前动作；"
    "全部人物以躯干或身体主体入画，工具仅取自 brief 或 Theme。",
    "锚点细节：用中景呈现核心动作和已有工具；"
    "全部人物以躯干或身体主体入画，不用局部肢体代替人物。",
    "非常规机位：采用明显高机位、低机位、俯视或仰视，突出锚点与人物的尺度关系。",
    "间接构图：使用前景遮挡、倒影、框中框或负空间呈现视觉锚点与人物。",
    "对称关系：以场景轴线组织人物与锚点，保留全部人物的清晰身份。",
    "纵深层次：利用前中后景分配人物，核心互动保持无遮挡。",
    "轮廓关系：以人物整体轮廓和负空间突出动作，不省略核心道具。",
    "斜向动势：用对角线组织人物、环境结构与核心动作。",
    "局部框景：仅用 Theme 已有门洞、构件或前景形成框景，全部人物主体仍入画。",
)

_APPEARANCE_FOCI = (
    "发型长度与轮廓",
    "发型质地与颜色",
    "面部稳定特征",
    "整洁或凌乱的造型方向",
    "头发束扎、编发或自然垂落方式",
    "额发、鬓发与面部轮廓关系",
    "发髻、盘发或顶部体积",
    "发尾长度与运动方向",
    "头部装饰与发型结合方式",
    "发型左右对称或偏侧结构",
)
_WARDROBE_FOCI = (
    "收束轮廓",
    "宽松分层轮廓",
    "垂坠轮廓",
    "礼仪性层叠结构",
    "简洁直线轮廓",
    "上下装比例对比",
    "长短层次对比",
    "宽窄轮廓对比",
    "披挂或外层覆盖结构",
    "适合动作的简洁轮廓",
)
_FOOTWEAR_FOCI = (
    "靴类",
    "符合时代的礼仪鞋履",
    "平底鞋履",
    "符合时代的实用鞋履",
    "低存在感鞋履",
    "包覆脚踝的鞋履",
    "低帮鞋履",
    "软底鞋履",
    "具有装饰性鞋面的鞋履",
    "与服装同色系的鞋履",
)
_ACCESSORY_FOCI = (
    "以服装结构为主，未要求时不另加配饰",
    "一件细小金属配饰",
    "一件醒目配饰",
    "腰间或腕部配饰",
    "耳部或颈部配饰",
    "头部或发间配饰",
    "腰间悬挂配饰",
    "手部或指间配饰",
    "织物类披挂配饰",
    "与服装同色系的小型配饰",
)
_SPATIAL_STRUCTURES = (
    "开放式中央焦点，背景沿周边展开",
    "轴向纵深，前中后景连续",
    "分层平台或高差形成上下层",
    "半围合区域与开口形成框景",
    "环形或周边结构包围核心区域",
    "对角通路贯穿核心区域",
    "连续门洞或开口形成多重框景",
    "左右分区以中央通道连接",
    "多个小型区域围绕主空间分布",
    "前景入口向开阔后景展开",
)
_MATERIAL_DIRECTIONS = (
    "木材与织物为主",
    "石材与深色金属为主",
    "灰泥与天然颜料为主",
    "石材与暖色金属为主",
    "陶瓷与哑光木材为主",
    "砖材与原木为主",
    "夯土或灰泥与织物为主",
    "雕刻石材与编织材料为主",
    "深色木材与编织纤维为主",
    "漆面木材与竹材为主",
)
_POPULATION_LAYOUTS = (
    "背景人物稀疏分布并留出负空间",
    "背景人物集中于单一纵深层",
    "背景人物分布于前后两层",
    "背景人物沿空间边缘分布",
    "背景人物围绕核心区域分布",
    "背景人物以数个小群分散分布",
    "背景人物集中于轴线远端",
    "背景人物停留在入口与开口附近",
    "背景人物集中于一侧，另一侧留空",
    "背景人物前疏后密形成纵深",
)
_ATMOSPHERE_DIRECTIONS = (
    "暖色、低反差、疏朗",
    "冷色、高反差、克制",
    "中性色、均匀亮度、开放",
    "冷暖分区、局部暗部、紧张",
    "低照度、轮廓高光、私密",
    "暖色、高亮度、活跃",
    "冷色、低反差、安静",
    "土色、柔和阴影、沉稳",
    "局部高饱和、其余低饱和、醒目",
    "逆光轮廓、前景暗部、朦胧",
)
_LIGHT_SOURCE_DIRECTIONS = (
    "侧向现场光为主",
    "顶部现场光为主",
    "侧后方轮廓光源为主",
    "前后两种现场光共同作用",
    "低位或近地现场光为主",
    "前侧现场光为主",
    "斜上方现场光为主",
    "后方高位现场光为主",
    "大面积漫射现场光为主",
    "两侧不同方位的现场光共同作用",
)
_PALETTE_STRATEGIES = (
    "同类色，以明度区分人物与环境",
    "邻近色，人物与环境保持连续过渡",
    "冷暖对比，人物服装与环境采用相反色相倾向",
    "中性色环境配一个人物强调色",
    "低饱和环境配较高饱和人物",
    "深色环境配浅色人物",
    "浅色环境配深色人物",
    "自然土色体系，以材质区分层次",
    "单一主色相，以明暗和材质区分",
    "克制互补色，强调色只用于人物",
)
_WARDROBE_MATERIAL_FOCI = (
    "哑光细织材质",
    "平滑微光材质",
    "可见粗织纹理",
    "柔软垂坠材质",
    "挺括结构材质",
    "轻量层叠材质",
    "压纹或提花材质",
    "编织或绳结纹理",
    "主体织物配少量硬质细节",
    "两种同色不同质感材质",
)
_COLOR_ROLES = (
    "主色人物",
    "辅色人物",
    "强调色人物",
    "中性色人物",
    "最亮人物",
    "最暗人物",
    "暖色服装人物",
    "冷色服装人物",
    "低饱和人物",
    "环境过渡色人物",
)

_LENS_PROFILES = (
    "wide",
    "normal",
    "telephoto",
    "fisheye",
    "ultra_wide",
    "normal",
    "telephoto",
    "wide",
    "ultra_wide",
    "normal",
)
_SEQUENTIAL_LENS_PROFILES = (
    "wide",
    "normal",
    "telephoto",
    "normal",
    "ultra_wide",
    "normal",
    "telephoto",
    "wide",
    "normal",
    "normal",
)
_SHOT_SCALES = (
    "establishing",
    "medium",
    "medium_full",
    "full_body",
    "wide",
    "full_body",
    "medium",
    "medium_full",
    "establishing",
    "wide",
)
_CAMERA_HEIGHTS = (
    "eye_level",
    "high_angle",
    "low_angle",
    "overhead",
    "eye_level",
    "low_angle",
    "high_angle",
    "eye_level",
    "high_angle",
    "low_angle",
)
_CAMERA_DIRECTIONS = (
    "front",
    "three_quarter",
    "side",
    "top_down",
    "rear_three_quarter",
    "three_quarter",
    "front",
    "side",
    "rear_three_quarter",
    "front",
)
_DEPTH_STRATEGIES = (
    ("deep", "环境与全部人物保持清晰"),
    ("moderate", "核心人物清晰，背景轻微渐虚"),
    ("moderate", "互动接触点清晰，前后层次分离"),
    ("shallow", "仅当全部核心人物处于同一焦平面时使用"),
    ("deep", "前景、人物与环境结构均可辨"),
    ("moderate", "全部人物清晰，远背景柔和渐虚"),
    ("shallow", "全部核心人物同平面清晰，背景形成散景"),
    ("deep", "纵深各层人物与关键环境均清晰"),
    ("moderate", "前景框景轻微虚化，核心人物清晰"),
    ("deep", "核心动作、人物轮廓与背景锚点均可辨"),
)
_LIGHT_DIRECTIONS = (
    "沿所选光源实际方位照射，主体形成明确明暗分区",
    "沿所选光源实际方位照射，强调人物与地面投影",
    "沿所选光源实际方位照射，勾勒人物轮廓",
    "沿所选光源实际方位照射，主体受光面保留细节",
    "沿所选光源实际方位照射，前景较亮、背景转暗",
    "沿所选光源实际方位照射，背景较亮、主体保留轮廓",
    "沿所选光源实际方位照射，强调面部与上身层次",
    "沿所选光源实际方位照射，强调服装褶皱与材质",
    "沿所选光源实际方位照射，形成由近至远的明暗梯度",
    "沿所选光源实际方位照射，保留暗部细节并控制高光",
)
_COLOR_TREATMENTS = (
    "使用所选光源本色",
    "所选光源本色经现场表面形成弱中性反射",
    "受光面保留所选光源本色，阴影降低饱和度",
    "人物保留所选光源本色，背景降低同色饱和度",
    "保持所选光源的单一主色温，减少杂色",
    "背景保留所选光源本色，人物暗部趋于中性",
    "所选光色集中于人物上身，环境降低饱和度",
    "所选光色突出服装材质，肤色保持自然",
    "由近至远降低所选光色的饱和度",
    "压低所选光色高光，暗部保持同一色温",
)
_GROUP_TOPOLOGIES = (
    "主体居中，其余人物沿两侧错位展开",
    "人物沿横向排列但前后略有错位",
    "人物沿纵深轴线依次分布",
    "人物形成稳定三角关系，人数不足时保留对角关系",
    "人物沿对角线分布",
    "核心人物在前，其余人物在后方呼应",
    "核心人物在后，其余人物在前景形成框景",
    "人物围绕核心接触点形成弧形关系",
    "人物利用场景高差形成上下层",
    "人物分组后由视线、接触或共同施力连接",
)
_SINGLE_SUBJECT_TOPOLOGIES = (
    "主体居中，环境沿两侧展开",
    "主体位于左侧三分线，右侧保留环境",
    "主体位于右侧三分线，左侧保留环境",
    "主体位于前景中央，背景建立空间",
    "主体位于中景，前景保留负空间",
    "主体位于后景，由前景构件形成框景",
    "主体偏离中心，与环境锚点形成对角关系",
    "主体位于场景轴线上，形成稳定对称关系",
    "主体利用场景高差与背景形成上下关系",
    "主体靠近核心物体，环境留出动作方向空间",
)
_DEPTH_DISTRIBUTIONS = (
    "核心人物位于中景，前后保留环境层次",
    "全部人物处于同一清晰焦平面",
    "一名核心人物在前景，其余人物位于中景",
    "核心人物在中景，其余人物分布于前后层",
    "人物由近至远错位排列，身份均可辨",
    "前景只作框景，全部人物位于中后景",
    "人物集中于前中景，背景留出清晰空间",
    "人物集中于中后景，前景保留负空间",
    "互动人物同层，其余人物退后一层",
    "人物跨两个深度层分组，核心接触点保持清晰",
)
_SINGLE_SUBJECT_DEPTHS = (
    "主体位于中景，前后保留环境层次",
    "主体与核心物体处于同一清晰焦平面",
    "主体位于前景，环境退至中后景",
    "主体位于中景，前景与后景形成两层",
    "主体与环境锚点由近至远错位排列",
    "前景只作框景，主体位于中后景",
    "主体位于前中景，背景保留清晰空间",
    "主体位于中后景，前景保留负空间",
    "主体与互动对象同层，环境退后一层",
    "主体跨越两个深度层的交界，动作点保持清晰",
)
_BODY_DYNAMICS = (
    "重心稳定，躯干保持直立",
    "重心前移，躯干形成前倾斜线",
    "重心后移，胸腹与腿部形成反向平衡",
    "单腿或单侧承重，另一侧自然延伸",
    "躯干扭转，肩线与胯线方向不同",
    "重心降低，以膝髋屈曲形成相容的低位姿态",
    "身体向上延展，四肢形成纵向动势",
    "转身中的瞬间，服饰与发尾顺应运动方向",
    "稳定支撑与运动肢体形成动静对比",
    "全身重心朝向核心接触点聚合",
)


def _axis_index(
    offset: int,
    *,
    stride: int,
    cycle_shift: int,
    super_shift: int = 0,
    size: int,
) -> int:
    """Rotate axes across ten-, hundred-, and thousand-item cycles."""
    block_index = offset % _VARIATION_BLOCK_SIZE
    cycle = (offset // _VARIATION_BLOCK_SIZE) % _VARIATION_BLOCK_SIZE
    super_cycle = offset // (_VARIATION_BLOCK_SIZE**2)
    return (
        block_index * stride
        + cycle * cycle_shift
        + super_cycle * super_shift
    ) % size


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
                    _axis_index(
                        theme_offset,
                        stride=1,
                        cycle_shift=1,
                        size=len(_SPATIAL_STRUCTURES),
                    )
                ],
                "material_direction": _MATERIAL_DIRECTIONS[
                    _axis_index(
                        theme_offset,
                        stride=3,
                        cycle_shift=2,
                        size=len(_MATERIAL_DIRECTIONS),
                    )
                ],
                "population_layout": _POPULATION_LAYOUTS[
                    _axis_index(
                        theme_offset,
                        stride=7,
                        cycle_shift=3,
                        size=len(_POPULATION_LAYOUTS),
                    )
                ],
                "atmosphere_direction": _ATMOSPHERE_DIRECTIONS[
                    _axis_index(
                        theme_offset,
                        stride=9,
                        cycle_shift=7,
                        size=len(_ATMOSPHERE_DIRECTIONS),
                    )
                ],
                "light_source_direction": _LIGHT_SOURCE_DIRECTIONS[
                    _axis_index(
                        theme_offset,
                        stride=1,
                        cycle_shift=9,
                        size=len(_LIGHT_SOURCE_DIRECTIONS),
                    )
                ],
                "palette_strategy": _PALETTE_STRATEGIES[
                    _axis_index(
                        theme_offset,
                        stride=7,
                        cycle_shift=4,
                        size=len(_PALETTE_STRATEGIES),
                    )
                ],
            },
            "character_variations": {
                f"{theme_id}-C{index:02d}": {
                    "appearance_focus": _APPEARANCE_FOCI[
                        _axis_index(
                            theme_offset * character_count + index - 1,
                            stride=1,
                            cycle_shift=3,
                            size=len(_APPEARANCE_FOCI),
                        )
                    ],
                    "wardrobe_silhouette": _WARDROBE_FOCI[
                        _axis_index(
                            theme_offset * character_count + index - 1,
                            stride=3,
                            cycle_shift=8,
                            size=len(_WARDROBE_FOCI),
                        )
                    ],
                    "footwear": _FOOTWEAR_FOCI[
                        _axis_index(
                            theme_offset * character_count + index - 1,
                            stride=7,
                            cycle_shift=9,
                            super_shift=1,
                            size=len(_FOOTWEAR_FOCI),
                        )
                    ],
                    "accessory_strategy": _ACCESSORY_FOCI[
                        _axis_index(
                            theme_offset * character_count + index - 1,
                            stride=9,
                            cycle_shift=1,
                            super_shift=3,
                            size=len(_ACCESSORY_FOCI),
                        )
                    ],
                    "wardrobe_color_role": _COLOR_ROLES[
                        0
                        if character_count == 1
                        else (theme_offset + index - 1) % character_count
                    ],
                    "wardrobe_material_focus": _WARDROBE_MATERIAL_FOCI[
                        _axis_index(
                            theme_offset * character_count + index - 1,
                            stride=3,
                            cycle_shift=4,
                            super_shift=7,
                            size=len(_WARDROBE_MATERIAL_FOCI),
                        )
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
    character_count: int,
    frame_mode: FrameMode,
) -> dict[str, dict[str, str]]:
    theme_match = re.fullmatch(r"T(\d+)", theme_id)
    if theme_match is None:
        raise ValueError(f"无效 Theme ID：{theme_id}")
    theme_offset = int(theme_match.group(1)) - 1

    if not available_light_sources:
        raise ValueError("Frame visual plan 至少需要一个可用光源")
    if character_count < 1:
        raise ValueError("Frame visual plan 至少需要一个人物")
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
        visual_offset = theme_offset + frame_index - 1
        lens_profiles = (
            _LENS_PROFILES
            if frame_mode == FrameMode.VARIATIONS
            else _SEQUENTIAL_LENS_PROFILES
        )
        lens_index = _axis_index(
            visual_offset,
            stride=1,
            cycle_shift=3,
            size=len(lens_profiles),
        )
        staging_index = _axis_index(
            visual_offset,
            stride=1,
            cycle_shift=7,
            size=len(_SHOT_SCALES),
        )
        depth_index = _axis_index(
            visual_offset,
            stride=1,
            cycle_shift=8,
            size=len(_DEPTH_STRATEGIES),
        )
        light_index = _axis_index(
            visual_offset,
            stride=1,
            cycle_shift=1,
            size=len(_LIGHT_DIRECTIONS),
        )
        topology_index = _axis_index(
            visual_offset,
            stride=3,
            cycle_shift=2,
            size=len(_GROUP_TOPOLOGIES),
        )
        distribution_index = _axis_index(
            visual_offset,
            stride=7,
            cycle_shift=4,
            size=len(_DEPTH_DISTRIBUTIONS),
        )
        dynamics_index = _axis_index(
            visual_offset,
            stride=9,
            cycle_shift=6,
            size=len(_BODY_DYNAMICS),
        )
        focus = _VARIATION_FOCI[focus_index]
        if cycle > 1:
            focus = (
                f"第 {cycle} 轮变化；{focus}"
                "不得复用前一轮同类焦点的机位、构图或人物调度。"
            )
        depth_mode, depth_effect = _DEPTH_STRATEGIES[depth_index]
        plan[frame_id] = {
            "focus": focus,
            "lens_profile": lens_profiles[lens_index],
            "shot_scale": _SHOT_SCALES[staging_index],
            "camera_height": _CAMERA_HEIGHTS[staging_index],
            "camera_direction": _CAMERA_DIRECTIONS[staging_index],
            "group_topology": (
                _SINGLE_SUBJECT_TOPOLOGIES[topology_index]
                if character_count == 1
                else _GROUP_TOPOLOGIES[topology_index]
            ),
            "depth_distribution": (
                _SINGLE_SUBJECT_DEPTHS[distribution_index]
                if character_count == 1
                else _DEPTH_DISTRIBUTIONS[distribution_index]
            ),
            "body_dynamics": _BODY_DYNAMICS[dynamics_index],
            "depth_mode": depth_mode,
            "depth_effect": depth_effect,
            "light_source": available_light_sources[
                (theme_offset + frame_index - 1)
                % len(available_light_sources)
            ],
            "light_direction": _LIGHT_DIRECTIONS[light_index],
            "color_treatment": _COLOR_TREATMENTS[light_index],
        }
    return plan
