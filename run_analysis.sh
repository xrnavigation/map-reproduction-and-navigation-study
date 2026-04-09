#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

cd "$ROOT_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "[setup] Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[setup] Installing/updating dependencies..."
pip install -r requirements.txt

echo "[run] Running map similarity analysis..."
python audiom_map_similarity_analysis.py

echo "[done] Output: $ROOT_DIR/map_similarity_results.xlsx"
