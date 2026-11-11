import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError


def test_password_hash_roundtrip_and_salting():
    h1, h2 = security.hash_password("s3cret-passphrase"), security.hash_password("s3cret-passphrase")
    assert h1 != h2 and h1.startswith("$argon2")
    assert security.verify_password(h1, "s3cret-passphrase")
    assert not security.verify_password(h1, "wrong")
    assert not security.verify_password("not-a-hash", "anything")


def test_access_token_roundtrip():
    uid, oid = uuid.uuid4(), uuid.uuid4()
    token, ttl = security.create_access_token(uid, oid)
    claims = security.decode_access_token(token)
    assert claims["sub"] == str(uid) and claims["org"] == str(oid) and ttl == 15 * 60


def test_tampered_expired_and_wrong_type_tokens_rejected():
    s = get_settings()
    token, _ = security.create_access_token(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(AppError):
        security.decode_access_token(token[:-2] + ("AA" if not token.endswith("AA") else "BB"))
    now = datetime.now(timezone.utc)
    expired = jwt.encode({"sub": "x", "org": "y", "type": "access", "iat": now - timedelta(hours=2),
                          "exp": now - timedelta(hours=1)}, s.jwt_secret, algorithm="HS256")
    with pytest.raises(AppError):
        security.decode_access_token(expired)
    wrong_type = jwt.encode({"sub": "x", "org": "y", "type": "refresh", "iat": now, "exp": now + timedelta(hours=1)},
                            s.jwt_secret, algorithm="HS256")
    with pytest.raises(AppError):
        security.decode_access_token(wrong_type)
    other_key = jwt.encode({"sub": "x", "org": "y", "type": "access", "iat": now, "exp": now + timedelta(hours=1)},
                           "another-secret-another-secret-123456", algorithm="HS256")
    with pytest.raises(AppError):
        security.decode_access_token(other_key)


def test_alg_none_token_rejected():
    now = datetime.now(timezone.utc)
    forged = jwt.encode({"sub": "x", "org": "y", "type": "access", "iat": now, "exp": now + timedelta(hours=1)},
                        key=None, algorithm="none")
    with pytest.raises(AppError):
        security.decode_access_token(forged)


def test_opaque_tokens_store_only_hashes():
    raw, digest = security.new_opaque_token()
    assert digest == security.hash_token(raw) and raw != digest and len(digest) == 64
    assert security.new_opaque_token()[0] != raw