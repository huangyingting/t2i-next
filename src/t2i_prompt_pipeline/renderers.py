"""Deterministic rendering with one owner for each visual fact."""

from __future__ import annotations

import re

from t2i_prompt_pipeline.models import (
    CastPlan,
    CharacterFraming,
    CharacterMoment,
    Frame,
    Gender,
    OutputLanguage,
    PromptBook,
    RenderedPrompt,
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
        if output_language == OutputLanguage.ENGLISH:
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


def _capture_text(
    style_constraints: StyleConstraints,
    output_language: OutputLanguage,
) -> str:
    phrases = "，".join(style_constraints.required_phrases)
    if output_language == OutputLanguage.ENGLISH:
        return f"Live-action photography, {phrases}" if phrases else (
            "Live-action photography"
        )
    return f"实拍摄影，{phrases}" if phrases else "实拍摄影"


def _setting_text(
    theme: Theme,
    output_language: OutputLanguage,
) -> str:
    setting = theme.setting
    fixed_elements = "、".join(setting.fixed_elements)
    if output_language == OutputLanguage.ENGLISH:
        return (
            f"Location: {setting.location}; fixed elements: {fixed_elements}; "
            f"background population: {setting.background_population}; "
            f"atmosphere: {setting.atmosphere}"
        )
    return (
        f"场所：{setting.location}；固定布景：{fixed_elements}；"
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
            f"{label}：{description}；受光：{lighting_effect}；{action}"
        )
    expression = _without_terminal_punctuation(moment.expression)
    if output_language == OutputLanguage.ENGLISH:
        return (
            f"{label}: {description}; lit by {lighting_effect}; "
            f"{expression}; {action}"
        )
    return (
        f"{label}：{description}；受光：{lighting_effect}；"
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
        return f"{label}: {placement}, {framing}, {facing}"
    return f"{label}：{placement}，{framing}，{facing}"


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
    camera_shot = _without_terminal_punctuation(frame.camera.shot)
    camera_view = _without_terminal_punctuation(frame.camera.view)
    depth = frame.camera.depth_of_field
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
            _capture_text(style_constraints, output_language),
            _setting_text(theme, output_language),
            f"Characters: {characters}",
            (
                f"Shot: {camera_shot}; View: {camera_view}; "
                f"Depth of field: {depth.mode.value}, focus on {depth_target}, "
                f"{depth_background}; Composition: {staging}; "
                f"Lighting: {light_source} from "
                f"{light_position}, {light_color}; Scene light: "
                f"{scene_light_effect}"
            ),
        )
        text = ". ".join(
            _without_terminal_punctuation(part) for part in parts
        ) + "."
        unknown_character = "character"
        current_frame = "current shot"
        current_theme = "current theme"
    else:
        parts = (
            _capture_text(style_constraints, output_language),
            _setting_text(theme, output_language),
            f"人物：{characters}",
            (
                f"镜头：{camera_shot}；视角：{camera_view}；"
                f"景深：{depth.mode.value}；焦点：{depth_target}；"
                f"背景成像：{depth_background}；构图：{staging}；"
                f"光源：{light_source}；"
                f"光位：{light_position}；光色：{light_color}；"
                f"场景明暗：{scene_light_effect}"
            ),
        )
        text = "。".join(
            _without_terminal_punctuation(part) for part in parts
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
