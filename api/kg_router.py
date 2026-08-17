"""知识图谱接口：AI 从文档中抽取实体与关系，前端渲染图谱。"""

import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth import require_auth
from core.kg_builder import delete_graph_cache, extract_knowledge_graph, load_cached_graph
from core.rag_engine import get_all_files
from utils.file_meta import storage_to_abs
from utils.file_parser import read_file

router = APIRouter(prefix="/kg", tags=["知识图谱"])
_INVALID_NAME = re.compile(r'[\\/:*?"<>|\r\n]')


def _safe_name(filename: str) -> str:
    safe = os.path.basename((filename or "").strip())
    if not safe or safe in {".", ".."} or _INVALID_NAME.search(safe):
        raise HTTPException(status_code=400, detail="文件名不合法")
    return safe


def _find_file(storage: str | None, safe_name: str | None, owner: str | None) -> dict | None:
    """优先按 storage 精确定位，避免不同用户同名文件歧义；未命中时回退按文件名匹配。"""
    files = get_all_files(owner=owner)
    if storage:
        found = next((item for item in files if item["storage"] == storage), None)
        if found:
            return found
    if safe_name:
        return next((item for item in files if item["name"] == safe_name), None)
    return None


def _resolve_file(filename: str | None, storage: str | None, current: dict) -> dict | None:
    safe_name = _safe_name(filename) if filename else None
    owner = None if current.get("role") == "admin" else current.get("username")
    return _find_file(storage, safe_name, owner)


@router.post("/extract")
def kg_extract(
    filename: str | None = Query(None, min_length=1, max_length=255),
    storage: str | None = Query(None, min_length=1, max_length=512),
    current: dict = Depends(require_auth),
):
    """读取文档并调用大模型抽取实体/关系，结果缓存到 data/kg/。"""
    info = _resolve_file(filename, storage, current)
    if not info:
        raise HTTPException(status_code=404, detail="文件不存在或格式不支持")
    path = storage_to_abs(info["storage"])
    suffix = os.path.splitext(info["storage"])[1].lower()
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在或格式不支持")
    text = read_file(path, suffix)
    return extract_knowledge_graph(info["name"], text, owner=info.get("owner"))


@router.get("/file")
def kg_file(
    filename: str | None = Query(None, min_length=1, max_length=255),
    storage: str | None = Query(None, min_length=1, max_length=512),
    current: dict = Depends(require_auth),
):
    """读取指定文档已生成的图谱；未生成时返回 missing。"""
    info = _resolve_file(filename, storage, current)
    if not info:
        raise HTTPException(status_code=404, detail="文件不存在或格式不支持")
    return load_cached_graph(info["name"], owner=info.get("owner"))


@router.delete("/file")
def kg_delete(
    filename: str | None = Query(None, min_length=1, max_length=255),
    storage: str | None = Query(None, min_length=1, max_length=512),
    current: dict = Depends(require_auth),
):
    """删除文档时同步清理图谱缓存。"""
    if not filename and not storage:
        raise HTTPException(status_code=400, detail="缺少文件参数")
    info = _resolve_file(filename, storage, current)
    name = info["name"] if info else (_safe_name(filename) if filename else None)
    delete_graph_cache(name, owner=info.get("owner") if info else None)
    return {"msg": "图谱缓存已清理"}
