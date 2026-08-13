"""数据库版 token 鉴权：登录签发 token，接口通过 Header 校验身份。"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException

from config.settings import AUTH_ENABLED, AUTH_TOKEN_TTL
from core.database import (
    create_auth_token,
    delete_auth_token,
    get_auth_token,
    get_user,
    get_user_by_email,
    purge_expired_tokens,
    verify_password,
)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(username: str, role: str = "user") -> str:
    token = secrets.token_hex(32)
    expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=AUTH_TOKEN_TTL)
    create_auth_token(_hash_token(token), username, role, expires_at)
    return token


def validate_token(token: str) -> dict | None:
    if not token:
        return None
    info = get_auth_token(_hash_token(token))
    if not info:
        return None
    return {"username": info["username"], "role": info["role"]}


def revoke_token(token: str):
    if token:
        delete_auth_token(_hash_token(token))


def login(username: str, password: str):
    """只校验 MySQL 用户表，避免默认管理员凭据绕过数据库鉴权。"""
    purge_expired_tokens()
    account = username.strip().lower()
    user = get_user(account) or get_user_by_email(account)
    if user and verify_password(password, user["password_hash"]):
        return create_token(user["username"], user["role"])
    return None


def require_auth(x_auth_token: str | None = Header(default=None)):
    """FastAPI 依赖：业务接口统一在这里校验登录状态。"""
    if not AUTH_ENABLED:
        return {"username": "guest", "role": "admin"}
    info = validate_token(x_auth_token or "")
    if not info:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return {"username": info["username"], "role": info["role"]}


def require_admin(x_auth_token: str | None = Header(default=None)):
    """管理端依赖：只有 admin 角色才能执行。"""
    auth = require_auth(x_auth_token)
    if auth.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return auth
