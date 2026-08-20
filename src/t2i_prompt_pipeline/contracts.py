"""Shared structural contracts for generated and persisted artifacts."""

from __future__ import annotations

import re
from collections.abc import Collection

from t2i_prompt_pipeline.errors import GenerationContractError
from t2i_prompt_pipeline.models import (
    CastPlan,
    Foundation,
    Frame,
    Gender,
    GenerationSpec,
    OutputLanguage,
    StyleConstraints,
    Theme,
    format_character_id,
    format_frame_id,
    format_theme_id,
)

_INVISIBLE_PLACEHOLDER = re.compile(
    r"^(?:面部[：:，, ]*)?(?:"
    r"不可见(?:[，, ]*(?:完全)?出画)?|"
    r"(?:完全)?出画(?:[，, ]*不可见)?|"
    r"(?:face )?not visible(?:[，, ]*out of frame)?|"
    r"out of frame(?:[，, ]*(?:face )?not visible)?"
    r")[。.]?$",
    re.IGNORECASE,
)
_EMPTY_PLACEHOLDER = re.compile(
    r"^(?:null|none|nil|undefined|n/?a|无|空|暂无|没有)[。.]?$",
    re.IGNORECASE,
)
_LATIN_FRAGMENT = re.compile(r"[A-Za-z]+(?:[ '-][A-Za-z]+)*")
_CJK_FRAGMENT = re.compile(r"[\u3400-\u9fff]+")
_CONCRETE_CAMERA_TERM = re.compile(
    r"相机位于|拍摄机位|固定机位|轨道横移|斯坦尼康|环绕近景|"
    r"景别为(?:特写|近景|中景|全景|远景)|"
    r"(?:特写|近景|中景|全景|远景)(?:镜头|取景|景别)|"
    r"长镜头|焦距偏移|镜头运动|\d+\s*度(?:俯拍|仰拍|侧拍)|"
    r"\d+\s*毫米(?:镜头|焦距)|\b(?:camera position|camera angle|"
    r"focal length|aperture|camera movement|tracking shot|long take|"
    r"steadicam|close-up|medium shot|wide shot|long shot|"
    r"rack focus)\b",
    re.IGNORECASE,
)
_CAMERA_CAPTURED_MEDIUM = re.compile(
    r"摄影|摄像|照片|电影静帧|实拍|\b(?:photograph(?:y|ic)?|"
    r"cinematograph(?:y|ic)?|videograph(?:y|ic)?|"
    r"cinematic (?:still|photo)|film still|live[- ]action|"
    r"(?:film|video) footage)\b",
    re.IGNORECASE,
)
_NON_CAMERA_CAPTURED_MEDIUM = re.compile(
    r"水彩|油画|素描|铅笔画|炭笔画|版画|蚀刻画|插画|漫画|动画|"
    r"像素画|三维渲染|3D\s*渲染|\b(?:watercolou?r|oil painting|"
    r"pencil drawing|charcoal drawing|etching|illustration|anime|"
    r"animation|pixel art|3d render)\b",
    re.IGNORECASE,
)
_SHALLOW_DEPTH = re.compile(
    r"浅景深|景深(?:偏|较|倾向)?浅|\bshallow (?:depth of field|focus)\b",
    re.IGNORECASE,
)
_DEEP_DEPTH = re.compile(
    r"深景深|景深(?:偏|较|倾向)?深|\bdeep (?:depth of field|focus)\b",
    re.IGNORECASE,
)
_ORDINAL_CHARACTER_LABEL = re.compile(
    r"^(?:[男女]\d+|(?:Woman|Man) \d+)$",
    re.IGNORECASE,
)
_EXPLICIT_ERA = re.compile(
    r"(?:[一二〇零][〇零一二三四五六七八九]{3}|(?:18|19|20)\d{2})年代|"
    r"[一二三四五六七八九]十年代|(?:十八|十九|二十|二十一)世纪|"
    r"\b(?:18|19|20)\d0s\b",
    re.IGNORECASE,
)
_LEADING_STYLE_PHRASE = re.compile(
    r"^(?P<phrase>[^，。；;]{1,120}?导演风格)(?=的|，|。|；|;|$)"
)
_ACTION_VISIBILITY_TERM = re.compile(
    r"不可见|出画|画外|\b(?:not visible|out of frame|off-screen)\b",
    re.IGNORECASE,
)
_TRANSIENT_STABLE_FACT_TERM = re.compile(
    r"仍|已|继续|保持|维持|重新|先前|复又|再度|未变|首帧|上一帧|"
    r"前几帧|如前|再次|终于|刚才|方才|不知何时|未复位|"
    r"\b(?:unchanged|previous(?:ly)?|again|still|already|"
    r"continues?|continued|remains?|remained)\b",
    re.IGNORECASE,
)
_EXPLICIT_CROSS_FRAME_REFERENCE = re.compile(
    r"首帧|上一帧|前几帧|如前|\bprevious(?:ly)?\b",
    re.IGNORECASE,
)
_NONVISUAL_TERM = re.compile(
    r"声音|声响|回声|回响|雨声|脚步声|落地声|汽笛声|嗡鸣|噪音|气味|香味|臭味|"
    r"触感|温度|微凉|发出可见|声|不可见|出画|画外|"
    r"\b(?:sound|noise|smell|odou?r|scent|temperature|audible|"
    r"inaudible|not visible|out of frame|off-screen)\b",
    re.IGNORECASE,
)
_CHINESE_ROUTE = re.compile(
    r"从(?P<path>[^，。；;]{1,80}?)到"
    r"(?P<end>[^，。；;]{1,24}?)(?="
    r"展开|进行|完成|重逢|寻找|移动|转移|，|。|；|;|$)"
)
_ENGLISH_ROUTE = re.compile(
    r"\bfrom\s+(?P<path>[^,.;]{1,80}?)\s+to\s+"
    r"(?P<end>[^,.;]{1,40}?)(?=\s+(?:for|while|where|and then)\b|[,.;]|$)",
    re.IGNORECASE,
)
_ROUTE_EQUIVALENT_GROUPS = (
    frozenset({"电梯", "升降机", "elevator", "lift"}),
    frozenset({"走廊", "廊道", "长廊", "corridor", "hallway"}),
    frozenset({"房间", "客房", "room", "guest room"}),
)


