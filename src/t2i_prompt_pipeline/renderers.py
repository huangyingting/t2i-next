"""Deterministic rendering with one owner for each visual fact."""

from __future__ import annotations

import re

from t2i_prompt_pipeline.models import (
    CameraDirection,
    CameraHeight,
    CastPlan,
    CharacterFraming,
    CharacterMoment,
    DepthMode,
    Frame,
    Gender,
    LensProfile,
    OutputLanguage,
    PromptBook,
    RenderedPrompt,
    ShotScale,
    StyleConstraints,
    Theme,
)

_FRAMING_TEXT = {
    OutputLanguage.CHINESE: {
        CharacterFraming.HEAD_AND_TORSO: "头部与躯干入画",
        CharacterFraming.FULL_BODY: "全身入画",
        CharacterFraming.HEAD_CROPPED_TORSO: "头部被裁切、躯干入画",
    },
    OutputLanguage.ENGLISH: {
        CharacterFraming.HEAD_AND_TORSO: "head and torso in frame",
        CharacterFraming.FULL_BODY: "full body in frame",
        CharacterFraming.HEAD_CROPPED_TORSO: (
            "head cropped out, torso in frame"
        ),
    },
}

_CAMERA_TEXT = {
    OutputLanguage.CHINESE: {
        "lens": {
            LensProfile.ULTRA_WIDE: "16mm超广角，强透视",
            LensProfile.WIDE: "24mm广角，自然空间延伸",
            LensProfile.NORMAL: "50mm标准镜头，自然透视",
            LensProfile.TELEPHOTO: "85mm长焦，压缩空间层次",
            LensProfile.FISHEYE: "鱼眼镜头，明显弧形畸变",
        },
        "scale": {
            ShotScale.ESTABLISHING: "环境建立镜头",
            ShotScale.WIDE: "远景",
            ShotScale.FULL_BODY: "全身群像",
            ShotScale.MEDIUM_FULL: "中全景",
            ShotScale.MEDIUM: "半身中景",
            ShotScale.CLOSE_UP: "近景",
        },
        "height": {
            CameraHeight.EYE_LEVEL: "平视机位",
            CameraHeight.HIGH_ANGLE: "高机位",
            CameraHeight.LOW_ANGLE: "低机位",
            CameraHeight.OVERHEAD: "正上方俯拍",
        },
        "direction": {
            CameraDirection.FRONT: "正面拍摄",
            CameraDirection.THREE_QUARTER: "三分之四侧面拍摄",
            CameraDirection.SIDE: "侧面拍摄",
            CameraDirection.TOP_DOWN: "垂直俯拍",
            CameraDirection.REAR_THREE_QUARTER: "后侧三分之四拍摄",
        },
        "depth": {
            DepthMode.SHALLOW: "较浅",
            DepthMode.MODERATE: "中等",
            DepthMode.DEEP: "较深",
        },
    },
    OutputLanguage.ENGLISH: {
        "lens": {
            LensProfile.ULTRA_WIDE: "16mm ultra-wide, strong perspective",
            LensProfile.WIDE: "24mm wide-angle, natural spatial expansion",
            LensProfile.NORMAL: "50mm normal lens, natural perspective",
            LensProfile.TELEPHOTO: "85mm telephoto, compressed spatial depth",
            LensProfile.FISHEYE: "fisheye lens, pronounced curved distortion",
        },
        "scale": {
            ShotScale.ESTABLISHING: "establishing shot",
            ShotScale.WIDE: "wide shot",
            ShotScale.FULL_BODY: "full-body group shot",
            ShotScale.MEDIUM_FULL: "medium full shot",
            ShotScale.MEDIUM: "medium shot",
            ShotScale.CLOSE_UP: "close-up",
        },
        "height": {
            CameraHeight.EYE_LEVEL: "eye-level",
            CameraHeight.HIGH_ANGLE: "high angle",
            CameraHeight.LOW_ANGLE: "low angle",
            CameraHeight.OVERHEAD: "overhead",
        },
        "direction": {
            CameraDirection.FRONT: "front",
            CameraDirection.THREE_QUARTER: "three-quarter",
            CameraDirection.SIDE: "side",
            CameraDirection.TOP_DOWN: "top-down",
            CameraDirection.REAR_THREE_QUARTER: "rear three-quarter",
        },
        "depth": {
            DepthMode.SHALLOW: "shallow",
            DepthMode.MODERATE: "moderate",
            DepthMode.DEEP: "deep",
        },
    },
}

_CHARACTER_ID_PATTERN = re.compile(r"T\d{2,4}-C(?P<index>\d{2})(?!\d)")
_FRAME_ID_PATTERN = re.compile(r"T\d{2,4}-F\d{2,3}(?!\d)")
_BARE_CHARACTER_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])C(?P<index>\d{2})(?![A-Za-z0-9_])"
)
_MODIFIER_TAIL_PATTERN = re.compile(r"\s+[A-Za-z]")
def _without_terminal_punctuation(value: str) -> str:
    return value.rstrip("。；，,.!?！？ ")


