"""Expected failures from the standalone film-style pipeline."""

from __future__ import annotations

from t2i_film_style_pipeline.prompt_models import TokenUsage


class FilmStylePipelineError(Exception):
    """Base class for failures callers may present to users."""


class FilmStyleConfigurationError(FilmStylePipelineError):
    """Provider or request configuration is invalid."""


class FilmStyleContractError(FilmStylePipelineError):
    """Generated film prompt data violates its publication contract."""


class FilmStyleProviderError(FilmStylePipelineError):
    """The configured model could not complete a request."""


class FilmStyleProviderAuthenticationError(FilmStyleProviderError):
    """The configured model rejected the current credentials."""


class FilmStyleProviderResponseError(FilmStyleProviderError):
    """The model returned an unsupported response."""

    def __init__(
        self,
        message: str,
        *,
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage or TokenUsage()


class FilmStyleStructuredOutputError(FilmStyleProviderResponseError):
    """The response did not match the requested schema."""

    def __init__(
        self,
        message: str,
        *,
        raw_content: str,
        usage: TokenUsage | None = None,
        validation_issues: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message, usage=usage)
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
    """A run record or compiled film context could not be persisted."""


class FilmPromptRunNotFoundError(FilmStyleStorageError):
    """The requested film prompt run does not exist."""


class FilmPromptRunIncompleteError(FilmStylePipelineError):
    """A resumable film prompt run stopped before all checkpoints completed."""

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
        detail = f"；原因：{'; '.join(causes)}" if causes else ""
        super().__init__(
            f"Run {run_id} 尚未完成：缺少 {missing_themes} 个 Theme、"
            f"{missing_frames} 个 Frame Sequence{detail}；请执行 resume {run_id}"
        )


class FilmStyleRunIncompleteError(FilmStylePipelineError):
    """A resumable film-style prompt run stopped before completion."""

    def __init__(self, run_id: str, cause: str) -> None:
        self.run_id = run_id
        self.cause = cause
        super().__init__(
            f"Run {run_id} 尚未完成：{cause}；请执行 resume {run_id}"
        )
