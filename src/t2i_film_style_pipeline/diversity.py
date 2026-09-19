"""Deterministic diversity planning and local run diagnostics."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from itertools import combinations

from pydantic import BaseModel, ConfigDict, Field

from t2i_film_style_pipeline.content_validation import (
    contains_clothing_state_conflict,
    content_level_evidence_complete,
)
from t2i_film_style_pipeline.frame_text import (
    anchor_insertion,
    canonical_anchor_sentence,
    frame_body,
)
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    FilmPromptResult,
    NarrativeTheme,
)

_NOVELTY_AXES = (
    "优先使用账本中较少出现的原作作品、场景或人物组合",
    "改变稳定的人物关系与权力张力，但不固定 Frame 动作发起者",
    "选择账本中较少出现的内容路径或互动范围",
    "改变场景内部的空间层次、人物距离和调度范围",
    "改变主要景别、机位方向、透视和焦点层级的组合",
    "改变主光来源、明暗关系、色彩重音和材质重点",
    "改变当前事件、环境状态或关键器物在画面中的作用",
    "改变前景框景、遮挡方式、空气状态和成片运动倾向",
)
_CONTENT_ROUTES = {
    ContentLevel.AESTHETIC: (
        "克制身体造型与空间关系",
        "服装轮廓与材质触觉",
        "回应式视线与轻度接触",
        "环境压力与人物距离",
    ),
    ContentLevel.EROTIC: (
        "全裸或半裸的非生殖器贴合",
        "亲吻与肩颈胸背接触",
        "解衣、更衣或湿润材质触觉",
        "松散情趣造型但不形成器具控制链",
        "按摩、跨坐或肢体交叠",
    ),
    ContentLevel.HARDCORE: (
        "明确性行为",
        "器具形成的无插入 BDSM 控制链",
        "命令式开放展示",
        "外部器具或受控自我刺激",
    ),
}
_RELATIONSHIP_DYNAMICS = (
    "所有参与者双向协商，具体 Frame 自行组织动作关系",
    "权力张力突出，但不预先固定动作发起者",
    "参与角色可在不同 Frame 之间变化",
    "参与者之间形成竞争与镜像回应",
    "每个人直接参与共同互动，Frame 自行组织关系网络",
)
_SPATIAL_STRATEGIES = (
    "前中后景分层与纵深调度",
    "门窗或帷幕形成前景框景",
    "横向并置与留白",
    "对角线调度与不对称重心",
    "镜面或屏风形成双层空间但不复制肢体",
    "家具支撑与高低层次",
    "封闭近距离空间与背景压缩",
)
_CAMERA_STRATEGIES = (
    "全景或较宽中景，强调完整空间关系",
    "中景，强调人物调度与身体拓扑",
    "中近景，兼顾表情与核心互动",
    "侧前方机位与自然透视",
    "侧后方机位与前景遮挡",
    "高机位但保持身体连接可读",
    "低机位但避免夸张肢体比例",
)
_LIGHTING_STRATEGIES = (
    "窗光与室内灯火形成冷暖对比",
    "烛光或油灯形成局部暖光",
    "月光或阴天天光形成低反差冷调",
    "侧光强调皮肤、织物与空间深度",
    "逆光勾边并保留面部补光",
    "顶光与深阴影组织权力关系",
)
_FRAME_CONTENT_ROUTES = {
    ContentLevel.AESTHETIC: (
        {
            "route": "克制身体造型与空间关系",
            "required_visible_evidence": (
                "较大面积皮肤或贴身轮廓",
                "稳定姿态与身体明暗塑形",
                "具体表情与视线落点",
                "非性化接触或明确人物距离",
            ),
        },
        {
            "route": "服装轮廓与材质触觉",
            "required_visible_evidence": (
                "较大面积皮肤或贴身服装轮廓",
                "皮肤或织物的可见受力",
                "强化身体曲线的明暗塑形",
                "具体表情、视线和空间支撑",
            ),
        },
        {
            "route": "回应式视线与轻度接触",
            "required_visible_evidence": (
                "较大面积皮肤或贴身轮廓",
                "双方具体视线落点与可见回应",
                "单一非性化接触链",
                "身体姿态张力与明暗塑形",
            ),
        },
        {
            "route": "环境压力与人物距离",
            "required_visible_evidence": (
                "较大面积皮肤或贴身轮廓",
                "明确人物距离与环境边界",
                "身体姿态张力或回应式接触",
                "环境光对身体曲线的明暗塑形",
            ),
        },
    ),
    ContentLevel.EROTIC: (
        {
            "route": "全裸或半裸的非生殖器贴合",
            "required_visible_evidence": (
                "非生殖器接触点",
                "双方稳定支撑",
                "具体欲望表情与主动回应",
            ),
        },
        {
            "route": "亲吻与肩颈胸背接触",
            "required_visible_evidence": (
                "具体亲吻或触碰部位",
                "皮肤与材质反应",
                "双方具体表情与视线",
            ),
        },
        {
            "route": "解衣、更衣或湿润材质触觉",
            "required_visible_evidence": (
                "唯一衣物状态",
                "具体手部职责",
                "非生殖器接触与双方主动回应",
                "皮肤、汗意、水汽或受压材质的强烈感官证据",
            ),
        },
        {
            "route": "松散情趣造型但不形成器具控制链",
            "required_visible_evidence": (
                "有场景来源且保持松弛或快速释放的造型器具",
                "器具无人牵引且不固定开放姿态",
                "双方独立支撑、欲望表情和主动回应",
                "明显裸露、紧密非生殖器接触或受压材质",
            ),
        },
        {
            "route": "按摩、跨坐或肢体交叠",
            "required_visible_evidence": (
                "按摩、跨坐或肢体交叠中的一种单一核心互动",
                "明确的非生殖器接触部位",
                "双方独立支撑、欲望表情和主动回应",
                "明显裸露与皮肤或织物受压细节",
            ),
        },
    ),
    ContentLevel.HARDCORE: (
        {
            "route": "明确性行为",
            "required_visible_evidence": (
                "具体行为与动作主客体",
                "性器官与接触方式",
                "稳定支撑与具体欲望表情",
            ),
        },
        {
            "route": "器具形成的无插入 BDSM 控制链",
            "required_visible_evidence": (
                "具体器具及其两端连接",
                "控制者动作与受力方向",
                "受方开放姿态、独立支撑、欲望表情和主动回应",
            ),
        },
        {
            "route": "命令式开放展示",
            "required_visible_evidence": (
                "可见指令来源",
                "受方主动维持的开放姿态与独立支撑",
                "直接暴露的性部位、欲望表情和主动展示",
            ),
        },
        {
            "route": "外部器具或受控自我刺激",
            "required_visible_evidence": (
                "器具或手部的明确来源与目标",
                "单一直接刺激方式",
                "动作主客体、稳定支撑和主动愉悦回应",
            ),
        },
    ),
}
_FRAME_LEVEL_EVIDENCE = {
    ContentLevel.AESTHETIC: (
        "较大面积皮肤或贴身轮廓",
        "具有张力的身体姿态",
        "回应式视线、轻度接触或可感知材质中的至少两项",
        "强化身体曲线的明暗塑形",
    ),
    ContentLevel.EROTIC: (
        (
            "衣物终态必须二选一：双臂完整穿袖且上衣只从前方完全"
            "敞开；或完全赤裸且脱下衣物与身体分离。衣袖、衣襟和"
            "肩带不得滑落、褪至或堆在肩部与手臂"
        ),
        "当前真实发生的紧密非生殖器接触",
        (
            "以至少两项面部状态落实并明确写成欲望或愉悦的表情；"
            "接纳、放松或专注不能替代欲望或愉悦"
        ),
        "汗意、水汽、受压皮肤或材质形成的触觉细节",
    ),
    ContentLevel.HARDCORE: (),
}
_COVERAGE_TERMS = {
    "content_route": {
        "明确性行为": (
            "插入",
            "口交",
            "性交",
            "自慰",
            "性器官接触",
            "penetration",
            "oral sex",
        ),
        "器具 BDSM": (
            "项圈",
            "牵引链",
            "腕带",
            "踝带",
            "手铐",
            "绳索",
            "collar",
            "leash",
            "restraint",
        ),
        "命令式展示": (
            "命令式",
            "开放展示",
            "展示指令",
            "张开双腿",
            "commanded display",
        ),
        "非生殖器亲密": (
            "亲吻",
            "拥抱",
            "肩颈",
            "胸背",
            "非生殖器",
            "kiss",
            "embrace",
        ),
    },
    "spatial_strategy": {
        "纵深分层": ("前景", "中景层", "后景", "纵深", "deep staging"),
        "框景": ("门框", "窗框", "帷幕", "屏风", "frame within"),
        "横向并置": ("横向", "并置", "留白", "lateral"),
        "对角线": ("对角线", "斜向", "diagonal"),
        "镜面空间": ("镜面", "镜中", "倒影", "mirror"),
        "家具层次": ("榻", "桌沿", "座椅", "软凳", "furniture"),
    },
    "camera_strategy": {
        "全景": ("全景", "远景", "wide shot", "long shot"),
        "中景": ("中景", "medium shot"),
        "中近景": ("中近景", "medium close"),
        "近景": ("近景", "特写", "close-up"),
        "高机位": ("高机位", "俯拍", "high angle"),
        "低机位": ("低机位", "仰拍", "low angle"),
        "侧向机位": ("侧前方", "侧后方", "侧面机位", "side angle"),
    },
    "lighting_strategy": {
        "烛光灯火": ("烛光", "油灯", "灯笼", "灯火", "candle", "lantern"),
        "窗光": ("窗光", "窗外天光", "window light"),
        "月光": ("月光", "moonlight"),
        "侧光": ("侧光", "side light"),
        "逆光": ("逆光", "backlight"),
        "顶光": ("顶光", "top light"),
    },
}
_FRAME_COVERAGE_TERMS = {
    "posture": {
        "站立": ("站立", "站姿", "站着", "standing"),
        "坐姿": ("坐姿", "坐在", "端坐", "seated"),
        "跪姿": ("跪姿", "跪地", "跪在", "kneeling"),
        "蹲姿": ("蹲姿", "蹲伏", "半蹲", "squatting"),
        "仰卧": ("仰卧", "平躺", "supine"),
        "俯卧": ("俯卧", "趴伏", "prone"),
        "侧卧": ("侧卧", "侧躺", "side-lying"),
    },
    "shot_scale": {
        "远景": ("远景", "long shot"),
        "全景": ("全景", "wide shot"),
        "中景": ("中景", "medium shot"),
        "中近景": ("中近景", "medium close"),
        "近景": ("近景", "close shot"),
        "特写": ("特写", "close-up"),
    },
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SimilarityMetrics(_Model):
    item_count: int = Field(ge=0)
    pair_count: int = Field(ge=0)
    mean_pair_similarity: float = Field(ge=0, le=1)
    mean_nearest_similarity: float = Field(ge=0, le=1)
    maximum_similarity: float = Field(ge=0, le=1)
    pairs_at_or_above_0_70: int = Field(ge=0)
    pairs_at_or_above_0_80: int = Field(ge=0)


class FilmPromptDiversityReport(_Model):
    theme_count: int = Field(ge=0)
    frame_count: int = Field(ge=0)
    unique_theme_titles: int = Field(ge=0)
    exact_duplicate_theme_texts: int = Field(ge=0)
    exact_duplicate_frame_texts: int = Field(ge=0)
    content_evidence_complete_frames: int = Field(ge=0)
    content_evidence_incomplete_frames: int = Field(ge=0)
    anchor_complete_frames: int = Field(ge=0)
    anchor_missing_required_frames: int = Field(ge=0)
    anchor_forbidden_term_frames: int = Field(ge=0)
    character_anchor_complete_frames: int = Field(ge=0)
    scene_anchor_complete_frames: int = Field(ge=0)
    participant_description_complete_slots: int = Field(ge=0)
    participant_face_complete_slots: int = Field(ge=0)
    participant_gaze_complete_slots: int = Field(ge=0)
    participant_support_complete_slots: int = Field(ge=0)
    participant_slot_count: int = Field(ge=0)
    clothing_state_conflict_frames: int = Field(ge=0)
    theme_similarity: SimilarityMetrics
    frame_similarity: SimilarityMetrics
    same_theme_frame_similarity: SimilarityMetrics
    theme_coverage: dict[str, dict[str, int]]
    frame_coverage: dict[str, dict[str, int]]


def theme_diversity_ledger(
    request: FilmPromptRequest,
    existing_themes: list[NarrativeTheme],
) -> dict[str, object]:
    return {
        "used_titles": [theme.title for theme in existing_themes],
        "used_theme_signatures": [
            {
                "theme_id": theme.theme_id,
                "premise_excerpt": _excerpt(theme.premise, limit=180),
                "style_excerpt": _excerpt(theme.style, limit=140),
            }
            for theme in existing_themes
        ],
        "coverage_counts": _coverage_counts(
            (
                " ".join((theme.title, theme.premise, theme.style))
                for theme in existing_themes
            ),
            _COVERAGE_TERMS,
        ),
        "source_anchor_mentions": _anchor_usage(
            request,
            existing_themes,
        ),
    }


def current_theme_diversity_contracts(
    request: FilmPromptRequest,
    *,
    start_index: int,
    count: int,
) -> list[dict[str, object]]:
    digest = hashlib.sha256(
        f"{request.content_level.value}\n{request.context}".encode()
    ).digest()
    axes = (
        (
            "content_route_emphasis",
            _CONTENT_ROUTES[request.content_level],
            1,
        ),
        ("relationship_dynamic", _RELATIONSHIP_DYNAMICS, 2),
        ("spatial_strategy", _SPATIAL_STRATEGIES, 3),
        ("camera_strategy", _CAMERA_STRATEGIES, 4),
        ("lighting_strategy", _LIGHTING_STRATEGIES, 5),
    )
    contracts = []
    for offset in range(count):
        absolute_index = start_index + offset - 1
        contract: dict[str, object] = {"output_position": offset + 1}
        if request.female_count is not None or request.male_count is not None:
            contract["cast_size_requirement"] = {
                "female_count": request.female_count,
                "male_count": request.male_count,
                "mode": (
                    "非 null 的性别人数必须严格采用；null 的性别人数"
                    "由当前 Theme 决定"
                ),
            }
        elif request.content_level == ContentLevel.AESTHETIC:
            contract["cast_size_requirement"] = "选择一至两名原作成年人"
        else:
            contract["cast_size_requirement"] = "恰好选择两名原作成年人"
        for name, values, digest_index in axes:
            contract[name] = values[
                (absolute_index + digest[digest_index]) % len(values)
            ]
        first_axis = absolute_index % len(_NOVELTY_AXES)
        second_axis = (absolute_index * 3 + 1) % len(_NOVELTY_AXES)
        if second_axis == first_axis:
            second_axis = (second_axis + 1) % len(_NOVELTY_AXES)
        contract["novelty_priorities"] = [
            _NOVELTY_AXES[first_axis],
            _NOVELTY_AXES[second_axis],
        ]
        contracts.append(contract)
    return contracts


def theme_anchor_contract(
    request: FilmPromptRequest,
    theme: NarrativeTheme,
) -> dict[str, object]:
    anchor_groups = _source_anchor_groups(request)
    anchors = tuple(
        anchor
        for group in anchor_groups
        for anchor in (*group["characters"], *group["scenes"])
    )
    selected_characters = [item.canonical_name for item in theme.selected_cast]
    selected_scenes = [
        anchor
        for anchor in anchor_groups[theme.source_work_index]["scenes"]
        if _scene_anchor_mentioned(anchor, theme.premise)
    ]
    required = [*selected_characters, *selected_scenes]
    forbidden = [anchor for anchor in anchors if anchor not in required]
    scene = selected_scenes[0] if len(selected_scenes) == 1 else None
    anchor_sentence = canonical_anchor_sentence(
        request,
        selected_characters,
        scene,
    )
    return {
        "source_work_index": theme.source_work_index,
        "selected_cast": [item.model_dump(mode="json") for item in theme.selected_cast],
        "required_characters": selected_characters,
        "required_scene": scene,
        "required_exact_terms": required,
        "forbidden_other_anchor_terms_in_body": forbidden,
        "deterministic_anchor_sentence": anchor_sentence,
    }


def normalize_theme_anchor_terms(
    request: FilmPromptRequest,
    theme: NarrativeTheme,
) -> NarrativeTheme:
    contract = theme_anchor_contract(request, theme)
    scene = contract["required_scene"]
    if scene is None or scene in theme.premise:
        return theme
    sentence = (
        f'The canonical setting is "{scene}".'
        if request.output_language.value == "english"
        else f"原作场景为“{scene}”。"
    )
    return theme.model_copy(
        update={"premise": f"{theme.premise.rstrip()}{sentence}"}
    )


def normalize_frame_anchor_prefix(
    request: FilmPromptRequest,
    theme: NarrativeTheme,
    prose: str,
) -> str:
    contract = theme_anchor_contract(request, theme)
    anchor_sentence = contract["deterministic_anchor_sentence"]
    if not anchor_sentence:
        return prose
    source = request.frame_source_sentence
    if not prose.startswith(source):
        return prose
    insertion = anchor_insertion(request, str(anchor_sentence))
    body = prose[len(source):]
    if body.startswith(insertion):
        return prose
    return source + insertion + body


def participant_frame_contracts(
    request: FilmPromptRequest,
    theme: NarrativeTheme,
    requested_frame_ids: list[str],
) -> dict[str, object]:
    anchor_contract = theme_anchor_contract(request, theme)
    characters = list(anchor_contract["required_characters"])
    participant_contracts = [
        {
            "canonical_name": character,
            "description_requirement": (
                "以 canonical_name 开始一段连续人物描述，明确成年身份、"
                "唯一衣物状态、姿态与独立支撑、至少两项面部状态、"
                "唯一视线落点，以及每条可见肢体的唯一职责"
            ),
        }
        for character in characters
    ]
    group_contracts = []
    route_name = str(
        current_theme_diversity_contracts(
            request,
            start_index=int(theme.theme_id[1:]),
            count=1,
        )[0]["content_route_emphasis"]
    )
    for frame_id in requested_frame_ids:
        if len(characters) >= 3:
            contract: dict[str, object] = {
                "frame_slot": frame_id,
                "participant_count": len(characters),
                "requested_cast_counts": {
                    "female_count": request.female_count,
                    "male_count": request.male_count,
                },
                "required_active_participants": characters,
                "participation_requirement": (
                    "required_active_participants 中每个人都必须通过具体可见"
                    "动作直接参与同一个共同互动事件，不得设置旁观者、外围"
                    "回应者、装饰人物或无动作人物"
                ),
                "interaction_topology_requirement": (
                    "模型根据输入男女数量、人物身体条件、场景与当前内容路径"
                    "自行设计互动拓扑；程序不预设核心二人组、角色类别、配对"
                    "数量、接触顺序或空间站位。每个人都必须成为至少一条可见"
                    "动作或接触链的明确端点，并写清动作主客体"
                ),
                "topology_safety_requirement": (
                    "无论模型选择何种互动结构，都要逐人闭合支撑、四肢职责"
                    "与接触路径；只删除无助于共同互动的多余动作，不得把"
                    "任何人物降级为观察者"
                ),
                "spatial_requirement": (
                    f"为 {len(characters)} 人自行选择互不矛盾且可读的空间位置，"
                    "确保每个人的面孔、主要身体轮廓、支撑面和参与动作可见"
                ),
                "camera_requirement": (
                    f"按 {len(characters)} 人群像选择能够容纳全部人物、支撑面"
                    "和参与动作的景别与机位；不得因为使用近景而漏掉任何人物"
                ),
            }
            if request.content_level == ContentLevel.HARDCORE:
                contract["hardcore_group_realization"] = (
                    _hardcore_group_realization(
                        route_name,
                        characters,
                    )
                )
            group_contracts.append(contract)
    return {
        "participants": participant_contracts,
        "requested_cast_counts": {
            "female_count": request.female_count,
            "male_count": request.male_count,
        },
        "selected_participant_count": len(characters),
        "group_frame_contracts": group_contracts,
    }


def _hardcore_group_realization(
    route_name: str,
    characters: list[str],
) -> dict[str, object]:
    return {
        "content_route": route_name,
        "participants": characters,
        "role_design_requirement": (
            "模型根据输入男女数量和当前可见身体拓扑，自行决定每个人在"
            "当前路径中的动作、对象与双向关系；程序不预设发起者、接受者、"
            "控制者、展示者、中心人物或固定配对"
        ),
        "all_participate_requirement": (
            "每个人都必须以直接可见且不可删除的动作参与当前 Hardcore "
            "路径，成为至少一条明确性动作、器具控制、命令展示或直接刺激"
            "链的发起端、接受端或连接端；不得仅仅观察、等待或表情回应"
        ),
        "evidence_requirement": (
            "逐人写明其动作、动作对象或器具、接触部位、受力方向、独立"
            "支撑和主动欲望或愉悦反应；current_frame_diversity_contracts "
            "中的当前路径证据适用于整个多人互动网络"
        ),
        "network_requirement": (
            "所有参与者必须属于同一个可追踪的互动网络；网络可以包含多条"
            "同时成立的动作或接触链，但每条链都必须物理可见、主客体清楚"
            "且不与任何人的支撑和肢体职责冲突"
        ),
        "no_euphemism": (
            "必须直接写出路径证据，不得改成协商、游戏、身体展示、"
            "亲密姿态、即将发生或画外暗示"
        ),
    }


def current_frame_diversity_contracts(
    request: FilmPromptRequest,
    theme: NarrativeTheme,
    requested_frame_ids: list[str],
) -> list[dict[str, object]]:
    routes = _FRAME_CONTENT_ROUTES[request.content_level]
    theme_index = int(theme.theme_id[1:])
    theme_contract = current_theme_diversity_contracts(
        request,
        start_index=theme_index,
        count=1,
    )[0]
    route_name = str(theme_contract["content_route_emphasis"])
    route = next(item for item in routes if item["route"] == route_name)
    contracts = []
    for frame_id in requested_frame_ids:
        contracts.append(
            {
                "frame_slot": frame_id,
                "content_route": route["route"],
                "required_level_evidence": list(
                    _FRAME_LEVEL_EVIDENCE[request.content_level]
                ),
                "required_route_evidence": list(
                    route["required_visible_evidence"]
                ),
                "variation_requirement": (
                    "与同 Theme 其他 Frame 改变姿态类别、核心互动链、"
                    "景别或摄影机方位中的至少三项"
                ),
            }
        )
    return contracts


def build_diversity_report(
    result: FilmPromptResult,
) -> FilmPromptDiversityReport:
    theme_texts = [
        " ".join((item.theme.title, item.theme.premise, item.theme.style))
        for item in result.themes
    ]
    frame_texts = [
        frame.prose
        for item in result.themes
        for frame in item.frames
    ]
    content_evidence_complete = sum(
        content_level_evidence_complete(
            result.request.content_level,
            text,
            result.request.output_language.value,
        )
        for text in frame_texts
    )
    anchor_complete = 0
    anchor_missing = 0
    anchor_forbidden = 0
    character_anchor_complete = 0
    scene_anchor_complete = 0
    participant_description_complete = 0
    participant_face_complete = 0
    participant_gaze_complete = 0
    participant_support_complete = 0
    participant_slot_count = 0
    for item in result.themes:
        contract = theme_anchor_contract(result.request, item.theme)
        for frame in item.frames:
            body = frame_body(
                result.request, item.theme, frame.prose, strip_anchor=False
            )
            narrative_body = frame_body(result.request, item.theme, frame.prose)
            characters = list(contract["required_characters"])
            scene = contract["required_scene"]
            character_anchor_complete += bool(characters) and all(
                term in frame.prose for term in characters
            )
            scene_anchor_complete += scene is not None and scene in frame.prose
            missing = (
                not characters
                or scene is None
                or any(
                    term not in body
                    for term in contract["required_exact_terms"]
                )
            )
            forbidden = any(
                term in body
                for term in contract["forbidden_other_anchor_terms_in_body"]
            )
            anchor_missing += missing
            anchor_forbidden += forbidden
            anchor_complete += not missing and not forbidden
            for character in characters:
                participant_slot_count += 1
                evidence = _participant_evidence(
                    narrative_body,
                    character,
                )
                participant_description_complete += evidence["description"]
                participant_face_complete += evidence["face"]
                participant_gaze_complete += evidence["gaze"]
                participant_support_complete += evidence["support"]
    same_theme_pairs = [
        (_char_ngrams(left.prose), _char_ngrams(right.prose))
        for item in result.themes
        for left, right in combinations(item.frames, 2)
    ]
    return FilmPromptDiversityReport(
        theme_count=len(result.themes),
        frame_count=len(frame_texts),
        unique_theme_titles=len(
            {_normalize(item.theme.title) for item in result.themes}
        ),
        exact_duplicate_theme_texts=_duplicate_count(theme_texts),
        exact_duplicate_frame_texts=_duplicate_count(frame_texts),
        content_evidence_complete_frames=content_evidence_complete,
        content_evidence_incomplete_frames=(
            len(frame_texts) - content_evidence_complete
        ),
        anchor_complete_frames=anchor_complete,
        anchor_missing_required_frames=anchor_missing,
        anchor_forbidden_term_frames=anchor_forbidden,
        character_anchor_complete_frames=character_anchor_complete,
        scene_anchor_complete_frames=scene_anchor_complete,
        participant_description_complete_slots=(
            participant_description_complete
        ),
        participant_face_complete_slots=participant_face_complete,
        participant_gaze_complete_slots=participant_gaze_complete,
        participant_support_complete_slots=participant_support_complete,
        participant_slot_count=participant_slot_count,
        clothing_state_conflict_frames=sum(
            contains_clothing_state_conflict(text)
            for text in frame_texts
        ),
        theme_similarity=_similarity_metrics(theme_texts),
        frame_similarity=_similarity_metrics(frame_texts),
        same_theme_frame_similarity=_pair_similarity_metrics(
            same_theme_pairs
        ),
        theme_coverage=_coverage_counts(
            theme_texts,
            _COVERAGE_TERMS,
        ),
        frame_coverage=_coverage_counts(
            frame_texts,
            {
                **_COVERAGE_TERMS,
                **_FRAME_COVERAGE_TERMS,
            },
        ),
    )


def _excerpt(value: str, *, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[:limit].rstrip()


def _anchor_usage(
    request: FilmPromptRequest,
    themes: list[NarrativeTheme],
) -> dict[str, int]:
    anchors = tuple(
        name
        for group in _source_anchor_groups(request)
        for name in (*group["characters"], *group["scenes"])
    )
    return {
        anchor: sum(anchor.casefold() in theme.premise.casefold() for theme in themes)
        for anchor in anchors
    }


def _source_anchor_groups(
    request: FilmPromptRequest,
) -> tuple[dict[str, tuple[str, ...]], ...]:
    return tuple(
        {
            "characters": tuple(
                item.canonical_name for item in film.anchors.adult_characters
            ),
            "scenes": tuple(item.canonical_name for item in film.anchors.scenes),
        }
        for film in request.source_films
    )


def _scene_anchor_mentioned(anchor: str, value: str) -> bool:
    normalized_anchor = anchor.casefold()
    normalized_value = value.casefold()
    if normalized_anchor in normalized_value:
        return True
    if len(normalized_anchor) < 4:
        return False
    candidates = []
    for split_at in range(2, len(normalized_anchor) - 1):
        prefix = normalized_anchor[:split_at]
        suffix = normalized_anchor[split_at:]
        prefix_index = normalized_value.find(prefix)
        if prefix_index < 0:
            continue
        suffix_index = normalized_value.find(
            suffix,
            prefix_index + len(prefix),
        )
        if suffix_index < 0:
            continue
        gap = suffix_index - prefix_index - len(prefix)
        candidates.append((len(prefix) + len(suffix), gap))
    return any(
        matched >= len(normalized_anchor) and gap <= 40
        for matched, gap in candidates
    )


def _participant_evidence(
    value: str,
    character: str,
) -> dict[str, bool]:
    indexes = [
        match.start()
        for match in re.finditer(re.escape(character), value)
    ]
    if not indexes:
        return {
            "description": False,
            "face": False,
            "gaze": False,
            "support": False,
        }
    windows = [
        value[index : min(len(value), index + 320)]
        for index in indexes
    ]
    face_terms = (
        "眉",
        "眼睑",
        "眼角",
        "嘴角",
        "嘴唇",
        "下颌",
        "面颊",
        "额头",
        "brow",
        "eyelid",
        "mouth",
        "lip",
        "jaw",
        "cheek",
        "forehead",
    )
    gaze_terms = (
        "视线",
        "凝视",
        "回望",
        "看向",
        "望向",
        "目光",
        "gaze",
        "looks",
        "eyes fixed",
    )
    support_terms = (
        "支撑",
        "承重",
        "双脚",
        "双膝",
        "骨盆",
        "坐在",
        "站在",
        "躺在",
        "靠在",
        "地面",
        "床榻",
        "座椅",
        "椅面",
        "supported",
        "weight",
        "feet",
        "knees",
        "pelvis",
        "seated",
        "standing",
        "lying",
    )
    appearance_terms = (
        "穿着",
        "身着",
        "衣物",
        "服装",
        "上衣",
        "长裤",
        "长裙",
        "长袍",
        "旗袍",
        "赤裸",
        "裸露",
        "发型",
        "头发",
        "wearing",
        "dressed",
        "clothing",
        "robe",
        "shirt",
        "trousers",
        "skirt",
        "nude",
        "hair",
    )
    normalized_windows = [window.casefold() for window in windows]
    return {
        "description": any(
            any(term.casefold() in window for term in appearance_terms)
            and any(term.casefold() in window for term in support_terms)
            for window in normalized_windows
        ),
        "face": any(
            sum(term.casefold() in window for term in face_terms) >= 2
            for window in normalized_windows
        ),
        "gaze": any(
            any(term.casefold() in window for term in gaze_terms)
            for window in normalized_windows
        ),
        "support": any(
            any(term.casefold() in window for term in support_terms)
            for window in normalized_windows
        ),
    }


def _coverage_counts(
    texts: Iterable[str],
    dimensions: dict[str, dict[str, tuple[str, ...]]],
) -> dict[str, dict[str, int]]:
    materialized = tuple(str(text) for text in texts)
    coverage = {}
    for dimension, categories in dimensions.items():
        counts = Counter()
        for text in materialized:
            matched = False
            normalized = text.casefold()
            for category, terms in categories.items():
                if any(term.casefold() in normalized for term in terms):
                    counts[category] += 1
                    matched = True
            if not matched:
                counts["未分类"] += 1
        coverage[dimension] = dict(counts)
    return coverage


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _duplicate_count(values: list[str]) -> int:
    counts = Counter(_normalize(value) for value in values)
    return sum(count - 1 for count in counts.values() if count > 1)


def _char_ngrams(value: str, *, size: int = 3) -> Counter[str]:
    normalized = _normalize(value)
    return Counter(
        normalized[index : index + size]
        for index in range(max(0, len(normalized) - size + 1))
    )


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if len(left) > len(right):
        left, right = right, left
    dot_product = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _similarity_metrics(values: list[str]) -> SimilarityMetrics:
    vectors = [_char_ngrams(value) for value in values]
    pairs = [
        _cosine(vectors[left], vectors[right])
        for left, right in combinations(range(len(vectors)), 2)
    ]
    nearest = [0.0] * len(vectors)
    for left, right in combinations(range(len(vectors)), 2):
        similarity = _cosine(vectors[left], vectors[right])
        nearest[left] = max(nearest[left], similarity)
        nearest[right] = max(nearest[right], similarity)
    return SimilarityMetrics(
        item_count=len(values),
        pair_count=len(pairs),
        mean_pair_similarity=_rounded_mean(pairs),
        mean_nearest_similarity=_rounded_mean(nearest),
        maximum_similarity=round(max(pairs, default=0.0), 4),
        pairs_at_or_above_0_70=sum(value >= 0.70 for value in pairs),
        pairs_at_or_above_0_80=sum(value >= 0.80 for value in pairs),
    )


def _pair_similarity_metrics(
    pairs: list[tuple[Counter[str], Counter[str]]],
) -> SimilarityMetrics:
    similarities = [_cosine(left, right) for left, right in pairs]
    return SimilarityMetrics(
        item_count=len(pairs),
        pair_count=len(pairs),
        mean_pair_similarity=_rounded_mean(similarities),
        mean_nearest_similarity=_rounded_mean(similarities),
        maximum_similarity=round(max(similarities, default=0.0), 4),
        pairs_at_or_above_0_70=sum(value >= 0.70 for value in similarities),
        pairs_at_or_above_0_80=sum(value >= 0.80 for value in similarities),
    )


def _rounded_mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0