def _display_labels(
    theme: Theme,
    cast_plan: CastPlan,
    output_language: OutputLanguage,
) -> dict[str, str]:
    counters = {Gender.FEMALE: 0, Gender.MALE: 0}
    labels: dict[str, str] = {}
    for character, cast_member in zip(
        theme.characters,
        cast_plan.members,
        strict=True,
    ):
        gender = cast_member.gender
        counters[gender] += 1
        if cast_member.display_name is not None:
            label = cast_member.display_name
        elif output_language == OutputLanguage.ENGLISH:
            label = (
                f"Woman {counters[gender]}"
                if gender == Gender.FEMALE
                else f"Man {counters[gender]}"
            )
        else:
            label = (
                f"女{counters[gender]}"
                if gender == Gender.FEMALE
                else f"男{counters[gender]}"
            )
        labels[character.character_id] = label
    return labels


def _reference_text(
    style_constraints: StyleConstraints,
    output_language: OutputLanguage,
) -> str:
    separator = ", " if output_language == OutputLanguage.ENGLISH else "，"
    return separator.join(style_constraints.required_phrases)


def _setting_text(
    theme: Theme,
    style_constraints: StyleConstraints,
    output_language: OutputLanguage,
) -> str:
    setting = theme.setting
    separator = ", " if output_language == OutputLanguage.ENGLISH else "，"
    reference_phrases = {
        phrase.strip(" ，,；;：:")
        for phrase in style_constraints.required_phrases
    }
    location_segments = [
        segment.strip()
        for segment in re.split(r"[，,；;]", setting.location)
    ]
    location = separator.join(
        segment
        for segment in location_segments
        if segment and segment.strip(" ：:") not in reference_phrases
    )
    if not location:
        location = setting.location
    fixed_elements = "、".join(setting.fixed_elements)
    if output_language == OutputLanguage.ENGLISH:
        return (
            f"Time: {setting.time_context}; Location: {location}; "
            f"fixed elements: {fixed_elements}; "
            f"background population: {setting.background_population}; "
            f"atmosphere: {setting.atmosphere}"
        )
    return (
        f"时间：{setting.time_context}；场所：{location}；"
        f"固定布景：{fixed_elements}；"
        f"背景人物：{setting.background_population}；"
        f"氛围：{setting.atmosphere}"
    )


def _character_text(
    moment: CharacterMoment,
    label: str,
    output_language: OutputLanguage,
) -> str:
    visible_appearance = _without_terminal_punctuation(
        moment.visible_appearance
    )
    lighting_effect = _without_terminal_punctuation(moment.lighting_effect)
    action = _without_terminal_punctuation(moment.action)
    if output_language == OutputLanguage.ENGLISH:
        description = visible_appearance
    else:
        description = visible_appearance
    if moment.expression is None:
        if output_language == OutputLanguage.ENGLISH:
            return (
                f"{label}: {description}; lit by {lighting_effect}; {action}"
            )
        return (
            f"{label}——{description}；受光：{lighting_effect}；{action}"
        )
    expression = _without_terminal_punctuation(moment.expression)
    if output_language == OutputLanguage.ENGLISH:
        return (
            f"{label}: {description}; lit by {lighting_effect}; "
            f"{expression}; {action}"
        )
    return (
        f"{label}——{description}；受光：{lighting_effect}；"
        f"{expression}；{action}"
    )


def _staging_text(
    moment: CharacterMoment,
    label: str,
    output_language: OutputLanguage,
) -> str:
    placement = _without_terminal_punctuation(moment.placement)
    facing = _without_terminal_punctuation(moment.facing)
    framing = _FRAMING_TEXT[output_language][moment.framing]
    if output_language == OutputLanguage.ENGLISH:
        return f"{label} at {placement}, {framing}, {facing}"
    return f"{label}位于{placement}，{framing}，{facing}"


