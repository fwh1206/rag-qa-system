"""登录鉴权接口：负责登录、登出、当前用户查询与管理员用户管理。"""

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from config.email_config import is_email_configured
from config.settings import AUTH_ENABLED, AUTH_PASSWORD, AUTH_USERNAME, EMAIL_CODE_TTL, EMAIL_DEV_MODE
from core.auth import create_token, login, require_admin, require_auth, revoke_token
from core.database import (
    ERR_USER_EXISTS,
    count_admins,
    create_email_code,
    create_user,
    delete_user,
    get_email_code,
    get_user,
    get_user_by_email,
    get_user_llm_config,
    has_active_email_code,
    list_users,
    mark_email_code_used,
    save_user_llm_config,
    update_user_email,
    update_user_password,
    update_user_role,
    verify_password,
)
from core.emailer import generate_verification_code, send_verification_email
from core.llm_client import llm_chat, resolve_user_llm_config
from core.rate_limiter import SlidingWindowRateLimiter
from core.secret_box import encrypt_secret

router = APIRouter(prefix="/auth", tags=["登录鉴权"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

LOGIN_LIMITER = SlidingWindowRateLimiter(limit=30, window_seconds=60)
SEND_CODE_LIMITER = SlidingWindowRateLimiter(limit=10, window_seconds=60)
REGISTER_LIMITER = SlidingWindowRateLimiter(limit=10, window_seconds=60)


def _client_key(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=4, max_length=128)
    email: str = Field(..., max_length=255)
    code: str = Field(..., min_length=6, max_length=6)


class SendCodeRequest(BaseModel):
    email: str = Field(..., max_length=255)
    purpose: str = Field("register", pattern="^(register|login|reset|bind)$")


class LoginCodeRequest(BaseModel):
    email: str = Field(..., max_length=255)
    code: str = Field(..., min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    email: str = Field(..., max_length=255)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=4, max_length=128)


class BindEmailRequest(BaseModel):
    email: str = Field(..., max_length=255)
    code: str = Field(..., min_length=6, max_length=6)


class UserLLMConfigUpdate(BaseModel):
    enabled: bool = False
    url: str = Field("", max_length=512)
    model: str = Field("", max_length=128)
    api_key: str | None = Field(None, max_length=512)


class UserLLMTestRequest(BaseModel):
    url: str = Field("", max_length=512)
    model: str = Field("", max_length=128)
    api_key: str | None = Field(None, max_length=512)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=4, max_length=128)
    role: str = Field("user", pattern="^(admin|user)$")
    email: str | None = Field(None, max_length=255)


class UserUpdate(BaseModel):
    role: str | None = Field(None, pattern="^(admin|user)$")
    password: str | None = Field(None, min_length=4, max_length=128)


class PasswordChange(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=4, max_length=128)


@router.post("/login")
def auth_login(payload: LoginRequest, request: Request):
    if not LOGIN_LIMITER.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")
    account = payload.username.strip()
    token = login(account, payload.password)
    if not token:
        raise HTTPException(status_code=401, detail="邮箱/用户名或密码错误")
    user = get_user(account) or get_user_by_email(account.lower())
    if not user:
        # login 成功但用户恰好被删除等竞态：安全起见 fail-closed，不再兜底成 admin
        raise HTTPException(status_code=401, detail="账号不存在或已注销")
    return {
        "token": token,
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "auth_enabled": AUTH_ENABLED,
    }


@router.post("/send-code")
def auth_send_code(payload: SendCodeRequest, request: Request):
    """发送注册/登录邮箱验证码；未配置 SMTP 时按开发模式开关决定是否回显。"""
    if not SEND_CODE_LIMITER.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="验证码发送过于频繁，请稍后再试")
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    purpose = payload.purpose
    if purpose == "register" and get_user_by_email(email):
        raise HTTPException(status_code=400, detail="该邮箱已注册，请直接登录")
    if purpose in ("login", "reset") and not get_user_by_email(email):
        raise HTTPException(status_code=400, detail="该邮箱尚未注册")
    if purpose == "bind" and get_user_by_email(email):
        raise HTTPException(status_code=400, detail="该邮箱已被其他账号绑定")
    if has_active_email_code(email, purpose):
        raise HTTPException(status_code=429, detail="验证码已发送，请稍后再试")

    code = generate_verification_code()
    expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=EMAIL_CODE_TTL)
    create_email_code(email, code, purpose, expires_at)
    email_configured = is_email_configured()
    if not email_configured and not EMAIL_DEV_MODE:
        raise HTTPException(
            status_code=500,
            detail="SMTP 邮箱服务未配置，请先在系统设置中完成邮箱配置",
        )
    sent = send_verification_email(email, code, purpose)
    if email_configured and not sent:
        raise HTTPException(status_code=500, detail="验证码发送失败，请检查 SMTP 配置")
    if not email_configured:
        return {
            "msg": "开发模式验证码已生成",
            "email": email,
            "dev_code": code,
            "dev_mode": True,
        }
    return {"msg": "验证码已发送", "email": email}


