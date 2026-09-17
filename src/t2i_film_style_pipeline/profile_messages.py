"""组装作品视觉档案请求消息。"""

from __future__ import annotations

import json
from collections.abc import Sequence

from t2i_film_style_pipeline.models import FilmStyleRequest
from t2i_film_style_pipeline.provider import ChatMessage


def profile_messages(
    request: FilmStyleRequest,
    rules: Sequence[str],
) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content="\n".join(rules)),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "director": request.director,
                    "works": [
                        work.model_dump(mode="json") for work in request.works
                    ],
                    "output_language": request.output_language,
                },
                ensure_ascii=False,
            ),
        ),
    ]
