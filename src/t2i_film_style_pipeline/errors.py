"""Expected failures from the standalone film-style pipeline."""

from __future__ import annotations


class FilmStylePipelineError(Exception):
    """Base class for failures callers may present to users."""


class FilmStyleConfigurationError(FilmStylePipelineError):
    """Provider or request configuration is invalid."""


class FilmStyleProviderError(FilmStylePipelineError):
    """The configured model could not complete a request."""


class FilmStyleProviderResponseError(FilmStyleProviderError):
    """The model returned an unsupported response."""


class FilmStyleStructuredOutputError(FilmStyleProviderResponseError):
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


class FilmStyleProviderTruncatedOutputError(FilmStyleStructuredOutputError):
    """The model stopped before returning a complete schema."""


class FilmStyleProviderHTTPError(FilmStyleProviderError):
    """The model returned a terminal HTTP response."""

    def __init__(self, status_code: int, response_text: str) -> None:
        self.status_code = status_code
        super().__init__(
            f"film-style model returned HTTP {status_code}: {response_text[:500]}"
        )


class FilmStyleStorageError(FilmStylePipelineError):
    """A run record or compiled story description could not be persisted."""


class FilmStyleRunIncompleteError(FilmStylePipelineError):
    """A resumable film-style prompt run stopped before completion."""

    def __init__(self, run_id: str, cause: str) -> None:
        self.run_id = run_id
        self.cause = cause
        super().__init__(
            f"Run {run_id} 尚未完成：{cause}；请执行 resume {run_id}"
        )
