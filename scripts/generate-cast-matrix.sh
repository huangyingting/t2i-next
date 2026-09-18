#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cli="${T2I_PROMPTS_CLI:-$repo_root/.venv/bin/t2i-prompts}"

if (($# > 2)); then
  printf 'Usage: %s [brief] [aesthetic|erotic|hardcore]\n' "$0" >&2
  exit 2
fi

brief="${1:-}"
content_level="${2:-}"

if [[ -z "$brief" ]]; then
  read -r -p "Brief (do not specify cast size): " brief
fi
if [[ -z "$brief" ]]; then
  printf 'Brief cannot be empty.\n' >&2
  exit 2
fi

if [[ -z "$content_level" ]]; then
  content_levels=(erotic hardcore)
else
  case "$content_level" in
    aesthetic|erotic|hardcore) content_levels=("$content_level") ;;
    *)
      printf 'Invalid content level: %s\n' "$content_level" >&2
      exit 2
      ;;
  esac
fi

if [[ ! -x "$cli" ]]; then
  printf 't2i-prompts is not executable: %s\n' "$cli" >&2
  exit 2
fi
cd -- "$repo_root"
for level in "${content_levels[@]}"; do
  printf 'Generating cast matrix with content level: %s\n' "$level"
  "$cli" generate-cast-matrix \
    "$brief" \
    --content-level "$level"
done
