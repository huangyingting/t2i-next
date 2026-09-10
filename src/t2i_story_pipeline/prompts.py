"""Provider instructions for themes and final narrative paragraphs."""

from __future__ import annotations

import json

from t2i_story_pipeline.models import (
    ContentLevel,
    NarrativeTheme,
    OutputLanguage,
    StoryRequest,
)
from t2i_story_pipeline.provider import ChatMessage

_CONTENT_LEVEL_INSTRUCTIONS = {
    ContentLevel.AESTHETIC: (
        "Use the aesthetic narrative level. Prioritize story, character, "
        "composition, and atmosphere, and do not add sexual content. If the "
        "story already requests adult nudity or intimacy, it may appear "
        "naturally, but do not describe explicit sexual activity."
    ),
    ContentLevel.EROTIC: (
        "Use the adult erotic narrative level. Adult nudity, intimate contact, "
        "or unmistakable bodily tension must be immediately visible rather "
        "than reduced to an ordinary clothed portrait, preparation, or "
        "atmosphere alone. Keep it non-explicit and make the erotic content "
        "serve the relationship. With multiple participants, show willingness, "
        "response, and ability to stop through gaze, posture, or active contact."
    ),
    ContentLevel.HARDCORE: (
        "Use the explicit erotic narrative level for adults aged twenty-one or "
        "older only. Explicit sexual activity must actually be occurring and "
        "serve the relationship and current story rather than becoming an "
        "isolated anatomical description. Every participant must visibly "
        "remain alert, willing, responsive, and able to stop."
    ),
}


def _content_level_instruction(request: StoryRequest) -> str:
    return (
        _CONTENT_LEVEL_INSTRUCTIONS[request.content_level]
        + " If the story sets stricter visible requirements for this selected "
        "level, every one of them is mandatory; do not substitute the broader "
        "alternatives above. If the story requires this content-level "
        "interaction to enact a concept, causal rule, or visual contradiction, "
        "use that same interaction as the sole human action rather than placing "
        "compliant content beside a separate task."
        + " Do not write the content-level name, CLI value, or compliance "
        "explanation in title, premise, or prose."
    )


def _cast_constraints(request: StoryRequest) -> dict[str, int | None]:
    return {
        "female_count": request.female_count,
        "male_count": request.male_count,
    }


def _cast_instruction(request: StoryRequest) -> str:
    female_count = request.female_count
    male_count = request.male_count
    if female_count is None and male_count is None:
        return (
            "The number and genders of people must follow the explicit facts in "
            "the story. Do not add, omit, or replace people."
        )
    if female_count is not None and male_count is not None:
        return (
            f"Every theme and every frame must contain exactly {female_count} "
            f"adult female participant(s) and {male_count} adult male "
            "participant(s). Do not omit, replace, or add anyone."
        )

    gender = (
        "adult female participant(s)"
        if female_count is not None
        else "adult male participant(s)"
    )
    count = female_count if female_count is not None else male_count
    return (
        f"Every theme and every frame must contain exactly {count} {gender}. "
        "For unconstrained genders, follow the explicit facts in the story. "
        "Do not omit or add people of the constrained gender."
    )


def _people_and_setting_defaults_instruction() -> str:
    return (
        "Preserve any nationality that the story explicitly assigns to a "
        "person; otherwise that person defaults to Chinese. Do not infer "
        "nationality from location, name, language, skin tone, or appearance. "
        "Every theme premise and frame prose must state each person's "
        "nationality explicitly rather than implying it through setting or "
        'name. Use "Chinese" in English output and the natural equivalent in '
        "Chinese output. Preserve an explicitly stated country or a location "
        "whose country is unambiguous; otherwise the setting defaults to China. "
        "Do not move it to another country. Every theme premise and frame prose "
        "must state the country explicitly rather than relying on a city, "
        "building, or environment to imply it."
    )


def _era_consistency_instruction() -> str:
    return (
        "Treat time and place as one coherent world. Architecture, furnishings, "
        "objects, materials, clothing, hair, transport, weapons, communication, "
        "lighting, social titles, and character language must agree with one "
        "another and with the era, region, season, time of day, and social "
        "setting given by the story. Clothing warmth, plant condition, light "
        "sources, etiquette, and institutions must also fit. When historical "
        "facts are uncertain, use credible generic descriptions rather than "
        "guessing brands, models, exact dates, or proper names merely to sound "
        "specific. Use anachronistic elements deliberately only when the story "
        "explicitly requests time travel, alternate history, or temporal "
        "dislocation."
    )


