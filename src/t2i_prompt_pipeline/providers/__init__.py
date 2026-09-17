"""Author-model adapters."""

from t2i_prompt_pipeline.providers.base import AuthorModel
from t2i_prompt_pipeline.providers.configured import author_model
from t2i_prompt_pipeline.providers.copilot import CopilotProvider
from t2i_prompt_pipeline.providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "AuthorModel",
    "CopilotProvider",
    "OpenAICompatibleProvider",
    "author_model",
]
