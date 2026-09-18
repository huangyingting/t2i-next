"""Offline commands for the neutral figure-study library."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from .pose_reference import (
    NeutralPoseLibrary,
    PoseReferenceBatch,
    audit_reference_library,
    sample_pose_references,
)
from .pose_reference_catalog import build_neutral_pose_library

app = typer.Typer(
    name="poses",
    help="List, sample and validate clothed adult figure-study poses offline.",
    no_args_is_help=True,
)


class ExportFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


def _library(family: str | None) -> NeutralPoseLibrary:
    library = build_neutral_pose_library()
    if family is None:
        return library
    poses = tuple(pose for pose in library.poses if pose.family == family)
    if not poses:
        raise ValueError(f"unknown reference pose family: {family}")
    return NeutralPoseLibrary(
        cameras=library.cameras,
        subjects=library.subjects,
        presentations=library.presentations,
        poses=poses,
    )


def _emit(content: str, output: Path | None) -> None:
    if output is None:
        typer.echo(content)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        output.unlink(missing_ok=True)
        raise
    typer.echo(f"Saved pose references: {output}")


@app.command("list")
def list_poses(
    family: Annotated[
        str | None, typer.Option(help="Filter by exact family ID.")
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(dir_okay=False, help="Write JSON to a new file; never overwrite."),
    ] = None,
) -> None:
    """Export the typed library, including supports and compatible cameras."""
    try:
        _emit(_library(family).model_dump_json(indent=2), output)
    except (OSError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command("sample")
def sample_poses(
    count: Annotated[int, typer.Option(min=1, help="Number of distinct poses.")] = 12,
    seed: Annotated[int, typer.Option(help="Deterministic selection seed.")] = 42,
    family: Annotated[
        str | None, typer.Option(help="Filter by exact family ID.")
    ] = None,
    subject: Annotated[
        str | None, typer.Option(help="Use one subject ID throughout the batch.")
    ] = None,
    presentation: Annotated[
        str | None,
        typer.Option(help="Filter to poses and cameras fitting this environment ID."),
    ] = None,
    history: Annotated[
        Path | None,
        typer.Option(
            exists=True, dir_okay=False, readable=True,
            help="Previous JSON batch; continue its immutable usage snapshot.",
        ),
    ] = None,
    output_format: Annotated[
        ExportFormat,
        typer.Option("--format", help="Structured JSON or one prompt per line."),
    ] = ExportFormat.JSON,
    output: Annotated[
        Path | None,
        typer.Option(dir_okay=False, help="Write to a new file; never overwrite."),
    ] = None,
) -> None:
    """Choose diverse neutral poses and render standalone clothed reference prompts."""
    try:
        previous: PoseReferenceBatch | None = None
        if history is not None:
            try:
                previous = PoseReferenceBatch.model_validate_json(
                    history.read_text(encoding="utf-8")
                )
            except ValidationError as exc:
                raise ValueError(
                    "history must be a valid current-schema reference JSON batch; "
                    "old schemas and text exports cannot be resumed"
                ) from exc
        batch = sample_pose_references(
            build_neutral_pose_library(),
            seed=seed,
            count=count,
            family=family,
            subject_id=(
                subject if subject is not None or previous is None
                else previous.subject.subject_id
            ),
            presentation_id=presentation,
            history=previous.history_after if previous is not None else None,
        )
        content = (
            "\n".join(scene.prompt for scene in batch.scenes)
            if output_format == ExportFormat.TEXT
            else batch.model_dump_json(indent=2)
        )
        _emit(content, output)
    except (OSError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command("audit")
def audit_poses(
    output: Annotated[
        Path | None,
        typer.Option(dir_okay=False, help="Write diagnostics to a new JSON file."),
    ] = None,
) -> None:
    """Validate all recipes and report symbolic structural coverage."""
    try:
        library = build_neutral_pose_library()
        report = audit_reference_library(library)
        _emit(report.model_dump_json(indent=2), output)
    except (OSError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
