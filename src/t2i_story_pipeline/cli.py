"""CLI for the minimal prose-first narrative pipeline."""

from __future__ import annotations

import asyncio
import json
from enum import StrEnum
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.errors import (
    StoryConfigurationError,
    StoryPipelineError,
    StoryRunIncompleteError,
)
from t2i_story_pipeline.inputs import (
    InputOverrides,
    ResolvedStoryInput,
    StoryDocument,
    load_run_configuration,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.models import (
    ContentLevel,
    OutputLanguage,
    QualityMode,
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
        help="读取只描述画面内容的 UTF-8 YAML 故事文档。",
    ),
    run_config: Path | None = typer.Option(
        None,
        "--run-config",
        help="读取外部 UTF-8 JSON 执行配置；显式 CLI 选项优先。",
    ),
    themes: int | None = typer.Option(
        None,
        "--themes",
        min=1,
        max=100,
        help="覆盖执行配置主题数；未配置时为 1。",
    ),
    frames: int | None = typer.Option(
        None,
        "--frames",
        min=1,
        max=6,
        help="覆盖执行配置每主题帧数；未配置时为 6。",
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
        help="Theme 与 Frame 共用的并发上限；未配置时为 8。",
    ),
    generation_retries: int | None = typer.Option(
        None,
        "--generation-retries",
        min=0,
        max=5,
        help="覆盖执行配置生成重试次数；未配置时为 2。",
    ),
    theme_batch_size: int | None = typer.Option(
        None,
        "--theme-batch-size",
        min=1,
        max=10,
        help="每批 Theme 数量；未配置时为 10。",
    ),
    theme_output_tokens: int | None = typer.Option(
        None,
        "--theme-output-tokens",
        min=512,
        max=65536,
        help="Theme 批次初始输出预算；未配置时为 12000，受 provider 上限约束。",
    ),
    frame_output_tokens: int | None = typer.Option(
        None,
        "--frame-output-tokens",
        min=512,
        max=65536,
        help="Frame 批次初始输出预算；未配置时为 32768，受 provider 上限约束。",
    ),
    theme_quality_mode: QualityMode | None = typer.Option(
        None,
        "--theme-quality-mode",
        help="Theme 可选质量检查：off、report 或 enforce。",
    ),
    frame_quality_mode: QualityMode | None = typer.Option(
        None,
        "--frame-quality-mode",
        help="Frame 可选质量检查：off、report 或 enforce。",
    ),
    frame_min_words: int | None = typer.Option(
        None,
        "--frame-min-words",
        min=1,
        max=32768,
        help="每帧正文最少空白分隔词数；中文通常应使用字符预算。",
    ),
    frame_max_words: int | None = typer.Option(
        None,
        "--frame-max-words",
        min=1,
        max=32768,
        help="每帧正文最多空白分隔词数。",
    ),
    frame_min_chars: int | None = typer.Option(
        None,
        "--frame-min-chars",
        min=1,
        max=32768,
        help="每帧正文最少字符数（含空格和标点）。",
    ),
    frame_max_chars: int | None = typer.Option(
        None,
        "--frame-max-chars",
        min=1,
        max=32768,
        help="每帧正文最多字符数（含空格和标点）。",
    ),
    content_level: ContentLevel | None = typer.Option(
        None,
        "--content-level",
        help="覆盖执行配置内容尺度；未配置时为 aesthetic。",
    ),
    output_language: OutputLanguage | None = typer.Option(
        None,
        "--language",
        help="覆盖执行配置正文语言；未配置时为 chinese。",
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
    assets_dir: Path | None = typer.Option(
        None,
        "--assets-dir",
        file_okay=False,
        help="显式模块与目录资产根；默认相对 YAML 文档所在目录。",
    ),
) -> None:
    """Generate themes and final narrative paragraphs from one story."""
    try:
        resolved = _resolve_input(
            story,
            input_file,
            assets_dir,
            InputOverrides(
                theme_count=themes,
                frames_per_theme=frames,
                female_count=female_count,
                male_count=male_count,
                content_level=content_level,
                output_language=output_language,
                concurrency=concurrency,
                generation_retries=generation_retries,
                theme_batch_size=theme_batch_size,
                theme_output_tokens=theme_output_tokens,
                frame_output_tokens=frame_output_tokens,
                theme_quality_mode=theme_quality_mode,
                frame_quality_mode=frame_quality_mode,
                frame_min_words=frame_min_words,
                frame_max_words=frame_max_words,
                frame_min_chars=frame_min_chars,
                frame_max_chars=frame_max_chars,
            ),
            run_config=run_config,
        )
        settings = StoryRunSettings(
            provider=load_story_provider_settings(),
            **resolved.runtime.model_dump(),
            quality=resolved.quality,
        )
        if not any(
            policy.checks and policy.mode != QualityMode.OFF
            for policy in (resolved.quality.themes, resolved.quality.frames)
        ):
            typer.echo("未启用可选质量检查；仅执行基础结构契约。")
        completed = asyncio.run(
            _generate(
                resolved,
                settings,
                runs_directory=runs_dir,
                prompts_directory=prompts_dir,
            )
        )
    except (ValidationError, StoryPipelineError) as exc:
        _exit_for_error(exc, runs_dir)

    _print_completed(completed)


class ExplainFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


@app.command("explain")
def explain_command(
    story: str | None = typer.Argument(None),
    input_file: Path | None = typer.Option(None, "--input"),
    run_config: Path | None = typer.Option(None, "--run-config"),
    assets_dir: Path | None = typer.Option(None, "--assets-dir"),
    themes: int | None = typer.Option(None, "--themes"),
    frames: int | None = typer.Option(None, "--frames"),
    female_count: int | None = typer.Option(None, "--female-count"),
    male_count: int | None = typer.Option(None, "--male-count"),
    content_level: ContentLevel | None = typer.Option(None, "--content-level"),
    output_language: OutputLanguage | None = typer.Option(None, "--language"),
    concurrency: int | None = typer.Option(None, "--concurrency"),
    generation_retries: int | None = typer.Option(None, "--generation-retries"),
    theme_batch_size: int | None = typer.Option(None, "--theme-batch-size"),
    theme_output_tokens: int | None = typer.Option(None, "--theme-output-tokens"),
    frame_output_tokens: int | None = typer.Option(None, "--frame-output-tokens"),
    theme_quality_mode: QualityMode | None = typer.Option(None, "--theme-quality-mode"),
    frame_quality_mode: QualityMode | None = typer.Option(None, "--frame-quality-mode"),
    frame_min_words: int | None = typer.Option(None, "--frame-min-words"),
    frame_max_words: int | None = typer.Option(None, "--frame-max-words"),
    frame_min_chars: int | None = typer.Option(None, "--frame-min-chars"),
    frame_max_chars: int | None = typer.Option(None, "--frame-max-chars"),
    output_format: ExplainFormat = typer.Option(ExplainFormat.JSON, "--format"),
) -> None:
    """离线预检最终输入、来源和槽位计划；不读取 provider 配置或创建 run。"""
    try:
        resolved = _resolve_input(
            story,
            input_file,
            assets_dir,
            InputOverrides(
                theme_count=themes,
                frames_per_theme=frames,
                female_count=female_count,
                male_count=male_count,
                content_level=content_level,
                output_language=output_language,
                concurrency=concurrency,
                generation_retries=generation_retries,
                theme_batch_size=theme_batch_size,
                theme_output_tokens=theme_output_tokens,
                frame_output_tokens=frame_output_tokens,
                theme_quality_mode=theme_quality_mode,
                frame_quality_mode=frame_quality_mode,
                frame_min_words=frame_min_words,
                frame_max_words=frame_max_words,
                frame_min_chars=frame_min_chars,
                frame_max_chars=frame_max_chars,
            ),
            run_config=run_config,
        )
    except (ValidationError, StoryPipelineError, typer.BadParameter) as exc:
        if output_format == ExplainFormat.JSON:
            typer.echo(
                json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False)
            )
        else:
            typer.secho(f"输入无效：{exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    if output_format == ExplainFormat.JSON:
        typer.echo(
            json.dumps(
                {
                    "status": "valid",
                    "fingerprint": resolved.fingerprint(),
                    "input": resolved.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        typer.echo(f"输入有效：{resolved.request.source_prompt_stem or '直接正文'}")
        typer.echo(
            f"主题：{resolved.request.theme_count}；每主题帧：{resolved.request.frames_per_theme}"
        )
        typer.echo(
            f"规则：Theme {len(resolved.rules.themes)}；"
            f"Frame {len(resolved.rules.frames)}"
        )
        typer.echo(f"计划槽位：{len(resolved.plans)}；指纹：{resolved.fingerprint()}")


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
    """Continue only missing themes and frames."""
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


def _resolve_input(
    story: str | None,
    input_file: Path | None,
    assets_dir: Path | None,
    overrides: InputOverrides,
    *,
    run_config: Path | None = None,
) -> ResolvedStoryInput:
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
    if input_file is not None:
        document = load_story_document(input_file)
    else:
        if story is None:
            raise AssertionError("story input resolution changed unexpectedly")
        document = StoryDocument(description=story)
    return resolve_story_input(
        document,
        overrides,
        run_configuration=(
            load_run_configuration(run_config) if run_config is not None else None
        ),
        asset_root=assets_dir,
        source_path=input_file,
    )


async def _generate(
    resolved: ResolvedStoryInput,
    settings: StoryRunSettings,
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
            on_progress=typer.echo,
        ).run(resolved)


async def _resume(
    run_id: str,
    provider: StoryProviderSettings,
    settings: StoryRunSettings,
    store: LocalStoryRunStore,
) -> CompletedStoryRun:
    async with story_model(provider) as model:
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
    report = completed.result.quality
    for label, stage_report in (("Theme", report.themes), ("Frame", report.frames)):
        typer.echo(
            f"{label} 质量检查：{stage_report.status}（{stage_report.mode.value}）"
        )
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
