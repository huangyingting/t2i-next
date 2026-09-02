#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cli="${T2I_PROMPTS_CLI:-$repo_root/.venv/bin/t2i-prompts}"

if (($# > 3)); then
  printf 'Usage: %s [brief] [aesthetic|erotic|hardcore] [rules-dir]\n' "$0" >&2
  exit 2
fi

brief="${1:-}"
content_level="${2:-}"
rules_dir="${3:-${T2I_RULES_DIR:-$repo_root/rules}}"
if [[ "$rules_dir" != /* ]]; then
  rules_dir="$repo_root/$rules_dir"
fi

if [[ -z "$brief" ]]; then
  read -r -p "Brief (do not specify cast size): " brief
fi
if [[ -z "$brief" ]]; then
  printf 'Brief cannot be empty.\n' >&2
  exit 2
fi

if [[ -z "$content_level" ]]; then
  read -r -p "Content level [aesthetic/erotic/hardcore]: " content_level
fi
case "$content_level" in
  aesthetic|erotic|hardcore) ;;
  *)
    printf 'Invalid content level: %s\n' "$content_level" >&2
    exit 2
    ;;
esac

if [[ ! -x "$cli" ]]; then
  printf 't2i-prompts is not executable: %s\n' "$cli" >&2
  exit 2
fi
if [[ ! -d "$rules_dir" ]]; then
  printf 'Rules directory does not exist: %s\n' "$rules_dir" >&2
  exit 2
fi

cd -- "$repo_root"
exec "$cli" generate-cast-matrix \
  "$brief" \
  --content-level "$content_level" \
  --rules-dir "$rules_dir"
