import os
import hashlib
import hmac
import base64
import json
import time
from typing import Optional

SECRET_KEY = os.getenv("SECRET_KEY", "keheilan-secret-change-in-prod-2024")
TOKEN_EXPIRE_HOURS = 24


# ── Password hashing (SHA-256 + HMAC, no extra deps) ──────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return base64.b64encode(salt + dk).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        raw = base64.b64decode(hashed.encode())
        salt, dk = raw[:16], raw[16:]
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
        return hmac.compare_digest(dk, check)
    except Exception:
        return False


# ── Minimal JWT (header.payload.signature) ───────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def create_token(user_id: int, role: str) -> str:
    header  = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user_id,
        "role": role,
        "exp": int(time.time()) + TOKEN_EXPIRE_HOURS * 3600
    }).encode())
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url_encode(
        hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> Optional[dict]:
    try:
        header, payload, sig = token.split(".")
        sig_input = f"{header}.{payload}".encode()
        expected  = _b64url_encode(
            hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


# ── FastAPI dependency ────────────────────────────────────────────────────

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    data = decode_token(credentials.credentials)
    if not data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    from database import get_user_by_id
    user = get_user_by_id(data["sub"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")
    return user


def require_role(*roles):
    def dep(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return dep