def theme_messages(
    request: StoryRequest,
    *,
    start_index: int,
    count: int,
    existing_themes: list[NarrativeTheme],
    semantic_name: str | None = None,
) -> list[ChatMessage]:
    end_index = start_index + count - 1
    language = (
        "Write title, premise, and style in natural Chinese. If the story "
        "explicitly requires a foreign-language title verbatim, preserve that "
        "title and keep all other content in natural Chinese."
        if request.output_language == OutputLanguage.CHINESE
        else (
            "Write title, premise, and style in natural English. Use “small” or "
            "“slight” rather than the age-ambiguous English adjective for low "
            "importance."
        )
    )
    semantic_name_instruction = (
        f"Return semantic_name exactly as {semantic_name}."
        if semantic_name is not None
        else (
            "Set semantic_name to a concise lowercase English snake_case name "
            "for the whole story."
        )
    )
    system = "\n".join(
        (
            "You are a narrative concept editor. From one story, devise truly "
            "different miniature stories that can each support several "
            "independent still images. Do not merely move the same action to a "
            "new location, color palette, or camera angle.",
            f"Themes must contain exactly {count} items with consecutive "
            f"theme_id values from T{start_index:03d} through T{end_index:03d}.",
            "Keep title concise and natural. Premise must contain no more than "
            "two sentences. The first establishes time, place, people, and "
            "their shared situation, giving every person an adult age, facial "
            "features, build, and hairstyle that remain stable across all "
            "frames. The second states only the most important emotional "
            "tension or choice in their relationship unless the story "
            "explicitly requires a visible material state or operating rule "
            "instead. Do not put concrete "
            "poses, rope paths, equipment, camera, lighting, operational steps, "
            "countdowns, external workplace crises, or outcomes in a premise "
            "unless the story explicitly requires them during Theme generation. "
            "Leave those details to each frame by default; when the story does "
            "require them, include only the minimum current material state or "
            "operating rule instead of a sequence.",
            "If the story provides a concrete event, deepen its characters and "
            "visible situation. If it provides only a broad subject, invent a "
            "credible event. If the story explicitly defines static, "
            "nonchronological tableaux, treat the currently visible condition "
            "itself as the event; do not add a deadline, repeated cycle, "
            "before-and-after change, intended next step, or future consequence. "
            "Do not fabricate names, exact dates or places, "
            "secret histories, object provenance, ranks, scars, or relationship "
            "backstory merely to add drama.",
            _cast_instruction(request),
            _people_and_setting_defaults_instruction(),
            _era_consistency_instruction(),
            "Style must be one complete, concise visual-style sentence, not a "
            "list of shot scales or composition alternatives. It must summarize "
            "and preserve the story's explicit presentation requirements "
            "without conflicting with or weakening them.",
            "Themes must differ genuinely in relationship, setting function, "
            "decision, or conflict. Use existing themes only to avoid repetition; "
            "do not rewrite and return them again.",
            semantic_name_instruction,
            _content_level_instruction(request),
            language,
            "Do not output explanations or fields outside the schema.",
        )
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story": request.story,
                    "cast_constraints": _cast_constraints(request),
                    "content_level": request.content_level.value,
                    "semantic_name": semantic_name,
                    "batch_start": start_index,
                    "batch_count": count,
                    "frames_per_theme": request.frames_per_theme,
                    "existing_themes": [
                        theme.model_dump(mode="json")
                        for theme in existing_themes
                    ],
                },
                ensure_ascii=False,
            ),
        ),
    ]


