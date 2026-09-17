"""Compile work-specific visual evidence into dynamic story context."""

from __future__ import annotations

from t2i_film_style_pipeline.models import (
    FilmStyleProfile,
    FilmStyleRequest,
    FilmWorkReference,
)


def _work_label(work: FilmWorkReference, *, chinese: bool) -> str:
    if chinese:
        return (
            f"《{work.title}》（{work.year}）"
            if work.year is not None
            else f"《{work.title}》"
        )
    return (
        f"{work.title} ({work.year})"
        if work.year is not None
        else work.title
    )


def source_attribution(request: FilmStyleRequest) -> str:
    chinese = request.output_language == "chinese"
    labels = "、".join(
        _work_label(work, chinese=chinese) for work in request.works
    )
    if chinese:
        return f"{request.director}导演的{labels}"
    return f"{labels}, directed by {request.director}"


def frame_source_sentence(request: FilmStyleRequest) -> str:
    source = source_attribution(request)
    if request.output_language == "chinese":
        return f"这是一个基于{source}原作人物与场景重新构图的电影画面。"
    return f"This film image recomposes characters and settings from {source}."


def compile_story_description(
    request: FilmStyleRequest,
    profile: FilmStyleProfile,
    *,
    scene_direction: str | None = None,
) -> str:
    section = (
        _compile_english(request, profile, scene_direction)
        if request.output_language == "english"
        else _compile_chinese(request, profile, scene_direction)
    )
    return f"BRIEF\n\n{section}"


def _compile_chinese(
    request: FilmStyleRequest,
    profile: FilmStyleProfile,
    scene_direction: str | None,
) -> str:
    source = source_attribution(request)
    source_sentence = frame_source_sentence(request)
    work_summaries = "\n".join(
        f"- {_work_label(work, chinese=True)}：{summary}"
        for work, summary in zip(
            request.works,
            profile.work_style_summaries,
            strict=True,
        )
    )
    work_anchors = "\n\n".join(
        "\n".join(
            (
                f"### {_work_label(work, chinese=True)}",
                "原作成年人物",
                *(
                    f"- {character.canonical_name}："
                    f"{character.identity_and_appearance}；"
                    f"原作服装：{character.canonical_costume}；"
                    f"服装短语：{'、'.join(character.costume_features)}"
                    for character in anchors.adult_characters
                ),
                "原作场景",
                *(
                    f"- {scene.canonical_name}："
                    f"原作情境：{scene.narrative_context}；"
                    f"环境：{scene.environment}；"
                    f"环境短语：{'、'.join(scene.environment_features)}；"
                    f"道具短语：{'、'.join(scene.canonical_props)}"
                    for scene in anchors.scenes
                ),
            )
        )
        for work, anchors in zip(
            request.works,
            profile.work_anchors,
            strict=True,
        )
    )
    devices = "\n".join(f"- {item}" for item in profile.signature_devices)
    refusals = "\n".join(f"- {item}" for item in profile.refusal_rules)
    direction = scene_direction or (
        "从下列作品锚点中选择原作成年人物与实际场景，生成可直接用于图像生成的"
        "电影画面。每个 Theme 优先使用不同的原作场景、人物组合、活动瞬间和视觉"
        "重点。画面必须像原作长片中的一个完整瞬间，不是海报、广告、拼贴或调色演示。"
    )
    return f"""WORK-SPECIFIC VISUAL CONTEXT

作品来源

只使用{source}提供的作品事实和视觉语言，不得扩大为对导演全部个人风格的模仿。
必须使用下列原作成年人物与实际场景；不得虚构或跨作品拼接，不得使用演员姓名、
逐字对白或逐镜复制原作具体镜头。

每个 Frame 必须准确且只在第一句使用以下来源说明：
“{source_sentence}”

场景要求

{direction}

作品视觉概述

{profile.style_summary}

逐部作品视觉证据

{work_summaries}

原作人物与场景锚点

{work_anchors}

色彩

{profile.palette}

构图与空间

{profile.composition}

人物调度

{profile.blocking}

镜头

{profile.camera}

光线

{profile.lighting}

运动

{profile.movement}

场景与美术

{profile.production_design}

材质与成片

{profile.material_and_finish}

优先采用的可见手段

{devices}

拒绝项

{refusals}
"""


def _compile_english(
    request: FilmStyleRequest,
    profile: FilmStyleProfile,
    scene_direction: str | None,
) -> str:
    source = source_attribution(request)
    source_sentence = frame_source_sentence(request)
    work_summaries = "\n".join(
        f"- {_work_label(work, chinese=False)}: {summary}"
        for work, summary in zip(
            request.works,
            profile.work_style_summaries,
            strict=True,
        )
    )
    work_anchors = "\n\n".join(
        "\n".join(
            (
                f"### {_work_label(work, chinese=False)}",
                "Adult characters from the film",
                *(
                    f"- {character.canonical_name}: "
                    f"{character.identity_and_appearance}; "
                    f"canonical costume: {character.canonical_costume}; "
                    f"required costume phrases: "
                    f"{', '.join(character.costume_features)}"
                    for character in anchors.adult_characters
                ),
                "Settings from the film",
                *(
                    f"- {scene.canonical_name}: "
                    f"source context: {scene.narrative_context}; "
                    f"environment: {scene.environment}; "
                    f"required environment phrases: "
                    f"{', '.join(scene.environment_features)}; "
                    f"required prop phrases: {', '.join(scene.canonical_props)}"
                    for scene in anchors.scenes
                ),
            )
        )
        for work, anchors in zip(
            request.works,
            profile.work_anchors,
            strict=True,
        )
    )
    devices = "\n".join(f"- {item}" for item in profile.signature_devices)
    refusals = "\n".join(f"- {item}" for item in profile.refusal_rules)
    direction = scene_direction or (
        "Select adult characters and an actual setting from the work anchors "
        "below to create directly imageable film scenes. Prefer a different "
        "canonical setting, character combination, activity instant, and visual "
        "focus for each Theme. Each image must feel like one complete instant "
        "from the source feature, not a poster, advertisement, collage, or "
        "grading demonstration."
    )
    return f"""WORK-SPECIFIC VISUAL CONTEXT

SOURCE

Use only facts and visual language from {source}. Do not broaden the source into
imitation of the director's unrestricted personal style. Use the canonical adult
characters and actual settings listed below. Do not invent or mix anchors across
works, use actor names, reproduce dialogue verbatim, or copy an exact shot.

Every Frame must use this source sentence exactly once as its first sentence:
"{source_sentence}"

SCENE DIRECTION

{direction}

WORK-SET VISUAL SUMMARY

{profile.style_summary}

PER-WORK VISUAL EVIDENCE

{work_summaries}

CHARACTER AND SETTING ANCHORS

{work_anchors}

PALETTE

{profile.palette}

COMPOSITION AND SPACE

{profile.composition}

BLOCKING

{profile.blocking}

CAMERA

{profile.camera}

LIGHTING

{profile.lighting}

MOVEMENT

{profile.movement}

PRODUCTION DESIGN

{profile.production_design}

MATERIAL AND FINISH

{profile.material_and_finish}

PREFERRED VISIBLE DEVICES

{devices}

REFUSALS

{refusals}
"""
