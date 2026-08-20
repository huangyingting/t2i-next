"""Author-model adapters."""

from t2i_prompt_pipeline.providers.base import AuthorModel
from t2i_prompt_pipeline.providers.openai_compatible import OpenAICompatibleProvider

__all__ = ["AuthorModel", "OpenAICompatibleProvider"]
