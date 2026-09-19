"""CLI for one-command, resumable film-style prompt generation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_film_style_pipeline.config import load_film_style_provider_settings
from t2i_film_style_pipeline.errors import (
    FilmStyleConfigurationError,
    FilmStylePipelineError,
    FilmStyleRunIncompleteError,
)
from t2i_film_style_pipeline.models import (
    FilmStyleRequest,
    FilmStyleRuleSet,
    parse_work_reference,
)
from t2i_film_style_pipeline.pipeline import (
    CompletedFilmStylePromptRun,
    FilmStylePipelineSettings,
    FilmStylePromptRequest,
    FilmStylePromptStudio,
    LocalFilmStyleRunStore,
)
from t2i_film_style_pipeline.prompt_config import (
    load_film_prompt_provider_settings,
)
from t2i_film_style_pipeline.prompt_models import ContentLevel, OutputLanguage
from t2i_film_style_pipeline.prompt_provider import (
    FilmPromptProviderSettings,
    film_prompt_model,
)
from t2i_film_style_pipeline.prompt_run_store import (
    FilmPromptRunSettings,
    ThemeOutputMode,
)
from t2i_film_style_pipeline.provider import (
    FilmStyleProviderSettings,
    film_style_model,
)
from t2i_film_style_pipeline.rules import resolve_film_style_rules

app = typer.Typer(
    name="t2i-film-style",
    help="从具体作品集合生成可恢复的最终电影静帧提示词。",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Generate final prompts from work-specific film language."""


@app.command("generate")
def generate_command(
    director: str = typer.Argument(..., help="作品集合的导演署名。"),
    work: list[str] = typer.Option(
        ...,
        "--work",
        help="具体作品，可重复；支持 TITLE 或 TITLE (YEAR)。",
    ),
    scene: str | None = typer.Option(
        None,
        "--scene",
        help="可选原作人物与场景方向；省略时从作品锚点自动选择。",
    ),
    filename_stem: str | None = typer.Option(
        None,
        "--filename-stem",
        help="可选英文输出文件名前缀，仅允许 ASCII 字母、数字、下划线和连字符。",
    ),
    themes: int = typer.Option(
        1,
        "--themes",
        min=1,
        max=100,
        help="电影画面主题数。",
    ),
    frames: int = typer.Option(
        6,
        "--frames",
        min=1,
        max=6,
        help="每个主题的平行画面数。",
    ),
    female_count: int = typer.Option(
        1,
        "--female-count",
        min=0,
        help="每个 Theme 的固定女性人数；允许为零，不设人数上限。",
    ),
    male_count: int = typer.Option(
        0,
        "--male-count",
        min=0,
        help="每个 Theme 的固定男性人数；允许为零，男女数量不能同时为零。",
    ),
    concurrency: int = typer.Option(
        8,
        "--concurrency",
        min=1,
        max=32,
        help="Theme 批次与 Frame 生成共享的最大模型调用并发数。",
    ),
    theme_batch_size: int = typer.Option(
        5,
        "--theme-batch-size",
        min=1,
        max=10,
        help="每次模型调用批量生成的 Theme 数；默认 5，每批带上全部历史主题。",
    ),
    content_level: ContentLevel = typer.Option(
        ContentLevel.AESTHETIC,
        "--content-level",
        help="内容尺度：aesthetic、erotic 或 hardcore。",
    ),
    validate_themes: bool = typer.Option(
        False,
        "--validate-themes",
        help="启用 Theme 的拒绝文本、原作锚点和内容等级语义验证。",
    ),
    validate_frames: bool = typer.Option(
        False,
        "--validate-frames",
        help="启用 Frame 的来源、内容、锚点、摄影和感官语义验证。",
    ),
    output_language: OutputLanguage = typer.Option(
        OutputLanguage.CHINESE,
        "--language",
        help="视觉档案与最终提示词语言。",
    ),
    prompts_dir: Path = typer.Option(
        Path("prompts"),
        "--prompts-dir",
        file_okay=False,
        help="按运行日期保存最终 TXT 提示词的根目录。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs") / "film-style",
        "--runs-dir",
        file_okay=False,
        help="保存顶层进度及 profile、Theme、Frame checkpoints。",
    ),
    rules_dir: Path | None = typer.Option(
        None,
        "--rules-dir",
        file_okay=False,
        help="可选 film-style 用户规则目录；默认只使用包内导演规则。",
    ),
) -> None:
    """Generate the profile and final prompts in one resumable command."""
    try:
        request = FilmStylePromptRequest(
            film_style=FilmStyleRequest(
                director=director,
                works=tuple(parse_work_reference(item) for item in work),
                output_language=output_language.value,
            ),
            scene_direction=scene,
            output_filename_stem=filename_stem,
            theme_count=themes,
            frames_per_theme=frames,
            female_count=female_count,
            male_count=male_count,
            content_level=content_level,
            output_language=output_language,
        )
        rules = resolve_film_style_rules(
            request.prompt_request("BRIEF\n\nDirector-work film scene generation."),
            user_directory=rules_dir,
        )
        film_provider = load_film_style_provider_settings()
        prompt_provider = load_film_prompt_provider_settings()
        settings = FilmStylePipelineSettings(
            film_provider=film_provider,
            prompt=FilmPromptRunSettings(
                provider=prompt_provider,
                concurrency=concurrency,
                theme_batch_size=theme_batch_size,
                theme_output_tokens=12000,
                theme_output_mode=ThemeOutputMode.STRUCTURED_WITHOUT_IDS,
            ),
            validate_themes=validate_themes,
            validate_frames=validate_frames,
        )
        completed = asyncio.run(
            _generate(
                request,
                settings,
                rules,
                runs_directory=runs_dir,
                prompts_directory=prompts_dir,
            )
        )
    except (
        OSError,
        UnicodeError,
        ValidationError,
        FilmStylePipelineError,
    ) as exc:
        _exit_for_error(exc, runs_dir)
    _print_completed(completed)


