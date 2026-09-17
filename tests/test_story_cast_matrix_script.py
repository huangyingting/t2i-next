from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("has_uv", [True, False])
def test_preflight_uses_project_environment_not_path_python(tmp_path, has_uv):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "generate-story-cast-matrix.sh"
    shutil.copy2(
        Path(__file__).resolve().parents[1] / "scripts" / script.name, script
    )
    document = tmp_path / "story.yaml"
    document.write_text("id: story\ndescription: Story.\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("dirname", "basename"):
        executable = shutil.which(name)
        assert executable is not None
        (bin_dir / name).symlink_to(executable)
    for name in ("python", "python3"):
        executable = bin_dir / name
        executable.write_text(
            '#!/bin/sh\nprintf unexpected > "$SYSTEM_PYTHON_LOG"\nexit 91\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)
    if has_uv:
        uv = bin_dir / "uv"
        uv.write_text(
            '#!/bin/sh\n'
            '[ "$1" = run ] && [ "$2" = python ] || exit 90\n'
            'printf "%s" "$PWD" > "$PREFLIGHT_LOG"\n',
            encoding="utf-8",
        )
        uv.chmod(0o755)
    cli = bin_dir / "fake-story"
    cli.write_text(
        '#!/bin/sh\nprintf "run\\n" >> "$CALLS_FILE"\n', encoding="utf-8"
    )
    cli.chmod(0o755)
    calls = tmp_path / "calls"
    preflight = tmp_path / "preflight"
    system_python = tmp_path / "system-python"
    result = subprocess.run(
        ["/bin/bash", str(script), str(document)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(bin_dir),
            "T2I_STORY_CLI": str(cli),
            "CALLS_FILE": str(calls),
            "PREFLIGHT_LOG": str(preflight),
            "SYSTEM_PYTHON_LOG": str(system_python),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert not system_python.exists()
    if has_uv:
        assert result.returncode == 0, result.stderr
        assert preflight.read_text(encoding="utf-8") == str(project)
        assert calls.read_text(encoding="utf-8").splitlines() == ["run"] * 5
    else:
        assert result.returncode == 2
        assert ".venv/bin/python or uv" in result.stderr
        assert not calls.exists()


def test_story_cast_matrix_script_runs_all_requested_casts(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "generate-story-cast-matrix.sh"
    story_file = tmp_path / "story input.yaml"
    story_file.write_text(
        "id: story-input\ndescription: |\n  A story description.\n",
        encoding="utf-8",
    )
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
            "--input",
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


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        pytest.param("empty.yaml", b" \n", id="empty-document"),
        pytest.param(
            "empty-description.yaml",
            b"id: empty-description\ndescription: '   '\n",
            id="empty-description",
        ),
        pytest.param(
            "missing-id.yaml",
            b"description: A story description.\n",
            id="missing-id",
        ),
        pytest.param(
            "missing-description.yaml",
            b"id: missing-description\n",
            id="missing-description",
        ),
        pytest.param(
            "invalid-id.yaml",
            b"id: Invalid ID\ndescription: A story description.\n",
            id="invalid-id",
        ),
        pytest.param(
            "invalid-description.yaml",
            b"id: invalid-description\ndescription: 42\n",
            id="invalid-description-type",
        ),
        pytest.param(
            "invalid-generation.yaml",
            b"id: invalid-generation\ndescription: A story description.\n"
            b"generation:\n  theme_count: 0\n",
            id="invalid-generation-config",
        ),
        pytest.param(
            "invalid-runtime.yaml",
            b"id: invalid-runtime\ndescription: A story description.\n"
            b"runtime:\n  concurrency: 0\n",
            id="invalid-runtime-config",
        ),
        pytest.param(
            "plain-prose.yaml",
            b"A story description.\n",
            id="non-mapping-document",
        ),
        pytest.param(
            "malformed.yaml",
            b"id: [\ndescription: A story description.\n",
            id="malformed-yaml",
        ),
        pytest.param(
            "invalid-encoding.yaml",
            b"id: invalid-encoding\ndescription: \xff\n",
            id="invalid-utf8",
        ),
        pytest.param(
            "legacy.txt",
            b"id: legacy\ndescription: A story description.\n",
            id="legacy-txt-extension",
        ),
        pytest.param(
            "unsupported.yml",
            b"id: unsupported\ndescription: A story description.\n",
            id="unsupported-yml-extension",
        ),
        pytest.param(
            "uppercase.YAML",
            b"id: uppercase\ndescription: A story description.\n",
            id="uppercase-extension",
        ),
    ],
)
def test_story_cast_matrix_script_rejects_invalid_documents_before_generation(
    tmp_path,
    filename: str,
    content: bytes,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "generate-story-cast-matrix.sh"
    story_file = tmp_path / filename
    story_file.write_bytes(content)
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
    assert "Invalid story document:" in result.stderr
    assert not calls_file.exists()
