"""Typed requests for story facts, creative themes, scenes, and reviews."""

from __future__ import annotations

import json
import re

from t2i_story_pipeline.models import (
    NarrativeReview,
    NarrativeSequence,
    NarrativeTheme,
    OutputLanguage,
    StoryBlueprint,
    StoryRequest,
)
from t2i_story_pipeline.provider import ChatMessage

_SAFETY_RULES = (
    "所有人物必须明确为二十一岁以上成年人。"
    "不得生成未成年人、年龄模糊人物、性胁迫、性暴力或无法退出的亲密互动。"
    "亲密互动只可表现双方清醒、自愿、回应且可随时停止。"
)


def _source_evidence_options(story: str) -> list[str]:
    return [
        clause.strip()
        for clause in re.split(r"[，。；！？!?;]", story)
        if clause.strip()
    ]


def interpretation_messages(request: StoryRequest) -> list[ChatMessage]:
    language = (
        "自然语言字段使用中文"
        if request.output_language == OutputLanguage.CHINESE
        else "Write every natural-language field in English"
    )
    system = "\n".join(
        (
            "你是故事视觉导演。把用户的一段故事描述编译为共享 StoryBlueprint。",
            _SAFETY_RULES,
            "只保留或具体化当前故事，不改写核心人物、关系、行为与因果。",
            "不得新增用户未提供的姓名、职业、明确年份、旧日约定、"
            "离散原因或其他人物经历；信息缺失时使用中性可见描述。",
            "time、location、environment、atmosphere 分别表达时间、地点、"
            "可见环境和情绪氛围。",
            "characters 按首次出现顺序使用 C01、C02 连续编号；"
            "每人给出明确年龄、角色、稳定外貌、服饰和初始情绪。",
            "原文没有姓名、性别、职业或服饰时不得自行指定；"
            "display_name 使用人物一、人物二等中性称呼。",
            "relationships.source_relationship 必须逐字复制故事原文中的"
            "连续关系短语；relationship 只能将该证据整理为简洁关系说明，"
            "没有原文依据时不创建该关系。",
            "beats 按叙事顺序使用 B01、B02 连续编号；每个节拍必须包含"
            "原文动作证据、正在发生的动作及其可见形式、对方或环境的可见回应、"
            "情绪变化和可见结果。",
            "每个 beat.source_action 必须逐字复制故事原文中一段连续的动作短语；"
            "优先从 user 提供的 source_evidence_options 中原样选择完整条目；"
            "不得改写、概括、补全或把推断写入 source_action。"
            "beat.action 只能把 source_action 分解为一个可见瞬间，"
            "不得改变参与人物、行为方向或结果。"
            "若同一原文动作需要多个画面，可让多个 beat 复用该原文短语。",
            "cinematography 保存整组镜头的摄影、光线、色彩与质感意图；"
            "用户明确给出时忠实保留，未给出时只补充宽泛而协调的方向。",
            f"需要规划每个主题 {request.frames_per_theme} 个连续画面所需的"
            "最小完整故事节拍。",
            f"{language}；机器 ID 保持规定格式。",
            "中文输出提交前逐个自然语言字段扫描 ASCII 字母；"
            "除故事原文已有英文与机器 ID 外，发现任何英文字母都必须先改写为中文。",
            "不要输出解释、合规说明或 schema 之外的字段。",
        )
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story": request.story,
                    "source_evidence_options": _source_evidence_options(
                        request.story
                    ),
                    "theme_count": request.theme_count,
                    "frames_per_theme": request.frames_per_theme,
                    "output_language": request.output_language.value,
                },
                ensure_ascii=False,
            ),
        ),
    ]


