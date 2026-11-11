import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.core.errors import unauthorized

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("timing-equalisation-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):  # VerifyMismatchError is a subclass
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# Argon2 is deliberately slow and CPU-bound: keep it off the event loop.
async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password_hash: str, password: str) -> bool:
    return await asyncio.to_thread(verify_password, password_hash, password)


async def burn_password_check(password: str) -> None:
    """Spend the same time as a real check so unknown emails are not detectable by timing."""
    await asyncio.to_thread(verify_password, _DUMMY_HASH, password)


def create_access_token(user_id: uuid.UUID, org_id: uuid.UUID) -> tuple[str, int]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "org": str(org_id),
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
    }
    return jwt.encode(claims, s.jwt_secret, algorithm=s.jwt_algorithm), s.access_token_minutes * 60


def decode_access_token(token: str) -> dict:
    s = get_settings()
    try:
        claims = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm],
                            options={"require": ["exp", "iat", "sub"]})
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid or expired token", "invalid_token") from None
    if claims.get("type") != "access":
        raise unauthorized("Invalid or expired token", "invalid_token")
    return claims


def new_opaque_token() -> tuple[str, str]:
    """Random bearer secret for refresh tokens and invitations. Only the hash is stored."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()