def frame_messages(
    request: StoryRequest,
    theme: NarrativeTheme,
) -> list[ChatMessage]:
    language = (
        "Write prose in natural, precise, fluent Chinese. Preserve verbatim any "
        "English labels or visible image text explicitly required by the story. "
        "Translate all other foreign concepts naturally into Chinese, and do "
        "not mix in English pronouns, clothing, photography, pose, or action "
        "phrases."
        if request.output_language == OutputLanguage.CHINESE
        else (
            "Write every prose paragraph entirely in natural, precise, fluent "
            "English. Do not include Chinese characters or switch to another "
            "language. Use “small” or “slight” rather than the age-ambiguous "
            "English adjective for low importance."
        )
    )
    frame_ids = [
        f"F{index:02d}" for index in range(1, request.frames_per_theme + 1)
    ]
    system = "\n".join(
        (
            "You are a cinematic still-image narrative writer. Turn the theme "
            "into independent images that are directly usable for text-to-image "
            "generation and make the characters' situation immediately legible. "
            "Narrative coherence, fluency, and visual plausibility take priority "
            "over filling fields, but never override the story's explicit "
            "output format. When the story requires a fixed field structure, "
            "use its labels and order verbatim and prioritize structural "
            "completeness.",
            f"Frames must contain exactly {len(frame_ids)} items with frame_id "
            f"values in this order: {', '.join(frame_ids)}.",
            "Follow the output form required by the story. When the story "
            "requires a fixed field structure, use its labels and order verbatim. "
            "Otherwise, each prose value must be one unbroken natural-language "
            "paragraph without field labels such as theme, character, action, "
            "camera, or lighting. Without a fixed structure, open by naturally "
            "establishing theme.style and make the era, place, and current moment "
            "clear near the beginning without repeating one sentence template "
            "across frames.",
            "Treat each frame as the only image in the set. The reader must not "
            "need another frame. Naturally establish who is in the situation, "
            "what they currently face, and why this instant matters. Mention a "
            "deadline or consequence only when the story truly needs it. Do not "
            "invent clients, acceptance checks, countdowns, delivery tasks, or "
            "abstract risk terminology.",
            "Fully redescribe every visible person's unmistakable adult identity, "
            "age, gender, stable appearance, hairstyle, clothing, expression, "
            "gaze, and current pose in every frame. Integrate these facts into "
            "the visual reading order rather than listing a dossier. Preserve "
            "stable appearance from theme premise; do not change the same "
            "person's hair color, hair length, face shape, or build between "
            "frames. Give different people emotionally and spatially responsive "
            "relationships.",
            _cast_instruction(request),
            _people_and_setting_defaults_instruction(),
            "Freeze the image at one clear instant. It may contain one dominant "
            "action, contact, or force relationship, but describe only the "
            "currently visible state and direct physical result. Do not narrate "
            "sequential steps or make a person change pose within one frame. Do "
            "not use a fixed opening such as 'at this moment' merely to satisfy "
            "a template.",
            "When the story explicitly requires static body mechanics, each "
            "person must remain in one physically possible held pose on a broad "
            "stable support. Assign each visible limb one consistent contact or "
            "force role. Use stative bodily predicates for held pose, fixed "
            "contact, sustained pressure, support, and gaze. A body or handled "
            "object must not travel between positions, and no body part may "
            "become an impossible structural component of the scene.",
            "The final state explicitly required by the story must appear "
            "directly in every frame, not as preparation, gradual change, or "
            "removal. Do not replace visible evidence with terminology.",
            "If the story assigns differentiated requirements by theme_id, read "
            "theme.theme_id from the current payload first and apply only "
            "requirements matching that ID. Do not choose freely, use the wrong "
            "assignment, or borrow another ID's design.",
            "Explicit story constraints take priority over general writing "
            "guidance and theme.style. Theme.style may only make those constraints "
            "concrete; it must not replace, conflict with, or weaken them.",
            "Use setting objects, materials, distance, and spatial evidence that "
            "matter to the characters' situation rather than unrelated decor. "
            "Body balance, limb direction, occlusion, contact points, clothing, "
            "and prop forces must be physically credible.",
            "Camera and lighting must be explicit and professional, including an "
            "appropriate shot scale, camera height or angle, composition focus, "
            "depth of field, light direction, and color treatment. Integrate "
            "them into the paragraph's natural rhythm without imposing a fixed "
            "sentence opening, position, or number of technical terms.",
            "Multiple frames for one theme are parallel visual alternatives with "
            "the same people, place, and emotional premise, not a chronological "
            "shot sequence. Re-establish the complete scene from scratch in "
            "every frame and give each a different styling, visual center, and "
            "emotional emphasis. Never make one frame a setup, sequel, escalation, "
            "or release of another, and do not use continuity shortcuts such as "
            "'the same,' 'still,' 'already,' 'again,' 'changed to,' or 'finally' "
            "to omit information.",
            "Length should be driven by cast size and visual complexity. Include "
            "enough detail for text-to-image generation without padding with "
            "synonymous emotions, false-precision timestamps, technical "
            "explanations, abstract criticism, or repeated causes.",
            "Preserve only the level of factual precision already present in the "
            "story and theme. Any visible image text specified by the story must "
            "be preserved verbatim inside double quotation marks. Do not invent "
            "visible text when none is specified.",
            _era_consistency_instruction(),
            _content_level_instruction(request),
            language,
            "Before submission, read the whole result once. Rewrite any fragment "
            "that is not in the requested output language, except literal text "
            "that the story requires, and confirm that people, space, and the "
            "visible image are coherent. Do not mention themes, frames, IDs, "
            "prompts, or internal generation steps in prose; fixed field labels "
            "explicitly required by the story are allowed. Do not output reviews, "
            "compliance explanations, or fields outside the schema.",
        )
    )
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "story": request.story,
                    "cast_constraints": _cast_constraints(request),
                    "content_level": request.content_level.value,
                    "theme": theme.model_dump(mode="json"),
                    "frames_per_theme": request.frames_per_theme,
                    "frame_ids": frame_ids,
                },
                ensure_ascii=False,
            ),
        ),
    ]
