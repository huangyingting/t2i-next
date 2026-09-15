"""CLI for the standalone spatial prompt pipeline."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_spatial_pipeline.catalog import cast_key_for_counts
from t2i_spatial_pipeline.errors import SpatialPipelineError
from t2i_spatial_pipeline.service import (
    build_scene_requests,
    generate_spatial_batch,
)

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
    female_count: int = typer.Option(
        1,
        "--female-count",
        min=1,
        max=3,
        help="每个场景的精确成年女性人数。",
    ),
    male_count: int = typer.Option(
        1,
        "--male-count",
        min=0,
        max=2,
        help="每个场景的精确成年男性人数。",
    ),
    seed: int = typer.Option(42, "--seed", help="蓝图和本地采样随机种子。"),
    count: int = typer.Option(
        12,
        "--count",
        min=1,
        max=20,
        help="生成场景数量；每批支持1至20个。",
    ),
    prompts_dir: Path = typer.Option(
        Path("prompts"),
        "--prompts-dir",
        file_okay=False,
        help="按运行日期在 hardcore 子目录中保存最终 TXT 提示词。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs") / "spatial",
        "--runs-dir",
        file_okay=False,
        help="保存蓝图、选择记录、解析层、报告和蓝图缓存。",
    ),
    refresh_blueprint: bool = typer.Option(
        False,
        "--refresh-blueprint",
        help="忽略内容寻址缓存并重新推导 CreativeBlueprint。",
    ),
) -> None:
    """Generate one validated spatial prompt batch."""
    try:
        cast_key = cast_key_for_counts(female_count, male_count)
        requests = build_scene_requests(cast_key, seed=seed, count=count)
        report = asyncio.run(
            generate_spatial_batch(
                brief,
                seed,
                refresh_blueprint=refresh_blueprint,
                scene_requests=requests,
                runs_directory=runs_dir,
                prompts_directory=prompts_dir,
            )
        )
    except (OSError, ValidationError, ValueError, SpatialPipelineError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise typer.Exit(code=1)
