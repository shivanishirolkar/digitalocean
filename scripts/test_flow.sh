#!/usr/bin/env bash
# test_flow.sh — Demonstrates the full upload → sign → download → audit → delete flow.
#
# Prerequisites:
#   - uvicorn running on localhost:8000
#   - PostgreSQL running with filestore_db created
#
# Usage:
#   ./scripts/test_flow.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
# When API key auth is added (Step 16), uncomment:
# API_KEY="${API_KEY:-changeme}"
# AUTH_HEADER="X-API-Key: ${API_KEY}"
AUTH_HEADER=""

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'  # No Color

pass() { echo -e "  ${GREEN}✓ $1${NC}"; }
fail() { echo -e "  ${RED}✗ $1${NC}"; exit 1; }

echo "=== Secure File Ingestion & Signed URL Service — Full Flow Test ==="
echo ""

# ── 1. Upload a test file ────────────────────────────────────────────────
echo "1. Uploading test file..."
UPLOAD_RESP=$(curl -sf -X POST "${BASE_URL}/files" \
    -F "user_id=flow_test_user" \
    -F "file=@scripts/test_flow.sh;type=text/x-shellscript")

FILE_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
FILENAME=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['filename'])")
SIZE=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['size_bytes'])")

if [[ -n "$FILE_ID" ]]; then
    pass "Uploaded: ${FILENAME} (${SIZE} bytes) → id=${FILE_ID}"
else
    fail "Upload failed"
fi

# ── 2. Sign the file ─────────────────────────────────────────────────────
echo "2. Signing file..."
SIGN_RESP=$(curl -sf -X POST "${BASE_URL}/files/${FILE_ID}/sign" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "flow_test_user", "ttl_seconds": 3600}')

DOWNLOAD_URL=$(echo "$SIGN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['download_url'])")
EXPIRES_AT=$(echo "$SIGN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['expires_at'])")

if [[ -n "$DOWNLOAD_URL" ]]; then
    pass "Signed URL: ${DOWNLOAD_URL} (expires: ${EXPIRES_AT})"
else
    fail "Signing failed"
fi

# ── 3. Download via signed URL (no API key) ──────────────────────────────
echo "3. Downloading via signed URL..."
DOWNLOAD_FILE=$(mktemp)
HTTP_CODE=$(curl -s -o "$DOWNLOAD_FILE" -w "%{http_code}" "${BASE_URL}${DOWNLOAD_URL}")

if [[ "$HTTP_CODE" == "200" ]]; then
    DL_SIZE=$(wc -c < "$DOWNLOAD_FILE")
    pass "Downloaded ${DL_SIZE} bytes (HTTP ${HTTP_CODE})"
else
    fail "Download failed with HTTP ${HTTP_CODE}"
fi

# ── 4. Verify content matches ────────────────────────────────────────────
echo "4. Verifying content..."
ORIGINAL_HASH=$(sha256sum scripts/test_flow.sh | awk '{print $1}')
DOWNLOAD_HASH=$(sha256sum "$DOWNLOAD_FILE" | awk '{print $1}')
rm -f "$DOWNLOAD_FILE"

if [[ "$ORIGINAL_HASH" == "$DOWNLOAD_HASH" ]]; then
    pass "SHA-256 match: ${ORIGINAL_HASH:0:16}..."
else
    fail "Content mismatch! Original=${ORIGINAL_HASH:0:16}... Downloaded=${DOWNLOAD_HASH:0:16}..."
fi

# ── 5. Query audit log ──────────────────────────────────────────────────
echo "5. Checking audit log..."
AUDIT_RESP=$(curl -sf "${BASE_URL}/files/${FILE_ID}/audit?user_id=flow_test_user")
AUDIT_TOTAL=$(echo "$AUDIT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")

if [[ "$AUDIT_TOTAL" -ge 1 ]]; then
    pass "Audit log has ${AUDIT_TOTAL} event(s)"
else
    fail "Audit log is empty"
fi

# ── 6. Delete the file ──────────────────────────────────────────────────
echo "6. Deleting file..."
DEL_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
    "${BASE_URL}/files/${FILE_ID}?user_id=flow_test_user")

if [[ "$DEL_CODE" == "204" ]]; then
    pass "Deleted (HTTP 204)"
else
    fail "Delete failed with HTTP ${DEL_CODE}"
fi

# ── 7. Confirm signed URL now returns 404 ───────────────────────────────
echo "7. Confirming signed URL is invalid after delete..."
POST_DEL_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${DOWNLOAD_URL}")

if [[ "$POST_DEL_CODE" == "404" ]]; then
    pass "Signed URL returns 404 after delete"
else
    fail "Expected 404, got HTTP ${POST_DEL_CODE}"
fi

echo ""
echo -e "${GREEN}=== All checks passed ===${NC}"
