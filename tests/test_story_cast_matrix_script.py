from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate-story-cast-matrix.sh"
CASTS = ((1, 1), (2, 0), (3, 0), (2, 1), (1, 2))


def write_cli(path, body):
    path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def fake_cli(tmp_path):
    return write_cli(
        tmp_path / "fake-story",
        """
        import json
        import os
        import sys

        arguments = sys.argv[1:]
        with open(os.environ["CALLS_FILE"], "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"args": arguments, "cwd": os.getcwd()}) + "\\n")
        command = arguments[0]
        if command not in ("explain", "generate"):
            raise SystemExit(97)
        female = arguments[arguments.index("--female-count") + 1]
        fails = (
            command == os.environ.get("FAIL_COMMAND")
            and female == os.environ.get("FAIL_FEMALE_COUNT")
        )
        if command == "explain":
            print(json.dumps(
                {"status": "invalid", "error": "incompatible test cast"}
                if fails else
                {"status": "valid", "fingerprint": "test-input", "input": {}}
            ))
        if fails:
            raise SystemExit(int(os.environ["FAIL_EXIT_CODE"]))
        """,
    )


@pytest.fixture
def real_cli(tmp_path):
    return write_cli(
        tmp_path / "real-story",
        """
        import json
        import os
        import sys
        from pathlib import Path
        import t2i_story_pipeline.cli as cli

        with open(os.environ["CALLS_FILE"], "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd()}) + "\\n")

        def unexpected_provider_load():
            Path(os.environ["PROVIDER_LOAD_LOG"]).write_text("called", encoding="utf-8")
            raise AssertionError("preflight must not load a provider")

        cli.load_story_provider_settings = unexpected_provider_load
        cli.app()
        """,
    )


