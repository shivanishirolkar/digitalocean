#!/usr/bin/env bash
# check.sh — Lightweight verification without rebuilding.
# Use after code-only changes since uvicorn's --reload picks them up.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

source venv/bin/activate

echo "==> Checking /health..."
HEALTH=$(curl -s http://localhost:8000/ 2>/dev/null || echo "UNREACHABLE")
echo "    Response: $HEALTH"

echo "==> Running tests..."
if pytest tests/ -v --cov=app; then
    echo "==> All checks passed."
else
    echo "==> CHECKS FAILED." >&2
    exit 1
fi