@router.post("/login-code")
def auth_login_code(payload: LoginCodeRequest, request: Request):
    """邮箱验证码登录：验证码通过后直接签发 token。"""
    if not LOGIN_LIMITER.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")
    email = payload.email.strip().lower()
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=400, detail="该邮箱尚未注册")
    record = get_email_code(email, "login")
    expected = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    if not record or not secrets.compare_digest(record["code_hash"], expected):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    mark_email_code_used(record["id"])
    token = create_token(user["username"], user["role"])
    return {
        "token": token,
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "auth_enabled": AUTH_ENABLED,
    }


@router.post("/reset-password")
def auth_reset_password(payload: ResetPasswordRequest, request: Request):
    """邮箱验证码找回密码：验证通过后直接更新密码。"""
    if not SEND_CODE_LIMITER.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
    email = payload.email.strip().lower()
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=400, detail="该邮箱尚未注册")
    record = get_email_code(email, "reset")
    expected = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    if not record or not secrets.compare_digest(record["code_hash"], expected):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    update_user_password(user["username"], payload.new_password)
    mark_email_code_used(record["id"])
    return {"msg": "密码已重置，请使用新密码登录", "username": user["username"]}


@router.post("/logout")
def auth_logout(x_auth_token: str | None = Header(default=None)):
    if x_auth_token:
        revoke_token(x_auth_token)
    return {"msg": "已退出登录"}


@router.get("/me")
def auth_me(current: dict = Depends(require_auth)):
    if not AUTH_ENABLED:
        return {"username": "guest", "role": "admin", "auth_enabled": False, "id": None, "created_at": None}
    user = get_user(current.get("username") or "")
    return {
        "username": current.get("username"),
        "role": current.get("role"),
        "auth_enabled": True,
        "id": user.get("id") if user else None,
        "email": user.get("email") if user else None,
        "created_at": user.get("created_at") if user else None,
    }


@router.post("/me/email")
def auth_bind_email(
    payload: BindEmailRequest,
    current: dict = Depends(require_auth),
):
    """当前用户绑定邮箱，供忘记密码等场景使用。"""
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    existing = get_user_by_email(email)
    if existing and existing["username"] != current.get("username"):
        raise HTTPException(status_code=400, detail="该邮箱已被其他账号绑定")
    record = get_email_code(email, "bind")
    expected = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    if not record or not secrets.compare_digest(record["code_hash"], expected):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    update_user_email(current.get("username") or "", email)
    mark_email_code_used(record["id"])
    return {"msg": "邮箱绑定成功", "email": email}


@router.get("/me/llm")
def auth_me_llm(current: dict = Depends(require_auth)):
    """读取当前用户自己的大模型配置，API Key 不回显。"""
    raw = get_user_llm_config(current.get("username") or "")
    return {
        "enabled": bool(raw and raw["llm_enabled"]),
        "url": (raw or {}).get("llm_url") or "",
        "model": (raw or {}).get("llm_model") or "",
        "has_api_key": bool(raw and raw.get("llm_api_key")),
    }


@router.put("/me/llm")
def auth_save_me_llm(
    payload: UserLLMConfigUpdate,
    current: dict = Depends(require_auth),
):
    """保存当前用户自己的 OpenAI 兼容模型配置，Key 加密后入库。"""
    username = current.get("username") or ""
    url = payload.url.strip()
    model = payload.model.strip()
    if payload.enabled and (not url or not model):
        raise HTTPException(status_code=400, detail="使用自己的模型时，API 地址和模型名称不能为空")

    existing = get_user_llm_config(username) or {}
    encrypted_key = existing.get("llm_api_key")
    if payload.api_key:
        encrypted_key = encrypt_secret(payload.api_key)
    elif payload.enabled and not encrypted_key:
        raise HTTPException(status_code=400, detail="使用自己的模型时必须填写 API Key")

    save_user_llm_config(username, payload.enabled, url, model, encrypted_key)
    return {"msg": "我的模型配置已保存", "enabled": payload.enabled, "has_api_key": bool(encrypted_key)}


