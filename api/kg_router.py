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


@router.post("/extract")
def kg_extract(
    filename: str = Query(..., min_length=1, max_length=255),
    current: dict = Depends(require_auth),
):
    """读取文档并调用大模型抽取实体/关系，结果缓存到 data/kg/。"""
    safe_name = _safe_name(filename)
    owner = None if current.get("role") == "admin" else current.get("username")
    info = next(
        (item for item in get_all_files(owner=owner) if item["name"] == safe_name),
        None,
    )
    if not info:
        raise HTTPException(status_code=404, detail="文件不存在或格式不支持")
    path = storage_to_abs(info["storage"])
    suffix = os.path.splitext(safe_name)[1].lower()
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在或格式不支持")
    text = read_file(path, suffix)
    return extract_knowledge_graph(safe_name, text, owner=info.get("owner"))


@router.get("/file")
def kg_file(
    filename: str = Query(..., min_length=1, max_length=255),
    current: dict = Depends(require_auth),
):
    """读取指定文档已生成的图谱；未生成时返回 missing。"""
    safe_name = _safe_name(filename)
    owner = None if current.get("role") == "admin" else current.get("username")
    info = next(
        (item for item in get_all_files(owner=owner) if item["name"] == safe_name),
        None,
    )
    if not info:
        raise HTTPException(status_code=404, detail="文件不存在或格式不支持")
    return load_cached_graph(safe_name, owner=info.get("owner"))


@router.delete("/file")
def kg_delete(
    filename: str = Query(..., min_length=1, max_length=255),
    current: dict = Depends(require_auth),
):
    """删除文档时同步清理图谱缓存。"""
    safe_name = _safe_name(filename)
    owner = None if current.get("role") == "admin" else current.get("username")
    info = next(
        (item for item in get_all_files(owner=owner) if item["name"] == safe_name),
        None,
    )
    delete_graph_cache(safe_name, owner=info.get("owner") if info else None)
    return {"msg": "图谱缓存已清理"}
