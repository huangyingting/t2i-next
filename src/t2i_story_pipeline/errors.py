"""Expected failures for the standalone story pipeline."""


class StoryPipelineError(Exception):
    """Base class for failures that callers may present to users."""


class StoryConfigurationError(StoryPipelineError):
    """Story provider configuration is invalid or incomplete."""


class UnsafeStoryError(StoryPipelineError):
    """The source story violates a non-negotiable safety invariant."""


class StoryContractError(StoryPipelineError):
    """Generated story data violates the requested shape or references."""


class StoryProviderError(StoryPipelineError):
    """The configured story model could not complete a request."""


class StoryProviderAuthenticationError(StoryProviderError):
    """The story model rejected the configured credentials."""


class StoryProviderResponseError(StoryProviderError):
    """The story model returned an unsupported response."""


class StoryStorageError(StoryPipelineError):
    """A completed story result could not be published."""
