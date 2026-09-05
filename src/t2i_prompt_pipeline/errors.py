"""Failures surfaced by the generation module."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from t2i_prompt_pipeline.models import TokenUsage


class PromptPipelineError(Exception):
    """Base class for expected application failures."""


class ConfigurationError(PromptPipelineError):
    """Application configuration is invalid or incomplete."""


class GenerationContractError(PromptPipelineError):
    """Generated IDs, counts, or references violate the requested shape."""


class ProviderError(PromptPipelineError):
    """The configured author model could not complete a request."""


class ProviderAuthenticationError(ProviderError):
    """The author model rejected the configured credentials."""


class ProviderResponseError(ProviderError):
    """The author model returned an unsupported response."""


class StructuredOutputError(ProviderResponseError):
    """The author model response did not match the requested model."""

    def __init__(
        self,
        message: str,
        *,
        raw_content: str,
        model: str | None = None,
        usage: TokenUsage | None = None,
        validation_issues: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.model = model
        self.usage = usage
        self.validation_issues = validation_issues


class ProviderTruncatedOutputError(StructuredOutputError):
    """The author model stopped because the output token limit was reached."""


class RunStoreError(PromptPipelineError):
    """A run checkpoint could not be persisted or loaded."""


class RunNotFoundError(RunStoreError):
    """The requested run does not exist."""


class BatchPausedError(PromptPipelineError):
    """A batch stopped with its progress and cumulative budget preserved."""

    def __init__(self, state_file: Path, reason: str) -> None:
        self.state_file = state_file
        super().__init__(
            f"批次已暂停：{reason}；状态：{state_file}。"
            "请再次执行相同批次命令继续；预算耗尽时需显式提高对应上限。"
        )


class RunIncompleteError(PromptPipelineError):
    """A resumable run stopped before all requested objects completed."""

    def __init__(
        self,
        run_id: str,
        *,
        missing_themes: int,
        missing_frames: int,
        causes: tuple[str, ...],
    ) -> None:
        self.run_id = run_id
        self.missing_themes = missing_themes
        self.missing_frames = missing_frames
        self.causes = causes
        super().__init__(
            f"Run {run_id} 尚未完成：缺少 {missing_themes} 个 Theme、"
            f"{missing_frames} 个 Frame；请执行 resume {run_id}"
        )
