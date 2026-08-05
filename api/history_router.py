"""对话记录接口：分页查询历史、导出和会话管理。"""

import json

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from core.auth import require_auth
from core.database import (
    clear_chat_history,
    count_chat_history,
    ensure_session,
    list_chat_history,
    list_sessions,
    rename_session,
    require_session_access,
)


router = APIRouter(prefix="", tags=["对话记录"])


class SessionRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


@router.get("/history/list")
def get_history(
    current: dict = Depends(require_auth),
    session_id: str = Query("default", min_length=1, max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    require_session_access(session_id, current)
    total = count_chat_history(session_id)
    history = list_chat_history(session_id, limit=page_size, offset=(page - 1) * page_size)
    return {
        "history": history,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.delete("/history/clear")
def clear_history(
    current: dict = Depends(require_auth),
    session_id: str = Query("default", min_length=1, max_length=128),
):
    require_session_access(session_id, current)
    clear_chat_history(session_id)
    return {"msg": "对话记录已清空"}


@router.get("/history/export")
def export_history(
    current: dict = Depends(require_auth),
    session_id: str = Query("default", min_length=1, max_length=128),
    format: str = Query("md", pattern="^(md|json)$"),
):
    require_session_access(session_id, current)
    history = list_chat_history(session_id, limit=1000)
    if format == "json":
        content = json.dumps(history, ensure_ascii=False, indent=2)
        media = "application/json"
        suffix = "json"
    else:
        lines = [f"# 会话：{session_id}", ""]
        for item in history:
            lines.append(f"## 用户\n\n{item['question']}\n")
            lines.append(f"## AI\n\n{item['answer']}\n")
            if item.get("thinking"):
                lines.append(f"### 思考过程\n\n{item['thinking']}\n")
        content = "\n".join(lines)
        media = "text/markdown"
        suffix = "md"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="chat_{session_id}.{suffix}"'},
    )


@router.get("/sessions/list")
def get_sessions(current: dict = Depends(require_auth)):
    owner = None if current.get("role") == "admin" else current.get("username")
    return {"sessions": list_sessions(owner=owner)}


@router.put("/sessions/rename")
def rename_session_api(
    payload: SessionRename,
    current: dict = Depends(require_auth),
    session_id: str = Query(..., min_length=1, max_length=128),
):
    require_session_access(session_id, current)
    owner = current.get("username") if current.get("role") != "admin" else None
    ensure_session(session_id, name=payload.name.strip(), owner=owner)
    rename_session(session_id, payload.name.strip())
    return {"msg": "会话已重命名", "session_id": session_id, "name": payload.name.strip()}
