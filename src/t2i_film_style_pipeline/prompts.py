"""Prompt compilation for work-specific visual-style analysis."""

from __future__ import annotations

import json

from t2i_film_style_pipeline.models import FilmStyleRequest
from t2i_film_style_pipeline.provider import ChatMessage

SYSTEM_PROMPT = """\
You create observable, production-ready visual profiles from a named director's
specific films. Analyze only the works supplied by the user. Do not describe or
imitate the director's unrestricted personal style. Do not copy characters,
actors, dialogue, protected costume designs, signature props, exact shots, or
plot sequences.

Infer a reusable work-specific visual system using only photographically and
physically controllable traits: palette, composition, blocking, camera distance
and movement, source lighting, production design, material behavior, motion
grammar, and image finish. Distinguish recurring evidence across the supplied
works from traits unique to one work. Return one concise style summary for each
work in exactly the supplied order, plus one concise aggregate style summary
for the complete work set. Do not repeat film titles or the director name inside
those summaries because the compiler adds exact source attribution. Use the
requested output language.

The profile must be concrete enough to compile into a Story Description. Every
field must describe visible choices, not praise, biography, symbolism,
audience reaction, or vague adjectives. Create an original profile name that
does not contain the director name or a film title. The aggregate style summary
must concisely name the profile's visible palette, composition, blocking,
lighting, motion, and finish identity. Refusal rules must prevent generic genre
drift and literal copying of source material.
"""


def profile_messages(request: FilmStyleRequest) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "director": request.director,
                    "works": [
                        work.model_dump(mode="json") for work in request.works
                    ],
                    "output_language": request.output_language,
                    "task": (
                        "Create one work-specific visual profile that can govern "
                        "Theme and Frame generation for the supplied base brief."
                    ),
                },
                ensure_ascii=False,
            ),
        ),
    ]