@app.command("resume")
def resume_command(
    run_id: str = typer.Argument(..., help="需要继续的 film-style run ID。"),
    runs_dir: Path = typer.Option(
        Path("runs") / "film-style",
        "--runs-dir",
        file_okay=False,
        help="保存顶层进度及 profile、Theme、Frame checkpoints。",
    ),
) -> None:
    """Continue the missing profile, Theme, or Frame stages."""
    try:
        store = LocalFilmStyleRunStore(runs_dir)
        snapshot = store.inspect(run_id)
        if snapshot.completed is not None:
            _print_completed(snapshot.completed)
            return
        film_provider = load_film_style_provider_settings()
        prompt_provider = load_film_prompt_provider_settings()
        if film_provider != snapshot.settings.film_provider:
            raise FilmStyleConfigurationError(
                "当前 film-style provider 配置与 run checkpoint 不一致"
            )
        if prompt_provider != snapshot.settings.prompt.provider:
            raise FilmStyleConfigurationError(
                "当前 film prompt provider 配置与 run checkpoint 不一致"
            )
        completed = asyncio.run(
            _resume(
                run_id,
                film_provider,
                prompt_provider,
                snapshot.settings,
                snapshot.rules,
                store,
            )
        )
    except (
        ValidationError,
        FilmStylePipelineError,
    ) as exc:
        _exit_for_error(exc, runs_dir)
    _print_completed(completed)


async def _generate(
    request: FilmStylePromptRequest,
    settings: FilmStylePipelineSettings,
    rules: FilmStyleRuleSet,
    *,
    runs_directory: Path,
    prompts_directory: Path,
) -> CompletedFilmStylePromptRun:
    store = LocalFilmStyleRunStore(runs_directory)
    async with (
        film_style_model(settings.film_provider) as film_model,
        film_prompt_model(settings.prompt.provider) as prompt_author,
    ):
        return await FilmStylePromptStudio(
            film_model,
            prompt_author,
            store,
            settings,
            rules,
            on_progress=typer.echo,
        ).run(
            request,
            prompts_directory=prompts_directory,
        )


async def _resume(
    run_id: str,
    film_provider: FilmStyleProviderSettings,
    prompt_provider: FilmPromptProviderSettings,
    settings: FilmStylePipelineSettings,
    rules: FilmStyleRuleSet,
    store: LocalFilmStyleRunStore,
) -> CompletedFilmStylePromptRun:
    async with (
        film_style_model(film_provider) as film_model,
        film_prompt_model(prompt_provider) as prompt_author,
    ):
        return await FilmStylePromptStudio(
            film_model,
            prompt_author,
            store,
            settings,
            rules,
            on_progress=typer.echo,
        ).resume(run_id)


def _print_completed(completed: CompletedFilmStylePromptRun) -> None:
    typer.secho("生成完成。", fg=typer.colors.GREEN)
    typer.echo(f"Run：{completed.run_id}")
    typer.echo(f"视觉档案：{completed.profile_file}")
    typer.echo(f"电影提示词：{completed.prompt_file}")
    typer.echo(f"多样性报告：{completed.diversity_report_file}")


def _exit_for_error(error: Exception, runs_dir: Path) -> None:
    typer.secho(f"生成失败：{error}", fg=typer.colors.RED, err=True)
    if isinstance(error, FilmStyleRunIncompleteError):
        typer.echo(
            f"继续命令：uv run t2i-film-style resume {error.run_id} "
            f"--runs-dir {runs_dir}",
            err=True,
        )
    raise typer.Exit(code=2) from error