def _render_prompt(
    style_constraints: StyleConstraints,
    cast_plan: CastPlan,
    theme: Theme,
    frame: Frame,
    output_language: OutputLanguage,
    known_theme_pattern: re.Pattern[str] | None,
    known_frame_pattern: re.Pattern[str] | None,
) -> str:
    display_by_id = _display_labels(theme, cast_plan, output_language)
    item_separator = (
        "; " if output_language == OutputLanguage.ENGLISH else "；"
    )
    characters = item_separator.join(
        _character_text(
            moment,
            display_by_id[moment.character_id],
            output_language,
        )
        for moment in frame.characters
    )
    staging = item_separator.join(
        _staging_text(
            moment,
            display_by_id[moment.character_id],
            output_language,
        )
        for moment in frame.characters
    )
    camera_text = _CAMERA_TEXT[output_language]
    lens = camera_text["lens"][frame.camera.lens_profile]
    shot_scale = camera_text["scale"][frame.camera.shot_scale]
    if frame.camera.shot_scale == ShotScale.FULL_BODY and len(frame.characters) == 1:
        shot_scale = (
            "full-body shot"
            if output_language == OutputLanguage.ENGLISH
            else "全身画面"
        )
    camera_height = camera_text["height"][frame.camera.height]
    camera_direction = camera_text["direction"][frame.camera.direction]
    depth = frame.camera.depth_of_field
    depth_mode = camera_text["depth"][depth.mode]
    depth_target = _without_terminal_punctuation(depth.focus_target)
    depth_background = _without_terminal_punctuation(
        depth.background_effect
    )
    lighting = frame.camera.lighting
    light_source = _without_terminal_punctuation(lighting.source)
    light_position = _without_terminal_punctuation(lighting.position)
    light_color = _without_terminal_punctuation(lighting.color)
    scene_light_effect = _without_terminal_punctuation(
        lighting.scene_effect
    )
    if output_language == OutputLanguage.ENGLISH:
        parts = (
            _reference_text(style_constraints, output_language),
            _setting_text(theme, style_constraints, output_language),
            f"Characters: {characters}",
            (
                f"Camera: {lens}, {shot_scale}, {camera_height}, "
                f"{camera_direction}; Depth: {depth_mode}, "
                f"focus on {depth_target}, "
                f"{depth_background}; Composition: {staging}"
            ),
            (
                f"Lighting: {light_source} from "
                f"{light_position}, {light_color}; Light distribution: "
                f"{scene_light_effect}"
            ),
        )
        text = ". ".join(
            _without_terminal_punctuation(part) for part in parts if part
        ) + "."
        unknown_character = "character"
        current_frame = "current shot"
        current_theme = "current theme"
    else:
        parts = (
            _reference_text(style_constraints, output_language),
            _setting_text(theme, style_constraints, output_language),
            f"人物：{characters}",
            (
                f"摄影：{lens}，{shot_scale}，{camera_height}，"
                f"{camera_direction}；景深：{depth_mode}，"
                f"焦点落在{depth_target}，{depth_background}；"
                f"构图：{staging}"
            ),
            (
                f"光线：{light_source}，来自{light_position}，"
                f"呈{light_color}；明暗关系：{scene_light_effect}"
            ),
        )
        text = "。".join(
            _without_terminal_punctuation(part) for part in parts if part
        ) + "。"
        unknown_character = "人物"
        current_frame = "当前镜头"
        current_theme = "当前主题"
    display_by_index = {
        int(character_id.rsplit("C", 1)[1]): label
        for character_id, label in display_by_id.items()
    }
    text = _CHARACTER_ID_PATTERN.sub(
        lambda match: display_by_id.get(
            match.group(0),
            display_by_index.get(
                int(match.group("index")),
                unknown_character,
            ),
        ),
        text,
    )
    text = _FRAME_ID_PATTERN.sub(current_frame, text)
    text = _BARE_CHARACTER_ID_PATTERN.sub(
        lambda match: display_by_index.get(
            int(match.group("index")),
            match.group(0),
        ),
        text,
    )
    text = _replace_known_bare_ids(
        text,
        known_frame_pattern,
        current_frame,
    )
    return _replace_known_bare_ids(
        text,
        known_theme_pattern,
        current_theme,
    )


def _replace_known_bare_ids(
    text: str,
    identifier_pattern: re.Pattern[str] | None,
    replacement: str,
) -> str:
    """Scrub leaked internal IDs while keeping look-alike vocabulary intact.

    A leaked ID is a bare reference to another object, so it ends the phrase or
    runs straight into the surrounding prose. A token that modifies a following
    Latin word ("F16 aperture", "T90 highway exit") is real vocabulary instead.
    """
    if identifier_pattern is None:
        return text

    def replace(match: re.Match[str]) -> str:
        if _MODIFIER_TAIL_PATTERN.match(text, match.end()):
            return match.group(0)
        return replacement

    return identifier_pattern.sub(replace, text)


def _compile_bare_id_pattern(
    identifiers: set[str],
) -> re.Pattern[str] | None:
    if not identifiers:
        return None
    return re.compile(
        r"(?<![A-Za-z0-9_-])(?:"
        + "|".join(
            re.escape(identifier)
            for identifier in sorted(identifiers, key=len, reverse=True)
        )
        + r")(?![A-Za-z0-9_])"
    )


def render_book(
    book: PromptBook,
    output_language: OutputLanguage,
) -> list[RenderedPrompt]:
    known_theme_pattern = _compile_bare_id_pattern(
        {theme_book.theme.theme_id for theme_book in book.themes}
    )
    known_frame_pattern = _compile_bare_id_pattern(
        {
            f"F{frame.frame_id.rsplit('-F', 1)[1]}"
            for theme_book in book.themes
            for frame in theme_book.frames
        }
    )
    return [
        RenderedPrompt(
            theme_id=theme_book.theme.theme_id,
            frame_id=frame.frame_id,
            text=_render_prompt(
                book.style_constraints,
                book.cast_plan,
                theme_book.theme,
                frame,
                output_language,
                known_theme_pattern,
                known_frame_pattern,
            ),
        )
        for theme_book in book.themes
        for frame in theme_book.frames
    ]
