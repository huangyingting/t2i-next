"""CLI for the minimal prose-first narrative pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.errors import (
    StoryConfigurationError,
    StoryPipelineError,
    StoryRunIncompleteError,
)
from t2i_story_pipeline.models import (
    ContentLevel,
    OutputLanguage,
    StoryRequest,
)
from t2i_story_pipeline.provider import (
    OpenAIStoryModel,
    StoryProviderSettings,
)
from t2i_story_pipeline.run_store import (
    CompletedStoryRun,
    LocalStoryRunStore,
    StoryRunSettings,
    StoryRunStatus,
    StoryRunSummary,
)
from t2i_story_pipeline.studio import StoryStudio

app = typer.Typer(
    name="t2i-story",
    help="从一段故事描述生成连续、可独立渲染的叙事提示词。",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Generate final narrative image prompts from story prose."""


@app.command("generate")
def generate_command(
    story: str | None = typer.Argument(
        None,
        help="包含时间、地点、人物、事件与氛围的故事描述。",
    ),
    prompt_file: Path | None = typer.Option(
        None,
        "--prompt-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="从 UTF-8 文本文件读取完整故事描述。",
    ),
    themes: int = typer.Option(
        1,
        "--themes",
        min=1,
        max=100,
        help="微型故事主题数。",
    ),
    frames: int = typer.Option(
        6,
        "--frames",
        min=1,
        max=6,
        help="每个主题的连续故事画面数。",
    ),
    female_count: int | None = typer.Option(
        None,
        "--female-count",
        min=0,
        max=8,
        help="可选女性人数约束；默认遵循 Story Description。",
    ),
    male_count: int | None = typer.Option(
        None,
        "--male-count",
        min=0,
        max=8,
        help="可选男性人数约束；默认遵循 Story Description。",
    ),
    concurrency: int = typer.Option(
        8,
        "--concurrency",
        min=1,
        max=32,
        help="并行生成主题画面序列的数量。",
    ),
    content_level: ContentLevel = typer.Option(
        ContentLevel.AESTHETIC,
        "--content-level",
        help="内容尺度：aesthetic、erotic 或 hardcore。",
    ),
    output_language: OutputLanguage = typer.Option(
        OutputLanguage.CHINESE,
        "--language",
        help="叙事正文语言。",
    ),
    prompts_dir: Path = typer.Option(
        Path("prompts"),
        "--prompts-dir",
        file_okay=False,
        help="按运行日期保存最终 TXT 提示词的根目录。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs"),
        "--runs-dir",
        file_okay=False,
        help="增量 checkpoint 和运行记录目录。",
    ),
) -> None:
    """Generate themes and final narrative paragraphs from one story."""
    try:
        request = StoryRequest(
            story=_resolve_story_input(story, prompt_file),
            theme_count=themes,
            frames_per_theme=frames,
            female_count=female_count,
            male_count=male_count,
            content_level=content_level,
            output_language=output_language,
        )
        settings = load_story_provider_settings()
        completed = asyncio.run(
            _generate(
                request,
                settings,
                concurrency=concurrency,
                runs_directory=runs_dir,
                prompts_directory=prompts_dir,
            )
        )
    except (ValidationError, StoryPipelineError) as exc:
        _exit_for_error(exc, runs_dir)

    _print_completed(completed)


@app.command("resume")
def resume_command(
    run_id: str = typer.Argument(..., help="需要继续的 story run ID。"),
    runs_dir: Path = typer.Option(
        Path("runs"),
        "--runs-dir",
        file_okay=False,
        help="增量 checkpoint 和运行记录目录。",
    ),
) -> None:
    """Continue only missing themes and frame sequences."""
    try:
        store = LocalStoryRunStore(runs_dir)
        snapshot = store.inspect(run_id)
        if snapshot.completed is not None:
            _print_completed(snapshot.completed)
            return
        provider = load_story_provider_settings()
        if provider != snapshot.manifest.settings.provider:
            raise StoryConfigurationError(
                "当前 story provider 配置与 run manifest 不一致"
            )
        completed = asyncio.run(
            _resume(
                run_id,
                provider,
                snapshot.manifest.settings,
                store,
            )
        )
    except (ValidationError, StoryPipelineError) as exc:
        _exit_for_error(exc, runs_dir)

    _print_completed(completed)


