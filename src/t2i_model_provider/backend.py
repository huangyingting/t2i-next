"""Configuration shared by every model-backed pipeline."""

from __future__ import annotations

import os
from enum import StrEnum


class ModelBackend(StrEnum):
    OPENAI = "openai"
    COPILOT = "copilot"


_COPILOT_ENV_FIELDS = {
    "COPILOT_MODEL": "model",
    "COPILOT_REASONING_EFFORT": "reasoning_effort",
    "COPILOT_OUTPUT_TOKEN_LIMIT": "output_token_limit",
    "COPILOT_TIMEOUT_SECONDS": "timeout_seconds",
}


def selected_backend_values(
    openai_fields: dict[str, str],
) -> dict[str, str]:
    backend = os.environ.get("T2I_MODEL_BACKEND", ModelBackend.OPENAI.value)
    values = {"backend": backend}
    fields = (
        _COPILOT_ENV_FIELDS
        if backend == ModelBackend.COPILOT.value
        else openai_fields
    )
    values.update(
        {
            field_name: value
            for environment_name, field_name in fields.items()
            if (value := os.environ.get(environment_name)) is not None
        }
    )
    if backend == ModelBackend.COPILOT.value:
        values.setdefault("model", "auto")
    return values