def theme_messages(
    request: StoryRequest,
    blueprint: StoryBlueprint,
    *,
    start_index: int,
    count: int,
    existing_themes: list[NarrativeTheme],
) -> list[ChatMessage]:
    language = (
        "自然语言字段使用中文"
        if request.output_language == OutputLanguage.CHINESE
        else "Write every natural-language field in English"
    )
    end_index = start_index + count - 1
    system = "\n".join(
        (
            "你是视觉叙事创意导演。根据 StoryBlueprint 设计一组彼此显著不同的 "
            "NarrativeTheme；不是堆砌细节，也不是改写故事事实。",
            _SAFETY_RULES,
            f"本批 themes 必须恰好包含 {count} 项，theme_id 从 "
            f"T{start_index:03d} 连续到 T{end_index:03d}。",
            f"每个主题只为 {request.frames_per_theme} 个连续画面设计；"
            "motif_progression 不得引用范围之外的画面序号。",
            "每个主题先确定单一 emotional_core，再找出两种相互拉扯的"
            "人物愿望、状态或环境力量作为 narrative_tension。",
            "决定性瞬间 decisive_moment 必须是最能同时呈现动作、回应和情绪变化的"
            "具体瞬间，而不是抽象主题或摄影术语。",
            "不得新增疤痕、胎记、纹身、戒痕等身份标记作为辨认依据，"
            "除非 StoryBlueprint 已明确包含。",
            "visual_motif 必须从当前人物、动作、道具或环境中生长出来；"
            "motif_progression 说明它如何跨连续画面发生可见变化。",
            "每个创意字段都必须是自然、简洁、可区分的表达；"
            "不得在同一字段内重复同一个物件、动作或短语，"
            "也不得用“形成呼应”等空话连接两个相同意象。",
            "restraint 必须主动舍弃虽漂亮但不服务于情感核心、因果动作"
            "或视觉母题的细节。",
            "不同主题的 emotional_core、decisive_moment、visual_motif 和"
            "画面组织策略必须有实质差异；不得只替换形容词、色调或镜头术语。",
            "已有主题只用于避免重复，不得复制或轻微改写。",
            "禁止 8K、杰作、最佳质量等元标签。",
            f"{language}；机器 ID 保持规定格式。",
            "中文输出提交前逐个自然语言字段扫描 ASCII 字母；"
            "除故事原文已有英文与机器 ID 外，发现任何英文字母都必须先改写为中文。",
            "不要输出解释、评分或 schema 之外的字段。",
        )
    )
    ledger = [
        {
            "theme_id": theme.theme_id,
            "title": theme.title,
            "decisive_moment": theme.creative_intent.decisive_moment,
            "visual_motif": theme.creative_intent.visual_motif,
        }
        for theme in existing_themes
    ]
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story_description": request.story,
                    "source_evidence_options": _source_evidence_options(
                        request.story
                    ),
                    "story_blueprint": blueprint.model_dump(mode="json"),
                    "existing_theme_ledger": ledger,
                    "batch_start": start_index,
                    "batch_count": count,
                    "frames_per_theme": request.frames_per_theme,
                },
                ensure_ascii=False,
            ),
        ),
    ]


