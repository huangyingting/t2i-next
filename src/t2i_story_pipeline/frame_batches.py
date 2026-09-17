"""Parse the sole text transport for a batch of independently authored frames."""

from __future__ import annotations

import re

from t2i_story_pipeline.errors import StoryContractError

_FRAME_BLOCK = re.compile(r"<FRAME>(.*?)</FRAME>", re.DOTALL)


def split_frame_batch(text: str, expected_count: int) -> list[str]:
    matches = list(_FRAME_BLOCK.finditer(text))
    cursor = 0
    for match in matches:
        if text[cursor : match.start()].strip():
            raise StoryContractError("Frame 批次包含标签之外的正文")
        if "<FRAME>" in match.group(1) or "</FRAME>" in match.group(1):
            raise StoryContractError("Frame 批次不能嵌套标签")
        cursor = match.end()
    if text[cursor:].strip():
        raise StoryContractError("Frame 批次包含标签之外的正文")
    if len(matches) != expected_count:
        raise StoryContractError(
            "Frame 批次数量不符合请求："
            f"expected={expected_count}, actual={len(matches)}"
        )
    return [match.group(1).strip() for match in matches]
