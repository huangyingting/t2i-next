from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate-asian-directors-aesthetic.py"
CASTS = ((1, 0), (1, 1), (2, 1), (2, 2), (3, 1))


def write_csv(path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    lines = ["导演,导演英文名,主要创作地区,导演风格关键词,作品类型,代表作,年份"]
    lines.extend(
        f"{director},{english},地区,风格,真人电影,{work},{year}"
        for director, english, work, year in rows
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_fake_cli(path: Path) -> Path:
    path.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            """
            import hashlib
            import json
            import os
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            with open(os.environ["CALLS_FILE"], "a", encoding="utf-8") as stream:
                stream.write(json.dumps(args, ensure_ascii=False) + "\\n")
            command = args[0]
            runs_dir = Path(args[args.index("--runs-dir") + 1])
            if command == "generate":
                cast = (
                    args[args.index("--female-count") + 1],
                    args[args.index("--male-count") + 1],
                )
                suffix = hashlib.sha256(",".join(cast).encode()).hexdigest()[:8]
                run_id = f"20260919T010101Z-{suffix}"
                run_dir = runs_dir / run_id
                run_dir.mkdir(parents=True)
                (run_dir / "fake.json").write_text(
                    json.dumps({"cast": cast}), encoding="utf-8"
                )
                if ",".join(cast) == os.environ.get("FAIL_CAST"):
                    raise SystemExit(9)
            elif command == "resume":
                run_id = args[1]
                if not (runs_dir / run_id / "fake.json").is_file():
                    raise SystemExit(8)
                if os.environ.get("FAIL_RESUME") == "1":
                    raise SystemExit(7)
            else:
                raise SystemExit(6)
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def run_script(
    tmp_path: Path,
    csv_path: Path,
    fake_cli: Path,
    *extra: str,
    fail_cast: str = "",
    fail_resume: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--csv",
            str(csv_path),
            "--prompts-dir",
            str(tmp_path / "prompts"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--state-file",
            str(tmp_path / "state.jsonl"),
            *extra,
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "T2I_FILM_STYLE_CLI": str(fake_cli),
            "CALLS_FILE": str(tmp_path / "calls.jsonl"),
            "FAIL_CAST": fail_cast,
            "FAIL_RESUME": "1" if fail_resume else "",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def read_calls(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_dry_run_selects_rows_and_prints_only_aesthetic_commands(
    tmp_path: Path,
) -> None:
    csv_path = write_csv(
        tmp_path / "directors.csv",
        [
            ("侯孝贤", "Hou Hsiao-hsien", "悲情城市", "1989"),
            ("杨德昌", "Edward Yang", "一一", "2000"),
        ],
    )
    fake_cli = write_fake_cli(tmp_path / "fake-film")

    result = run_script(
        tmp_path,
        csv_path,
        fake_cli,
        "--start-row",
        "2",
        "--max-rows",
        "1",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "Selected 5 jobs from 1 CSV rows" in result.stdout
    assert result.stdout.count("--content-level aesthetic") == 5
    assert result.stdout.count("--themes 50") == 5
    assert result.stdout.count("--frames 4") == 5
    assert result.stdout.count("generate:") == 5
    assert "一一 (2000)" in result.stdout
    assert "悲情城市" not in result.stdout
    assert "--content-level erotic" not in result.stdout
    assert "--content-level hardcore" not in result.stdout
    assert not (tmp_path / "calls.jsonl").exists()
    assert not (tmp_path / "state.jsonl").exists()


def test_runs_five_casts_and_skips_completed_jobs_on_rerun(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "directors.csv",
        [("侯孝贤", "Hou Hsiao-hsien", "悲情城市", "1989")],
    )
    fake_cli = write_fake_cli(tmp_path / "fake-film")

    first = run_script(tmp_path, csv_path, fake_cli)
    second = run_script(tmp_path, csv_path, fake_cli)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "5 completed, 0 pending" in second.stdout
    calls = read_calls(tmp_path / "calls.jsonl")
    assert len(calls) == 5
    observed_casts = []
    stems = set()
    for call in calls:
        assert call[:3] == ["generate", "侯孝贤", "--work"]
        assert call[3] == "悲情城市 (1989)"
        assert call[call.index("--content-level") + 1] == "aesthetic"
        assert call[call.index("--themes") + 1] == "50"
        assert call[call.index("--frames") + 1] == "4"
        assert "--scene" not in call
        observed_casts.append(
            (
                int(call[call.index("--female-count") + 1]),
                int(call[call.index("--male-count") + 1]),
            )
        )
        stems.add(call[call.index("--filename-stem") + 1])
    assert tuple(observed_casts) == CASTS
    assert len(stems) == 5
    events = [
        json.loads(line)
        for line in (tmp_path / "state.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(events) == 5
    assert {event["status"] for event in events} == {"completed"}
    assert {event["action"] for event in events} == {"generate"}
    assert all(event["run_id"] for event in events)


def test_failed_job_is_resumed_while_completed_jobs_remain_skipped(
    tmp_path: Path,
) -> None:
    csv_path = write_csv(
        tmp_path / "directors.csv",
        [("侯孝贤", "Hou Hsiao-hsien", "悲情城市", "1989")],
    )
    fake_cli = write_fake_cli(tmp_path / "fake-film")

    first = run_script(tmp_path, csv_path, fake_cli, fail_cast="2,1")
    first_events = [
        json.loads(line)
        for line in (tmp_path / "state.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    failed = [event for event in first_events if event["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["action"] == "generate"
    assert failed[0]["run_id"]
    second = run_script(tmp_path, csv_path, fake_cli)

    assert first.returncode == 1
    assert second.returncode == 0, second.stderr
    assert "4 completed, 1 pending" in second.stdout
    assert "action=resume" in second.stdout
    calls = read_calls(tmp_path / "calls.jsonl")
    assert len(calls) == 6
    assert calls[-1] == [
        "resume",
        failed[0]["run_id"],
        "--runs-dir",
        str(tmp_path / "runs" / failed[0]["job_id"]),
    ]
    events = [
        json.loads(line)
        for line in (tmp_path / "state.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["status"] == "completed"
    assert events[-1]["action"] == "resume"
    assert events[-1]["run_id"] == failed[0]["run_id"]


def test_discovers_resumable_run_when_failed_state_event_is_missing(
    tmp_path: Path,
) -> None:
    csv_path = write_csv(
        tmp_path / "directors.csv",
        [("侯孝贤", "Hou Hsiao-hsien", "悲情城市", "1989")],
    )
    fake_cli = write_fake_cli(tmp_path / "fake-film")
    first = run_script(tmp_path, csv_path, fake_cli, fail_cast="2,1")
    assert first.returncode == 1
    events = [
        json.loads(line)
        for line in (tmp_path / "state.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    failed = next(event for event in events if event["status"] == "failed")
    completed_lines = [
        json.dumps(event, ensure_ascii=False)
        for event in events
        if event["status"] == "completed"
    ]
    (tmp_path / "state.jsonl").write_text(
        "\n".join(completed_lines) + "\n", encoding="utf-8"
    )

    second = run_script(tmp_path, csv_path, fake_cli)

    assert second.returncode == 0, second.stderr
    assert "action=resume" in second.stdout
    assert read_calls(tmp_path / "calls.jsonl")[-1][0:2] == [
        "resume",
        failed["run_id"],
    ]


def test_failed_resume_remains_resumable_on_later_invocation(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "directors.csv",
        [("侯孝贤", "Hou Hsiao-hsien", "悲情城市", "1989")],
    )
    fake_cli = write_fake_cli(tmp_path / "fake-film")
    assert run_script(tmp_path, csv_path, fake_cli, fail_cast="2,1").returncode == 1

    second = run_script(tmp_path, csv_path, fake_cli, fail_resume=True)
    third = run_script(tmp_path, csv_path, fake_cli)

    assert second.returncode == 1
    assert third.returncode == 0, third.stderr
    resume_calls = [
        call for call in read_calls(tmp_path / "calls.jsonl") if call[0] == "resume"
    ]
    assert len(resume_calls) == 2
    assert resume_calls[0] == resume_calls[1]


@pytest.mark.parametrize(
    ("header", "row", "message"),
    [
        (
            "导演,导演英文名,作品类型,代表作",
            "侯孝贤,Hou Hsiao-hsien,真人电影,悲情城市",
            "missing required columns",
        ),
        (
            "导演,导演英文名,作品类型,代表作,年份",
            "宫崎骏,Hayao Miyazaki,动画电影,千与千寻,2001",
            "unsupported 作品类型",
        ),
    ],
)
def test_rejects_invalid_csv_before_starting_cli(
    tmp_path: Path,
    header: str,
    row: str,
    message: str,
) -> None:
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    fake_cli = write_fake_cli(tmp_path / "fake-film")

    result = run_script(tmp_path, csv_path, fake_cli)

    assert result.returncode == 2
    assert message in result.stderr
    assert read_calls(tmp_path / "calls.jsonl") == []