def _theme_natural_text(theme: Theme) -> tuple[str, ...]:
    return (
        theme.title,
        theme.scene,
        theme.style,
        *(
            value
            for character in theme.characters
            for value in (
                character.label,
                character.appearance,
                character.outfit,
            )
        ),
    )


def _frame_natural_text(frame: Frame) -> tuple[str, ...]:
    return (
        frame.camera.shot,
        frame.camera.view,
        frame.camera.composition,
        frame.details,
        *(
            value
            for moment in frame.characters
            for value in (
                *((moment.expression,) if moment.expression else ()),
                moment.action,
            )
        ),
    )


def _validate_output_language(
    spec: GenerationSpec,
    artifact_id: str,
    texts: tuple[str, ...],
) -> None:
    pattern = (
        _LATIN_FRAGMENT
        if spec.output_language == OutputLanguage.CHINESE
        else _CJK_FRAGMENT
    )
    brief = spec.brief.casefold()
    unexpected = sorted(
        {
            match.group(0)
            for text in texts
            for match in pattern.finditer(text)
            if match.group(0).casefold() not in brief
        }
    )
    if unexpected:
        raise GenerationContractError(
            f"{artifact_id} 混入输出语言之外的文字：{unexpected}"
        )


def _depth_tendency(text: str) -> str | None:
    is_shallow = _SHALLOW_DEPTH.search(text) is not None
    is_deep = _DEEP_DEPTH.search(text) is not None
    if is_shallow == is_deep:
        return None
    return "浅景深" if is_shallow else "深景深"


def _matched_terms(pattern: re.Pattern[str], texts: tuple[str, ...]) -> list[str]:
    return sorted(
        {
            match.group(0)
            for text in texts
            for match in pattern.finditer(text)
        }
    )


