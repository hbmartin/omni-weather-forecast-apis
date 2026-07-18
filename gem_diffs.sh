#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_TEMPLATE_FILE="${SCRIPT_DIR}/prompts/gem_compare_prompt.txt"

if [ $# -ne 2 ]; then
  echo "Usage: $0 <commit_hash_1> <commit_hash_2>"
  exit 1
fi

COMMIT_1="$1"
COMMIT_2="$2"
SQLITE_DB_PATH="${SCRIPT_DIR}/gem_compare_ratings.sqlite"

if [ ! -f "${PROMPT_TEMPLATE_FILE}" ]; then
  echo "Error: Prompt template file not found at ${PROMPT_TEMPLATE_FILE}"
  exit 1
fi

# Check for modified or untracked files
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Error: Working tree has modified or untracked files. Please commit or stash changes first."
  exit 1
fi

# Fetch latest commits
echo "Fetching latest commits..."
git fetch --all --quiet

RESOLVED_COMMIT_1="$(git rev-parse --verify "${COMMIT_1}^{commit}")"
RESOLVED_COMMIT_2="$(git rev-parse --verify "${COMMIT_2}^{commit}")"

# Print commit titles
echo ""
echo "Commit 1: $(git log --format='%s' -1 "$RESOLVED_COMMIT_1")"
echo "Commit 2: $(git log --format='%s' -1 "$RESOLVED_COMMIT_2")"
echo ""

PROMPT_TEMPLATE="$(cat "${PROMPT_TEMPLATE_FILE}")"
PROMPT_TEMPLATE="${PROMPT_TEMPLATE//\{\{COMMIT_1\}\}/$RESOLVED_COMMIT_1}"
PROMPT_TEMPLATE="${PROMPT_TEMPLATE//\{\{COMMIT_2\}\}/$RESOLVED_COMMIT_2}"
PROMPT_TEMPLATE="${PROMPT_TEMPLATE//\{\{SQLITE_DB_PATH\}\}/$SQLITE_DB_PATH}"

gemini -y -i "${PROMPT_TEMPLATE}"

rm -f ./*-a.ts ./*-b.ts diff_*
