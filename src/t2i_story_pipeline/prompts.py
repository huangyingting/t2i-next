"""Provider instructions for themes and final narrative paragraphs."""

from __future__ import annotations

import json
import re

from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeTheme,
    OutputLanguage,
    StoryRequest,
)
from t2i_story_pipeline.provider import ChatMessage

FRAME_TRANSITION_MARKERS = (
    "此前",
    "前一刻",
    "随后",
    "然后",
    "转而",
    "起身",
    "走向",
    "抽回",
    "再度",
    "已经",
    "已从",
    "转为",
    "固定为",
)
STATIC_TRANSITION_MARKERS = (
    "已经",
    "已从",
    "已移",
    "已站",
    "曾经",
    "方才",
    "先前",
    "继续",
    "重新",
    "彻底",
    "终于",
    "放弃站立",
    "随之",
    "蹲落",
    "直起",
    "退后",
    "逼近",
    "移步",
    "撤出",
    "收回",
    "改为",
    "变为",
)
PORTRAIT_ACTION_MARKERS = (
    "提着",
    "手提",
    "按住",
    "按在",
    "捏住",
    "捏着",
    "抓住",
    "推向",
    "将玉扣向",
    "拉住",
    "扯开",
    "伸向",
    "探向",
    "握住",
    "握着",
    "轻蹭",
    "摩挲",
    "展开",
    "拢住",
    "扶住",
    "扶于",
    "撑住",
    "触及",
    "勾住",
    "捂住",
    "掖住",
    "取出",
    "放下",
    "跨前",
    "退至",
    "移至",
    "挪近",
    "走近",
    "靠近",
    "前踏",
    "轻敲",
    "蹭到",
)
ACTION_CHAIN_MARKERS = (
    "先",
    "随后",
    "然后",
    "继而",
    "随即",
    "接着",
    "转而",
    "这一退一进",
)
SOURCE_SENSITIVE_MARKERS = (
    "低位",
    "高位",
    "贵妃",
    "皇后",
    "宠妃",
    "御赐",
    "封嫔",
    "首次",
    "第一次",
    "关系史",
    "旧抓痕",
    "伤痕",
    "疤痕",
    "伤口",
    "血珠",
    "咬破",
    "自导自演",
    "康熙",
    "雍正",
    "乾隆",
    "嘉庆",
    "道光",
    "咸丰",
    "同治",
    "光绪",
    "宣统",
)
SHOT_SCALES = ("全景", "中景", "近景", "特写")
SHOT_ANGLES = ("平视", "俯拍", "仰拍", "侧拍")
EROTIC_VISIBLE_MARKERS = (
    "全裸",
    "半裸",
    "赤裸",
    "裸露",
    "乳房",
    "胸部",
    "臀部",
    "内衣",
    "内裤",
    "亲吻",
    "接吻",
    "爱抚",
    "抚摸",
    "跨坐",
    "肢体交叠",
)
HARDCORE_VISIBLE_MARKERS = (
    "性交",
    "交合",
    "口交",
    "插入",
    "阴茎",
    "阴道",
    "性器官接触",
    "骑乘位",
    "后入",
)
EROTIC_VISIBLE_MARKERS_EN = (
    "nude",
    "naked",
    "bare breasts",
    "lingerie",
    "underwear",
    "kiss",
    "caress",
    "straddle",
    "entwined bodies",
)
HARDCORE_VISIBLE_MARKERS_EN = (
    "intercourse",
    "penetration",
    "oral sex",
    "penis",
    "vagina",
    "genital contact",
    "fellatio",
    "cunnilingus",
)
MODERN_TECH_MARKERS = (
    "智能手机",
    "手机",
    "平板电脑",
    "笔记本电脑",
    "个人电脑",
    "互联网",
    "无线网络",
    "Wi-Fi",
    "二维码",
    "社交媒体",
    "电子邮件",
    "液晶屏",
    "LED灯",
    "数码相机",
    "无人机",
    "卫星导航",
    "高铁",
    "网约车",
    "电子支付",
)
MODERN_TECH_MARKERS_EN = (
    "smartphone",
    "mobile phone",
    "tablet computer",
    "laptop",
    "personal computer",
    "internet",
    "Wi-Fi",
    "QR code",
    "social media",
    "email",
    "LCD screen",
    "LED light",
    "digital camera",
    "drone",
    "satellite navigation",
    "high-speed rail",
    "ride-hailing",
    "electronic payment",
)
INTENTIONAL_ANACHRONISM_MARKERS = (
    "时代错置",
    "时空错位",
    "历史混搭",
    "穿越",
    "架空",
    "蒸汽朋克",
    "赛博朋克",
    "intentional anachronism",
    "time travel",
    "alternate history",
    "steampunk",
    "cyberpunk",
)
_HISTORICAL_ERA_ANCHORS = (
    "古代",
    "先秦",
    "秦代",
    "秦朝",
    "汉代",
    "汉朝",
    "魏晋",
    "南北朝",
    "隋代",
    "隋朝",
    "唐代",
    "唐朝",
    "五代",
    "宋代",
    "宋朝",
    "辽代",
    "辽朝",
    "金代",
    "金朝",
    "元代",
    "元朝",
    "明代",
    "明朝",
    "清代",
    "清朝",
    "民国",
    "ancient",
    "medieval",
    "qin dynasty",
    "han dynasty",
    "tang dynasty",
    "song dynasty",
    "yuan dynasty",
    "ming dynasty",
    "qing dynasty",
    "republican china",
    "victorian",
)
_FOUR_DIGIT_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")
_QING_ERA_ANCHORS = ("清代", "清朝", "qing dynasty")
_COLD_SEASON_ANCHORS = (
    "深秋",
    "寒秋",
    "霜降",
    "冬季",
    "冬天",
    "寒冬",
    "严冬",
    "寒夜",
    "deep autumn",
    "late autumn",
    "winter",
)