def brief_route_points(brief: str) -> tuple[str, ...]:
    points: list[str] = []
    for match in _CHINESE_ROUTE.finditer(brief):
        path = re.sub(
            r"(?:转移|移动|搬运|行进|前往|经过)$",
            "",
            match.group("path"),
        )
        points.extend(re.split(r"[、，,]", path))
        points.append(match.group("end"))
    for match in _ENGLISH_ROUTE.finditer(brief):
        points.extend(
            re.split(r"\s+(?:through|via)\s+|,", match.group("path"))
        )
        points.append(match.group("end"))
    return tuple(
        dict.fromkeys(point.strip() for point in points if point.strip())
    )


def _route_point_is_present(point: str, scene: str) -> bool:
    normalized_point = point.casefold()
    candidates = {normalized_point}
    for group in _ROUTE_EQUIVALENT_GROUPS:
        if normalized_point in group:
            candidates.update(group)
            break
    normalized_scene = scene.casefold()
    return any(candidate in normalized_scene for candidate in candidates)


def theme_ids(spec: GenerationSpec) -> tuple[str, ...]:
    return tuple(
        format_theme_id(index, spec.theme_count)
        for index in range(1, spec.theme_count + 1)
    )


def frame_ids(spec: GenerationSpec, theme_id: str) -> tuple[str, ...]:
    return tuple(
        format_frame_id(theme_id, index, spec.frames_per_theme)
        for index in range(1, spec.frames_per_theme + 1)
    )


def normalize_foundation(
    spec: GenerationSpec,
    foundation: Foundation,
) -> Foundation:
    required_phrases = foundation.style_constraints.required_phrases
    if len(required_phrases) != len(set(required_phrases)):
        raise GenerationContractError("风格约束包含重复原文")
    for phrase in required_phrases:
        if phrase not in spec.brief:
            raise GenerationContractError(
                f"风格约束不是 brief 原文：{phrase}"
            )
    explicit_style = _LEADING_STYLE_PHRASE.match(spec.brief)
    if (
        explicit_style is not None
        and explicit_style.group("phrase") not in required_phrases
    ):
        raise GenerationContractError(
            "风格约束遗漏 brief 明示风格："
            f"{explicit_style.group('phrase')}"
        )
    constraints = (
        (Gender.FEMALE, spec.female_count, "--female-count"),
        (Gender.MALE, spec.male_count, "--male-count"),
    )
    for gender, requested_count, option_name in constraints:
        if requested_count is None:
            continue
        resolved_count = foundation.cast_plan.gender_count(gender)
        if resolved_count != requested_count:
            raise GenerationContractError(
                "人物约束冲突：brief 解析为"
                f"{gender.value} {resolved_count} 名，但 {option_name} "
                f"要求 {requested_count} 名"
            )
    return foundation