def narrative_messages(
    request: StoryRequest,
    blueprint: StoryBlueprint,
    theme: NarrativeTheme,
) -> list[ChatMessage]:
    language = (
        "自然语言字段使用中文完整句"
        if request.output_language == OutputLanguage.CHINESE
        else "Write every natural-language field as a complete English sentence"
    )
    system = "\n".join(
        (
            "你是电影场景叙事导演。根据唯一的 StoryBlueprint 生成 NarrativeSequence。",
            _SAFETY_RULES,
            f"scenes 必须恰好包含 {request.frames_per_theme} 项，"
            "按叙事顺序使用 S01、S02 连续编号。",
            "全部画面必须共同实现 NarrativeTheme 的 emotional_core、"
            "narrative_tension、decisive_moment、visual_motif、"
            "motif_progression 和 restraint。",
            "CreativeIntent 只用于指导取舍，不得把 emotional_core、"
            "visual_motif 或 motif_progression 的原句直接复制进场景；"
            "必须把它们转化为具体人物动作、物件位置、环境变化和光影关系。",
            "每个新增细节至少承担一种职责：证明时代与处境、推动动作因果、"
            "表现人物关系、形成物理反馈或强化视觉母题；"
            "不得添加可替换的装饰。",
            "根据主要叙事动力选择 mode：tableau 用于姿态、材质和视觉焦点；"
            "atmospheric 用于环境痕迹、人物内心和时间感；"
            "dramatic 用于前因、冲突、动作与结果。",
            "前因、关系与风险只通过 source_context 表达；"
            "不得在其他字段补写约定、经历、利益、身份凭证或风险。",
            "不得为了填字段虚构前因或人物关系。",
            "每个场景严格按以下叙事职责写作："
            "时空开场、环境证据、人物进入、前因、关系与风险、"
            "当前动作及反馈、材质物理反馈、摄影、光线色彩、"
            "感官的可见证据、主题收束。",
            "每个 scene 是一张静态画面中的一个决定性瞬间，"
            "不是包含多个镜头的电影段落；"
            "不得写切镜、推镜、镜头运动或连续时间推进。",
            "present_actions 及结果不得出现逐渐、随后、随即、然后、继而、"
            "先后、最终等时间推进词；camera_composition 不得变换景别。",
            "每个 source_context 条目必须逐字复制故事原文中的连续片段，"
            "优先从 user 提供的 source_evidence_options 中原样选择完整条目，"
            "用于证明当前画面的动作、前因或关系；不得把生成内容写入其中。",
            "环境物件必须证明时代、人物处境或故事前因，不作无关装饰。",
            "present_actions 中每项都写当前发生的动作、"
            "对象或环境的可见回应，以及动作留下的结果状态。",
            "声音、气味、冷热和抽象情绪不能直接声称可见；"
            "sensory_evidence 必须把它们转换为水汽、磨损、尘埃、"
            "人物姿态、表情或物件状态等可成像证据。",
            "任何字段不得写“不可见却可感”等自相矛盾表述，"
            "也不得虚构温度导致锈迹或颜色瞬间变化等物理效果。",
            "material_and_physical_feedback 必须说明动作、身体、服饰、"
            "道具或环境之间真实可见的接触、形变、反光或位移。",
            "camera_composition 与 lighting_and_color 必须说明它们"
            "突出什么叙事信息，不能只罗列摄影术语。",
            "环境证据、物理反馈和感官证据各最多四项，动作必须恰好一项；"
            "每项只保留一个不可替换的视觉事实，避免细节清单。",
            "thematic_closure 从当前可见物件或动作结果收束人物处境，"
            "不得引入画面无法支持的新剧情。",
            "摄影、光线、环境和动作必须共同突出 decisive_moment；"
            "visual_motif 应在画面序列中发生可见演进，而非重复出现。",
            "用户要求画面出现的文字必须一字不差保存在 visible_text.content；"
            "同时具体描述承载物、位置、字体或材质。不存在可见文字时使用空列表。",
            "允许由当前可见事实产生的克制视觉隐喻，禁止空泛修辞、"
            "8K、杰作、最佳质量等元标签。",
            "所有自然语言字段只写可直接按顺序拼接的最终句子，"
            "不写字段名、项目符号、解释或合规说明。",
            "自然语言字段必须使用人物 display_name，不得出现 C01、B01、S01"
            "等机器 ID。中文输出不得混入 establishing shot 等英文摄影术语。",
            "中文输出除用户原文已有的英文和 visible_text.content 外，"
            "不得混入任何英文单词。",
            f"{language}；机器 ID 保持规定格式。",
            "提交 JSON 前逐个自然语言字段扫描 ASCII 字母；"
            "除故事原文已有英文、visible_text.content 与机器 ID 外，"
            "发现任何英文字母都必须先改写为中文。",
        )
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story_description": request.story,
                    "source_evidence_options": _source_evidence_options(
                        request.story
                    ),
                    "story_blueprint": blueprint.model_dump(mode="json"),
                    "narrative_theme": theme.model_dump(mode="json"),
                    "frames_per_theme": request.frames_per_theme,
                    "output_language": request.output_language.value,
                },
                ensure_ascii=False,
            ),
        ),
    ]