_SAFETY = (
    "所有人物必须明确为二十一岁以上成年人。"
    "不得生成未成年人、年龄模糊人物、性胁迫、性暴力或无法退出的亲密互动。"
    "情色或亲密互动只可表现参与者清醒、自愿、持续回应且可随时停止。"
)

_CONTENT_LEVEL_INSTRUCTIONS = {
    ContentLevel.AESTHETIC: (
        "本次使用美学叙事尺度。故事、人物和构图优先，不主动增加裸露或性接触。"
        "story 明确要求成人裸露或亲密互动时可以忠实呈现，但保持非露骨，"
        "不得描写或聚焦自慰、口交、插入或性器官接触。"
    ),
    ContentLevel.EROTIC: (
        "本次使用成人情色尺度。每帧必须直接呈现与 story 相容的成人裸露、"
        "非露骨亲密接触、姿态张力和表情回应中的至少三项，不能只用气氛、"
        "构图暗示、靠近或即将发生替代。多人互动必须写出至少一处双方主动形成的"
        "具体身体接触，并以视线、相向姿态或共同施力呈现清醒、自愿、持续回应"
        "和可随时停止。不得描写或聚焦自慰、口交、插入或性器官接触。"
    ),
    ContentLevel.HARDCORE: (
        "本次使用仅限二十一岁以上成年人的露骨情色尺度。每帧必须直接、清楚地"
        "呈现与 story 相容的明确性行为，不得用拥抱、亲吻、挑逗、遮挡、气氛"
        "或即将发生替代；允许客观写明成人性器官与具体接触，但仍只能有一个"
        "决定性主动作，不能串联动作过程。每位参与者都必须以主动接触、回应视线、"
        "相向姿态或共同施力明确呈现清醒、自愿、持续回应且可随时停止。"
    ),
}


