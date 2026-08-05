"""运行配置接口：读取和更新 RAG 参数。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config.rag_config import get_config, save_config
from core.auth import require_admin
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