def normalize_theme(
    spec: GenerationSpec,
    style_constraints: StyleConstraints,
    cast_plan: CastPlan,
    theme: Theme,
    allowed_theme_ids: Collection[str],
) -> Theme:
    if theme.theme_id not in allowed_theme_ids:
        raise GenerationContractError(f"Theme ID 未请求：{theme.theme_id}")
    style = theme.style
    phrase_counts = {
        phrase: style.count(phrase)
        for phrase in style_constraints.required_phrases
    }
    missing_phrases = [
        phrase
        for phrase, count in phrase_counts.items()
        if count == 0
    ]
    if missing_phrases:
        raise GenerationContractError(
            f"{theme.theme_id} style 缺少 brief 原文约束："
            f"{missing_phrases}"
        )
    repeated_phrases = [
        phrase for phrase, count in phrase_counts.items() if count > 1
    ]
    if repeated_phrases:
        raise GenerationContractError(
            f"{theme.theme_id} style 重复 brief 原文约束："
            f"{repeated_phrases}"
        )
    unconstrained_style = style
    for phrase in style_constraints.required_phrases:
        unconstrained_style = unconstrained_style.replace(phrase, "")
    if not _CAMERA_CAPTURED_MEDIUM.search(style):
        raise GenerationContractError(
            f"{theme.theme_id} style 必须使用摄影或摄像媒介"
        )
    non_camera_captured_medium = _NON_CAMERA_CAPTURED_MEDIUM.search(
        unconstrained_style
    )
    if non_camera_captured_medium:
        raise GenerationContractError(
            f"{theme.theme_id} style 使用非相机实拍媒介："
            f"{non_camera_captured_medium.group(0)}"
        )
    deterministic_issues: list[str] = []
    camera_term = _CONCRETE_CAMERA_TERM.search(unconstrained_style)
    if camera_term:
        deterministic_issues.append(
            "style 包含 Frame 专属具体摄影参数："
            f"{camera_term.group(0)}"
        )
    unsupported_eras = sorted(
        {
            match.group(0)
            for text in _theme_natural_text(theme)
            for match in _EXPLICIT_ERA.finditer(text)
            if match.group(0).casefold() not in spec.brief.casefold()
        }
    )
    if unsupported_eras:
        deterministic_issues.append(
            f"包含 brief 未指定的时代：{unsupported_eras}"
        )
    missing_route_points = [
        point
        for point in brief_route_points(spec.brief)
        if not _route_point_is_present(point, theme.scene)
    ]
    if missing_route_points:
        deterministic_issues.append(
            "Theme.scene 缺少 brief 路线地点："
            f"{missing_route_points}"
        )
    stable_texts = (
        theme.scene,
        *(
            value
            for character in theme.characters
            for value in (character.appearance, character.outfit)
        ),
    )
    transient_terms = _matched_terms(_TRANSIENT_STABLE_FACT_TERM, stable_texts)
    if transient_terms:
        deterministic_issues.append(
            f"稳定事实包含瞬时状态：{transient_terms}"
        )
    nonvisual_terms = _matched_terms(_NONVISUAL_TERM, stable_texts)
    if nonvisual_terms:
        deterministic_issues.append(
            f"稳定事实包含非视觉信息：{nonvisual_terms}"
        )
    if deterministic_issues:
        raise GenerationContractError(
            f"{theme.theme_id} {'; '.join(deterministic_issues)}"
        )
    _validate_output_language(
        spec,
        theme.theme_id,
        _theme_natural_text(theme),
    )
    if spec.output_language == OutputLanguage.CHINESE:
        if not style.endswith("。"):
            if style.endswith(("，", "、", "；")):
                style = f"{style[:-1]}。"
            elif style.endswith("："):
                raise GenerationContractError(
                    f"{theme.theme_id} style 疑似在句中截断"
                )
            else:
                style += "。"
    else:
        if not style.endswith("."):
            if style.endswith((",", ";")):
                style = f"{style[:-1]}."
            elif style.endswith(":"):
                raise GenerationContractError(
                    f"{theme.theme_id} style 疑似在句中截断"
                )
            else:
                style += "."
    expected_ids = tuple(
        format_character_id(theme.theme_id, index)
        for index in range(1, cast_plan.member_count + 1)
    )
    by_id = {
        character.character_id: character for character in theme.characters
    }
    if (
        len(theme.characters) != len(expected_ids)
        or set(by_id) != set(expected_ids)
    ):
        raise GenerationContractError(f"{theme.theme_id} 人物 ID 不完整或重复")
    ordered = [by_id[character_id] for character_id in expected_ids]
    for character, cast_member in zip(
        ordered,
        cast_plan.members,
        strict=True,
    ):
        if character.gender != cast_member.gender:
            raise GenerationContractError(
                f"{character.character_id} 性别不符合 Cast Plan"
            )
    return theme.model_copy(update={"style": style, "characters": ordered})


