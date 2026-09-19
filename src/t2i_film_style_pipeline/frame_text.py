"""Read the exact source sentence from the frozen compiled film context."""

from __future__ import annotations

import re


def source_sentence(context: str) -> str | None:
    match = re.search(
        r"(?:每个 Frame 必须准确且只在第一句使用以下来源说明：|"
        r"Every Frame must use this source sentence exactly once "
        r"as its first sentence:)"
        r"\s*\n[“\"]([^\r\n]+)[”\"](?:\r?\n|$)",
        context,
    )
    return match.group(1) if match else None


def frame_body(context: str, prose: str) -> str:
    source = source_sentence(context)
    return prose[len(source) :] if source and prose.startswith(source) else prose
