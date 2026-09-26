#!/usr/bin/env bash
# Standardized entrypoint for this contribution. Two ways to invoke it:
#   - Service mode: W4H_API_KEY (and usually W4H_API_BASE) already set in the
#     environment — used non-interactively (e.g. by w4h-api's in-app "Run" trigger).
#   - Manual mode: run it yourself in a terminal; if credentials aren't set and
#     you're attached to a TTY, it prompts for them.
#
# In-app Run sets W4H_API_KEY / W4H_API_BASE / W4H_DATASET_ID in the process env.
# This then loads the live sample declared in contribution.yaml (tests/fixtures).
#
# Usage: ./run.sh [plan|validate|import|sync] [extra CLI args passed through]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-import}"
if [ "$MODE" != "import" ] && [ "$MODE" != "sync" ] && [ "$MODE" != "plan" ] && [ "$MODE" != "validate" ]; then
  echo "Usage: $0 [plan|validate|import|sync] [extra CLI args]" >&2
  exit 1
fi
shift || true

if [ "$MODE" != "plan" ] && [ "$MODE" != "validate" ] && [ -z "${W4H_API_KEY:-}" ]; then
  if [ -t 0 ]; then
    echo "W4H_API_KEY is not set."
    read -r -p "Paste your personal API key (app: Profile -> API keys, starts with w4h_sk_): " W4H_API_KEY
    export W4H_API_KEY
    if [ -z "${W4H_API_BASE:-}" ]; then
      read -r -p "W4H API base URL [http://localhost:2026]: " input_base
      export W4H_API_BASE="${input_base:-http://localhost:2026}"
    fi
    read -r -p "Save these to .env for next time? [y/N] " save_choice
    if [[ "${save_choice:-}" =~ ^[Yy]$ ]]; then
      {
        echo "W4H_API_KEY=$W4H_API_KEY"
        echo "W4H_API_BASE=$W4H_API_BASE"
      } >> .env
      echo "Saved to $SCRIPT_DIR/.env"
    fi
  else
    echo "Error: set W4H_API_KEY (and W4H_API_BASE) in the environment to run this non-interactively." >&2
    exit 1
  fi
fi
: "${W4H_API_BASE:=http://localhost:2026}"
export W4H_API_BASE

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found on PATH." >&2
  echo "Install it (e.g. https://www.python.org/downloads/, or 'brew install python3' on macOS) and re-run this script." >&2
  exit 1
fi

VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ ! -f "$VENV_DIR/.installed" ] || [ "$SCRIPT_DIR/pyproject.toml" -nt "$VENV_DIR/.installed" ]; then
  echo "Installing dependencies..."
  pip install --quiet --upgrade pip
  pip install --quiet -e "$SCRIPT_DIR"
  touch "$VENV_DIR/.installed"
fi

exec w4h-glucose-monitor-csv-file-import "$MODE" "$@"
