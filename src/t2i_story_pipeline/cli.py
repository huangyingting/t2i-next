"""CLI for the minimal prose-first narrative pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.errors import StoryPipelineError
from t2i_story_pipeline.models import (
    ContentLevel,
    OutputLanguage,
    StoryRequest,
    StoryResult,
)
from t2i_story_pipeline.provider import (
    OpenAIStoryModel,
    StoryProviderSettings,
)
from t2i_story_pipeline.storage import publish_story
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
    output_dir: Path = typer.Option(
        Path("story-prompts"),
        "--output-dir",
        file_okay=False,
        help="JSON 与提示词输出目录。",
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
        result = asyncio.run(
            _generate(request, settings, concurrency=concurrency)
        )
        published = publish_story(result, output_dir)
    except (ValidationError, StoryPipelineError) as exc:
        typer.echo(f"生成失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"结构化结果：{published.json_file}")
    typer.echo(f"叙事提示词：{published.prompt_file}")


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
) -> StoryResult:
    async with OpenAIStoryModel(settings) as model:
        return await StoryStudio(
            model,
            concurrency=concurrency,
        ).generate(request)
