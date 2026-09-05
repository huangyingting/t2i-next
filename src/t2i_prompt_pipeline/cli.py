"""Command-line entry points for generation and resume."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_prompt_pipeline.batch import BatchLimits, BatchResult
from t2i_prompt_pipeline.cast_matrix_batch import (
    build_cast_matrix_tasks,
    default_cast_matrix_state_file,
    run_cast_matrix_batch,
)
from t2i_prompt_pipeline.config import (
    build_config,
    load_provider_settings,
    load_theme_similarity_settings,
)
from t2i_prompt_pipeline.errors import (
    PromptPipelineError,
    RunIncompleteError,
)
from t2i_prompt_pipeline.models import (
    AppConfig,
    ArchivedRun,
    ContentLevel,
    FrameMode,
    GenerationSpec,
    OutputLanguage,
    ProviderSettings,
    RunSettings,
    RunStatus,
    RunSummary,
)
from t2i_prompt_pipeline.pipeline import PromptStudio
from t2i_prompt_pipeline.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from t2i_prompt_pipeline.safe_avant_garde_batch import (
    build_safe_avant_garde_tasks,
    run_safe_avant_garde_batch,
)
from t2i_prompt_pipeline.store import LocalRunStore
from t2i_prompt_pipeline.theme_similarity import ThemeSimilarityAnalyzer

app = typer.Typer(
    name="t2i-prompts",
    help="生成 brief 风格约束、自适应 Theme 和当前 Frame。",
    no_args_is_help=True,
)

_RUN_STATUS_COLORS = {
    RunStatus.RUNNING: typer.colors.YELLOW,
    RunStatus.FAILED: typer.colors.RED,
    RunStatus.COMPLETED: typer.colors.GREEN,
}


@app.callback()
def main() -> None:
    """Generate and resume image-prompt runs."""


@app.command("generate")
def generate_command(
    brief: str = typer.Argument(
        ...,
        help="需要生成的画面内容；包含空格时请使用引号。",
    ),
    theme_count: int = typer.Option(
        1,
        "--theme-count",
        min=1,
        max=100,
        help="主题数量。",
    ),
    frames_per_theme: int = typer.Option(
        1,
        "--frames-per-theme",
        min=1,
        max=100,
        help="每个主题的镜头数量。",
    ),
    female_count: int | None = typer.Option(
        None,
        "--female-count",
        min=0,
        max=8,
        help="可选女性人数约束；默认从 brief 解析。",
    ),
    male_count: int | None = typer.Option(
        None,
        "--male-count",
        min=0,
        max=8,
        help="可选男性人数约束；默认从 brief 解析。",
    ),
    content_level: ContentLevel = typer.Option(
        ContentLevel.AESTHETIC,
        "--content-level",
        help="提供给模型的内容尺度提示，不进行规则校验。",
    ),
    frame_mode: FrameMode = typer.Option(
        FrameMode.SEQUENTIAL,
        "--frame-mode",
        help="连续分镜或独立变化。",
    ),
    output_language: OutputLanguage = typer.Option(
        OutputLanguage.CHINESE,
        "--output-language",
        "--language",
        help="Theme、Frame 和最终提示词的输出语言。",
    ),
    concurrency: int = typer.Option(
        8,
        "--concurrency",
        min=1,
        max=16,
        help="并发模型调用数；默认 8。",
    ),
    theme_batch_size: int = typer.Option(
        5,
        "--theme-batch-size",
        min=1,
        max=20,
        help="每次 Theme 调用的最大主题数；默认 5。",
    ),
    generation_retries: int = typer.Option(
        2,
        "--generation-retries",
        min=0,
        max=5,
        help="结构错误、截断或缺失补全的额外尝试次数；默认 2。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs"),
        "--runs-dir",
        file_okay=False,
        help="增量 checkpoint 目录。",
    ),
    prompts_dir: Path = typer.Option(
        Path("prompts"),
        "--prompts-dir",
        file_okay=False,
        help="最终提示词文件目录。",
    ),
    rules_dir: Path | None = typer.Option(
        None,
        "--rules-dir",
        file_okay=False,
        help="用户规则目录；默认自动使用当前目录下的 rules/。",
    ),
) -> None:
    """Create a run, checkpoint each object, and publish when complete."""
    try:
        spec = GenerationSpec(
            brief=brief,
            theme_count=theme_count,
            frames_per_theme=frames_per_theme,
            female_count=female_count,
            male_count=male_count,
            content_level=content_level,
            frame_mode=frame_mode,
            output_language=output_language,
        )
        config = build_config(
            spec,
            runs_directory=runs_dir,
            prompts_directory=prompts_dir,
            rules_directory=rules_dir,
            max_concurrency=concurrency,
            theme_batch_size=theme_batch_size,
            generation_retries=generation_retries,
        )
        base_calls = (
            1
            + math.ceil(
                theme_count / config.run_settings.theme_batch_size
            )
            + theme_count
        )
        typer.echo(
            f"开始生成：基础调用约 {base_calls} 次；"
            "缺失项会定向补全。"
        )
        archived = asyncio.run(_run(config))
    except (ValidationError, PromptPipelineError) as exc:
        _exit_for_error(exc, runs_dir)

    _print_completed(archived)


@app.command("generate-safe-avant-garde")
def generate_safe_avant_garde_command(
    concurrency: int = typer.Option(
        16,
        "--concurrency",
        min=1,
        max=16,
        help="并发模型调用数；默认 16。",
    ),
    theme_batch_size: int = typer.Option(
        5,
        "--theme-batch-size",
        min=1,
        max=20,
        help="每次 Theme 调用的最大主题数；默认 5。",
    ),
    generation_retries: int = typer.Option(
        2,
        "--generation-retries",
        min=0,
        max=5,
        help="每次结构补全的额外尝试次数；默认 2。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs"),
        "--runs-dir",
        file_okay=False,
        help="增量 checkpoint 和批次状态目录。",
    ),
    prompts_dir: Path = typer.Option(
        Path("prompts"),
        "--prompts-dir",
        file_okay=False,
        help="最终提示词文件目录。",
    ),
    rules_dir: Path = typer.Option(
        Path("rules/batches/safe_avant_garde"),
        "--rules-dir",
        file_okay=False,
        help="安全先锋艺术批次规则目录。",
    ),
    state_file: Path | None = typer.Option(
        None,
        "--state-file",
        dir_okay=False,
        help="批次状态文件；默认位于 runs 目录。",
    ),
    batch_max_attempts: int | None = typer.Option(
        None, "--batch-max-attempts", min=1, max=1000,
        help="每个任务累计 run 尝试上限（含首次）；新批次默认 10，恢复时保留。",
    ),
    batch_timeout_seconds: float | None = typer.Option(
        None, "--batch-timeout-seconds", min=1, max=31536000,
        help="从创建起的批次总秒数（含中断时间）；新批次默认 86400。",
    ),
) -> None:
    """Generate the fixed 24-artist safe, clothed portrait matrix."""
    tasks = build_safe_avant_garde_tasks()
    resolved_state_file = (
        state_file
        if state_file is not None
        else runs_dir / "safe-avant-garde-batch.json"
    )
    try:
        config = build_config(
            tasks[0].spec,
            runs_directory=runs_dir,
            prompts_directory=prompts_dir,
            rules_directory=rules_dir,
            max_concurrency=concurrency,
            theme_batch_size=theme_batch_size,
            generation_retries=generation_retries,
        )
        typer.echo("开始安全先锋艺术批次：72 个 run，43,200 个 Frame。")
        result = asyncio.run(
            run_safe_avant_garde_batch(
                config,
                resolved_state_file,
                limits=_batch_limits(
                    batch_max_attempts, None, batch_timeout_seconds
                ),
                on_progress=typer.echo,
            )
        )
    except (ValidationError, PromptPipelineError) as exc:
        _exit_for_error(exc, runs_dir)

    typer.secho("安全先锋艺术批次完成", fg=typer.colors.GREEN)
    typer.echo(f"完成 run：{result.completed_tasks}/72")
    typer.echo(f"生成 Frame：{result.generated_frames}/43200")
    typer.echo(f"批次状态：{result.state_file}")


@app.command("generate-cast-matrix")
def generate_cast_matrix_command(
    brief: str = typer.Argument(
        ...,
        help="五组人物配置共享的场景、时代和视觉要求；不要在此指定人数。",
    ),
    content_level: ContentLevel = typer.Option(
        ...,
        "--content-level",
        help="五组任务共同使用的内容尺度。",
    ),
    rules_dir: Path | None = typer.Option(
        None,
        "--rules-dir",
        file_okay=False,
        help="可选用户规则目录；默认使用当前目录下的 rules/。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs"),
        "--runs-dir",
        file_okay=False,
        help="增量 checkpoint 和批次状态目录。",
    ),
    prompts_dir: Path = typer.Option(
        Path("prompts"),
        "--prompts-dir",
        file_okay=False,
        help="最终提示词文件目录。",
    ),
    state_file: Path | None = typer.Option(
        None,
        "--state-file",
        dir_okay=False,
        help="批次状态文件；默认按 brief、尺度和规则生成稳定文件名。",
    ),
    retry_delay_seconds: float = typer.Option(
        5,
        "--retry-delay-seconds",
        min=0,
        help="可恢复失败后的等待秒数。",
    ),
    batch_max_attempts: int | None = typer.Option(
        None, "--batch-max-attempts", min=1, max=1000,
        help="每个任务累计 run 尝试上限（含首次）；新批次默认 10，恢复时保留。",
    ),
    batch_max_replacements: int | None = typer.Option(
        None, "--batch-max-replacements", min=0, max=100,
        help="每个任务的替代 run 上限；新批次默认 2，恢复时保留。",
    ),
    batch_timeout_seconds: float | None = typer.Option(
        None, "--batch-timeout-seconds", min=1, max=31536000,
        help="从创建起的批次总秒数（含中断时间）；新批次默认 86400。",
    ),
) -> None:
    """Generate five resumable 100-theme by 6-frame cast combinations."""
    try:
        tasks = build_cast_matrix_tasks(brief, content_level)
        config = build_config(
            tasks[0].spec,
            runs_directory=runs_dir,
            prompts_directory=prompts_dir,
            rules_directory=rules_dir,
            max_concurrency=16,
            theme_batch_size=5,
            generation_retries=5,
        )
        resolved_state_file = (
            state_file
            if state_file is not None
            else default_cast_matrix_state_file(
                runs_dir,
                tasks,
                config.rules.fingerprint(),
            )
        )
        typer.echo("开始人物矩阵：5 个 run，500 个 Theme，3,000 个 Frame。")
        result = asyncio.run(
            run_cast_matrix_batch(
                config,
                tasks,
                resolved_state_file,
                limits=_batch_limits(
                    batch_max_attempts,
                    batch_max_replacements,
                    batch_timeout_seconds,
                ),
                retry_delay_seconds=retry_delay_seconds,
                on_progress=typer.echo,
            )
        )
    except (ValidationError, PromptPipelineError) as exc:
        _exit_for_error(exc, runs_dir)

    _print_cast_matrix_completed(result)


def _batch_limits(
    attempts: int | None,
    replacements: int | None,
    duration: float | None,
) -> BatchLimits:
    return BatchLimits.model_validate({
        name: value
        for name, value in {
            "max_task_attempts": attempts,
            "max_replacement_runs": replacements,
            "max_duration_seconds": duration,
        }.items()
        if value is not None
    })


def _print_cast_matrix_completed(result: BatchResult) -> None:
    typer.secho("人物矩阵生成完成。", fg=typer.colors.GREEN)
    typer.echo(f"完成 run：{result.completed_tasks}/5")
    typer.echo(f"生成 Frame：{result.generated_frames}/3000")
    for prompt_file in result.prompt_files:
        typer.echo(f"Prompts：{prompt_file}")
    typer.echo(f"批次状态：{result.state_file}")


@app.command("resume")
def resume_command(
    run_id: str = typer.Argument(..., help="需要继续的 run ID。"),
    runs_dir: Path = typer.Option(
        Path("runs"),
        "--runs-dir",
        file_okay=False,
        help="增量 checkpoint 目录。",
    ),
) -> None:
    """Continue only the missing objects in an existing run."""
    try:
        # Resume republishes to the prompts directory recorded in the run
        # manifest, so this store needs no prompts root.
        store = LocalRunStore(runs_dir)
        snapshot = store.inspect(run_id)
        if snapshot.completed is not None:
            _print_completed(snapshot.completed)
            return
        provider = load_provider_settings()
        live_settings = snapshot.settings.model_copy(
            update={
                "provider_signature": provider.signature(),
                "output_token_limit": provider.output_token_limit,
                "theme_similarity": load_theme_similarity_settings(provider),
            }
        )
        snapshot.settings.ensure_resumable_with(live_settings)
        archived = asyncio.run(
            _resume(
                run_id,
                provider,
                live_settings,
                store,
            )
        )
    except (ValidationError, PromptPipelineError) as exc:
        _exit_for_error(exc, runs_dir)

    _print_completed(archived)


@app.command("runs")
def runs_command(
    runs_dir: Path = typer.Option(
        Path("runs"),
        "--runs-dir",
        file_okay=False,
        help="增量 checkpoint 目录。",
    ),
) -> None:
    """List existing runs so an interrupted one can be found and resumed."""
    try:
        listing = LocalRunStore(runs_dir).list_runs()
    except PromptPipelineError as exc:
        _exit_for_error(exc, runs_dir)

    if not listing.runs and not listing.unreadable:
        typer.echo(f"{runs_dir} 中没有 run。")
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


def _print_run_summary(summary: RunSummary, runs_dir: Path) -> None:
    typer.echo(f"{summary.run_id}  ", nl=False)
    typer.secho(
        f"{summary.status.value:<9}",
        fg=_RUN_STATUS_COLORS[summary.status],
        nl=False,
    )
    typer.echo(
        f"  {summary.theme_count}×{summary.frames_per_theme}"
        f"  {_local_minute(summary.updated_at)}"
        f"  {_ellipsize(summary.brief, 32)}"
    )
    if summary.status == RunStatus.COMPLETED:
        typer.echo(f"    提示词：{summary.prompt_file}")
        return
    if summary.error:
        typer.echo(f"    错误：{_ellipsize(summary.error, 72)}")
    typer.echo(
        f"    继续：uv run t2i-prompts resume {summary.run_id} "
        f"--runs-dir {runs_dir}"
    )


def _local_minute(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value[:16]
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def _ellipsize(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


async def _run(config: AppConfig) -> ArchivedRun:
    store = LocalRunStore(
        config.runs_directory,
        config.prompts_directory,
    )
    async with OpenAICompatibleProvider(config.provider) as author:
        similarity = (
            ThemeSimilarityAnalyzer(author, config.run_settings.theme_similarity)
            if config.run_settings.theme_similarity is not None
            else None
        )
        studio = PromptStudio(
            author,
            store,
            config.run_settings,
            theme_similarity=similarity,
            on_progress=typer.echo,
        )
        return await studio.run(config.spec, config.rules)


async def _resume(
    run_id: str,
    provider: ProviderSettings,
    settings: RunSettings,
    store: LocalRunStore,
) -> ArchivedRun:
    async with OpenAICompatibleProvider(provider) as author:
        similarity = (
            ThemeSimilarityAnalyzer(author, settings.theme_similarity)
            if settings.theme_similarity is not None
            else None
        )
        studio = PromptStudio(
            author,
            store,
            settings,
            theme_similarity=similarity,
            on_progress=typer.echo,
        )
        return await studio.resume(run_id)


def _exit_for_error(error: Exception, runs_dir: Path) -> None:
    typer.secho(f"生成失败：{error}", fg=typer.colors.RED, err=True)
    if isinstance(error, RunIncompleteError):
        typer.echo(
            f"继续命令：uv run t2i-prompts resume {error.run_id} "
            f"--runs-dir {runs_dir}",
            err=True,
        )
    raise typer.Exit(code=2) from error


def _print_completed(archived: ArchivedRun) -> None:
    typer.secho("生成完成。", fg=typer.colors.GREEN)
    typer.echo(f"Run：{archived.run_id}")
    typer.echo(f"Book：{archived.book_file}")
    typer.echo(f"Prompts：{archived.prompt_file}")
    typer.echo(f"提示词：{len(archived.result.prompts)}")
