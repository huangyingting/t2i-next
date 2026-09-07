"""Render narrative scenes as cinematic prose and image prompts."""

from __future__ import annotations

import re

from t2i_story_pipeline.models import (
    NarrativeScene,
    NarrativeSequence,
    NarrativeTheme,
    OutputLanguage,
    RenderedNarrative,
    StoryBlueprint,
    StoryCharacter,
)


def render_narratives(
    blueprint: StoryBlueprint,
    theme: NarrativeTheme,
    sequence: NarrativeSequence,
    language: OutputLanguage = OutputLanguage.CHINESE,
) -> list[RenderedNarrative]:
    characters = {
        character.character_id: character for character in blueprint.characters
    }
    return [
        RenderedNarrative(
            scene_id=scene.scene_id,
            prose=_resolve_internal_references(
                _render_prose(scene),
                characters,
            ),
            prompt=_resolve_internal_references(
                _render_narrative_prompt(
                    scene,
                    characters,
                    theme,
                    language,
                ),
                characters,
            ),
        )
        for scene in sequence.scenes
    ]


def _render_prose(scene: NarrativeScene) -> str:
    sections = [
        scene.temporal_spatial_opening,
        *scene.environmental_evidence,
        scene.character_entry,
        *scene.source_context,
    ]
    sections.extend(
        (
            *(
                clause
                for action in scene.present_actions
                for clause in (
                    action.action,
                    action.visible_response,
                    action.resulting_state,
                )
            ),
            *scene.material_and_physical_feedback,
            scene.camera_composition,
            scene.lighting_and_color,
            *scene.sensory_evidence,
            *(
                _visible_text_instruction(
                    item.content,
                    item.carrier,
                    item.placement,
                    item.appearance,
                )
                for item in scene.visible_text
            ),
            scene.thematic_closure,
        )
    )
    separator = "" if any(_contains_cjk(item) for item in sections) else " "
    return separator.join(_as_sentence(item) for item in sections)


def _render_narrative_prompt(
    scene: NarrativeScene,
    characters: dict[str, StoryCharacter],
    theme: NarrativeTheme,
    language: OutputLanguage,
) -> str:
    if language == OutputLanguage.ENGLISH:
        cast = "; ".join(
            f"{characters[character_id].display_name}, "
            f"age {characters[character_id].age}, "
            f"{characters[character_id].appearance}, wearing "
            f"{characters[character_id].outfit}"
            for character_id in scene.visible_character_ids
        )
        actions = "; ".join(
            ", ".join(
                _without_terminal_punctuation(clause)
                for clause in (
                    action.action,
                    action.visible_response,
                    action.resulting_state,
                )
            )
            for action in scene.present_actions
        )
        environment = "; ".join(
            _without_terminal_punctuation(item)
            for item in (
                *scene.environmental_evidence,
                *scene.material_and_physical_feedback,
                *scene.sensory_evidence,
            )
        )
        theme_text = "; ".join(
            _without_terminal_punctuation(item)
            for item in (*scene.source_context, scene.thematic_closure)
        )
        creative = "; ".join(
            (
                theme.creative_intent.emotional_core,
                theme.creative_intent.narrative_tension,
                theme.creative_intent.decisive_moment,
                theme.creative_intent.visual_motif,
                theme.creative_intent.restraint,
            )
        )
        sections = [
            f"Creative direction: {creative}",
            "Time and place: "
            + _without_terminal_punctuation(scene.temporal_spatial_opening),
            f"Visible characters: {cast}",
            "Blocking: " + _without_terminal_punctuation(scene.character_entry),
            f"Interaction and action: {actions}",
            f"Emotion and theme: {theme_text}",
            f"Environment: {environment}",
            "Camera: " + _without_terminal_punctuation(scene.camera_composition),
            "Lighting: " + _without_terminal_punctuation(scene.lighting_and_color),
        ]
        if scene.visible_text:
            sections.append(
                "Visible text: "
                + "; ".join(
                    _visible_text_instruction(
                        item.content,
                        item.carrier,
                        item.placement,
                        item.appearance,
                    )
                    for item in scene.visible_text
                )
            )
        return ". ".join(sections) + "."
    cast = "；".join(
        f"{characters[character_id].display_name}，"
        f"{characters[character_id].age}岁，"
        f"{characters[character_id].appearance}，"
        f"身穿{characters[character_id].outfit}"
        for character_id in scene.visible_character_ids
    )
    actions = "；".join(
        "，".join(
            _without_terminal_punctuation(clause)
            for clause in (
                action.action,
                action.visible_response,
                action.resulting_state,
            )
        )
        for action in scene.present_actions
    )
    environment = "；".join(
        _without_terminal_punctuation(item)
        for item in (
            *scene.environmental_evidence,
            *scene.material_and_physical_feedback,
            *scene.sensory_evidence,
        )
    )
    theme_text = "；".join(
        _without_terminal_punctuation(item)
        for item in (*scene.source_context, scene.thematic_closure)
    )
    creative = "；".join(
        (
            theme.creative_intent.emotional_core,
            theme.creative_intent.narrative_tension,
            theme.creative_intent.decisive_moment,
            theme.creative_intent.visual_motif,
            theme.creative_intent.restraint,
        )
    )
    sections = [
        f"创意主线：{creative}",
        f"时间与地点：{scene.temporal_spatial_opening.rstrip('。')}",
        f"入画人物：{cast}",
        f"人物调度：{scene.character_entry.rstrip('。')}",
        f"互动与动作：{actions}",
        f"情绪与主题：{theme_text}",
        f"环境：{environment}",
        f"摄影：{scene.camera_composition.rstrip('。')}",
        f"光线：{scene.lighting_and_color.rstrip('。')}",
    ]
    if scene.visible_text:
        sections.append(
            "画面文字："
            + "；".join(
                _visible_text_instruction(
                    item.content,
                    item.carrier,
                    item.placement,
                    item.appearance,
                )
                for item in scene.visible_text
            )
        )
    return "。".join(sections) + "。"


def _as_sentence(value: str) -> str:
    return value if value.endswith(("。", ".", "！", "!", "？", "?")) else f"{value}。"


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= character <= "\u9fff" for character in value)


def _without_terminal_punctuation(value: str) -> str:
    return value.rstrip("。；，,.!?！？ ")


def _visible_text_instruction(
    content: str,
    carrier: str,
    placement: str,
    appearance: str,
) -> str:
    quoted = content.replace('"', '\\"')
    return f'"{quoted}"，{carrier}，{placement}，{appearance}'


def _resolve_internal_references(
    value: str,
    characters: dict[str, StoryCharacter],
) -> str:
    for character_id, character in characters.items():
        value = value.replace(character_id, character.display_name)
    value = re.sub(r"B\d{2}(?:\s*至\s*B\d{2})?", "此前过程", value)
    return re.sub(r"S\d{2}", "当前画面", value)
