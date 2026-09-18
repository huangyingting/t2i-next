"""Shared types for the offline neutral pose and presentation modules."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z]+(?:_[a-z]+)*$")]
Surface = Literal[
    "floor", "mat", "chair_seat", "chair_back", "wall", "table", "step", "headrest"
]
CameraView = Literal[
    "front", "left_three_quarter", "right_three_quarter", "left_profile",
    "right_profile",
]
CameraHeight = Literal["subject_eye_level", "slightly_above_subject"]


class ReferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
