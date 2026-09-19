"""Exact frozen-prefix handling, independent of punctuation inside film names."""

from __future__ import annotations

from t2i_film_style_pipeline.prompt_models import (
    FilmPromptRequest,
    NarrativeTheme,
    OutputLanguage,
)


def canonical_anchor_sentence(
    request: FilmPromptRequest,
    theme: NarrativeTheme,
    scene: str | None,
) -> str | None:
    if scene is None:
        return None
    characters = [item.canonical_name for item in theme.selected_cast]
    if request.output_language == OutputLanguage.ENGLISH:
        return (
            f"The original characters {', '.join(characters)} are in the "
            f'canonical setting "{scene}". '
        )
    return f"原作人物{'、'.join(characters)}位于原作场景“{scene}”。"


def anchor_insertion(request: FilmPromptRequest, sentence: str) -> str:
    separator = " " if request.output_language == OutputLanguage.ENGLISH else ""
    return separator + sentence


def frame_body(
    request: FilmPromptRequest,
    theme: NarrativeTheme,
    prose: str,
    *,
    strip_anchor: bool = True,
) -> str:
    source = request.frame_source_sentence
    if not prose.startswith(source):
        return prose
    body = prose[len(source) :]
    if strip_anchor:
        for scene in request.source_films[theme.source_work_index].anchors.scenes:
            sentence = canonical_anchor_sentence(
                request, theme, scene.canonical_name
            )
            if sentence is not None:
                insertion = anchor_insertion(request, sentence)
                if body.startswith(insertion):
                    return body[len(insertion) :]
    return body
