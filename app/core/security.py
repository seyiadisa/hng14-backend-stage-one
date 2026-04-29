import jwt
import secrets
import hashlib
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings


def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=get_settings().access_token_expire_minutes),
    }

    return jwt.encode(
        payload, get_settings().jwt_secret_key, algorithm=get_settings().jwt_algorithm
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