@app.command("runs")
def runs_command(
    runs_dir: Path = typer.Option(
        Path("runs"),
        "--runs-dir",
        file_okay=False,
        help="增量 checkpoint 和运行记录目录。",
    ),
) -> None:
    """List story runs and show how to resume incomplete work."""
    try:
        listing = LocalStoryRunStore(runs_dir).list_runs()
    except StoryPipelineError as exc:
        _exit_for_error(exc, runs_dir)

    if not listing.runs and not listing.unreadable:
        typer.echo(f"{runs_dir} 中没有 story run。")
        return
    for summary in listing.runs:
        _print_run_summary(summary, runs_dir)
    if listing.unreadable:
        typer.secho(
            f"{len(listing.unreadable)} 个 run 无法读取："
            f"{'、'.join(listing.unreadable)}",
            fg=typer.colors.RED,
            err=True,
        )


def _resolve_story_input(
    story: str | None,
    prompt_file: Path | None,
) -> str:
    if story is not None and prompt_file is not None:
        raise typer.BadParameter(
            "不能同时提供故事描述和 --prompt-file。",
            param_hint="STORY/--prompt-file",
        )
    if story is None and prompt_file is None:
        raise typer.BadParameter(
            "必须提供故事描述或 --prompt-file。",
            param_hint="STORY/--prompt-file",
        )
    if story is not None:
        return story

    if prompt_file is None:
        raise AssertionError("story input resolution changed unexpectedly")
    try:
        text = prompt_file.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise typer.BadParameter(
            "提示词文件必须是有效的 UTF-8 文本。",
            param_hint="--prompt-file",
        ) from exc
    except OSError as exc:
        raise typer.BadParameter(
            f"无法读取提示词文件：{exc}",
            param_hint="--prompt-file",
        ) from exc
    text = text.strip()
    if not text:
        raise typer.BadParameter(
            "提示词文件不能为空。",
            param_hint="--prompt-file",
        )
    return text


async def _generate(
    request: StoryRequest,
    settings: StoryProviderSettings,
    *,
    concurrency: int,
    runs_directory: Path = Path("runs"),
    prompts_directory: Path = Path("prompts"),
) -> CompletedStoryRun:
    run_settings = StoryRunSettings(
        provider=settings,
        concurrency=concurrency,
    )
    store = LocalStoryRunStore(runs_directory, prompts_directory)
    async with OpenAIStoryModel(settings) as model:
        return await StoryStudio(
            model,
            store,
            run_settings,
            on_progress=typer.echo,
        ).run(request)


async def _resume(
    run_id: str,
    provider: StoryProviderSettings,
    settings: StoryRunSettings,
    store: LocalStoryRunStore,
) -> CompletedStoryRun:
    async with OpenAIStoryModel(provider) as model:
        return await StoryStudio(
            model,
            store,
            settings,
            on_progress=typer.echo,
        ).resume(run_id)


def _print_completed(completed: CompletedStoryRun) -> None:
    typer.secho("生成完成。", fg=typer.colors.GREEN)
    typer.echo(f"Run：{completed.run_id}")
    typer.echo(f"叙事提示词：{completed.published.prompt_file}")


def _print_run_summary(
    summary: StoryRunSummary,
    runs_dir: Path,
) -> None:
    typer.echo(f"{summary.run_id}  ", nl=False)
    color = (
        typer.colors.GREEN
        if summary.status == StoryRunStatus.COMPLETED
        else typer.colors.RED
        if summary.status == StoryRunStatus.FAILED
        else typer.colors.YELLOW
    )
    typer.secho(f"{summary.status.value:<9}", fg=color, nl=False)
    typer.echo(
        f"  {summary.theme_count}×{summary.frames_per_theme}"
        f"  {summary.updated_at[:16]}"
        f"  {_ellipsize(summary.story, 32)}"
    )
    if summary.status == StoryRunStatus.COMPLETED:
        typer.echo(f"    提示词：{summary.prompt_file}")
        return
    if summary.error:
        typer.echo(f"    错误：{_ellipsize(summary.error, 72)}")
    typer.echo(
        f"    继续：uv run t2i-story resume {summary.run_id} "
        f"--runs-dir {runs_dir}"
    )


def _ellipsize(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _exit_for_error(error: Exception, runs_dir: Path) -> None:
    typer.secho(f"生成失败：{error}", fg=typer.colors.RED, err=True)
    if isinstance(error, StoryRunIncompleteError):
        typer.echo(
            f"继续命令：uv run t2i-story resume {error.run_id} "
            f"--runs-dir {runs_dir}",
            err=True,
        )
    raise typer.Exit(code=2) from error
