#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_COLUMNS = (
    "导演",
    "导演英文名",
    "作品类型",
    "代表作",
    "年份",
)
CASTS = (
    ("1w", 1, 0),
    ("1w1m", 1, 1),
    ("2w1m", 2, 1),
    ("2w2m", 2, 2),
    ("3w1m", 3, 1),
)
THEME_COUNT = 50
FRAMES_PER_THEME = 4
CONTENT_LEVEL = "hardcore"
RUN_ID_PATTERN = re.compile(r"\d{8}T\d{6}Z-[a-f0-9]{8}")


class BatchConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class FilmRow:
    row_number: int
    director: str
    english_name: str
    work: str
    year: str


@dataclass(frozen=True)
class Job:
    film: FilmRow
    cast_label: str
    female_count: int
    male_count: int

    @property
    def job_id(self) -> str:
        payload = "\0".join(
            (
                str(self.film.row_number),
                self.film.director,
                self.film.english_name,
                self.film.work,
                self.film.year,
                self.cast_label,
                str(self.female_count),
                str(self.male_count),
                CONTENT_LEVEL,
                str(THEME_COUNT),
                str(FRAMES_PER_THEME),
            )
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:20]

    @property
    def filename_stem(self) -> str:
        director = re.sub(r"[^A-Za-z0-9]+", "_", self.film.english_name).strip("_")
        if not director:
            raise BatchConfigurationError(
                f"CSV row {self.film.row_number}: 导演英文名 must contain ASCII "
                "letters or numbers"
            )
        return (
            f"{director}_{self.film.year}_r{self.film.row_number:04d}_{self.cast_label}"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Generate aesthetic Film prompts for every director-film row and "
            "the built-in five-cast matrix."
        )
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=repo_root / "asian-directors.csv",
        help="Input director-film CSV (default: repository asian-directors.csv).",
    )
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=repo_root / "prompts",
        help="Published prompt root.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=repo_root / "runs" / "asian-directors-aesthetic" / "runs",
        help="Film run checkpoint directory.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=repo_root / "runs" / "asian-directors-aesthetic" / "batch-state.jsonl",
        help="Append-only completion and failure ledger.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=16,
        choices=range(1, 33),
        metavar="1..32",
        help="Concurrency passed to each Film run.",
    )
    parser.add_argument(
        "--theme-batch-size",
        type=int,
        default=10,
        choices=range(1, 11),
        metavar="1..10",
        help="Theme batch size passed to each Film run.",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=1,
        help="First one-based CSV data row to include.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        help="Maximum number of CSV data rows to include.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pending commands without starting generation or writing state.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop after the first failed generation instead of continuing.",
    )
    args = parser.parse_args(argv)
    if args.start_row < 1:
        parser.error("--start-row must be at least 1")
    if args.max_rows is not None and args.max_rows < 1:
        parser.error("--max-rows must be at least 1")
    return args


def resolve_cli(repo_root: Path) -> list[str]:
    configured = os.environ.get("T2I_FILM_STYLE_CLI")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise BatchConfigurationError(
                f"T2I_FILM_STYLE_CLI is not executable: {path}"
            )
        return [str(path.resolve())]
    local_cli = repo_root / ".venv" / "bin" / "t2i-film-style"
    if local_cli.is_file() and os.access(local_cli, os.X_OK):
        return [str(local_cli)]
    installed = shutil.which("t2i-film-style")
    if installed:
        return [str(Path(installed).resolve())]
    uv = shutil.which("uv")
    if uv:
        return [str(Path(uv).resolve()), "run", "t2i-film-style"]
    raise BatchConfigurationError("Cannot find t2i-film-style or uv.")


