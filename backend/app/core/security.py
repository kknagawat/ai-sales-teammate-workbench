from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

import bcrypt
import jwt

from app.core.config import get_settings


class InvalidTokenError(Exception):
    pass


def _bcrypt_input(password: str) -> bytes:
    # bcrypt silently truncates after 72 bytes, so hash the full password first.
    return sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(_bcrypt_input(password), password_hash.encode("utf-8"))


DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")


def create_access_token(user_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.auth_cookie_max_age_seconds)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        if not subject:
            raise InvalidTokenError
        return UUID(subject)
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise InvalidTokenError from exc
