"""极简令牌认证（本地演示）：token = uid.hmac(secret, uid)。
不引第三方依赖；密钥存于 data/.secret，重启后旧令牌仍有效。
"""
import hmac
import hashlib
import secrets

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from . import models
from .config import DATA_DIR
from .database import get_db

_SECRET_FILE = DATA_DIR / ".secret"


def _load_secret() -> bytes:
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_bytes()
    value = secrets.token_bytes(32)
    _SECRET_FILE.write_bytes(value)
    return value


SECRET = _load_secret()


def issue_token(user_id: int) -> str:
    sig = hmac.new(SECRET, str(user_id).encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"


def parse_token(token: str) -> int | None:
    try:
        uid_str, sig = token.split(".", 1)
        uid = int(uid_str)
    except (ValueError, AttributeError):
        return None
    expect = hmac.new(SECRET, uid_str.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expect):
        return uid
    return None


def current_user(
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None),
    token: str | None = Query(default=None),   # 便于 <img src> 直接带令牌
    db: Session = Depends(get_db),
) -> models.User:
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:]
    raw = raw or x_token or token
    if not raw:
        raise HTTPException(status_code=401, detail="未登录")
    uid = parse_token(raw)
    user = db.get(models.User, uid) if uid else None
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


def require_roles(*roles: str):
    def checker(user: models.User = Depends(current_user)) -> models.User:
        owned = set(user.role.split(","))
        if not owned.intersection(roles):
            names = "、".join(models.ROLE_NAMES.get(r, r) for r in roles)
            raise HTTPException(status_code=403, detail=f"需要以下身份之一：{names}")
        return user
    return checker