def read_films(path: Path) -> list[FilmRow]:
    if not path.is_file():
        raise BatchConfigurationError(f"CSV file does not exist: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames is None:
                raise BatchConfigurationError(f"CSV has no header: {path}")
            missing = [
                name for name in REQUIRED_COLUMNS if name not in reader.fieldnames
            ]
            if missing:
                raise BatchConfigurationError(
                    f"CSV is missing required columns: {', '.join(missing)}"
                )
            films = []
            seen = set()
            for row_number, row in enumerate(reader, start=1):
                values = {
                    name: (row.get(name) or "").strip() for name in REQUIRED_COLUMNS
                }
                empty = [name for name, value in values.items() if not value]
                if empty:
                    raise BatchConfigurationError(
                        f"CSV row {row_number}: empty fields: {', '.join(empty)}"
                    )
                if values["作品类型"] != "真人电影":
                    raise BatchConfigurationError(
                        f"CSV row {row_number}: unsupported 作品类型 "
                        f"{values['作品类型']!r}; expected '真人电影'"
                    )
                if not re.fullmatch(r"\d{4}", values["年份"]):
                    raise BatchConfigurationError(
                        f"CSV row {row_number}: 年份 must be four digits"
                    )
                identity = (
                    values["导演"],
                    values["导演英文名"],
                    values["代表作"],
                    values["年份"],
                )
                if identity in seen:
                    raise BatchConfigurationError(
                        f"CSV row {row_number}: duplicate director-film-year record"
                    )
                seen.add(identity)
                films.append(
                    FilmRow(
                        row_number=row_number,
                        director=values["导演"],
                        english_name=values["导演英文名"],
                        work=values["代表作"],
                        year=values["年份"],
                    )
                )
    except (OSError, UnicodeError, csv.Error) as exc:
        raise BatchConfigurationError(f"Cannot read CSV {path}: {exc}") from exc
    if not films:
        raise BatchConfigurationError(f"CSV has no data rows: {path}")
    return films


def read_completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed = set()
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise BatchConfigurationError(
                        f"Invalid state JSON at {path}:{line_number}: {exc}"
                    ) from exc
                if event.get("status") == "completed":
                    completed.add(str(event["job_id"]))
    except (OSError, UnicodeError, KeyError) as exc:
        raise BatchConfigurationError(f"Cannot read state file {path}: {exc}") from exc
    return completed


def discover_run_id(job_runs_dir: Path) -> str | None:
    if not job_runs_dir.exists():
        return None
    if not job_runs_dir.is_dir():
        raise BatchConfigurationError(
            f"Job runs path is not a directory: {job_runs_dir}"
        )
    run_ids = sorted(
        path.name
        for path in job_runs_dir.iterdir()
        if path.is_dir() and RUN_ID_PATTERN.fullmatch(path.name)
    )
    if len(run_ids) > 1:
        raise BatchConfigurationError(
            f"Job runs directory contains multiple top-level runs: {job_runs_dir}"
        )
    return run_ids[0] if run_ids else None


def append_state(
    path: Path,
    job: Job,
    status: str,
    returncode: int,
    *,
    action: str,
    run_id: str | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "job_id": job.job_id,
        "status": status,
        "action": action,
        "run_id": run_id,
        "returncode": returncode,
        "csv_row": job.film.row_number,
        "director": job.film.director,
        "work": job.film.work,
        "year": job.film.year,
        "cast": job.cast_label,
        "female_count": job.female_count,
        "male_count": job.male_count,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def generate_command(
    cli: list[str],
    job: Job,
    *,
    prompts_dir: Path,
    runs_dir: Path,
    concurrency: int,
    theme_batch_size: int,
) -> list[str]:
    return [
        *cli,
        "generate",
        job.film.director,
        "--work",
        f"{job.film.work} ({job.film.year})",
        "--female-count",
        str(job.female_count),
        "--male-count",
        str(job.male_count),
        "--themes",
        str(THEME_COUNT),
        "--frames",
        str(FRAMES_PER_THEME),
        "--content-level",
        CONTENT_LEVEL,
        "--theme-batch-size",
        str(theme_batch_size),
        "--concurrency",
        str(concurrency),
        "--language",
        "chinese",
        "--filename-stem",
        job.filename_stem,
        "--prompts-dir",
        str(prompts_dir),
        "--runs-dir",
        str(runs_dir),
    ]


def resume_command(cli: list[str], run_id: str, *, runs_dir: Path) -> list[str]:
    return [
        *cli,
        "resume",
        run_id,
        "--runs-dir",
        str(runs_dir),
    ]


def command_for_job(
    cli: list[str],
    job: Job,
    *,
    prompts_dir: Path,
    runs_root: Path,
    concurrency: int,
    theme_batch_size: int,
) -> tuple[str, str | None, Path, list[str]]:
    job_runs_dir = runs_root / job.job_id
    run_id = discover_run_id(job_runs_dir)
    if run_id is not None:
        return (
            "resume",
            run_id,
            job_runs_dir,
            resume_command(cli, run_id, runs_dir=job_runs_dir),
        )
    return (
        "generate",
        None,
        job_runs_dir,
        generate_command(
            cli,
            job,
            prompts_dir=prompts_dir,
            runs_dir=job_runs_dir,
            concurrency=concurrency,
            theme_batch_size=theme_batch_size,
        ),
    )


def selected_jobs(
    films: list[FilmRow],
    *,
    start_row: int,
    max_rows: int | None,
) -> list[Job]:
    selected = [film for film in films if film.row_number >= start_row]
    if max_rows is not None:
        selected = selected[:max_rows]
    return [
        Job(film, cast_label, female_count, male_count)
        for film in selected
        for cast_label, female_count, male_count in CASTS
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        films = read_films(args.csv.resolve())
        jobs = selected_jobs(
            films,
            start_row=args.start_row,
            max_rows=args.max_rows,
        )
        if not jobs:
            raise BatchConfigurationError("The selected CSV row range is empty.")
        cli = resolve_cli(repo_root)
        completed = read_completed(args.state_file.resolve())
    except BatchConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    pending = [job for job in jobs if job.job_id not in completed]
    skipped = len(jobs) - len(pending)
    print(
        f"Selected {len(jobs)} jobs from {len(jobs) // len(CASTS)} CSV rows; "
        f"{skipped} completed, {len(pending)} pending."
    )
    if args.dry_run:
        try:
            for job in pending:
                action, _, _, command = command_for_job(
                    cli,
                    job,
                    prompts_dir=args.prompts_dir.resolve(),
                    runs_root=args.runs_dir.resolve(),
                    concurrency=args.concurrency,
                    theme_batch_size=args.theme_batch_size,
                )
                print(f"[{job.job_id}] {action}: {shlex.join(command)}")
        except BatchConfigurationError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        return 0

    failures = 0
    for index, job in enumerate(pending, start=1):
        try:
            action, run_id, job_runs_dir, command = command_for_job(
                cli,
                job,
                prompts_dir=args.prompts_dir.resolve(),
                runs_root=args.runs_dir.resolve(),
                concurrency=args.concurrency,
                theme_batch_size=args.theme_batch_size,
            )
        except BatchConfigurationError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        print(
            f"\n[{index}/{len(pending)}] CSV row {job.film.row_number}: "
            f"{job.film.director} — {job.film.work} ({job.film.year}), "
            f"cast={job.cast_label}, action={action}"
            + (f", run={run_id}" if run_id else ""),
            flush=True,
        )
        try:
            result = subprocess.run(command, cwd=repo_root, check=False)
        except KeyboardInterrupt:
            discovered = discover_run_id(job_runs_dir)
            append_state(
                args.state_file.resolve(),
                job,
                "interrupted",
                130,
                action=action,
                run_id=discovered or run_id,
            )
            print(
                f"\nInterrupted. Job {job.job_id} will resume on the next invocation.",
                file=sys.stderr,
            )
            return 130
        except OSError as exc:
            print(f"Cannot start Film CLI: {exc}", file=sys.stderr)
            append_state(
                args.state_file.resolve(),
                job,
                "failed_to_start",
                127,
                action=action,
                run_id=run_id,
            )
            return 2
        try:
            discovered = discover_run_id(job_runs_dir)
        except BatchConfigurationError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        if result.returncode == 0 and discovered is None:
            print(
                f"Job {job.job_id} exited successfully without a persistent run.",
                file=sys.stderr,
            )
            append_state(
                args.state_file.resolve(),
                job,
                "missing_run_checkpoint",
                1,
                action=action,
                run_id=None,
            )
            failures += 1
            if args.stop_on_error:
                break
            continue
        status = "completed" if result.returncode == 0 else "failed"
        append_state(
            args.state_file.resolve(),
            job,
            status,
            result.returncode,
            action=action,
            run_id=discovered or run_id,
        )
        if result.returncode != 0:
            failures += 1
            print(
                f"Job {job.job_id} failed with exit code {result.returncode}; "
                "its persistent run will be resumed on the next invocation.",
                file=sys.stderr,
            )
            if args.stop_on_error:
                break

    if failures:
        print(f"\n{failures} job(s) failed.", file=sys.stderr)
        return 1
    print(f"\nAll {len(pending)} pending jobs completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
