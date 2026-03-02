#!/usr/bin/env bash
# rebuild.sh — Full environment reset.
# Use when changing .env, adding packages to requirements.txt,
# or making database schema changes.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

source venv/bin/activate

echo "==> Installing dependencies..."
pip install -r requirements.txt --quiet

echo "==> Dropping and recreating filestore_db..."
sudo -u postgres dropdb --if-exists filestore_db
sudo -u postgres createdb filestore_db
echo "    filestore_db recreated."

echo "==> Killing any existing uvicorn processes..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

echo "==> Starting uvicorn..."
uvicorn app.main:app --reload --port 8000 &
sleep 2

echo "==> Running checks..."
"$SCRIPT_DIR/check.sh"