def review_messages(
    request: StoryRequest,
    blueprint: StoryBlueprint,
    theme: NarrativeTheme,
    sequence: NarrativeSequence,
) -> list[ChatMessage]:
    system = "\n".join(
        (
            "你是严格的电影场景叙事评审。只评估，不重写。",
            _SAFETY_RULES,
            "对每个 scene 的十个维度分别给出 1 至 5 分："
            "时空落地、环境叙事、因果动作、物理反馈、摄影叙事整合、"
            "感官视觉化、主题收束、语言连贯、创意统一性、故事独有性。",
            "4 分表示达到可发布标准，5 分表示清晰且无明显缺口。",
            "4 分不要求文学完美：只要满足用户明确要求、因果可读、"
            "信息可成像且创意方向一致，就应判为达到标准。",
            "任何低于 4 分的维度都必须产生一条 issue；"
            "issue 必须指出具体问题和可直接执行的 required_change。",
            "problem 不超过 120 个汉字，required_change 不超过 160 个汉字；"
            "只写一个最关键且可在当前 schema 内完成的修正。",
            "检查每个 scene 是否遵循：时空、环境证据、人物进入与前因、"
            "动作反馈、材质物理、摄影光线、感官证据、主题收束。",
            "抽象情绪、声音、气味或温度若没有可成像证据，"
            "sensory_visualization 不得超过 3 分。",
            "摄影或光线若只是术语罗列而未突出人物、动作或环境证据，"
            "cinematography_integration 不得超过 3 分。",
            "摄影、光线、环境和动作若没有共同服务 emotional_core、"
            "decisive_moment 与 visual_motif，creative_unity 不得超过 3 分。",
            "若替换人物、地点或关键道具后描述仍基本成立，或只使用通用"
            "漂亮话，story_specificity 不得超过 3 分。",
            "若画面违反 restraint，或母题没有按 motif_progression 演进，"
            "creative_unity 不得超过 3 分。",
            "若 scene 直接复述 emotional_core、visual_motif 或"
            "motif_progression，而不是以可见事实体现，creative_unity 和"
            "language_coherence 均不得超过 3 分。",
            "若自然语言字段泄漏 C01、B01、S01 等机器 ID，"
            "或中文请求混入非专有名词的英文摄影术语，"
            "language_coherence 不得超过 3 分。",
            "若生成内容新增用户未提供的姓名、职业、明确年份、旧日约定"
            "或离散原因，story_specificity 不得超过 3 分，"
            "required_change 必须要求删除该虚构事实。",
            "不得因题材偏好打分，只按叙事结构、可见性、连贯性和用户明确要求评估。",
            "不得要求添加用户未提供的人物经历、品牌、机构、铭文、车次、"
            "对白或历史事件；不得把缺少这些虚构细节作为扣分理由。",
            "不得要求单幅画面展示画外声音层次、完整前后剧情或多个时间点。",
            "scene_reviews 必须覆盖全部 scene_id 并保持原顺序。",
            "不要输出 schema 之外的字段。",
        )
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story_description": request.story,
                    "story_blueprint": blueprint.model_dump(mode="json"),
                    "narrative_theme": theme.model_dump(mode="json"),
                    "narrative_sequence": sequence.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
        ),
    ]


def revision_messages(
    request: StoryRequest,
    blueprint: StoryBlueprint,
    theme: NarrativeTheme,
    sequence: NarrativeSequence,
    review: NarrativeReview,
) -> list[ChatMessage]:
    system = "\n".join(
        (
            "你是电影场景叙事修订导演。根据 typed review "
            "只返回输入 current_sequence 中需要修订的 scenes。",
            _SAFETY_RULES,
            "逐项落实每条 issue.required_change；不得删除、合并、"
            "重排或新增输入范围内的 scene_id、beat_id、人物与核心故事事实。",
            "不要补写 current_sequence 未包含的其他 scenes，Studio 会保留并合并它们。",
            "不得修改任何 visible_text.content，只可修正其承载物、位置或外观描述。",
            "没有 issue 的场景和维度保持不变，避免无关改写。",
            "所有修改必须继续服务 NarrativeTheme 的创意核心、决定性瞬间、"
            "视觉母题与取舍，不得用通用漂亮话替代故事独有细节。",
            "修订后每个场景仍须遵循：时空、环境证据、人物进入与前因、"
            "动作反馈、材质物理、摄影光线、感官证据、主题收束。",
            "只返回 schema 数据，不解释修改过程。",
        )
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story_description": request.story,
                    "story_blueprint": blueprint.model_dump(mode="json"),
                    "narrative_theme": theme.model_dump(mode="json"),
                    "current_sequence": sequence.model_dump(mode="json"),
                    "review": review.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
        ),
    ]
