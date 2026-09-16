"""Compile a film-style profile into a current-contract Story Description."""

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
        return f"{request.director}执导的作品{labels}"
    return f"{labels}, directed by {request.director}"


def compile_story_description(
    request: FilmStyleRequest,
    profile: FilmStyleProfile,
) -> str:
    if request.output_language == "english":
        section = _compile_english(request, profile)
    else:
        section = _compile_chinese(request, profile)
    body = request.base_brief.removeprefix("BRIEF\n\n")
    return f"BRIEF\n\n{section}\n\n{body}"


def _compile_chinese(
    request: FilmStyleRequest,
    profile: FilmStyleProfile,
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
    return f"""WORK-SPECIFIC FILM STYLE PROFILE

只把{source}作为作品层面的视觉参考。不得把该来源扩大为对导演全部个人风格的模仿，也不得复制原作人物、演员肖像、对白、剧情、标志性服装、独特道具或可逐镜对应的构图。
本节要求的 Frame 第一分句唯一来源署名优先于基础 brief 中任何禁止真实电影名或
导演名的宽泛规则；该例外只适用于这一次来源署名，不允许在其余正文重复。

精确风格名称

“{profile.profile_name}”

作品集合风格总结

{profile.style_summary}

逐部电影风格总结

{work_summaries}

色彩系统

{profile.palette}

构图秩序

{profile.composition}

人物调度

{profile.blocking}

镜头语言

{profile.camera}

光线

{profile.lighting}

运动语法

{profile.movement}

场景与美术

{profile.production_design}

材质与成片

{profile.material_and_finish}

每个 Theme 必须从以上作品集合中重新组合一套原创、可见、可摄影执行的
风格系统，并为该 Theme 创建一个不含导演名和电影名的精确原创风格名称。
每个 Frame 必须逐字复述母风格名称“{profile.profile_name}”、母风格总结和
其 Theme 的精确原创风格名称，并在画面中保留色彩、构图、调度、光线、
运动、材质和成片特征中的至少五项。

每个 Frame 的第一分句必须准确且只出现一次以下来源关系：
“这是一帧以{source}为作品层面视觉参考的原创电影剧照，
采用母风格‘{profile.profile_name}’及<Theme 的精确原创风格名称>”；
紧接着必须写出“作品集合风格总结：{profile.style_summary}”，再说明主导色、
构图秩序和当前完成态动作。导演、电影、母风格名称与风格总结缺少任何一项
都必须重写。作品署名不能替代具体视觉描述。

必须使用的可见装置

{devices}

拒绝规则

{refusals}
- 不得输出导演个人风格的泛化标签。
- 不得仅靠电影名、导演名、类型名或情绪形容词传达风格。
- 不得复制来源作品的角色、演员外貌、对白、剧情、独特道具或具体镜头。
"""


def _compile_english(
    request: FilmStyleRequest,
    profile: FilmStyleProfile,
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
    return f"""WORK-SPECIFIC FILM STYLE PROFILE

Use only {source} as work-specific visual references. Do not broaden the source
into imitation of the director's unrestricted personal style. Do not copy
characters, actor likenesses, dialogue, plots, signature costumes, unique props,
or shot-for-shot compositions.
The single source attribution required in each Frame's first clause overrides
any broader ban on real film or director names in the base brief. This exception
applies only to that attribution and nowhere else in the prose.

EXACT STYLE NAME

"{profile.profile_name}"

AGGREGATE STYLE SUMMARY

{profile.style_summary}

PER-FILM STYLE SUMMARIES

{work_summaries}

PALETTE

{profile.palette}

COMPOSITION

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

Every Theme must recombine the work-specific evidence above into an original,
visible, photographically executable system and create an exact original style
name containing neither the director name nor a film title. Every Frame must
repeat the parent style name "{profile.profile_name}", its aggregate style
summary, and its Theme's exact style name, then visibly preserve at least five
traits across palette, composition, blocking, light, movement, material, and
finish.

Every Frame's first clause must state this source relationship exactly once:
"This is an original feature-film still using {source} as work-specific visual
references, using the parent style '{profile.profile_name}' and <the Theme's
exact original style name>"; immediately follow it with "Aggregate style
summary: {profile.style_summary}", the dominant palette, compositional order,
and completed current action. The director, films, parent style name, and style
summary are all mandatory. Attribution never replaces concrete visual
description.

REQUIRED VISIBLE DEVICES

{devices}

REFUSAL RULES

{refusals}
- Do not output a generic label for the director's personal style.
- Do not communicate style only through a film title, director name, genre, or mood.
- Do not copy source characters, actor likenesses, dialogue, plots, unique props,
  or exact shots.
"""