def _content_level_instruction(request: StoryRequest) -> str:
    instruction = _CONTENT_LEVEL_INSTRUCTIONS[request.content_level]
    if request.output_language == OutputLanguage.CHINESE:
        if request.content_level == ContentLevel.EROTIC:
            instruction += (
                "中文正文必须把可见尺度写成具体事实，并至少使用以下词语中的一个："
                f"{_quoted_list(EROTIC_VISIBLE_MARKERS)}。"
            )
        elif request.content_level == ContentLevel.HARDCORE:
            instruction += (
                "中文正文必须明确写出性行为本身，并至少使用以下词语中的一个："
                f"{_quoted_list(HARDCORE_VISIBLE_MARKERS)}。"
            )
    elif request.content_level == ContentLevel.EROTIC:
        instruction += (
            " English prose must state visible adult erotic content directly"
            " and use at least one of these terms: "
            f"{', '.join(EROTIC_VISIBLE_MARKERS_EN)}."
        )
    elif request.content_level == ContentLevel.HARDCORE:
        instruction += (
            " English prose must state the explicit adult sexual act directly"
            " and use at least one of these terms: "
            f"{', '.join(HARDCORE_VISIBLE_MARKERS_EN)}."
        )
    return (
        instruction
        + "不得把内容等级名称、英文值或合规说明写入 title、premise 或 prose。"
    )


def anachronism_markers_for_story(
    request: StoryRequest,
) -> tuple[str, ...]:
    source = request.story.casefold()
    if any(marker.casefold() in source for marker in INTENTIONAL_ANACHRONISM_MARKERS):
        return ()
    years = [int(value) for value in _FOUR_DIGIT_YEAR.findall(source)]
    is_historical = any(
        anchor.casefold() in source for anchor in _HISTORICAL_ERA_ANCHORS
    ) or any(year <= 1989 for year in years)
    if not is_historical:
        return ()
    candidates: tuple[str, ...] = (
        MODERN_TECH_MARKERS
        if request.output_language == OutputLanguage.CHINESE
        else MODERN_TECH_MARKERS_EN
    )
    if any(
        marker.casefold() in source for marker in _QING_ERA_ANCHORS
    ) and any(
        marker.casefold() in source for marker in _COLD_SEASON_ANCHORS
    ):
        candidates += (
            ("凉帽",)
            if request.output_language == OutputLanguage.CHINESE
            else ("summer court hat",)
        )
    return tuple(
        marker for marker in candidates if marker.casefold() not in source
    )


def _era_consistency_instruction(request: StoryRequest) -> str:
    instruction = (
        "时间与地点是事实约束。所有建筑、室内陈设、家具、器物、材料、服装、"
        "发型、交通工具、武器、通信与照明技术、社会称谓和人物用语都必须同时"
        "符合 story 指定的时代、地域、季节、时辰与社会环境。服装冷暖、植物状态"
        "和取暖降温方式必须符合季节，天然光与人工光源必须符合时辰，官职、礼仪、"
        "制度和称谓必须属于正确朝代。不得因追求画面丰富而混入后世技术、现代物件、"
        "错误制度或年代尚未出现的材料；不确定时使用时代成立的通用描述，不猜测"
        "品牌、型号、精确年代或专名。只有 story 明确要求穿越、架空、时代错置或"
        "历史混搭时才允许违时代元素，并保留其有意对比。"
    )
    forbidden = anachronism_markers_for_story(request)
    if not forbidden:
        return instruction
    rendered = (
        _quoted_list(forbidden)
        if request.output_language == OutputLanguage.CHINESE
        else ", ".join(forbidden)
    )
    return (
        instruction
        + "当前 story 具有明确的历史或季节锚点，且原文未指定以下不相容事物，"
        f"因此不得生成：{rendered}。"
    )


def _quoted_list(values: tuple[str, ...]) -> str:
    return "、".join(f"“{value}”" for value in values)


