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
    story: str = typer.Argument(
        ...,
        help="包含时间、地点、人物、事件与氛围的故事描述。",
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
    concurrency: int = typer.Option(
        10,
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
            story=story,
            theme_count=themes,
            frames_per_theme=frames,
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
