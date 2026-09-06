"""Shared structural contracts for generated and persisted artifacts."""

from __future__ import annotations

import re
from collections.abc import Collection

from t2i_prompt_pipeline.errors import GenerationContractError
from t2i_prompt_pipeline.models import (
    CastPlan,
    CharacterFraming,
    Foundation,
    Frame,
    Gender,
    GenerationSpec,
    OutputLanguage,
    ShotScale,
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
_CHARACTER_ID_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9])T\d{2,4}-C\d{2}(?![A-Za-z0-9])"
)
_CAMERA_FACING_REFERENCE = re.compile(r"镜头|\bcamera\b", re.IGNORECASE)
_INTERNAL_SCHEMA_TERM = re.compile(
    r"\b(?:brief|required_phrases|required_route_points|validation_issues|"
    r"available_character_ids|theme_ids|frame_ids|character_ids|"
    r"variation_plan)\b",
    re.IGNORECASE,
)
_STRUCTURED_OUTPUT_RESIDUE = re.compile(r"[{}\[\]]")
_CHINESE_FACING_PREFIX = re.compile(r"^(?:朝向|面向|略朝|朝).+")
_ENGLISH_FACING_PREFIX = re.compile(
    r"^(?:facing|towards?)\s+.+",
    re.IGNORECASE,
)
_LEADING_STYLE_PHRASE = re.compile(
    r"^(?P<phrase>[^，。；;]{1,120}?导演风格)(?=的|，|。|；|;|$)"
)
_ACTION_VISIBILITY_TERM = re.compile(
    r"不可见|出画|画外|\b(?:not visible|out of frame|off-screen)\b",
    re.IGNORECASE,
)
_EXPLICIT_CROSS_FRAME_REFERENCE = re.compile(
    r"首帧|上一帧|前几帧|如前|\bprevious(?:ly)?\b",
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
        theme.setting.time_context,
        theme.setting.location,
        *theme.setting.fixed_elements,
        *theme.setting.available_light_sources,
        theme.setting.background_population,
        theme.setting.atmosphere,
        *(
            value
            for character in theme.characters
            for value in (
                character.appearance,
                character.outfit,
            )
        ),
    )


