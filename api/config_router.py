"""运行配置接口：读取和更新 RAG 参数。"""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config.email_config import is_email_configured, load_email_config, save_email_config
from config.llm_config import load_llm_config, save_llm_config
from config.rag_config import get_config, save_config
from core.auth import require_admin
from core.emailer import send_test_email
from core.llm_client import llm_chat
from core.logger import write_log

router = APIRouter(prefix="/config", tags=["运行配置"])


class ConfigUpdate(BaseModel):
    prompt_template: str | None = None
    chunk_size: int | None = Field(None, ge=100, le=2000)
    chunk_overlap: int | None = Field(None, ge=0, le=500)
    top_k: int | None = Field(None, ge=1, le=10)
    similarity_threshold: float | None = Field(None, ge=0.0, le=1.0)
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    thinking_enabled: bool | None = None
    rewrite_enabled: bool | None = None
    rerank_enabled: bool | None = None
    rerank_top_k: int | None = Field(None, ge=1, le=10)


class EmailConfigUpdate(BaseModel):
    host: str = Field("", max_length=255)
    port: int = Field(465, ge=1, le=65535)
    user: str = Field("", max_length=255)
    password: str | None = Field(None, max_length=255)
    from_address: str = Field("", max_length=255)
    use_ssl: bool = True


class EmailTestRequest(BaseModel):
    to_email: str = Field(..., max_length=255)


class LLMConfigUpdate(BaseModel):
    api_key: str | None = Field(None, max_length=512)
    url: str = Field(..., max_length=512)
    model: str = Field(..., min_length=1, max_length=128)


class LLMTestRequest(BaseModel):
    url: str = Field("", max_length=512)
    model: str = Field("", max_length=128)
    api_key: str | None = Field(None, max_length=512)


@router.get("")
def get_runtime_config():
    return get_config()


@router.put("", dependencies=[Depends(require_admin)])
def update_runtime_config(payload: ConfigUpdate):
    current = get_config()
    data = payload.model_dump(exclude_none=True)
    if not data:
        return current
    merged = dict(current, **data)
    try:
        saved = save_config(merged)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_log(f"运行配置已更新：{data}")
    return saved


@router.post("/reset", dependencies=[Depends(require_admin)])
def reset_runtime_config():
    """恢复默认配置：删除持久化配置并返回默认值。"""
    from config.rag_config import DEFAULT_CONFIG
    from config.settings import CONFIG_PATH

    try:
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
    except OSError:
        pass
    write_log("运行配置已恢复默认")
    return {"msg": "已恢复默认设置", "config": DEFAULT_CONFIG}


def _masked_email_config() -> dict:
    cfg = load_email_config()
    return {
        "host": cfg.get("host", ""),
        "port": cfg.get("port", 465),
        "user": cfg.get("user", ""),
        "from_address": cfg.get("from_address", ""),
        "use_ssl": bool(cfg.get("use_ssl", True)),
        "has_password": bool(cfg.get("password")),
        "configured": bool(cfg.get("host")),
    }


@router.get("/email")
def get_email_config(_: dict = Depends(require_admin)):
    return _masked_email_config()


@router.put("/email", dependencies=[Depends(require_admin)])
def update_email_config(payload: EmailConfigUpdate):
    current = load_email_config()
    password = payload.password
    if not password:
        password = current.get("password", "")
    save_email_config(
        {
            "host": payload.host.strip(),
            "port": payload.port,
            "user": payload.user.strip(),
            "password": password,
            "from_address": payload.from_address.strip(),
            "use_ssl": payload.use_ssl,
        }
    )
    write_log("邮箱 SMTP 配置已更新")
    return {"msg": "邮箱设置已保存", **_masked_email_config()}


@router.post("/email/test", dependencies=[Depends(require_admin)])
def test_email_config(payload: EmailTestRequest):
    if not is_email_configured():
        raise HTTPException(status_code=400, detail="SMTP 邮箱服务未配置")
    if not send_test_email(payload.to_email.strip()):
        raise HTTPException(status_code=500, detail="测试邮件发送失败，请检查 SMTP 配置")
    return {"msg": "测试邮件已发送"}


def _masked_llm_config() -> dict:
    cfg = load_llm_config()
    return {
        "url": cfg.get("url", ""),
        "model": cfg.get("model", ""),
        "has_api_key": bool(cfg.get("api_key")),
        "configured": bool(cfg.get("api_key")),
    }


@router.get("/llm")
def get_llm_config(_: dict = Depends(require_admin)):
    return _masked_llm_config()


@router.put("/llm", dependencies=[Depends(require_admin)])
def update_llm_config(payload: LLMConfigUpdate):
    current = load_llm_config()
    api_key = payload.api_key
    if not api_key:
        api_key = current.get("api_key", "")
    save_llm_config(
        {
            "api_key": api_key,
            "url": payload.url.strip(),
            "model": payload.model.strip(),
        }
    )
    write_log("大模型服务配置已更新")
    return {"msg": "大模型配置已保存", **_masked_llm_config()}


@router.post("/llm/test", dependencies=[Depends(require_admin)])
def test_llm_config(payload: LLMTestRequest):
    current = load_llm_config()
    cfg = {
        "api_key": payload.api_key or current.get("api_key", ""),
        "url": payload.url.strip() or current.get("url", ""),
        "model": payload.model.strip() or current.get("model", ""),
    }
    if not all(cfg.values()):
        raise HTTPException(status_code=400, detail="请填写 API 地址、模型名称和 API Key")
    try:
        answer = llm_chat("请只回复：OK", 0, cfg, read_timeout=20)
    except HTTPException as exc:
        raise HTTPException(status_code=500, detail=f"模型调用失败：{exc.detail}") from exc
    return {"msg": "模型调用成功", "reply": (answer or "")[:200]}
