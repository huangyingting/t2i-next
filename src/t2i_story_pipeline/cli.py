"""CLI for the minimal prose-first narrative pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.documents import (
    StoryDocument,
    StoryGeneration,
    StoryRuntime,
    load_story_document,
)
from t2i_story_pipeline.errors import (
    StoryConfigurationError,
    StoryPipelineError,
    StoryRunIncompleteError,
)
from t2i_story_pipeline.models import (
    ContentLevel,
    OutputLanguage,
    QualityMode,
    StoryQualityPolicy,
    StoryRequest,
    StoryRuleSet,
)
from t2i_story_pipeline.provider import (
    StoryProviderSettings,
    story_model,
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
    input_file: Path | None = typer.Option(
        None,
        "--input",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="读取 UTF-8 YAML 故事文档（正文、生成参数、创作规则与质量策略）。",
    ),
    themes: int | None = typer.Option(
        None,
        "--themes",
        min=1,
        max=100,
        help="覆盖文档主题数；未配置时为 1。",
    ),
    frames: int | None = typer.Option(
        None,
        "--frames",
        min=1,
        max=6,
        help="覆盖文档每主题帧数；未配置时为 6。",
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
    concurrency: int | None = typer.Option(
        None,
        "--concurrency",
        min=1,
        max=32,
        help="覆盖文档并发数；未配置时为 8。",
    ),
    generation_retries: int | None = typer.Option(
        None,
        "--generation-retries",
        min=0,
        max=5,
        help="覆盖文档生成重试次数；未配置时为 2。",
    ),
    quality_mode: QualityMode | None = typer.Option(
        None,
        "--quality-mode",
        help="可选质量检查：off、report 或 enforce；不影响基础结构契约。",
    ),
    content_level: ContentLevel | None = typer.Option(
        None,
        "--content-level",
        help="覆盖文档内容尺度；未配置时为 aesthetic。",
    ),
    output_language: OutputLanguage | None = typer.Option(
        None,
        "--language",
        help="覆盖文档正文语言；未配置时为 chinese。",
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
    rules_dir: Path | None = typer.Option(
        None,
        "--rules-dir",
        file_okay=False,
        help="可选 story 用户规则目录；默认使用 story-inputs/rules/。",
    ),
) -> None:
    """Generate themes and final narrative paragraphs from one story."""
    try:
        document = _resolve_document(story, input_file)
        generation = document.generation if document else StoryGeneration()
        generation_overrides = {
            key: value
            for key, value in {
                "theme_count": themes,
                "frames_per_theme": frames,
                "content_level": content_level,
                "output_language": output_language,
            }.items()
            if value is not None
        }
        cast_overrides = {
            key: value
            for key, value in {
                "female_count": female_count,
                "male_count": male_count,
            }.items()
            if value is not None
        }
        generation = StoryGeneration.model_validate(
            {
                **generation.model_dump(),
                **generation_overrides,
                "cast": {**generation.cast.model_dump(), **cast_overrides},
            }
        )
        description = document.description if document else story
        if description is None:
            raise AssertionError("story input resolution changed unexpectedly")
        request = generation.request(description, document.id if document else None)
        runtime = document.runtime if document else StoryRuntime()
        quality = document.validation.quality if document else StoryQualityPolicy()
        quality = StoryQualityPolicy.model_validate(
            {
                **quality.model_dump(),
                **({"mode": quality_mode} if quality_mode is not None else {}),
            }
        )
        default_rules_directory = Path("story-inputs") / "rules"
        user_rules_directory = (
            rules_dir
            if rules_dir is not None
            else (default_rules_directory if default_rules_directory.is_dir() else None)
        )
        rules = resolve_story_rules(
            request,
            user_directory=user_rules_directory,
            authoring=document.authoring if document else None,
        )
        settings = StoryRunSettings(
            provider=load_story_provider_settings(),
            concurrency=(
                concurrency if concurrency is not None else runtime.concurrency
            ),
            generation_retries=(
                generation_retries
                if generation_retries is not None
                else runtime.generation_retries
            ),
            quality=quality,
        )
        if not quality.checks and quality.mode != QualityMode.OFF:
            typer.echo("未配置可选质量检查；仅执行基础结构契约。")
        completed = asyncio.run(
            _generate(
                request,
                settings,
                rules,
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


def _resolve_document(
    story: str | None,
    input_file: Path | None,
) -> StoryDocument | None:
    if story is not None and input_file is not None:
        raise typer.BadParameter(
            "不能同时提供故事描述和 --input。",
            param_hint="STORY/--input",
        )
    if story is None and input_file is None:
        raise typer.BadParameter(
            "必须提供故事描述或 --input。",
            param_hint="STORY/--input",
        )
    return load_story_document(input_file) if input_file is not None else None


async def _generate(
    request: StoryRequest,
    settings: StoryRunSettings,
    rules: StoryRuleSet,
    *,
    runs_directory: Path = Path("runs"),
    prompts_directory: Path = Path("prompts"),
) -> CompletedStoryRun:
    store = LocalStoryRunStore(runs_directory, prompts_directory)
    async with story_model(settings.provider) as model:
        return await StoryStudio(
            model,
            store,
            settings,
            rules,
            on_progress=typer.echo,
        ).run(request)


async def _resume(
    run_id: str,
    provider: StoryProviderSettings,
    settings: StoryRunSettings,
    store: LocalStoryRunStore,
) -> CompletedStoryRun:
    rules = store.inspect(run_id).rules
    async with story_model(provider) as model:
        return await StoryStudio(
            model,
            store,
            settings,
            rules,
            on_progress=typer.echo,
        ).resume(run_id)


def _print_completed(completed: CompletedStoryRun) -> None:
    typer.secho("生成完成。", fg=typer.colors.GREEN)
    typer.echo(f"Run：{completed.run_id}")
    typer.echo(f"叙事提示词：{completed.published.prompt_file}")
    report = completed.result.quality
    typer.echo(f"质量检查：{report.status}（{report.mode.value}）")
    if report.issues:
        typer.secho(
            f"存在 {len(report.issues)} 条质量告警；结果按 report 策略发布。",
            fg=typer.colors.YELLOW,
        )
    typer.echo(f"完整结果与质量报告：{completed.result_file}")


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
        f"    继续：uv run t2i-story resume {summary.run_id} --runs-dir {runs_dir}"
    )


def _ellipsize(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _exit_for_error(error: Exception, runs_dir: Path) -> None:
    typer.secho(f"生成失败：{error}", fg=typer.colors.RED, err=True)
    if isinstance(error, StoryRunIncompleteError):
        typer.echo(
            f"继续命令：uv run t2i-story resume {error.run_id} --runs-dir {runs_dir}",
            err=True,
        )
    raise typer.Exit(
        code=1 if isinstance(error, StoryRunIncompleteError) else 2
    ) from error