def _frame_natural_text(frame: Frame) -> tuple[str, ...]:
    return (
        frame.camera.depth_of_field.focus_target,
        frame.camera.depth_of_field.background_effect,
        frame.camera.lighting.source,
        frame.camera.lighting.position,
        frame.camera.lighting.color,
        frame.camera.lighting.scene_effect,
        *(
            value
            for moment in frame.characters
            for value in (
                moment.placement,
                moment.facing,
                moment.visible_appearance,
                moment.lighting_effect,
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
    if spec.output_language == OutputLanguage.CHINESE:
        pattern = _LATIN_FRAGMENT
    else:
        pattern = _CJK_FRAGMENT
    brief = spec.brief.casefold()
    unexpected = sorted(
        {
            match.group(0)
            for text in texts
            for match in pattern.finditer(
                _CHARACTER_ID_REFERENCE.sub("", text)
            )
            if match.group(0).casefold() not in brief
        }
    )
    if unexpected:
        raise GenerationContractError(
            f"{artifact_id} 混入输出语言之外的文字：{unexpected}"
        )


def _validate_no_structured_output_residue(
    artifact_id: str,
    texts: tuple[str, ...],
) -> None:
    residues = sorted(
        {
            match.group(0)
            for text in texts
            for match in _STRUCTURED_OUTPUT_RESIDUE.finditer(text)
        }
    )
    if residues:
        raise GenerationContractError(
            f"{artifact_id} 自然文本混入结构化输出残片：{residues}"
        )


def _validate_no_internal_schema_terms(
    artifact_id: str,
    texts: tuple[str, ...],
) -> None:
    leaked = _matched_terms(_INTERNAL_SCHEMA_TERM, texts)
    if leaked:
        raise GenerationContractError(
            f"{artifact_id} 输出泄漏内部字段名：{leaked}"
        )


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
    display_names = [
        member.display_name
        for member in foundation.cast_plan.members
        if member.display_name is not None
    ]
    if len(display_names) != len(set(display_names)):
        raise GenerationContractError("人物姓名重复")
    for display_name in display_names:
        if display_name not in spec.brief:
            raise GenerationContractError(
                f"人物姓名不是 brief 原文：{display_name}"
            )
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
    cast_plan: CastPlan,
    theme: Theme,
    allowed_theme_ids: Collection[str],
) -> Theme:
    if theme.theme_id not in allowed_theme_ids:
        raise GenerationContractError(f"Theme ID 未请求：{theme.theme_id}")
    deterministic_issues: list[str] = []
    setting_text = " ".join(
        (
            theme.setting.time_context,
            theme.setting.location,
            *theme.setting.fixed_elements,
            *theme.setting.available_light_sources,
            theme.setting.background_population,
        )
    )
    missing_route_points = [
        point
        for point in brief_route_points(spec.brief)
        if not _route_point_is_present(point, setting_text)
    ]
    if missing_route_points:
        deterministic_issues.append(
            "Theme.setting 缺少 brief 路线地点："
            f"{missing_route_points}"
        )
    if deterministic_issues:
        raise GenerationContractError(
            f"{theme.theme_id} {'; '.join(deterministic_issues)}"
        )
    _validate_no_internal_schema_terms(
        theme.theme_id,
        _theme_natural_text(theme),
    )
    _validate_no_structured_output_residue(
        theme.theme_id,
        _theme_natural_text(theme),
    )
    _validate_output_language(
        spec,
        theme.theme_id,
        _theme_natural_text(theme),
    )
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
    return theme.model_copy(update={"characters": ordered})


def normalize_frame(
    spec: GenerationSpec,
    theme: Theme,
    frame: Frame,
    allowed_frame_ids: Collection[str],
) -> Frame:
    if frame.frame_id not in allowed_frame_ids:
        raise GenerationContractError(f"Frame ID 未请求：{frame.frame_id}")
    expected_ids = tuple(
        character.character_id for character in theme.characters
    )
    by_id = {moment.character_id: moment for moment in frame.characters}
    if (
        len(frame.characters) != len(expected_ids)
        or set(by_id) != set(expected_ids)
    ):
        raise GenerationContractError(
            f"{frame.frame_id} 每个 Frame 必须包含 Theme 全部人物，"
            "人物 ID 不得缺失、重复或来自其他 Theme"
        )
    normalized_moments = []
    text_issues: list[str] = []
    for moment in frame.characters:
        facing_character_ids = set(
            _CHARACTER_ID_REFERENCE.findall(moment.facing)
        )
        unknown_facing_ids = facing_character_ids.difference(expected_ids)
        if unknown_facing_ids:
            text_issues.append(
                f"{moment.character_id} facing 引用未知人物 ID："
                f"{sorted(unknown_facing_ids)}"
            )
        if (
            not facing_character_ids
            and not _CAMERA_FACING_REFERENCE.search(moment.facing)
        ):
            text_issues.append(
                f"{moment.character_id} facing 必须直接写人物 ID 或镜头"
            )
        facing_without_ids = _CHARACTER_ID_REFERENCE.sub("", moment.facing)
        facing_has_foreign_text = (
            _LATIN_FRAGMENT.search(facing_without_ids)
            if spec.output_language == OutputLanguage.CHINESE
            else _CJK_FRAGMENT.search(facing_without_ids)
        )
        facing_prefix = (
            _CHINESE_FACING_PREFIX
            if spec.output_language == OutputLanguage.CHINESE
            else _ENGLISH_FACING_PREFIX
        )
        if (
            not facing_has_foreign_text
            and not facing_prefix.fullmatch(moment.facing)
        ):
            text_issues.append(
                f"{moment.character_id} facing 格式不完整，必须写完整朝向短语"
            )
        if (
            frame.camera.shot_scale
            in {ShotScale.MEDIUM, ShotScale.CLOSE_UP}
            and moment.framing == CharacterFraming.FULL_BODY
        ):
            text_issues.append(
                f"{moment.character_id} {frame.camera.shot_scale.value} "
                "与 full_body 不兼容"
            )
        if _INVISIBLE_PLACEHOLDER.fullmatch(moment.action):
            text_issues.append(
                "所有人物必须入画，action 不能声明人物不可见"
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
        lighting_character_ids = set(
            _CHARACTER_ID_REFERENCE.findall(moment.lighting_effect)
        )
        wrong_lighting_ids = lighting_character_ids.difference(
            {moment.character_id}
        )
        if wrong_lighting_ids:
            text_issues.append(
                f"{moment.character_id} lighting_effect 引用其他人物："
                f"{sorted(wrong_lighting_ids)}"
            )
        expression = moment.expression
        head_cropped = (
            moment.framing == CharacterFraming.HEAD_CROPPED_TORSO
        )
        if head_cropped and expression is not None:
            text_issues.append(
                f"{moment.character_id} head_cropped_torso 的 "
                "expression 必须为 null"
            )
        elif not head_cropped and expression is None:
            text_issues.append(
                f"{moment.character_id} 头部入画时 expression 不能为空"
            )
        elif expression and (
            _INVISIBLE_PLACEHOLDER.fullmatch(expression)
            or _EMPTY_PLACEHOLDER.fullmatch(expression)
        ):
            text_issues.append(
                f"{moment.character_id} expression 与 framing 不一致"
            )
        normalized_moments.append(moment)
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
    if text_issues:
        raise GenerationContractError(
            f"{frame.frame_id} {'; '.join(text_issues)}"
        )
    _validate_no_structured_output_residue(
        normalized.frame_id,
        _frame_natural_text(normalized),
    )
    _validate_no_internal_schema_terms(
        normalized.frame_id,
        _frame_natural_text(normalized),
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
