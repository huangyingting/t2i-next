"""验证导演风格 Theme 与 Frame 的关键语义契约。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from t2i_film_style_pipeline.compiler import frame_source_sentence
from t2i_film_style_pipeline.errors import FilmStyleContractError
from t2i_film_style_pipeline.models import (
    FilmStyleProfile,
    FilmStyleRequest,
    contains_image_geometry,
)
from t2i_film_style_pipeline.prompt_models import (
    ContentLevel,
    FilmPromptRequest,
    NarrativeFrame,
    NarrativeTheme,
)

_REFUSAL = re.compile(
    r"抱歉|无法(?:协助|提供|创作)|不能(?:协助|提供|创作)|"
    r"\b(?:sorry|i cannot|i can't|unable to assist)\b",
    re.IGNORECASE,
)
_EXPLICIT_SEX = re.compile(
    r"(?:阴茎|生殖器|性器官).{0,24}(?:插入|进入|接触).{0,16}"
    r"(?:阴道|肛门|外阴|性器官)|"
    r"(?:插入|进入).{0,16}(?:阴道|肛门)|"
    r"(?:口|口舌|舌头|嘴唇).{0,20}(?:阴茎|外阴|阴蒂|生殖器|性器官)|"
    r"(?:阴茎|外阴|阴蒂|生殖器|性器官).{0,20}(?:口|口舌|舌头|嘴唇)|"
    r"(?:外阴|阴蒂|阴道|生殖器|性器官).{0,24}"
    r"(?:直接)?(?:刺激|摩擦|揉按|抚弄|抚触)|"
    r"(?:手指|指尖).{0,24}(?:外阴|阴蒂|阴道|生殖器|性器官)|"
    r"(?:外阴|阴蒂|阴道|生殖器|性器官).{0,24}(?:手指|指尖)|"
    r"自慰|手淫|指交|乳交|性交|肛交|口交|"
    r"\b(?:penetrat(?:e|es|ed|ing|ion)|oral sex|fellatio|cunnilingus|"
    r"masturbat(?:e|es|ed|ing|ion)|anal sex|vaginal sex|fingering|"
    r"(?:clitoral|genital|vaginal) (?:stimulation|rubbing)|"
    r"manual (?:genital|clitoral|vaginal) stimulation)\b",
    re.IGNORECASE,
)
_HARDCORE_DESIRE_RESPONSE = re.compile(
    r"媚眼|欲望|愉悦|潮红|喘息|迷离|兴奋|享受|"
    r"主动.{0,12}(?:迎合|回望|配合|抬高|展示|维持)|"
    r"(?:挑逗|顺从).{0,8}(?:目光|眼神|表情)|"
    r"\b(?:desirous|pleasured|teasing) (?:gaze|look)|"
    r"actively (?:arches|responds|looks back|displays)\b",
    re.IGNORECASE,
)
_HARDCORE_BDSM_EVIDENCE = (
    re.compile(
        r"项圈|颈圈|狗链|牵引链|链条|束缚带|腕带|手铐|绳索|"
        r"\b(?:collar|leash|chain|restraint|wrist cuffs?|rope)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"握住|握紧|攥住|牵引|牵住|拉住|拉紧|收紧|持链|扣住|拴住|束缚|"
        r"一端.{0,12}(?:手中|手里)|"
        r"\b(?:holds?|grips?|guides?|pulls?|controls?|restrains?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"跪地|跪姿|跪在|跪伏|双膝.{0,12}支撑|四肢着地|"
        r"前臂.{0,12}支撑|俯伏|伏身|弯腰|前倾|"
        r"臀部.{0,12}(?:抬高|翘起)|骨盆.{0,12}(?:抬高|上提)|"
        r"\b(?:kneels?|kneeling|on all fours|hips? raised|bent over)\b",
        re.IGNORECASE,
    ),
    _HARDCORE_DESIRE_RESPONSE,
)
_HARDCORE_DISPLAY_EVIDENCE = (
    re.compile(
        r"(?:命令|指令|指示|手势|示意|要求).{0,20}"
        r"(?:展示|张开|分开|抬高|转身)|"
        r"\b(?:commands?|directs?|signals?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:分开|张开)双腿|双腿.{0,8}(?:分开|张开)|"
        r"抬高臀部|翘起臀部|开放姿态|暴露姿态|"
        r"\b(?:legs spread|hips? raised|open display pose)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:直接|完全|清楚)?(?:暴露|展示).{0,16}"
        r"(?:外阴|生殖器|性器官|胯下)|"
        r"(?:外阴|生殖器|性器官|胯下).{0,16}"
        r"(?:直接暴露|完全暴露|清楚可见|无遮挡)|"
        r"\b(?:genitals?|vulva).{0,16}(?:exposed|clearly visible)\b",
        re.IGNORECASE,
    ),
    _HARDCORE_DESIRE_RESPONSE,
)
_NEGATED_CONTENT = re.compile(
    r"非生殖器(?:的)?(?:直接)?(?:接触|互动)|"
    r"(?:不(?:再)?(?:出现|包含|呈现|展示|描写|描绘|涉及)|"
    r"不得(?:出现|包含|呈现|展示|描写|描绘|涉及)|没有|并无)"
    r"[^。；;\n]{0,120}(?:[。；;\n]|$)|"
    r"\b(?:without|does not (?:show|include|depict)|"
    r"do not (?:show|include|depict)|no)\b"
    r"[^.;\n]{0,160}(?:[.;\n]|$)",
    re.IGNORECASE,
)
_COMPLIANCE_BOILERPLATE = re.compile(
    r"平等而自愿|清醒[、，,\s]*(?:且|并)?自愿|"
    r"可随时(?:退出|停止|离开)|没有受困|未受束缚|"
    r"(?:通道|出口|空地|门口|身后).{0,20}保持畅通|"
    r"\b(?:consenting adults|free to leave|can stop at any time|"
    r"not trapped|not restrained|compliance statement)\b",
    re.IGNORECASE,
)
_AESTHETIC_EVIDENCE = {
    "chinese": (
        ("皮肤或贴身轮廓", re.compile(r"裸露|皮肤|肩颈|肩线|锁骨|背部|腰线|贴身|敞开")),
        (
            "身体姿态张力",
            re.compile(
                r"前倾|倾向|后仰|扭转|绷紧|肌肉|骨骼|身体张力|"
                r"抬颌|弓身|跨坐|重心.{0,12}(?:落在|偏向)|"
                r"(?:膝|手肘).{0,8}(?:微曲|弯曲)|脚尖.{0,8}(?:点地|支撑)"
            ),
        ),
        (
            "回应式视线或接触",
            re.compile(r"凝视|对视|回望|亲吻|拥抱|相扣|相触|贴住|环住|掌心|抚摸|触碰"),
        ),
        (
            "皮肤或织物质地",
            re.compile(
                r"受压|凹痕|褶皱|汗|水汽|潮湿|发丝|织物|粗布|"
                r"皮革|床褥|温润|起栗|丝绸|绸缎|纹理|材质|光泽"
            ),
        ),
        (
            "身体明暗塑形",
            re.compile(
                r"(?:光|高光|阴影|冷暖).{0,36}"
                r"(?:皮肤|肩|颈|锁骨|肌肉|曲线|身体)|"
                r"(?:皮肤|肩|颈|锁骨|肌肉|曲线|身体).{0,36}"
                r"(?:光|高光|阴影|冷暖)"
            ),
        ),
    ),
    "english": (
        (
            "skin or fitted contour",
            re.compile(
                r"\b(?:bare skin|exposed skin|shoulder|collarbone|back|"
                r"waistline|fitted clothing|open neckline)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "physical pose tension",
            re.compile(
                r"\b(?:leans|arches|twists|taut|tense muscle|body tension|"
                r"raised chin|straddles)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "reciprocal gaze or contact",
            re.compile(
                r"\b(?:gaze|eye contact|kisses|embraces|interlaced fingers|"
                r"touches|palm|caresses)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "skin or textile texture",
            re.compile(
                r"\b(?:pressure mark|compressed|crease|sweat|mist|damp|"
                r"wet hair|textile|leather|bedding|goosebumps)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "light shaping the body",
            re.compile(
                r"\b(?:light|highlight|shadow|warm|cool).{0,50}"
                r"(?:skin|shoulder|neck|collarbone|muscle|curve|body)|"
                r"\b(?:skin|shoulder|neck|collarbone|muscle|curve|body)"
                r".{0,50}(?:light|highlight|shadow|warm|cool)\b",
                re.IGNORECASE,
            ),
        ),
    ),
}
_EROTIC_EVIDENCE = {
    "chinese": (
        (
            "明显裸露或半解服装",
            re.compile(
                r"全裸|半裸|赤裸|裸露|袒露|上身仅着|"
                r"衣襟.{0,8}(?:敞开|解开)|下装.{0,8}褪至|"
                r"露出.{0,20}(?:肩|颈|锁骨|胸|背|腰|大腿)"
            ),
        ),
        (
            "实际非生殖器接触",
            re.compile(
                r"贴合|紧贴|相拥|拥抱|亲吻|吻住|跨坐|交叠|"
                r"(?:掌心|手掌|嘴唇).{0,16}(?:贴|压|触|吻)"
            ),
        ),
        (
            "欲望或愉悦表情",
            re.compile(
                r"欲望|愉悦|喘息|迷离|潮红|媚眼|兴奋|享受|"
                r"(?:眼睑|嘴唇|嘴角).{0,12}(?:半垂|微张|上扬)"
            ),
        ),
        (
            "皮肤或材质触觉",
            re.compile(
                r"汗|水汽|水珠|受压|凹痕|泛红|潮湿|湿润|"
                r"褶皱|绷紧|陷入|皮肤.{0,12}(?:贴合|变形)"
            ),
        ),
    ),
    "english": (
        (
            "visible nudity or loosened clothing",
            re.compile(
                r"\b(?:fully nude|naked|bare skin|half-dressed|"
                r"open robe|open shirt|lowered clothing)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "actual non-genital contact",
            re.compile(
                r"\b(?:presses? against|embraces?|kisses?|straddles?|"
                r"intertwined|palm|lips).{0,40}(?:skin|shoulder|neck|"
                r"chest|back|waist|hip|thigh)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "desire or pleasure expression",
            re.compile(
                r"\b(?:desire|pleasure|aroused|flushed|panting|"
                r"half-lidded eyes|parted lips|raised mouth corner)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "skin or material tactility",
            re.compile(
                r"\b(?:sweat|steam|droplet|compressed|pressure mark|"
                r"flushed skin|damp|wet|crease|indentation)\b",
                re.IGNORECASE,
            ),
        ),
    ),
}
_CAMERA_EVIDENCE = {
    "chinese": (
        ("景别", re.compile(r"特写|近景|中近景|中景|中远景|全景|远景")),
        (
            "摄影机相对位置",
            re.compile(
                r"(?:机位|摄影机|观察点|视点).{0,30}"
                r"(?:位于|设在|置于|靠近|面对|朝向|正对|侧对)"
            ),
        ),
        (
            "拍摄距离",
            re.compile(
                r"距离人物|距(?:离)?(?:人物|主体)|"
                r"约\s*[一二三四五六七八九十\d.]+\s*米|"
                r"[一二两三四五六七八九十\d.]+(?:个)?身位|"
                r"[一二两三四五六七八九十\d.]+步(?:外|远)?|"
                r"近距离|中等距离|中距离|远距离|贴近人物|远离人物"
            ),
        ),
        (
            "机位高度",
            re.compile(
                r"(?:眼平|视线|腰部|胸口|胸部|肩部|膝部|地面).{0,8}"
                r"(?:高度|高|平齐|齐平|水平)|"
                r"(?:平齐|齐平)于(?:人物|两人)?(?:眼睛|视线|腰部|胸口|胸部|肩部)|"
                r"高机位|低机位|"
                r"机位.{0,12}(?:高于|低于)"
            ),
        ),
        (
            "水平角度",
            re.compile(r"正面|侧面|背面|后方|三分之二|斜侧|侧前|侧后"),
        ),
        ("俯仰角度", re.compile(r"平视|俯视|俯角|仰视|仰角|顶视|鸟瞰")),
        (
            "镜头或焦距",
            re.compile(
                r"(?:超广角|广角|标准|中焦|中长焦|长焦|微距|移轴)"
                r"(?:镜头|焦段)|\d{2,3}\s*(?:毫米|mm)|焦距",
                re.IGNORECASE,
            ),
        ),
        (
            "透视效果",
            re.compile(r"透视|空间压缩|空间压叠|尺度夸张|畸变|前后尺度"),
        ),
        ("焦点", re.compile(r"主焦点|焦点|对焦")),
        ("景深", re.compile(r"景深|深焦|浅焦|虚焦|焦外|柔化|清晰可辨")),
        (
            "前景遮挡或框景",
            re.compile(
                r"前景.{0,50}(?:遮挡|框景|虚焦|柔化|门框|帘|栏|枝|玻璃)|"
                r"(?:遮挡|框景).{0,30}前景|无前景遮挡"
            ),
        ),
    ),
    "english": (
        (
            "shot scale",
            re.compile(
                r"\b(?:close-up|medium close-up|medium shot|medium wide shot|"
                r"full shot|wide shot|long shot)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "camera position",
            re.compile(
                r"\b(?:camera|viewpoint).{0,40}"
                r"(?:positioned|placed|located|faces|looks from)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "camera distance",
            re.compile(
                r"\b(?:close|near|medium|far|distant) distance\b|"
                r"\b\d+(?:\.\d+)?\s*(?:m|meters?|feet|ft)\s+from\b",
                re.IGNORECASE,
            ),
        ),
        (
            "camera height",
            re.compile(
                r"\b(?:eye|waist|chest|shoulder|knee|ground)[ -]level\b|"
                r"\b(?:high|low) camera position\b",
                re.IGNORECASE,
            ),
        ),
        (
            "horizontal angle",
            re.compile(
                r"\b(?:frontal|front|profile|side|rear|back|three-quarter)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "vertical angle",
            re.compile(
                r"\b(?:eye-level|high-angle|low-angle|overhead|bird's-eye)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "lens or focal length",
            re.compile(
                r"\b(?:ultra-wide|wide-angle|normal|standard|medium telephoto|"
                r"telephoto|macro|tilt-shift) lens\b|"
                r"\b\d{2,3}\s*mm\b|\bfocal length\b",
                re.IGNORECASE,
            ),
        ),
        (
            "perspective effect",
            re.compile(
                r"\b(?:perspective|spatial compression|scale exaggeration|"
                r"distortion)\b",
                re.IGNORECASE,
            ),
        ),
        ("focus", re.compile(r"\b(?:primary focus|focus plane|focused on)\b", re.I)),
        (
            "depth of field",
            re.compile(
                r"\b(?:depth of field|deep focus|shallow focus|soft focus|bokeh)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "foreground occlusion or framing",
            re.compile(
                r"\bforeground.{0,60}(?:occlusion|frame|framing|soft|blurred)|"
                r"\bno foreground occlusion\b",
                re.IGNORECASE,
            ),
        ),
    ),
}
_CLOTHING_STATE_CONFLICT = re.compile(
    r"(?:衣襟|衣衫|上衣|肩带|丝绸面料).{0,16}"
    r"(?:滑落|褪至|堆叠|堆在).{0,16}(?:手肘|手臂|肩头)|"
    r"(?:滑落|褪至|堆叠|堆在).{0,16}(?:手肘|手臂)|"
    r"完全赤裸[^。；;\n]{0,80}(?:仍穿|穿着|衣襟|衣袖|长袍|旗袍)",
    re.IGNORECASE,
)


def _contains_explicit_sex(value: str) -> bool:
    affirmative_content = _NEGATED_CONTENT.sub(" ", value)
    return _EXPLICIT_SEX.search(affirmative_content) is not None


def _contains_hardcore_bdsm(value: str) -> bool:
    affirmative_content = _NEGATED_CONTENT.sub(" ", value)
    return any(
        all(
            pattern.search(affirmative_content) is not None
            for pattern in evidence
        )
        for evidence in (
            _HARDCORE_BDSM_EVIDENCE,
            _HARDCORE_DISPLAY_EVIDENCE,
        )
    )


def content_level_evidence_complete(
    content_level: ContentLevel,
    value: str,
    output_language: str,
) -> bool:
    if content_level == ContentLevel.HARDCORE:
        return _contains_explicit_sex(value) or _contains_hardcore_bdsm(value)
    if content_level == ContentLevel.EROTIC:
        return all(
            pattern.search(value) is not None
            for _, pattern in _EROTIC_EVIDENCE[output_language]
        )
    evidence = _AESTHETIC_EVIDENCE[output_language]
    present = {
        name for name, pattern in evidence if pattern.search(value) is not None
    }
    return (
        len(present) >= 4
        and evidence[0][0] in present
        and evidence[-1][0] in present
    )


def contains_clothing_state_conflict(value: str) -> bool:
    return _CLOTHING_STATE_CONFLICT.search(value) is not None


@dataclass(frozen=True, slots=True)
class _AnchorSelection:
    work_index: int
    character_names: frozenset[str]
    scene_name: str


@dataclass(frozen=True, slots=True)
class FilmStyleContentValidator:
    film_request: FilmStyleRequest
    profile: FilmStyleProfile

    def validate_theme(
        self,
        request: FilmPromptRequest,
        theme: NarrativeTheme,
    ) -> None:
        self._validate_output(theme.premise, label=f"{theme.theme_id} premise")
        self._selected_anchors(
            theme.premise,
            label=f"{theme.theme_id} premise",
        )
        self._validate_content_level(
            request,
            theme.premise,
            label=f"{theme.theme_id} premise",
            require_hardcore_explicit=False,
        )

    def validate_frame(
        self,
        request: FilmPromptRequest,
        theme: NarrativeTheme,
        frame: NarrativeFrame,
    ) -> None:
        label = f"{theme.theme_id}-{frame.frame_id}"
        prose = frame.prose
        self._validate_output(prose, label=label)
        source_sentence = frame_source_sentence(self.film_request)
        if not prose.startswith(source_sentence) or prose.count(source_sentence) != 1:
            raise FilmStyleContractError(
                f"{label} 必须且只能以这句作品来源句原文开头一次：{source_sentence}"
            )
        if contains_image_geometry(prose):
            raise FilmStyleContractError(
                f"{label} 不得包含画幅比例、横竖方向或图像尺寸"
            )
        if _COMPLIANCE_BOILERPLATE.search(prose):
            raise FilmStyleContractError(
                f"{label} 使用了结论式合规话术；必须改为主动回握、"
                "回应式视线、双向施力和各自支撑等可见事实"
            )
        if contains_clothing_state_conflict(prose):
            raise FilmStyleContractError(
                f"{label} 包含互斥衣物状态；衣袖和上衣不得滑落、褪至或"
                "堆在手臂，完全赤裸时身体上不得仍穿衣物"
            )
        self._validate_content_level(request, prose, label=label)
        minimum_length = (
            300 if self.film_request.output_language == "chinese" else 600
        )
        if len(prose) < minimum_length:
            raise FilmStyleContractError(
                f"{label} 画面正文过短，无法完整覆盖环境、人物、互动、"
                "摄影和光线"
            )
        theme_anchors = self._selected_anchors(
            theme.premise,
            label=f"{theme.theme_id} premise",
        )
        frame_anchors = self._selected_anchors(prose, label=label)
        if (
            frame_anchors.work_index != theme_anchors.work_index
            or frame_anchors.scene_name != theme_anchors.scene_name
            or frame_anchors.character_names != theme_anchors.character_names
        ):
            required_characters = "、".join(
                sorted(theme_anchors.character_names)
            )
            raise FilmStyleContractError(
                f"{label} 必须延续 Theme，并逐字包含其选定的全部人物 canonical_name"
                f"（{required_characters}）与场景 canonical_name"
                f"（{theme_anchors.scene_name}），且不得加入其他电影的人物或场景"
            )
        self._validate_anchor_details(prose, frame_anchors, label=label)
        missing_camera_evidence = [
            evidence
            for evidence, pattern in _CAMERA_EVIDENCE[
                self.film_request.output_language
            ]
            if pattern.search(prose) is None
        ]
        if missing_camera_evidence:
            camera_example = (
                "请明确写成类似“中景；摄影机置于两人侧前方、距主要人物约两米；"
                "保持眼平高度，以三分之二侧前角度平视；使用五十毫米标准镜头，"
                "形成自然透视；主焦点落在面孔，浅景深，前景门框形成框景”。"
                if self.film_request.output_language == "chinese"
                else "Use explicit wording such as: medium shot; the camera is "
                "placed two meters from the main figures at eye level in a "
                "three-quarter frontal position; a 50 mm standard lens creates "
                "natural perspective; primary focus on the faces, shallow depth "
                "of field, with a foreground doorway framing them."
            )
            raise FilmStyleContractError(
                f"{label} 缺少强制摄影证据："
                + "、".join(missing_camera_evidence)
                + f"。{camera_example}"
            )
        if request.content_level == ContentLevel.AESTHETIC:
            evidence = _AESTHETIC_EVIDENCE[self.film_request.output_language]
            present = [
                name for name, pattern in evidence if pattern.search(prose) is not None
            ]
            required_names = {evidence[0][0], evidence[-1][0]}
            if len(present) < 4 or not required_names.issubset(present):
                missing = [name for name, _ in evidence if name not in present]
                raise FilmStyleContractError(
                    f"{label} 美学级感官证据不足：已满足 {len(present)}/5，"
                    "必须至少满足 4/5 且包含皮肤或贴身轮廓与身体明暗塑形；"
                    "缺少" + "、".join(missing)
                )
        elif request.content_level == ContentLevel.EROTIC:
            evidence = _EROTIC_EVIDENCE[self.film_request.output_language]
            missing = [
                name
                for name, pattern in evidence
                if pattern.search(prose) is None
            ]
            if missing:
                raise FilmStyleContractError(
                    f"{label} 极致情色级感官证据不足；必须同时包含明显裸露或"
                    "半解服装、实际非生殖器接触、欲望或愉悦表情，以及皮肤"
                    "或材质触觉；缺少" + "、".join(missing)
                )

    def _selected_anchors(
        self,
        value: str,
        *,
        label: str,
    ) -> _AnchorSelection:
        normalized = value.casefold()
        matches: list[tuple[int, frozenset[str], tuple[str, ...]]] = []
        for index, anchors in enumerate(self.profile.work_anchors):
            characters = frozenset(
                character.canonical_name
                for character in anchors.adult_characters
                if character.canonical_name.casefold() in normalized
            )
            scenes = tuple(
                scene.canonical_name
                for scene in anchors.scenes
                if scene.canonical_name.casefold() in normalized
            )
            scenes = tuple(
                scene
                for scene in scenes
                if not any(
                    scene != other and scene.casefold() in other.casefold()
                    for other in scenes
                )
            )
            if characters and scenes:
                matches.append((index, characters, scenes))
        if not matches:
            raise FilmStyleContractError(
                f"{label} 必须使用同一部输入电影的原作成年人物 canonical_name "
                "与原作场景 canonical_name"
            )
        if len(matches) > 1:
            raise FilmStyleContractError(
                f"{label} 不得跨电影混合原作人物与场景锚点"
            )
        work_index, character_names, scene_names = matches[0]
        if len(scene_names) != 1:
            raise FilmStyleContractError(
                f"{label} 必须选择且只选择一个原作场景 canonical_name"
            )
        return _AnchorSelection(
            work_index=work_index,
            character_names=character_names,
            scene_name=scene_names[0],
        )

    def _validate_anchor_details(
        self,
        prose: str,
        selection: _AnchorSelection,
        *,
        label: str,
    ) -> None:
        normalized = prose.casefold()
        anchors = self.profile.work_anchors[selection.work_index]
        missing_costumes = [
            character.canonical_name
            for character in anchors.adult_characters
            if character.canonical_name in selection.character_names
            and not any(
                feature.casefold() in normalized
                for feature in character.costume_features
            )
        ]
        if missing_costumes:
            raise FilmStyleContractError(
                f"{label} 缺少原作人物服装特征："
                + "、".join(missing_costumes)
            )
        scene = next(
            item
            for item in anchors.scenes
            if item.canonical_name == selection.scene_name
        )
        environment_count = sum(
            feature.casefold() in normalized
            for feature in scene.environment_features
        )
        if environment_count < 2:
            raise FilmStyleContractError(
                f"{label} 必须逐字使用至少两个原作场景 environment_features"
            )
        if not any(
            prop.casefold() in normalized
            for prop in scene.canonical_props
        ):
            raise FilmStyleContractError(
                f"{label} 必须逐字使用至少一个原作场景 canonical_props"
            )

    @staticmethod
    def _validate_output(value: str, *, label: str) -> None:
        if _REFUSAL.search(value):
            raise FilmStyleContractError(
                f"{label} 返回了拒绝或无法协助文本，必须改写为有效画面内容"
            )

    @staticmethod
    def _validate_content_level(
        request: FilmPromptRequest,
        value: str,
        *,
        label: str,
        require_hardcore_explicit: bool = True,
    ) -> None:
        contains_hardcore_content = (
            _contains_explicit_sex(value)
            or _contains_hardcore_bdsm(value)
        )
        if request.content_level == ContentLevel.HARDCORE:
            if require_hardcore_explicit and not contains_hardcore_content:
                raise FilmStyleContractError(
                    f"{label} 未直接写出可见的明确性行为，或具体可见的"
                    "高强度 BDSM 支配互动，"
                    "不得降级为普通亲密互动"
                )
            return
        if contains_hardcore_content:
            raise FilmStyleContractError(
                f"{label} 超出当前内容级别，不得出现明确性行为或"
                "高强度 BDSM 支配互动"
            )
