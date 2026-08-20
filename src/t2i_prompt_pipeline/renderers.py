"""Deterministic rendering with one owner for each visual fact."""

from __future__ import annotations

import re

from t2i_prompt_pipeline.models import (
    CastMember,
    CastPlan,
    Character,
    CharacterMoment,
    Frame,
    Gender,
    OutputLanguage,
    PromptBook,
    RenderedPrompt,
    Theme,
)

_CHARACTER_ID_PATTERN = re.compile(r"T\d{2,4}-C(?P<index>\d{2})(?!\d)")
_FRAME_ID_PATTERN = re.compile(r"T\d{2,4}-F\d{2,3}(?!\d)")
_BARE_CHARACTER_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])C(?P<index>\d{2})(?![A-Za-z0-9_])"
)
_BARE_INTERNAL_ID_LABEL_PATTERN = re.compile(r"[CFT]\d{2,4}")
_MODIFIER_TAIL_PATTERN = re.compile(r"\s+[A-Za-z]")
_GENERIC_LABEL_PATTERN = re.compile(
    r"^(?:女性|男性|成年女性|成年男性|女主角|男主角|人物\d*|角色\d*|"
    r"female\s*\d*|male\s*\d*|adult woman|adult man|"
    r"female lead|male lead|"
    r"woman|man|character\s*\d*|person\s*\d*)$",
    re.IGNORECASE,
)


def _without_terminal_punctuation(value: str) -> str:
    return value.rstrip("。；，,.!?！？ ")


def _display_labels(
    theme: Theme,
    output_language: OutputLanguage,
) -> dict[str, str]:
    counters = {Gender.FEMALE: 0, Gender.MALE: 0}
    labels: dict[str, str] = {}
    for character in theme.characters:
        counters[character.gender] += 1
        if output_language == OutputLanguage.ENGLISH:
            fallback = (
                f"Woman {counters[character.gender]}"
                if character.gender == Gender.FEMALE
                else f"Man {counters[character.gender]}"
            )
        else:
            fallback = (
                f"女{counters[character.gender]}"
                if character.gender == Gender.FEMALE
                else f"男{counters[character.gender]}"
            )
        label = character.label
        if (
            _GENERIC_LABEL_PATTERN.fullmatch(label)
            or _CHARACTER_ID_PATTERN.search(label)
            or _BARE_INTERNAL_ID_LABEL_PATTERN.fullmatch(label)
        ):
            label = fallback
        labels[character.character_id] = label
    return labels


def _stable_character_text(
    character: Character,
    cast_member: CastMember,
    label: str,
    output_language: OutputLanguage,
) -> str:
    appearance = _without_terminal_punctuation(character.appearance)
    outfit = _without_terminal_punctuation(character.outfit)
    role = (
        _without_terminal_punctuation(cast_member.role)
        if cast_member.role
        else None
    )
    if output_language == OutputLanguage.ENGLISH:
        descriptors = []
        if role and role.casefold() != label.casefold():
            descriptors.append(role)
        if not re.fullmatch(r"(?:Woman|Man) \d+", label):
            descriptors.append(
                "female"
                if character.gender == Gender.FEMALE
                else "male"
            )
        descriptors.append(f"age {character.age}")
        identity = f"{label} ({', '.join(descriptors)})"
        return f"{identity}: {appearance}; outfit: {outfit}"
    descriptors = []
    if role and role != label:
        descriptors.append(role)
    if not re.fullmatch(r"[男女]\d+", label):
        descriptors.append(character.gender.value)
    descriptors.append(f"{character.age}岁")
    identity = f"{label}（{'，'.join(descriptors)}）"
    return f"{identity}：{appearance}；服饰：{outfit}"


def _moment_text(
    moment: CharacterMoment,
    label: str,
    output_language: OutputLanguage,
) -> str:
    action = _without_terminal_punctuation(moment.action)
    if moment.expression is None:
        if output_language == OutputLanguage.ENGLISH:
            return f"{label}: {action}"
        return f"{label}：{action}"
    expression = _without_terminal_punctuation(moment.expression)
    if output_language == OutputLanguage.ENGLISH:
        return f"{label}: {expression}; {action}"
    return f"{label}：{expression}；{action}"


def _render_prompt(
    cast_plan: CastPlan,
    theme: Theme,
    frame: Frame,
    output_language: OutputLanguage,
    known_theme_pattern: re.Pattern[str] | None,
    known_frame_pattern: re.Pattern[str] | None,
) -> str:
    character_by_id = {
        character.character_id: character for character in theme.characters
    }
    display_by_id = _display_labels(theme, output_language)
    item_separator = (
        "; " if output_language == OutputLanguage.ENGLISH else "；"
    )
    stable_characters = item_separator.join(
        _stable_character_text(
            character_by_id[moment.character_id],
            cast_plan.members[
                int(moment.character_id.rsplit("C", 1)[1]) - 1
            ],
            display_by_id[moment.character_id],
            output_language,
        )
        for moment in frame.characters
    )
    moments = item_separator.join(
        _moment_text(
            moment,
            display_by_id[moment.character_id],
            output_language,
        )
        for moment in frame.characters
    )
    camera_shot = _without_terminal_punctuation(frame.camera.shot)
    camera_view = _without_terminal_punctuation(frame.camera.view)
    camera_composition = _without_terminal_punctuation(
        frame.camera.composition
    )
    if output_language == OutputLanguage.ENGLISH:
        parts = (
            theme.style,
            f"Theme: {theme.title}",
            f"Scene: {theme.scene}",
            f"Characters: {stable_characters}",
            (
                f"Shot: {camera_shot}; View: {camera_view}; "
                f"Composition: {camera_composition}"
            ),
            f"Current characters: {moments}",
            f"Details: {frame.details}",
        )
        text = ". ".join(
            _without_terminal_punctuation(part) for part in parts
        ) + "."
        unknown_character = "character"
        current_frame = "current shot"
        current_theme = "current theme"
    else:
        parts = (
            theme.style,
            f"主题：{theme.title}",
            f"场景：{theme.scene}",
            f"人物：{stable_characters}",
            (
                f"镜头：{camera_shot}；视角：{camera_view}；"
                f"构图：{camera_composition}"
            ),
            f"当前人物：{moments}",
            f"细节：{frame.details}",
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
