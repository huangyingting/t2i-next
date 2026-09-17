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
    work_summaries = "\n".join(
        f"- {_work_label(work, chinese=True)}：{summary}"
        for work, summary in zip(
            request.works,
            profile.work_style_summaries,
            strict=True,
        )
    )
    devices = "\n".join(f"- {item}" for item in profile.signature_devices)
    refusals = "\n".join(f"- {item}" for item in profile.refusal_rules)
    direction = scene_direction or (
        "生成原创、可直接用于图像生成的电影场景。每个 Theme 使用不同的具体地点、"
        "人物关系、活动和视觉重点。场景必须像真实长片中的一个完整瞬间，不是海报、"
        "广告、拼贴或调色演示。"
    )
    return f"""WORK-SPECIFIC VISUAL CONTEXT

作品来源

只把{source}作为作品层面的视觉参考。不得扩大为对导演全部个人风格的模仿，
也不得复制原作人物、演员肖像、对白、剧情、标志性服装、独特道具或具体镜头。

每个 Frame 必须准确且只在第一句使用以下来源说明：
“这是一个采用{source}视觉风格的原创电影场景。”

场景要求

{direction}

作品视觉概述

{profile.style_summary}

逐部作品视觉证据

{work_summaries}

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
    work_summaries = "\n".join(
        f"- {_work_label(work, chinese=False)}: {summary}"
        for work, summary in zip(
            request.works,
            profile.work_style_summaries,
            strict=True,
        )
    )
    devices = "\n".join(f"- {item}" for item in profile.signature_devices)
    refusals = "\n".join(f"- {item}" for item in profile.refusal_rules)
    direction = scene_direction or (
        "Create original, directly imageable film scenes. Give every Theme a "
        "different specific location, relationship, activity, and visual focus. "
        "Each scene must be one complete feature-film instant, not a poster, "
        "advertisement, collage, or grading demonstration."
    )
    return f"""WORK-SPECIFIC VISUAL CONTEXT

SOURCE

Use only {source} as work-specific visual references. Do not broaden the source
into imitation of the director's unrestricted personal style. Do not copy
characters, actor likenesses, dialogue, plots, signature costumes, unique props,
or exact shots.

Every Frame must use this source sentence exactly once as its first sentence:
"This is an original film scene using the visual style of {source}."

SCENE DIRECTION

{direction}

WORK-SET VISUAL SUMMARY

{profile.style_summary}

PER-WORK VISUAL EVIDENCE

{work_summaries}

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
