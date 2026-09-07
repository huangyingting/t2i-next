"""CLI for the standalone story-first pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_story_pipeline.config import load_story_provider_settings
from t2i_story_pipeline.errors import StoryPipelineError
from t2i_story_pipeline.models import (
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
    help="从一段故事描述生成连续、可独立渲染的文生图提示词。",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Generate image prompts from story prose."""


@app.command("generate")
def generate_command(
    story: str = typer.Argument(
        ...,
        help="包含时间、地点、人物、互动、动作与氛围的故事描述。",
    ),
    themes: int = typer.Option(
        1,
        "--themes",
        min=1,
        max=100,
        help="生成彼此不同的创意主题数。",
    ),
    frames: int = typer.Option(
        6,
        "--frames",
        min=1,
        max=6,
        help="每个主题的连续画面数。",
    ),
    output_language: OutputLanguage = typer.Option(
        OutputLanguage.CHINESE,
        "--language",
        help="提示词语言。",
    ),
    max_revisions: int = typer.Option(
        2,
        "--max-revisions",
        min=0,
        max=5,
        help="叙事评审不通过时允许的最大修订次数。",
    ),
    output_dir: Path = typer.Option(
        Path("story-prompts"),
        "--output-dir",
        file_okay=False,
        help="JSON 与提示词输出目录。",
    ),
) -> None:
    """Generate creative themes and ordered image prompts from one story."""
    try:
        request = StoryRequest(
            story=story,
            theme_count=themes,
            frames_per_theme=frames,
            output_language=output_language,
        )
        settings = load_story_provider_settings()
        result = asyncio.run(_generate(request, settings, max_revisions=max_revisions))
        published = publish_story(result, output_dir)
    except (ValidationError, StoryPipelineError) as exc:
        typer.echo(f"生成失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"故事结构：{published.json_file}")
    typer.echo(f"电影化叙事：{published.prose_file}")
    typer.echo(f"提示词：{published.prompt_file}")


async def _generate(
    request: StoryRequest,
    settings: StoryProviderSettings,
    *,
    max_revisions: int,
) -> StoryResult:
    async with OpenAIStoryModel(settings) as model:
        return await StoryStudio(
            model,
            max_revisions=max_revisions,
        ).generate(request)