def read_calls(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_matrix(tmp_path, cli, story_file, *directories, script=SCRIPT, **environment):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("T2I_STORY_")
    }
    return subprocess.run(
        [
            "/bin/bash",
            str(script),
            str(story_file),
            *(str(path) for path in directories),
        ],
        cwd=tmp_path,
        env={
            **env,
            "T2I_STORY_CLI": str(cli),
            "CALLS_FILE": str(tmp_path / "calls.jsonl"),
            "PROVIDER_LOAD_LOG": str(tmp_path / "provider-load"),
            **environment,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


@pytest.mark.parametrize("has_uv", [True, False])
def test_preflight_uses_selected_cli_without_independent_python_or_uv(
    tmp_path, has_uv, fake_cli
):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "generate-story-cast-matrix.sh"
    shutil.copy2(SCRIPT, script)
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
            '#!/bin/sh\nprintf unexpected > "$UV_LOG"\nexit 90\n',
            encoding="utf-8",
        )
        uv.chmod(0o755)
    uv_log = tmp_path / "uv-log"
    system_python = tmp_path / "system-python"
    result = run_matrix(
        tmp_path,
        fake_cli,
        document,
        script=script,
        PATH=str(bin_dir),
        UV_LOG=str(uv_log),
        SYSTEM_PYTHON_LOG=str(system_python),
    )
    assert result.returncode == 0, result.stderr
    assert not system_python.exists()
    assert not uv_log.exists()
    calls = read_calls(tmp_path / "calls.jsonl")
    assert [call["args"][0] for call in calls] == ["explain"] * 5 + ["generate"] * 5
    assert {call["cwd"] for call in calls} == {str(project)}


@pytest.mark.parametrize("directory_source", ["arguments", "environment", "defaults"])
def test_story_cast_matrix_script_preflights_then_generates_identical_casts(
    tmp_path, fake_cli, directory_source
) -> None:
    story_file = tmp_path / "story input.yaml"
    story_file.write_text(
        "id: story-input\ndescription: |\n  A story description.\n",
        encoding="utf-8",
    )
    prompts_root = tmp_path / "prompts"
    runs_dir = tmp_path / "story runs"
    directories = ()
    environment = {}
    if directory_source == "arguments":
        directories = (prompts_root, runs_dir)
    elif directory_source == "environment":
        environment = {
            "T2I_STORY_PROMPTS_ROOT": "relative prompts",
            "T2I_STORY_RUNS_DIR": "relative runs",
        }
        prompts_root = REPO_ROOT / "relative prompts"
        runs_dir = REPO_ROOT / "relative runs"
    else:
        prompts_root = REPO_ROOT / "prompts"
        runs_dir = REPO_ROOT / "runs"
    result = run_matrix(
        tmp_path,
        f"./{fake_cli.name}",
        story_file.relative_to(tmp_path),
        *directories,
        **environment,
    )

    assert result.returncode == 0, result.stderr
    calls = read_calls(tmp_path / "calls.jsonl")
    assert [call["args"][0] for call in calls] == ["explain"] * 5 + ["generate"] * 5
    assert {call["cwd"] for call in calls} == {str(REPO_ROOT)}
    for index, (female_count, male_count) in enumerate(CASTS):
        shared = [
            "--input",
            str(story_file),
            "--content-level",
            "hardcore",
            "--themes",
            "100",
            "--frames",
            "6",
            "--language",
            "english",
            "--female-count",
            str(female_count),
            "--male-count",
            str(male_count),
        ]
        assert calls[index]["args"] == ["explain", *shared, "--format", "json"]
        assert calls[index + 5]["args"] == [
            "generate",
            *shared,
            "--runs-dir",
            str(runs_dir),
            "--prompts-dir",
            str(prompts_root),
        ]


@pytest.mark.parametrize("exit_code", [1, 2])
def test_any_explain_failure_finishes_preflight_but_starts_no_generation(
    tmp_path, fake_cli, exit_code
):
    document = tmp_path / "story.yaml"
    document.write_text("id: story\ndescription: Story.\n", encoding="utf-8")
    result = run_matrix(
        tmp_path,
        fake_cli,
        document,
        tmp_path / "prompts",
        tmp_path / "runs",
        FAIL_COMMAND="explain",
        FAIL_FEMALE_COUNT="3",
        FAIL_EXIT_CODE=str(exit_code),
    )
    assert result.returncode == 2
    assert "Incompatible cast 3-women" in result.stderr
    assert '"status": "invalid"' in result.stderr
    assert "1 cast configurations failed preflight" in result.stderr
    assert "no generation was started" in result.stderr
    calls = read_calls(tmp_path / "calls.jsonl")
    assert [call["args"][0] for call in calls] == ["explain"] * 5
    assert not (tmp_path / "prompts").exists()
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize(("exit_code", "generation_count"), [(1, 5), (2, 3)])
def test_generation_failure_continues_only_for_resumable_run_errors(
    tmp_path, fake_cli, exit_code, generation_count
):
    document = tmp_path / "story.yaml"
    document.write_text("id: story\ndescription: Story.\n", encoding="utf-8")
    result = run_matrix(
        tmp_path,
        fake_cli,
        document,
        FAIL_COMMAND="generate",
        FAIL_FEMALE_COUNT="3",
        FAIL_EXIT_CODE=str(exit_code),
    )
    assert result.returncode == exit_code
    calls = read_calls(tmp_path / "calls.jsonl")
    assert [call["args"][0] for call in calls] == (
        ["explain"] * 5 + ["generate"] * generation_count
    )
    if exit_code == 1:
        assert "1 of 5 cast configurations failed" in result.stderr
        assert "resumable run" in result.stderr
    else:
        assert "remaining casts were not attempted" in result.stderr


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
    real_cli,
    filename: str,
    content: bytes,
) -> None:
    story_file = tmp_path / filename
    story_file.write_bytes(content)
    result = run_matrix(
        tmp_path, real_cli, story_file, tmp_path / "prompts", tmp_path / "runs"
    )
    assert result.returncode == 2, result.stderr
    assert result.stderr.count("Incompatible cast") == 5
    assert result.stderr.count('"status": "invalid"') == 5
    assert "5 cast configurations failed preflight" in result.stderr
    calls = read_calls(tmp_path / "calls.jsonl")
    assert [call["args"][0] for call in calls] == ["explain"] * 5
    assert not (tmp_path / "provider-load").exists()
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "prompts").exists()


def test_real_preflight_checks_all_casts_before_generating_any(tmp_path, real_cli):
    document = tmp_path / "limited-cast.yaml"
    document.write_text(
        "id: limited-cast\ndescription: A station composition.\n"
        "generation: {cast: {female_count: 1, male_count: 1}}\n"
        "requirements: {female_count: {max: 2}}\n",
        encoding="utf-8",
    )
    result = run_matrix(
        tmp_path, real_cli, document, tmp_path / "prompts", tmp_path / "runs"
    )
    assert result.returncode == 2, result.stderr
    assert result.stderr.count("Incompatible cast") == 1
    assert "Incompatible cast 3-women" in result.stderr
    assert "1 cast configurations failed preflight" in result.stderr
    calls = read_calls(tmp_path / "calls.jsonl")
    assert [call["args"][0] for call in calls] == ["explain"] * 5
    assert not (tmp_path / "provider-load").exists()
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "prompts").exists()
