"""CLI for the standalone spatial prompt pipeline."""

from __future__ import annotations

import asyncio
import json
from enum import StrEnum
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_spatial_pipeline.errors import SpatialPipelineError
from t2i_spatial_pipeline.service import (
    build_scene_requests,
    generate_spatial_batch,
)


class CastKey(StrEnum):
    ONE_WOMAN = "one_woman"
    ONE_WOMAN_ONE_MAN = "one_woman_one_man"
    ONE_WOMAN_TWO_MEN = "one_woman_two_men"
    TWO_WOMEN = "two_women"
    THREE_WOMEN = "three_women"


app = typer.Typer(
    name="t2i-spatial",
    help="从自然语言主题生成具有锁定人数、姿势、接触和镜头几何的提示词。",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Generate constraint-solved spatial image prompts."""


@app.command("generate")
def generate_command(
    brief: str = typer.Argument(..., help="场景、时代、氛围和视觉风格描述。"),
    cast: CastKey = typer.Option(
        CastKey.ONE_WOMAN_ONE_MAN,
        "--cast",
        help="每个场景使用的精确成年人物配置。",
    ),
    seed: int = typer.Option(42, "--seed", help="蓝图和本地采样随机种子。"),
    output: Path = typer.Option(
        Path("spatial-output"),
        "--output",
        file_okay=False,
        help="保存 prompts.txt、layers.json、selections.json 和 report.json。",
    ),
    refresh_blueprint: bool = typer.Option(
        False,
        "--refresh-blueprint",
        help="忽略内容寻址缓存并重新推导 CreativeBlueprint。",
    ),
) -> None:
    """Generate one validated twelve-prompt spatial batch."""
    try:
        requests = build_scene_requests(cast.value, seed=seed)
        report = asyncio.run(
            generate_spatial_batch(
                brief,
                seed,
                refresh_blueprint=refresh_blueprint,
                scene_requests=requests,
                output=output,
            )
        )
    except (OSError, ValidationError, ValueError, SpatialPipelineError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise typer.Exit(code=1)
