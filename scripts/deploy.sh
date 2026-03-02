#!/usr/bin/env bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
DROPLET_IP="64.23.253.28"          # Replace with your Droplet IP
REMOTE_DIR="/app"
# ───────────────────────────────────────────────────────────────

# Load local .env so we can read API_KEY for the health check
if [[ -f .env ]]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "▸ Syncing project to $DROPLET_IP:$REMOTE_DIR …"
rsync -avz --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'venv' \
  --exclude 'uploads' \
  --exclude '.coverage' \
  --exclude '.pytest_cache' \
  --exclude '.env' \
  . root@"$DROPLET_IP":"$REMOTE_DIR"

echo "▸ Installing dependencies & restarting service …"
ssh root@"$DROPLET_IP" bash -s <<'REMOTE'
  cd /app
  source venv/bin/activate
  pip install -q -r requirements.txt

  # Kill any manually-started uvicorn
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  sleep 1

  # Restart via systemd if the unit exists, otherwise start manually
  if systemctl is-enabled filestore &>/dev/null; then
    systemctl restart filestore
  else
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
  fi
REMOTE

echo "▸ Waiting for service to come up …"
sleep 3

echo "▸ Health check:"
curl -sf http://"$DROPLET_IP":8000/health && echo ""
echo "✔ Deploy complete"