@router.post("/me/llm/test")
def auth_test_me_llm(
    payload: UserLLMTestRequest,
    current: dict = Depends(require_auth),
):
    """用当前用户填写的模型配置发起一次最小调用；未填写时使用已保存配置。"""
    username = current.get("username") or ""
    saved = resolve_user_llm_config(get_user_llm_config(username))
    if payload.url or payload.model or payload.api_key:
        user_config = {
            "api_key": payload.api_key or (saved or {}).get("api_key", ""),
            "url": payload.url.strip() or (saved or {}).get("url", ""),
            "model": payload.model.strip() or (saved or {}).get("model", ""),
        }
    else:
        user_config = saved
    if not user_config or not all(user_config.values()):
        raise HTTPException(status_code=400, detail="请先保存并启用自己的模型配置")
    try:
        answer = llm_chat("请只回复：OK", 0, user_config, read_timeout=20)
    except HTTPException as exc:
        raise HTTPException(status_code=500, detail=f"模型调用失败：{exc.detail}") from exc
    return {"msg": "模型调用成功", "reply": (answer or "")[:200]}


@router.post("/password")
def change_password(payload: PasswordChange, current: dict = Depends(require_auth)):
    if not AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="当前环境未启用账号密码认证")
    username = current.get("username") or ""
    user = get_user(username)
    if user:
        if not verify_password(payload.old_password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="当前密码不正确")
        update_user_password(username, payload.new_password)
    else:
        if username != AUTH_USERNAME or payload.old_password != AUTH_PASSWORD:
            raise HTTPException(status_code=401, detail="当前密码不正确")
        ok, err = create_user(username, payload.new_password, current.get("role") or "admin")
        if not ok:
            raise HTTPException(status_code=400 if err == ERR_USER_EXISTS else 500, detail=err)
    return {"msg": "密码已更新", "username": username}


@router.post("/register")
def auth_register(payload: RegisterRequest, request: Request):
    """自助注册：邮箱验证码校验通过后创建普通用户。"""
    if not REGISTER_LIMITER.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="注册过于频繁，请稍后再试")
    username = payload.username.strip().lower()
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if get_user(username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    if get_user_by_email(email):
        raise HTTPException(status_code=400, detail="该邮箱已注册")
    record = get_email_code(email, "register")
    expected = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    if not record or not secrets.compare_digest(record["code_hash"], expected):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")
    ok, err = create_user(username, payload.password, "user", email=email)
    if not ok:
        raise HTTPException(status_code=400 if err == ERR_USER_EXISTS else 500, detail=err)
    mark_email_code_used(record["id"])
    return {"msg": "注册成功", "username": username, "email": email}


@router.get("/users")
def auth_users_list(_: dict = Depends(require_admin)):
    return {"users": list_users()}


@router.post("/users")
def auth_users_create(payload: UserCreate, _: dict = Depends(require_admin)):
    username = payload.username.strip().lower()
    if get_user(username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    email = (payload.email or "").strip().lower() or None
    if email and get_user_by_email(email):
        raise HTTPException(status_code=400, detail="邮箱已存在")
    ok, err = create_user(username, payload.password, payload.role, email=email)
    if not ok:
        raise HTTPException(status_code=400 if err == ERR_USER_EXISTS else 500, detail=err)
    return {"msg": "用户创建成功", "username": username, "email": email}


@router.put("/users/{username}")
def auth_users_update(
    username: str,
    payload: UserUpdate,
    _: dict = Depends(require_admin),
):
    if not get_user(username):
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.role:
        update_user_role(username, payload.role)
    if payload.password:
        update_user_password(username, payload.password)
    return {"msg": "用户信息已更新", "username": username}


@router.delete("/users/{username}")
def auth_users_delete(
    username: str,
    current: dict = Depends(require_admin),
):
    if username == current["username"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    target = get_user(username)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target["role"] == "admin" and count_admins() <= 1:
        raise HTTPException(status_code=400, detail="至少保留一个管理员")
    delete_user(username)
    return {"msg": "用户已删除", "username": username}
