"""Expected failures for the standalone story pipeline."""

from t2i_story_pipeline.models import TokenUsage


class StoryPipelineError(Exception):
    """Base class for failures that callers may present to users."""


class StoryConfigurationError(StoryPipelineError):
    """Story provider configuration is invalid or incomplete."""


class StoryContractError(StoryPipelineError):
    """Generated story data violates the requested shape or references."""


class StoryProviderError(StoryPipelineError):
    """The configured story model could not complete a request."""


class StoryProviderAuthenticationError(StoryProviderError):
    """The story model rejected the configured credentials."""


class StoryProviderResponseError(StoryProviderError):
    """The story model returned an unsupported response."""

    def __init__(
        self,
        message: str,
        *,
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage or TokenUsage()


class StoryStorageError(StoryPipelineError):
    """A completed story result could not be published."""


class StoryRunNotFoundError(StoryStorageError):
    """The requested story run does not exist."""


class StoryRunIncompleteError(StoryPipelineError):
    """A resumable story run stopped before all checkpoints completed."""

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
            f"{missing_frames} 个 Frame Sequence；请执行 resume {run_id}"
        )
