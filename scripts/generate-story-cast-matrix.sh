#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

resolve_executable() {
  local executable="$1"

  if [[ "$executable" == /* ]]; then
    printf '%s\n' "$executable"
    return
  fi
  (
    cd -- "$(dirname -- "$executable")"
    printf '%s/%s\n' "$PWD" "$(basename -- "$executable")"
  )
}

if (($# < 1 || $# > 3)); then
  printf 'Usage: %s STORY_FILE [PROMPTS_ROOT] [RUNS_DIR]\n' "$0" >&2
  exit 2
fi

story_file="$1"
prompts_root="${2:-${T2I_STORY_PROMPTS_ROOT:-$repo_root/prompts}}"
runs_dir="${3:-${T2I_STORY_RUNS_DIR:-$repo_root/runs}}"

if [[ ! -f "$story_file" ]]; then
  printf 'Story file does not exist: %s\n' "$story_file" >&2
  exit 2
fi
if [[ ! -r "$story_file" ]]; then
  printf 'Story file is not readable: %s\n' "$story_file" >&2
  exit 2
fi

story_file="$(
  cd -- "$(dirname -- "$story_file")"
  printf '%s/%s\n' "$PWD" "$(basename -- "$story_file")"
)"
if [[ "$prompts_root" != /* ]]; then
  prompts_root="$repo_root/$prompts_root"
fi
if [[ "$runs_dir" != /* ]]; then
  runs_dir="$repo_root/$runs_dir"
fi

uv_executable=""
if command -v uv >/dev/null 2>&1; then
  uv_executable="$(resolve_executable "$(command -v uv)")"
fi

if [[ -n "${T2I_STORY_CLI:-}" ]]; then
  if [[ ! -x "$T2I_STORY_CLI" ]]; then
    printf 't2i-story is not executable: %s\n' "$T2I_STORY_CLI" >&2
    exit 2
  fi
  story_cli=("$(resolve_executable "$T2I_STORY_CLI")")
elif [[ -x "$repo_root/.venv/bin/t2i-story" ]]; then
  story_cli=("$repo_root/.venv/bin/t2i-story")
elif command -v t2i-story >/dev/null 2>&1; then
  story_cli=("$(resolve_executable "$(command -v t2i-story)")")
elif [[ -n "$uv_executable" ]]; then
  story_cli=("$uv_executable" run t2i-story)
else
  printf 'Cannot find t2i-story or uv.\n' >&2
  exit 2
fi

if [[ -x "$repo_root/.venv/bin/python" ]]; then
  story_python=("$repo_root/.venv/bin/python")
elif command -v python3 >/dev/null 2>&1; then
  story_python=("$(resolve_executable "$(command -v python3)")")
elif command -v python >/dev/null 2>&1; then
  story_python=("$(resolve_executable "$(command -v python)")")
elif [[ -n "$uv_executable" ]]; then
  story_python=("$uv_executable" run python)
else
  story_python=()
fi

cd -- "$repo_root"

if ((${#story_python[@]} > 0)) && ! "${story_python[@]}" - "$story_file" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    text = path.read_text(encoding="utf-8")
except UnicodeError:
    print(f"Story file must be valid UTF-8 text: {path}", file=sys.stderr)
    raise SystemExit(2)
except OSError as exc:
    print(f"Cannot read story file {path}: {exc}", file=sys.stderr)
    raise SystemExit(2)

if not text.strip():
    print(f"Story file must not be empty: {path}", file=sys.stderr)
    raise SystemExit(2)
PY
then
  exit 2
fi

labels=(
  "1-man-1-woman"
  "2-women"
  "3-women"
  "1-man-2-women"
  "2-men-1-woman"
)
female_counts=(1 2 3 2 1)
male_counts=(1 0 0 1 2)

trap 'exit 130' INT
trap 'exit 143' TERM

failures=0
for index in "${!labels[@]}"; do
  label="${labels[$index]}"
  female_count="${female_counts[$index]}"
  male_count="${male_counts[$index]}"
  printf '\nGenerating %s: female=%s, male=%s\n' \
    "$label" "$female_count" "$male_count"
  if "${story_cli[@]}" generate \
    --prompt-file "$story_file" \
    --female-count "$female_count" \
    --male-count "$male_count" \
    --content-level hardcore \
    --themes 100 \
    --frames 6 \
    --language english \
    --runs-dir "$runs_dir" \
    --prompts-dir "$prompts_root"; then
    :
  else
    status=$?
    if ((status == 2)); then
      printf 'Generation rejected the shared input or configuration; remaining casts were not attempted.\n' >&2
      exit 2
    fi
    printf 'Generation failed for %s; inspect %s for any resumable run.\n' \
      "$label" "$runs_dir" >&2
    failures=$((failures + 1))
  fi
done

if ((failures > 0)); then
  printf '\n%d of %d cast configurations failed.\n' \
    "$failures" "${#labels[@]}" >&2
  exit 1
fi

printf '\nGenerated all %d cast configurations under %s\n' \
  "${#labels[@]}" "$prompts_root"
