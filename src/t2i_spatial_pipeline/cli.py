"""CLI for the standalone spatial prompt pipeline."""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

import typer
from pydantic import ValidationError

from t2i_spatial_pipeline.audit import run_spatial_audit
from t2i_spatial_pipeline.catalog import cast_key_for_counts
from t2i_spatial_pipeline.errors import SpatialPipelineError
from t2i_spatial_pipeline.pose_reference_cli import app as pose_reference_app
from t2i_spatial_pipeline.service import (
    build_scene_requests,
    generate_spatial_batch,
    generate_spatial_bulk,
)

app = typer.Typer(
    name="t2i-spatial",
    help="生成覆盖完整空间 catalog、且必须经出图复核的提示词。",
    no_args_is_help=True,
)
app.add_typer(pose_reference_app, name="poses")


@app.callback()
def main() -> None:
    """Generate constraint-solved spatial image prompts."""


@app.command("audit-geometry")
def geometry_audit_command(
    input_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="包含显式场景几何和逐角色求解变量的 JSON 请求。",
    ),
    output: Path | None = typer.Option(
        None, "--output", dir_okay=False, help="保存数值验收证据 JSON。",
    ),
    preview: Path | None = typer.Option(
        None, "--preview", dir_okay=False, help="保存按相同容差重新验收的三视图 SVG。",
    ),
) -> None:
    """Jointly fit explicit scene contacts and independently validate all bodies."""
    from t2i_pose_geometry import SceneSolveRequest, solve_scene
    from t2i_pose_geometry.preview import render_scene_svg

    try:
        paths = [path.resolve() for path in (input_path, output, preview) if path]
        if len(paths) != len(set(paths)):
            raise ValueError("Input, report and preview paths must be distinct")
        request = SceneSolveRequest.model_validate_json(
            input_path.read_text(encoding="utf-8")
        )
        result = solve_scene(
            request.scene,
            request.variables_by_actor,
            max_nfev=request.max_nfev,
            root_translation_bound_m=request.root_translation_bound_m,
            tolerances=request.tolerances,
        )
        evidence = {
            "schema_version": "1.0",
            "validation_scope": "explicit_static_proxy_scene",
            "accepted": result.accepted,
            "physical_validation": False,
            "catalog_certification": False,
            "request": request.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
        serialized = json.dumps(evidence, indent=2) + "\n"
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized, encoding="utf-8")
        if preview is not None:
            image = render_scene_svg(result.scene, tolerances=result.tolerances)
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_text(image, encoding="utf-8")
    except (OSError, ValidationError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(serialized, nl=False)
    if not result.accepted:
        raise typer.Exit(code=1)


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
    """Generate one symbolically audited spatial prompt batch."""
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
    typer.secho(
        "Local symbolic audit passed; image anatomy and cast count still require "
        "render review.",
        fg=typer.colors.YELLOW,
        err=True,
    )


@app.command("bulk")
def bulk_command(
    brief: str = typer.Argument(..., help="五种人数配置共享的主题。"),
    count_per_category: int = typer.Option(
        600,
        "--count-per-category",
        min=1,
        help="每种人数配置生成的记录数。",
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        min=0,
        help="基础随机种子；省略时生成并输出一个新种子。",
    ),
    prompts_dir: Path = typer.Option(
        Path("prompts"),
        "--prompts-dir",
        file_okay=False,
        help="保存每种人数配置的聚合 TXT。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs") / "spatial",
        "--runs-dir",
        file_okay=False,
        help="保存可恢复的批次、共享蓝图缓存和 bulk 报告。",
    ),
    refresh_blueprints: bool = typer.Option(
        False,
        "--refresh-blueprints",
        help="为每种人数配置重新推导一次 CreativeBlueprint。",
    ),
) -> None:
    """Generate resumable batches for every supported cast category."""
    base_seed = secrets.randbelow(2_000_000_000) if seed is None else seed
    bulk_directory = runs_dir / f"bulk-{base_seed}"
    typer.echo(f"bulk base seed: {base_seed}")
    try:
        report = asyncio.run(
            generate_spatial_bulk(
                brief,
                base_seed,
                count_per_cast=count_per_category,
                refresh_blueprints=refresh_blueprints,
                runs_directory=bulk_directory,
                prompts_directory=prompts_dir,
                on_progress=typer.echo,
            )
        )
    except (OSError, ValidationError, ValueError, SpatialPipelineError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    typer.secho(
        "Bulk prompts passed symbolic checks only; rendered images still require "
        "visual review.",
        fg=typer.colors.YELLOW,
        err=True,
    )


@app.command("audit")
def audit_command(
    start_seed: int = typer.Option(
        0,
        "--start-seed",
        min=0,
        help="开始审核的本地随机种子。",
    ),
    seed_count: int = typer.Option(
        100,
        "--seed-count",
        min=1,
        help="每种人数配置审核的连续随机种子数量。",
    ),
    count: int = typer.Option(
        20,
        "--count",
        min=1,
        max=20,
        help="每个随机种子分配并审核的场景数量。",
    ),
    runs_dir: Path = typer.Option(
        Path("runs") / "spatial",
        "--runs-dir",
        file_okay=False,
        help="保存可恢复的本地审计进度。",
    ),
    restart: bool = typer.Option(
        False,
        "--restart",
        help="丢弃不完整或已完成的同路径审计进度并重新开始。",
    ),
) -> None:
    """Audit production catalogs and stress scene allocation without an LLM."""
    progress_path = runs_dir / "audit-progress.json"
    try:
        report = run_spatial_audit(
            progress_path,
            start_seed=start_seed,
            seed_count=seed_count,
            scene_count=count,
            restart=restart,
            on_progress=typer.echo,
        )
    except (OSError, ValidationError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(report.model_dump_json(indent=2))
