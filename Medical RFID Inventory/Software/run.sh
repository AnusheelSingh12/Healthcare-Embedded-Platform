#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "Error: backend directory not found at $BACKEND_DIR"
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Virtual environment not found. Running setup first ..."
  "$ROOT_DIR/setup.sh"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

cd "$BACKEND_DIR"

echo "Starting server at http://localhost:8000 ..."
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
