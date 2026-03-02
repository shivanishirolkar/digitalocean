"""Service for HMAC-SHA256 signed URL token generation and verification.

Cryptographic signing logic only — no database access, no HTTP code.
Tokens are self-contained: {file_id, exp} + HMAC-SHA256 signature.
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID


def generate_signed_token(
    file_id: UUID,
    ttl_seconds: int,
    secret: str,
) -> tuple[str, datetime]:
    """Create a signed token encoding *file_id* and an expiry.

    Args:
        file_id: The file to create a download token for.
        ttl_seconds: Time-to-live in seconds.
        secret: HMAC-SHA256 signing key.

    Returns:
        A tuple of (token_string, expires_at_datetime).
    """
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    payload = {"file_id": str(file_id), "exp": int(expires_at.timestamp())}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode()

    signature = hmac.new(
        secret.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode()

    token = f"{payload_b64}.{signature_b64}"
    return token, expires_at


def verify_signed_token(token: str, secret: str) -> UUID:
    """Validate a signed token and return the embedded file_id.

    Args:
        token: The token string (payload_b64.signature_b64).
        secret: HMAC-SHA256 signing key.

    Returns:
        The file_id UUID from the token payload.

    Raises:
        ValueError: "invalid signature" if tampered or malformed.
        ValueError: "link expired" if past the expiry time.
    """
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("invalid signature")

    payload_b64, signature_b64 = parts

    # Recompute HMAC and compare in constant time
    expected_sig = hmac.new(
        secret.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode()

    if not hmac.compare_digest(expected_sig_b64, signature_b64):
        raise ValueError("invalid signature")

    # Decode payload
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)
    except Exception:
        raise ValueError("invalid signature")

    # Check expiration
    exp = payload.get("exp")
    if exp is None:
        raise ValueError("invalid signature")

    if datetime.now(timezone.utc) > datetime.fromtimestamp(exp, tz=timezone.utc):
        raise ValueError("link expired")

    # Extract file_id
    try:
        file_id = UUID(payload["file_id"])
    except (KeyError, ValueError):
        raise ValueError("invalid signature")

    return file_id
