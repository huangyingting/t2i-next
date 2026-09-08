"""Provider instructions for themes and final narrative paragraphs."""

from __future__ import annotations

import json

from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeTheme,
    OutputLanguage,
    StoryRequest,
)
from t2i_story_pipeline.provider import ChatMessage

_SAFETY = (
    "所有人物必须明确为二十一岁以上成年人。成年人只能称为成年女性、成年男性"
    "或其明确成年身份，不得使用少女、少年等年龄模糊称谓。不得生成未成年人、"
    "性胁迫、性暴力或无法退出的亲密互动。情色或亲密互动只可表现参与者清醒、"
    "自愿、持续回应且可随时停止。"
)

_CONTENT_LEVEL_INSTRUCTIONS = {
    ContentLevel.AESTHETIC: (
        "采用美学叙事尺度。以故事、人物、构图和氛围为主，不主动增加性内容。"
        "story 已经要求成人裸露或亲密互动时可以自然呈现，但不描写明确性行为。"
    ),
    ContentLevel.EROTIC: (
        "采用成人情色尺度。画面应当一眼可见成人裸露、亲密接触或鲜明的身体张力，"
        "不能退化为普通服装肖像、准备过程或纯气氛暗示；这些情色内容要自然服务于"
        "人物关系，保持非露骨，不描写明确性行为。多人互动要让自愿、回应和可停止"
        "从视线、姿态或主动接触中看得出来。"
    ),
    ContentLevel.HARDCORE: (
        "采用仅限二十一岁以上成年人的露骨情色尺度。明确性行为必须真实发生并"
        "服务于人物关系和当前故事，而不是孤立的器官说明；参与者的清醒、自愿、"
        "持续回应和停止权必须在画面中成立。"
    ),
}


def _content_level_instruction(request: StoryRequest) -> str:
    return (
        _CONTENT_LEVEL_INSTRUCTIONS[request.content_level]
        + "不要把内容等级名称、英文值或合规说明写入 title、premise 或 prose。"
    )


def _era_consistency_instruction() -> str:
    return (
        "时间和地点是整体世界的一部分。建筑、陈设、器物、材料、服装、发型、"
        "交通、武器、通信、照明、社会称谓和人物用语应当彼此协调，并符合 story "
        "给出的时代、地域、季节、时辰和社会环境；服装冷暖、植物状态、光源、"
        "礼仪与制度也要自然成立。不确定史实时使用可信的通用描述，不为显得具体"
        "而猜测品牌、型号、精确年代或专名。story 明确要求穿越、架空或时代错置"
        "时，才把违时代元素作为有意设计。"
    )


def theme_messages(
    request: StoryRequest,
    *,
    start_index: int,
    count: int,
    existing_themes: list[NarrativeTheme],
) -> list[ChatMessage]:
    end_index = start_index + count - 1
    language = (
        "title、premise 和 style 使用自然中文"
        if request.output_language == OutputLanguage.CHINESE
        else "Write title, premise, and style in natural English"
    )
    system = "\n".join(
        (
            "你是叙事选题编辑。围绕同一 story 构思真正不同、可以拍成若干独立"
            "静态画面的微型故事，不是把同一动作换地点、换颜色或换机位。",
            _SAFETY,
            f"themes 必须恰好包含 {count} 项，theme_id 从 "
            f"T{start_index:03d} 连续到 T{end_index:03d}。",
            "title 简洁自然。premise 最多两句：第一句确定时间、地点、人物和"
            "他们共同进入的情境，并为每个人给出可在所有 frame 保持一致的成年"
            "年龄、面部特征、身形与发型；第二句只写人物关系中最重要的情绪张力"
            "或选择。"
            "premise 不写具体姿态、绳路、器具、镜头、光线、操作过程、倒计时、"
            "外部职业危机或结局，把这些留给各个 frame 独立发挥。",
            "若 story 已给出具体事件，就深化人物和可见处境；若只是宽泛题材，可以"
            "构思可信的新事件。不要为了戏剧性虚构姓名、精确年号地点、秘密身世、"
            "物件来历、身份等级、伤痕或关系史。",
            _era_consistency_instruction(),
            "style 是一句完整、简洁的视觉风格描述，不罗列不同景别或多个构图方案。",
            "不同主题要从人物关系、场景用途、决定或冲突上真正不同。已有主题只用于"
            "避开重复，不要改写后再次输出。",
            _content_level_instruction(request),
            language,
            "不要输出解释或 schema 之外的字段。",
        )
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story": request.story,
                    "content_level": request.content_level.value,
                    "batch_start": start_index,
                    "batch_count": count,
                    "frames_per_theme": request.frames_per_theme,
                    "existing_themes": [
                        theme.model_dump(mode="json")
                        for theme in existing_themes
                    ],
                },
                ensure_ascii=False,
            ),
        ),
    ]


