"""JWT authentication helpers."""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

_DEFAULT_SECRET_KEYS = frozenset(
    {
        "dev-secret-changeme-in-production",
        "changeme-in-production",
        "changeme-run-openssl-rand-hex-32",
        "change-me-openssl-rand-hex-32",
    }
)

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-changeme-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# Demo credentials accepted in development mode
_DEMO_CREDENTIALS: dict[str, list[str]] = {
    "admin": ["voiceshield2026", "voiceguard2026", "admin", "admin123", "password"],
    "analyst": ["analyst2026", "voiceshield2026", "voiceguard2026", "analyst", "password"],
}

_USER_PASSWORD_ENV: dict[str, str] = {
    "admin": "VG_ADMIN_PASSWORD",
    "analyst": "VG_ANALYST_PASSWORD",
}

_USER_ROLES: dict[str, str] = {
    "admin": "admin",
    "analyst": "analyst",
}


def role_for(username: str) -> str:
    """Role for a username (defaults to least-privileged)."""
    return _USER_ROLES.get(username, "analyst")


def is_dev_mode() -> bool:
    """True unless VG_ENV is explicitly set to production."""
    return os.environ.get("VG_ENV", "development").strip().lower() != "production"


def check_production_security() -> None:
    """Fail fast if the app is misconfigured for production."""
    if not is_dev_mode() and SECRET_KEY in _DEFAULT_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY is set to a default/placeholder value while VG_ENV=production. "
            "Set SECRET_KEY to a strong random value (e.g. `openssl rand -hex 32`)."
        )


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=15))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> str:
    """Decode and verify JWT. Returns username on success."""
    return verify_token_claims(token)[0]


def verify_token_claims(token: str) -> tuple[str, str]:
    """Decode and verify JWT. Returns (username, role) on success."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
        return username, payload.get("role") or role_for(username)
    except JWTError as err:
        raise credentials_exc from err


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    return verify_token(token)


async def get_current_claims(token: str = Depends(oauth2_scheme)) -> tuple[str, str]:
    return verify_token_claims(token)


def require_role(role: str):
    async def _checker(token: str = Depends(oauth2_scheme)) -> str:
        username, user_role = verify_token_claims(token)
        if user_role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This operation requires the '{role}' role.",
            )
        return username

    return _checker


def authenticate_user(username: str, password: str) -> dict[str, str] | None:
    """Authenticate username & password. Returns dict with username and role on success, None on failure."""
    username_clean = username.strip().lower()

    # 1. Check production environment variable if set
    env_var = _USER_PASSWORD_ENV.get(username_clean)
    if env_var:
        env_pw = os.environ.get(env_var)
        if env_pw and secrets.compare_digest(env_pw, password):
            return {"username": username_clean, "role": role_for(username_clean)}

    # 2. Check dev mode demo credentials
    if is_dev_mode():
        allowed_passwords = _DEMO_CREDENTIALS.get(username_clean, [])
        for valid_pw in allowed_passwords:
            if secrets.compare_digest(valid_pw, password):
                return {"username": username_clean, "role": role_for(username_clean)}

    return None