def _chinese_frame_contract() -> str:
    return "\n".join(
        (
            "以下是提交前必须满足的精确质量门：",
            "全文不得出现这些连续推进词："
            f"{_quoted_list(FRAME_TRANSITION_MARKERS)}。",
            "主动作前最后一个人物句不得出现这些姿态变化词："
            f"{_quoted_list(STATIC_TRANSITION_MARKERS)}。",
            "人物句只能写位置、静止姿态、表情、视线和受力状态，不得出现"
            "这些次动作词："
            f"{_quoted_list(PORTRAIT_ACTION_MARKERS)}。",
            "唯一动作句必须精确以“此刻，”开头，并在施动者后使用一次“正”或"
            "“正在”表示进行态，且不得出现这些串联词："
            f"{_quoted_list(ACTION_CHAIN_MARKERS)}，也不得同时出现“又”和“再”。",
            "全文实行封闭世界：以下来源敏感词只有在 story 原文出现时才可使用："
            f"{_quoted_list(SOURCE_SENSITIVE_MARKERS)}。",
            "倒数第二句必须以“镜头采用”开头，并至少包含一个景别词"
            f"（{_quoted_list(SHOT_SCALES)}）和一个角度词"
            f"（{_quoted_list(SHOT_ANGLES)}）。",
            "最后一句必须以“光线”开头。全文只能出现 story、title、premise"
            "或 style 原文已有的英文字词。",
        )
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
        "title 与 premise 使用中文"
        if request.output_language == OutputLanguage.CHINESE
        else "Write title and premise in English"
    )
    system = "\n".join(
        (
            "你是叙事选题编辑。为同一 story 设计彼此不同、可拍成六个静止画面的"
            "微型故事，而不是风格变体。",
            _SAFETY,
            f"themes 必须恰好包含 {count} 项，theme_id 从 "
            f"T{start_index:03d} 连续到 T{end_index:03d}。",
            "title 是简洁题名。premise 控制在八十至一百八十个汉字，用一个"
            "完整故事种子写明谁、何时何地、触发事实、当前目标、期限或失败后果、"
            "人物关系张力和一个改变局面的可见瞬间。不要列六帧，不写连续动作清单、"
            "台词或结尾后的整理过程。",
            "若 story 已给出具体事件，只能深化其可见细节；若 story 只是宽泛题材，"
            "可以构思符合该题材的新事件。始终沿用原文身份、关系、年代与地点精度，"
            "不得新增历史人物姓名、具体年号、宫殿名、物件来历、秘密身世或旧事。",
            _era_consistency_instruction(request),
            "实行封闭世界：不得给人物增加原文没有的等级高低、封号、受宠关系、"
            "御赐经历、身体伤痕、具体朝代年号或关系史事件。",
            "为 story 选择一个明确风格写入 style，例如暗黑武侠、民国电影、"
            "美式辣妹、山村纪实、宋代美学或用户明确指定的电影风格。"
            "style 必须是可放在每帧开头的简短中文短语，并与故事时代、地点、"
            "事件和情绪一致，控制在二至二十个汉字，不得写成导演阐述、画面规划"
            "或六帧摘要；不同主题可以选择不同但合理的风格。",
            "主题差异必须来自故事本身，不能只改变道具、色调或摄影角度。",
            "已有主题只用于避开重复，不得改写后再次输出。",
            _content_level_instruction(request),
            language,
            "中文字段不得混入 story 原文之外的英文词。",
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
                    "content_level_requirement": _content_level_instruction(
                        request
                    ),
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
        "prose 使用自然、准确、连贯的中文"
        if request.output_language == OutputLanguage.CHINESE
        else "Write prose in natural, precise, continuous English"
    )
    frame_ids = [
        f"F{index:02d}" for index in range(1, request.frames_per_theme + 1)
    ]
    system = "\n".join(
        (
            "你是静态电影画面叙事作家。把故事写成可直接用于文生图的独立画面，"
            "不是动作过程、故事梗概或视觉规格表。",
            _SAFETY,
            f"frames 必须恰好包含 {len(frame_ids)} 项，且只包含这些 frame_id："
            f"{'、'.join(frame_ids)}，顺序必须一致。",
            "每个 prose 是一个无换行自然段，以 theme.style 原文和逗号开头，"
            "不得使用字段标签。严格依次写六部分："
            "一，年代、地点、当前时刻；"
            "二，一句静态因果，写明人物身份与关系、一个触发事实、当前目标、"
            "期限及失败后果；"
            "三，能证明故事的环境；"
            "四，所有人物；"
            "五，唯一动作；"
            "六，镜头与光线。",
            "默认每帧控制在五百五十至八百五十个汉字；人物多或空间关系复杂时"
            "可以合理放宽，但不得通过重复前因、同义情绪、连续比喻或抽象评论增字。",
            "静态因果只能陈述局面，不能复述对话或连续动作，不能提前泄露本帧结果。"
            "例如写“因玉扣遗失，三人必须在宫人进门前找到它，否则移位家具会暴露"
            "私密行迹”，不要写谁先做了什么、随后又做了什么。",
            "每帧重新完整写出每个人的原有身份、明确成年年龄与性别、稳定长相、"
            "发型和基础服装，以及各自不同的当前情绪、产生该情绪的原因、"
            "表情、视线目标和一个静止姿态。不得用“男人、女人、几名成年人”"
            "抹去帝王、妃嫔、学生、记者等已知身份。"
            "人物段只写此刻可见状态，绝不写其如何到达姿态。"
            "每个人只占一个分号分隔的静态分句。"
            "手只能写成“位于、垂在、停在、保持”，不能在人物段提、按、握、"
            "推、拉、伸、探、蹭、整理衣物或改变位置；这些只能择一作为主动作。"
            "错误：“她放弃站姿蹲身，随后伸手”；"
            "正确：“她半蹲在箱子左侧，眉心紧绷，目光落在锁扣上”。",
            "唯一动作句必须以“此刻，”开头，在施动者后使用一次“正”或“正在”，"
            "只描述一个人或"
            "共同动作对一个对象造成的一次变化。句内写清方向、接触点、力度、"
            "静态回应和物理结果，并使线索、风险、人物判断或关系发生变化。"
            "动作句只允许一个主动谓语；逗号后的内容只能用“被、形成、呈现、"
            "保持”描写受力结果或静态回应，不得让另一人物或另一只手再执行动作。"
            "正确示例：“此刻，妃嫔正在用右手压住衣带结，织物被指腹压出凹痕，"
            "帝王保持垂目姿态。”"
            "错误示例：“此刻，她抬起手，覆上手背，穿过指缝并向下按压。”"
            "动作句结束后不得再发生故事，只能写镜头句和光线句。",
            "倒数第二句必须以“镜头采用”开头，包含全景、中景、近景或特写之一，"
            "以及平视、俯拍、仰拍或侧拍之一，并写机位、构图、焦点、"
            "前中后景与景深；构图必须看见动作和至少一人的表情或视线，"
            "不能把所有面部裁出画面。",
            "最后一句必须以“光线”开头，写光源、方向、软硬、明暗和色调，"
            "照亮动作结果与人物表情，以可见细节收束各自情绪、关系和氛围。",
            "六帧各选一个不同静止瞬间，依次建立局面、加压、改变关系、抵达发现、"
            "呈现结果、留下余波。主动作、发现和情绪转折不得重复；"
            "每帧仍须脱离其他帧独立成立。",
            "身体、重心、四肢、朝向、遮挡、接触、衣物受力和道具位置必须成立。"
            "人物外貌、发型和基础服装在六帧稳定，只保留事件造成的可见变化。",
            "只沿用 story 与 theme 的事实精度，不得新增姓名、精确年月地点、"
            "台词、物件来历、秘密动机、伤疤或人物往事。"
            "不得添加原文没有的身份等级、封号、受宠关系、御赐经历、身体伤痕"
            "或具体朝代年号。"
            "story 指定的画面文字必须逐字保留并用双引号括起；否则不添加文字。",
            _era_consistency_instruction(request),
            "任意两帧的唯一动作句不得只是换词复写；字符与事件核心相似度达到"
            "百分之八十二即视为重复，必须更换主动作、接触点、发现或关系结果。",
            _content_level_instruction(request),
            language,
            "中文不得混入 story 或 theme.style 原文之外的英文词。"
            "提交前逐帧检查以上要求，发现问题先重写，只提交修正后的正文。",
            _chinese_frame_contract()
            if request.output_language == OutputLanguage.CHINESE
            else "",
            "不要输出解释、评语、合规说明或 schema 之外的字段。",
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
                    "content_level_requirement": _content_level_instruction(
                        request
                    ),
                    "theme": theme.model_dump(mode="json"),
                    "frames_per_theme": request.frames_per_theme,
                    "frame_ids": frame_ids,
                },
                ensure_ascii=False,
            ),
        ),
    ]