def frame_messages(
    request: StoryRequest,
    theme: NarrativeTheme,
) -> list[ChatMessage]:
    language = (
        "prose 使用自然、准确、流畅的中文"
        if request.output_language == OutputLanguage.CHINESE
        else "Write prose in natural, precise, fluent English"
    )
    frame_ids = [
        f"F{index:02d}" for index in range(1, request.frames_per_theme + 1)
    ]
    system = "\n".join(
        (
            "你是电影感静态画面叙事作家。把 theme 写成若干可直接用于文生图、"
            "又能让人一眼理解人物处境的独立画面。整体叙事的自然、通顺和画面成立"
            "优先于逐项填表。",
            _SAFETY,
            f"frames 必须恰好包含 {len(frame_ids)} 项，frame_id 依次为 "
            f"{'、'.join(frame_ids)}。",
            "每个 prose 是一个无换行的自然段，不使用主题、人物、动作、摄影、"
            "光线等字段标签。开头自然点明 theme.style，并在前部让年代、地点和"
            "当前时刻清楚成立，但不要每帧套用完全相同的句式。",
            "把每帧当作这组图片中唯一存在的一张来写，读者不需要知道其他五帧。"
            "自然交代谁在什么处境中、他们正在面对"
            "什么，以及这一瞬间为何有意义；只有故事确实需要时才写期限或失败后果，"
            "不要强造委托方、验收、倒计时、交付任务或抽象的风险术语。",
            "每帧重新完整描写所有可见人物的明确成年身份、年龄、性别、稳定外貌、"
            "发型、服装、表情、视线和当前姿态。把这些信息融入观察顺序，不要像"
            "档案一样逐项罗列；稳定外貌沿用 theme premise，不能在各帧改变同一"
            "人的发色、发长、脸型或身形。不同人物要有能够彼此回应的情绪和空间"
            "关系。",
            "画面定格在一个清晰瞬间。可以有一个最重要的动作、接触或受力关系，"
            "但只写当前可见状态和直接物理结果，不叙述先后步骤，不让人物在同一帧"
            "连续改变姿态。不要为了符合句式而使用“此刻”或其他固定开头。",
            "story 若围绕绳艺、口塞、服装展示或其他明确视觉主题，每一帧都直接"
            "呈现已经完成、可被拍摄的核心造型，而不是准备、逐步增加、调整或解除"
            "过程；从 story 提供的造型中选择适合当前画面的一种，不把全部术语"
            "同时堆入一帧。",
            "环境应提供与人物处境有关的物件、材质、距离和空间证据，不堆砌无关"
            "陈设。身体重心、四肢方向、遮挡、接触点、衣物和道具受力必须可信。",
            "镜头与光线必须明确而专业，包括合适的景别、机位或角度、构图焦点、"
            "景深、光源方向和色调；把它们写进段落的自然节奏，不要求固定句首、"
            "固定位置或固定数量的摄影术语。",
            "同一主题的多帧是同一人物、场所和情绪前提的平行画面方案，不是一件事"
            "按时间先后展开的镜头序列。每帧都从头建立完整现场，并拥有不同的造型、"
            "视觉中心和情绪重点；不能把一帧写成另一帧的前置、后续、升级或解除"
            "状态，也不能借助“同一、仍然、已经、再次、换成、终于”等前文状态"
            "来省略本帧信息。",
            "篇幅由人物数量和画面复杂度决定。细节足够支撑文生图即可，不要用同义"
            "情绪、伪精确时间、技术说明、抽象评论或重复前因填充长度。",
            "只沿用 story 与 theme 已有的事实精度。story 指定的画面文字必须逐字"
            "保留并用双引号括起；没有指定就不要主动添加文字。",
            _era_consistency_instruction(),
            _content_level_instruction(request),
            language,
            "输出中文时，把 story 中的外语概念自然翻译成中文，整段不得夹入英文"
            "代词、服装、摄影、姿态或动作短语。",
            "提交前只做一次整体通读：把正文中残留的外语碎片改写成自然中文，并"
            "确认人物和空间成立、画面能被直接看见。正文不得提及 theme、frame、"
            "编号、提示词、字段或其他内部生成过程，也不要输出评语、合规说明或"
            "schema 之外的字段。",
        )
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story": request.story,
                    "content_level": request.content_level.value,
                    "theme": theme.model_dump(mode="json"),
                    "frames_per_theme": request.frames_per_theme,
                    "frame_ids": frame_ids,
                },
                ensure_ascii=False,
            ),
        ),
    ]
