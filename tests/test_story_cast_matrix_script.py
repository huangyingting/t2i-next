from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_story_cast_matrix_script_runs_all_requested_casts(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "generate-story-cast-matrix.sh"
    story_file = tmp_path / "story input.txt"
    story_file.write_text("A story description.", encoding="utf-8")
    calls_file = tmp_path / "calls.jsonl"
    fake_cli = tmp_path / "t2i-story"
    fake_cli.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "with open(os.environ['CALLS_FILE'], 'a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "fail_count = os.environ.get('FAIL_FEMALE_COUNT')\n"
        "female_index = sys.argv.index('--female-count') + 1\n"
        "if fail_count and sys.argv[female_index] == fail_count:\n"
        "    raise SystemExit(1)\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)
    prompts_root = tmp_path / "prompts"
    runs_dir = tmp_path / "story runs"

    command = [
        str(script),
        str(story_file),
        str(prompts_root),
        str(runs_dir),
    ]
    environment = {
        **os.environ,
        "T2I_STORY_CLI": f"./{fake_cli.name}",
        "CALLS_FILE": str(calls_file),
    }
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = [
        json.loads(line)
        for line in calls_file.read_text(encoding="utf-8").splitlines()
    ]
    assert len(calls) == 5
    expected_casts = ((1, 1), (2, 0), (3, 0), (2, 1), (1, 2))
    expected_labels = (
        "1-man-1-woman",
        "2-women",
        "3-women",
        "1-man-2-women",
        "2-men-1-woman",
    )
    for call, (female_count, male_count), _label in zip(
        calls,
        expected_casts,
        expected_labels,
        strict=True,
    ):
        assert call == [
            "generate",
            "--prompt-file",
            str(story_file),
            "--female-count",
            str(female_count),
            "--male-count",
            str(male_count),
            "--content-level",
            "hardcore",
            "--themes",
            "100",
            "--frames",
            "6",
            "--language",
            "english",
            "--runs-dir",
            str(runs_dir),
            "--prompts-dir",
            str(prompts_root),
        ]

    calls_file.unlink()
    default_result = subprocess.run(
        [str(script), str(story_file)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert default_result.returncode == 0, default_result.stderr
    default_calls = [
        json.loads(line)
        for line in calls_file.read_text(encoding="utf-8").splitlines()
    ]
    assert len(default_calls) == 5
    for call in default_calls:
        assert call[call.index("--prompts-dir") + 1] == str(
            repo_root / "prompts"
        )
        assert call[call.index("--runs-dir") + 1] == str(repo_root / "runs")

    calls_file.unlink()
    failed_result = subprocess.run(
        command,
        cwd=tmp_path,
        env={**environment, "FAIL_FEMALE_COUNT": "3"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert failed_result.returncode == 1
    assert "1 of 5 cast configurations failed" in failed_result.stderr
    assert len(calls_file.read_text(encoding="utf-8").splitlines()) == 5


def test_story_cast_matrix_script_rejects_empty_input_before_generation(
    tmp_path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "generate-story-cast-matrix.sh"
    story_file = tmp_path / "empty.txt"
    story_file.write_text(" \n\t", encoding="utf-8")
    calls_file = tmp_path / "calls.txt"
    fake_cli = tmp_path / "t2i-story"
    fake_cli.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'called\\n' >> \"$CALLS_FILE\"\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    result = subprocess.run(
        [str(script), str(story_file)],
        cwd=repo_root,
        env={
            **os.environ,
            "T2I_STORY_CLI": str(fake_cli),
            "CALLS_FILE": str(calls_file),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "must not be empty" in result.stderr
    assert not calls_file.exists()