def normalize_frame(
    spec: GenerationSpec,
    theme: Theme,
    frame: Frame,
    allowed_frame_ids: Collection[str],
) -> Frame:
    if frame.frame_id not in allowed_frame_ids:
        raise GenerationContractError(f"Frame ID 未请求：{frame.frame_id}")
    style_depth = _depth_tendency(theme.style)
    frame_depth = _depth_tendency(frame.camera.shot)
    if style_depth and frame_depth and style_depth != frame_depth:
        raise GenerationContractError(
            f"{frame.frame_id} camera.shot 必须继承 Theme.style 的"
            f"{style_depth}；不得使用{frame_depth}。"
        )
    expected_ids = tuple(
        character.character_id for character in theme.characters
    )
    by_id = {moment.character_id: moment for moment in frame.characters}
    if (
        len(frame.characters) != len(by_id)
        or not set(by_id).issubset(expected_ids)
    ):
        raise GenerationContractError(
            f"{frame.frame_id} 人物 ID 重复或不属于 Theme"
        )
    frame_text = "\n".join(_frame_natural_text(frame)).casefold()
    omitted_references = [
        character.label
        for character in theme.characters
        if character.character_id not in by_id
        and _ORDINAL_CHARACTER_LABEL.fullmatch(character.label)
        and character.label.casefold() in frame_text
    ]
    if omitted_references:
        raise GenerationContractError(
            f"{frame.frame_id} 引用了未列入 characters 的可见人物："
            f"{omitted_references}"
        )
    normalized_moments = []
    text_issues: list[str] = []
    for moment in frame.characters:
        if _INVISIBLE_PLACEHOLDER.fullmatch(moment.action):
            text_issues.append(
                "完全不可见的人物必须从 characters 省略"
            )
        else:
            visibility_term = _ACTION_VISIBILITY_TERM.search(moment.action)
            if visibility_term:
                text_issues.append(
                    "action 包含不可见描述："
                    f"{visibility_term.group(0)}"
                )
        if _EMPTY_PLACEHOLDER.fullmatch(moment.action):
            text_issues.append(
                "action 是空值占位符而不是可见姿态"
            )
        expression = moment.expression
        if expression and (
            _INVISIBLE_PLACEHOLDER.fullmatch(expression)
            or _EMPTY_PLACEHOLDER.fullmatch(expression)
        ):
            expression = None
        normalized_moments.append(
            moment.model_copy(update={"expression": expression})
        )
    normalized_by_id = {
        moment.character_id: moment for moment in normalized_moments
    }
    normalized = frame.model_copy(
        update={
            "characters": [
                normalized_by_id[character_id]
                for character_id in expected_ids
                if character_id in normalized_by_id
            ]
        }
    )
    normalized_text = "\n".join(_frame_natural_text(normalized))
    cross_frame_references = _matched_terms(
        _EXPLICIT_CROSS_FRAME_REFERENCE,
        (normalized_text,),
    )
    if cross_frame_references:
        text_issues.append(
            "引用了其他 Frame："
            f"{cross_frame_references}"
        )
    nonvisual_terms = _matched_terms(_NONVISUAL_TERM, (normalized_text,))
    if nonvisual_terms:
        text_issues.append(f"包含非视觉信息：{nonvisual_terms}")
    if text_issues:
        raise GenerationContractError(
            f"{frame.frame_id} {'; '.join(text_issues)}"
        )
    _validate_output_language(
        spec,
        normalized.frame_id,
        _frame_natural_text(normalized),
    )
    return normalized


def normalize_checkpoint_graph(
    spec: GenerationSpec,
    foundation: Foundation | None,
    themes: dict[str, Theme],
    frames: dict[str, Frame],
) -> tuple[dict[str, Theme], dict[str, Frame]]:
    if foundation is None:
        if themes or frames:
            raise GenerationContractError(
                "Theme 或 Frame checkpoint 缺少 Foundation checkpoint"
            )
        return {}, {}
    normalize_foundation(spec, foundation)
    allowed_theme_ids = theme_ids(spec)
    normalized_themes: dict[str, Theme] = {}
    for stored_id, theme in themes.items():
        if stored_id != theme.theme_id:
            raise GenerationContractError(
                f"Theme checkpoint key 与内容不匹配：{stored_id}"
            )
        normalized_themes[stored_id] = normalize_theme(
            spec,
            foundation.style_constraints,
            foundation.cast_plan,
            theme,
            allowed_theme_ids,
        )
    normalized_frames: dict[str, Frame] = {}
    for stored_id, frame in frames.items():
        if stored_id != frame.frame_id:
            raise GenerationContractError(
                f"Frame checkpoint key 与内容不匹配：{stored_id}"
            )
        theme_id = frame.frame_id.split("-F", 1)[0]
        theme = normalized_themes.get(theme_id)
        if theme is None:
            raise GenerationContractError(
                f"{frame.frame_id} 缺少对应 Theme checkpoint"
            )
        normalized_frames[stored_id] = normalize_frame(
            spec,
            theme,
            frame,
            frame_ids(spec, theme_id),
        )
    return normalized_themes, normalized_frames
