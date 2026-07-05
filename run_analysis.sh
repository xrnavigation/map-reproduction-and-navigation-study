#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# A venv created by Windows Python is unusable from Linux/WSL (and vice
# versa), so give each platform its own directory.
case "$(uname -s)" in
  Linux*) VENV_DIR="$ROOT_DIR/.venv-linux" ;;
  *)      VENV_DIR="$ROOT_DIR/.venv" ;;
esac

cd "$ROOT_DIR"

# Pick a Python launcher (python3 is not always on PATH on Windows)
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
elif command -v py >/dev/null 2>&1; then
  PYTHON="py -3"
else
  echo "Error: no Python interpreter found on PATH." >&2
  exit 1
fi

# (Re)create the venv if missing or broken (e.g. a partially created one
# left behind when python3-venv wasn't installed yet).
if [ ! -f "$VENV_DIR/Scripts/activate" ] && [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "[setup] Creating virtual environment..."
  rm -rf "$VENV_DIR"
  $PYTHON -m venv "$VENV_DIR" || { rm -rf "$VENV_DIR"; exit 1; }
fi

# Windows venvs use Scripts/, Unix venvs use bin/
if [ -f "$VENV_DIR/Scripts/activate" ]; then
  ACTIVATE="$VENV_DIR/Scripts/activate"
else
  ACTIVATE="$VENV_DIR/bin/activate"
fi

# shellcheck disable=SC1091
source "$ACTIVATE"

echo "[setup] Installing/updating dependencies..."
python -m pip install -r requirements.txt

echo "[run] Running map similarity analysis..."
python audiom_map_similarity_analysis.py

echo "[done] Output: $ROOT_DIR/map_similarity_results.xlsx"
