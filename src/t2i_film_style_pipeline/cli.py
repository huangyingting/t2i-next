"""CLI for work-specific film-style profile generation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_film_style_pipeline.config import load_film_style_provider_settings
from t2i_film_style_pipeline.errors import FilmStylePipelineError
from t2i_film_style_pipeline.models import (
    FilmStyleRequest,
    parse_work_reference,
)
from t2i_film_style_pipeline.provider import OpenAIFilmStyleModel
from t2i_film_style_pipeline.service import FilmStyleStudio

app = typer.Typer(
    name="t2i-film-style",
    help="从导演的具体作品集合提炼可执行视觉档案并编译 Story Description。",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Compile work-specific film language for the story pipeline."""


@app.command("generate")
def generate_command(
    director: str = typer.Argument(..., help="作品集合的导演署名。"),
    work: list[str] = typer.Option(
        ...,
        "--work",
        help="具体作品，可重复；支持 TITLE 或 TITLE (YEAR)。",
    ),
    brief_file: Path = typer.Option(
        ...,
        "--brief-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="以 BRIEF 开头的基础 Story Description。",
    ),
    output_language: str = typer.Option(
        "chinese",
        "--language",
        help="视觉档案语言：chinese 或 english。",
    ),
    output_dir: Path = typer.Option(
        Path("film-style-inputs"),
        "--output-dir",
        file_okay=False,
        help="保存可直接传给 t2i-story 的编译后 Story Description。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs") / "film-style",
        "--runs-dir",
        file_okay=False,
        help="保存请求、结构化视觉档案和完整结果。",
    ),
) -> None:
    """Generate one reusable style profile and compile a story input."""
    try:
        base_brief = brief_file.read_text(encoding="utf-8").strip()
        request = FilmStyleRequest(
            director=director,
            works=tuple(parse_work_reference(item) for item in work),
            base_brief=base_brief,
            output_language=output_language,
        )
        settings = load_film_style_provider_settings()
        completed = asyncio.run(
            _generate(
                request,
                source_stem=brief_file.stem,
                settings=settings,
                runs_directory=runs_dir,
                output_directory=output_dir,
            )
        )
    except (
        OSError,
        UnicodeError,
        ValidationError,
        FilmStylePipelineError,
    ) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Run：{completed.result.run_id}")
    typer.echo(f"视觉档案：{completed.published.profile_file}")
    typer.echo(f"Story Description：{completed.published.prompt_file}")


async def _generate(
    request: FilmStyleRequest,
    *,
    source_stem: str,
    settings,
    runs_directory: Path,
    output_directory: Path,
):
    async with OpenAIFilmStyleModel(settings) as model:
        return await FilmStyleStudio(
            model,
            runs_directory=runs_directory,
            output_directory=output_directory,
        ).run(request, source_stem=source_stem)
