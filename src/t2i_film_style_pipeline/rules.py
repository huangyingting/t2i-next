"""解析并冻结导演风格流程的阶段规则。"""

from __future__ import annotations

from pathlib import Path

from t2i_film_style_pipeline.errors import FilmStyleConfigurationError
from t2i_film_style_pipeline.models import FilmStyleRuleSet
from t2i_film_style_pipeline.prompt_models import FilmPromptRequest, OutputLanguage

_SYSTEM_RULES_DIRECTORY = Path(__file__).resolve().parent / "rule_packs" / "system"
_STAGE_FILENAMES = ("themes.rules", "frames.rules")


def resolve_film_style_rules(
    request: FilmPromptRequest,
    *,
    user_directory: Path | None = None,
) -> FilmStyleRuleSet:
    """Compile film-style system and optional user rules for a new run."""
    system_directory = _require_directory(
        _SYSTEM_RULES_DIRECTORY,
        "film-style system rules directory",
    )
    resolved_user_directory = (
        _require_directory(
            user_directory.resolve(),
            "film-style user rules directory",
        )
        if user_directory is not None
        else None
    )
    profile_rules = list(
        _read_rule_file(system_directory / "profile.rules", required=True)
    )
    if resolved_user_directory is not None:
        profile_rules.extend(
            _read_rule_file(
                resolved_user_directory / "profile.rules",
                required=False,
            )
        )
    return FilmStyleRuleSet(
        profile=tuple(profile_rules),
        themes=_compile(
            _STAGE_FILENAMES[0],
            request,
            system_directory,
            resolved_user_directory,
        ),
        frames=_compile(
            _STAGE_FILENAMES[1],
            request,
            system_directory,
            resolved_user_directory,
        ),
    )


def _compile(
    stage_filename: str,
    request: FilmPromptRequest,
    system_directory: Path,
    user_directory: Path | None,
) -> tuple[str, ...]:
    rules = [
        rule
        for path in _selected_paths(system_directory, stage_filename, request)
        for rule in _read_rule_file(path, required=True)
    ]
    if user_directory is not None:
        rules.extend(
            rule
            for path in _selected_paths(user_directory, stage_filename, request)
            for rule in _read_rule_file(path, required=False)
        )
    rules.append(_output_language_rule(request))
    return tuple(rules)


def _selected_paths(
    directory: Path,
    stage_filename: str,
    request: FilmPromptRequest,
) -> tuple[Path, ...]:
    return (
        directory / "common.rules",
        directory / stage_filename,
        directory / "content_levels" / f"{request.content_level.value}.rules",
    )


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise FilmStyleConfigurationError(f"{label} does not exist: {path}")
    return path


def _read_rule_file(path: Path, *, required: bool) -> tuple[str, ...]:
    if not path.exists():
        if required:
            raise FilmStyleConfigurationError(
                f"film-style rule file does not exist: {path}"
            )
        return ()
    if not path.is_file():
        raise FilmStyleConfigurationError(
            f"film-style rule path is not a file: {path}"
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise FilmStyleConfigurationError(
            f"cannot read film-style rule file {path}: {exc}"
        ) from exc
    return tuple(
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )


def _output_language_rule(request: FilmPromptRequest) -> str:
    if request.output_language == OutputLanguage.ENGLISH:
        return (
            "所有自然语言输出字段必须使用准确、流畅的英文。只有电影场景上下文"
            "明确要求逐字保留的外文文字可以例外。"
        )
    return (
        "所有自然语言输出字段必须使用准确、流畅的中文。只有电影场景上下文明确"
        "要求逐字保留的外文文字可以例外，不得混入未翻译的外文段落。"
    )
