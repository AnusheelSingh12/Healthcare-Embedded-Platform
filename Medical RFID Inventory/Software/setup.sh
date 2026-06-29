#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "Error: backend directory not found at $BACKEND_DIR"
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Error: Python is not installed. Install Python 3.10+ and retry."
  exit 1
fi

echo "Using Python: $PYTHON_CMD"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment in backend/.venv ..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Upgrading pip ..."
python -m pip install --upgrade pip

echo "Installing backend dependencies ..."
python -m pip install -r "$BACKEND_DIR/requirements.txt"

echo "Setup complete."
echo "Run the app with: ./run.sh"
