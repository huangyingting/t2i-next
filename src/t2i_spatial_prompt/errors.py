"""Expected failures from the standalone spatial prompt module."""

from __future__ import annotations


class SpatialPromptError(Exception):
    """Base class for failures callers may present to users."""


class SpatialConfigurationError(SpatialPromptError):
    """Provider configuration is invalid or incomplete."""


class SpatialProviderError(SpatialPromptError):
    """The configured model could not complete a request."""


class SpatialProviderResponseError(SpatialProviderError):
    """The model returned an unsupported response."""


class SpatialStructuredOutputError(SpatialProviderResponseError):
    """The response did not match the requested schema."""

    def __init__(
        self,
        message: str,
        *,
        raw_content: str,
        validation_issues: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.validation_issues = validation_issues


class SpatialProviderTruncatedOutputError(SpatialStructuredOutputError):
    """The model stopped before returning a complete schema."""


class SpatialProviderHTTPError(SpatialProviderError):
    """The model returned a terminal HTTP response."""

    def __init__(self, status_code: int, response_text: str) -> None:
        self.status_code = status_code
        super().__init__(
            f"spatial model returned HTTP {status_code}: {response_text[:500]}"
        )
