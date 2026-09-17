from __future__ import annotations

import pytest

from t2i_story_pipeline.errors import StoryContractError
from t2i_story_pipeline.frame_batches import split_frame_batch


def test_frame_blocks_preserve_body_and_order_without_transport_tags():
    assert split_frame_batch(
        "\n<FRAME>\n第一幅图像。\n</FRAME>\n\n<FRAME>Second image.</FRAME>\n", 2
    ) == ["第一幅图像。", "Second image."]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "plain untagged paragraph",
        '{"frames": [{"prose": "image"}]}',
        "```text\n<FRAME>image</FRAME>\n```",
        "Here are the results:\n<FRAME>image</FRAME>",
        "<FRAME>image</FRAME> explanation",
        "<FRAME>image",
        "<FRAME>one</FRAME><FRAME>two</FRAME>",
        "<FRAME><FRAME>nested</FRAME></FRAME>",
        "<FRAME>unclosed nested <FRAME>image</FRAME>",
        "<FRAME id='F01'>image</FRAME>",
        "<frame>image</frame>",
    ],
)
def test_malformed_or_ambiguous_batches_are_rejected_without_slot_guessing(text):
    with pytest.raises(StoryContractError):
        split_frame_batch(text, 1)


def test_empty_blocks_keep_their_slot_for_individual_contract_validation():
    assert split_frame_batch("<FRAME></FRAME><FRAME>good</FRAME>", 2) == ["", "good"]
