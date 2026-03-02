"""Unit tests for app.services.signing_service.

Pure crypto logic — no database, no HTTP. Tests run in isolation.
"""

import time
import uuid

import pytest

from app.services.signing_service import generate_signed_token, verify_signed_token

SECRET = "test-signing-secret-abc123"


# ── required tests ─────────────────────────────────────────────────────

def test_generate_and_verify_roundtrip():
    """Generate a token, then verify it — returns the same file_id."""
    file_id = uuid.uuid4()
    token, expires_at = generate_signed_token(file_id, 3600, SECRET)

    result = verify_signed_token(token, SECRET)
    assert result == file_id


def test_verify_expired_token():
    """Token generated with ttl=1 and checked after 2s raises 'link expired'."""
    file_id = uuid.uuid4()
    token, _ = generate_signed_token(file_id, 1, SECRET)

    time.sleep(2)

    with pytest.raises(ValueError, match="link expired"):
        verify_signed_token(token, SECRET)


def test_verify_tampered_signature():
    """Altering the signature portion raises 'invalid signature'."""
    token, _ = generate_signed_token(uuid.uuid4(), 3600, SECRET)
    payload_b64, sig_b64 = token.split(".")

    # Flip a character in the signature
    tampered_sig = ("A" if sig_b64[0] != "A" else "B") + sig_b64[1:]
    tampered_token = f"{payload_b64}.{tampered_sig}"

    with pytest.raises(ValueError, match="invalid signature"):
        verify_signed_token(tampered_token, SECRET)


def test_verify_tampered_payload():
    """Altering the payload portion raises 'invalid signature'."""
    token, _ = generate_signed_token(uuid.uuid4(), 3600, SECRET)
    payload_b64, sig_b64 = token.split(".")

    # Flip a character in the payload
    tampered_payload = ("X" if payload_b64[0] != "X" else "Y") + payload_b64[1:]
    tampered_token = f"{tampered_payload}.{sig_b64}"

    with pytest.raises(ValueError, match="invalid signature"):
        verify_signed_token(tampered_token, SECRET)


def test_verify_wrong_secret():
    """Generating with one secret and verifying with another raises 'invalid signature'."""
    token, _ = generate_signed_token(uuid.uuid4(), 3600, "secret-one")

    with pytest.raises(ValueError, match="invalid signature"):
        verify_signed_token(token, "secret-two")


def test_verify_malformed_token():
    """A string with no '.' separator raises 'invalid signature'."""
    with pytest.raises(ValueError, match="invalid signature"):
        verify_signed_token("nodotinthisstring", SECRET)


# ── edge cases ─────────────────────────────────────────────────────────

def test_verify_empty_string():
    """Empty string has no dot separator — raises 'invalid signature'."""
    with pytest.raises(ValueError, match="invalid signature"):
        verify_signed_token("", SECRET)


def test_verify_multiple_dots():
    """Token with more than one dot is rejected because split produces >2 parts."""
    with pytest.raises(ValueError, match="invalid signature"):
        verify_signed_token("a.b.c", SECRET)


def test_verify_empty_secret():
    """Generating and verifying with an empty secret still works as a valid HMAC key."""
    file_id = uuid.uuid4()
    token, _ = generate_signed_token(file_id, 3600, "")
    result = verify_signed_token(token, "")
    assert result == file_id


def test_generate_returns_future_expiry():
    """expires_at returned by generate is in the future by approximately ttl_seconds."""
    from datetime import datetime, timezone

    file_id = uuid.uuid4()
    _, expires_at = generate_signed_token(file_id, 300, SECRET)

    now = datetime.now(timezone.utc)
    delta = (expires_at - now).total_seconds()
    # Should be close to 300 seconds (within 5s tolerance for test execution)
    assert 295 <= delta <= 305


def test_token_is_deterministic_payload_structure():
    """Token payload contains file_id and exp keys when decoded."""
    import base64
    import json

    file_id = uuid.uuid4()
    token, _ = generate_signed_token(file_id, 3600, SECRET)
    payload_b64 = token.split(".")[0]

    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    assert payload["file_id"] == str(file_id)
    assert isinstance(payload["exp"], int)
