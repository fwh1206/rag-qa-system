"""文件与知识库接口：上传解析、文本录入、向量入库、列表、删除与重建索引。"""

import os
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from config.rag_config import get_config
from core.auth import require_auth
from core.kg_builder import clear_graph_cache, delete_graph_cache
from core.logger import write_log
from core.rag_engine import (
    SUPPORTED_SUFFIXES,
    delete_file_vectors,
    file_to_vector,
    get_all_files,
    hybrid_search_with_rerank,
)
from utils.file_meta import (
    DEFAULT_CATEGORY,
    clear_file_meta,
    remove_file_meta,
    set_file_meta,
    storage_to_abs,
    user_upload_dir,
    user_upload_rel,
)
from utils.file_parser import read_file

router = APIRouter(prefix="", tags=["文件与知识库"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 单文件最大 20MB
STREAM_CHUNK_SIZE = 1024 * 1024  # 分块读取大小 1MB
MAX_TEXT_LENGTH = 1024 * 1024  # 手动录入文本最大 1MB
INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n]')


def _scope_owner(current: dict) -> str | None:
    """普通用户只看自己的知识库；管理员查看全站。"""
    if current.get("role") == "admin":
        return None
    return current.get("username") or "guest"


def _find_file(name: str, owner: str | None) -> dict | None:
    return next((item for item in get_all_files(owner=owner) if item["name"] == name), None)


class TextUpload(BaseModel):
    """手动粘贴文本入库的请求体。"""

    doc_name: str = Field(..., min_length=1, max_length=200)
    text_content: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    category: str = Field(DEFAULT_CATEGORY, min_length=1, max_length=50)


def _safe_filename(name: str) -> str:
    """清洗文件名，只保留 basename 并过滤非法字符，阻止路径穿越。"""
    safe = os.path.basename((name or "").strip())
    if not safe or safe in {".", ".."} or INVALID_FILENAME_CHARS.search(safe):
        raise HTTPException(status_code=400, detail="文件名不合法")
    return safe


@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    category: str = Form(DEFAULT_CATEGORY),
    current: dict = Depends(require_auth),
):
    """上传文件：先写临时文件，再解析文本、切分并写入向量库，成功后才转正。"""
    filename = _safe_filename(file.filename)
    category = (category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY
    owner = current.get("username") or "guest"
    storage = user_upload_rel(owner, filename)
    upload_dir = user_upload_dir(owner)
    os.makedirs(upload_dir, exist_ok=True)
    write_log(f"开始上传：{filename}（{owner}）")
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持pdf/txt/docx/doc/md/xlsx/xls/json")

    tmp_path = os.path.join(upload_dir, f".{uuid.uuid4().hex}.part")
    size = 0
    try:
        # 同步路由由 FastAPI 放入线程池执行，这里同步读取底层文件并限制单文件大小
        with open(tmp_path, "wb") as f:
            while True:
                chunk = file.file.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="文件过大，最大支持20MB")
                f.write(chunk)

        try:
            text = read_file(tmp_path, suffix)
        except Exception as exc:
            write_log(f"文件解析失败：{filename}，{exc}")
            raise HTTPException(status_code=400, detail="文件解析失败，请检查文件是否损坏") from exc
        if not text:
            raise HTTPException(status_code=400, detail="文件无有效文本")

        chunk_num = file_to_vector(filename, text, category, owner=owner, storage=storage)
        set_file_meta(storage, category=category, owner=owner, display_name=filename)
        # 解析与入库成功后再把临时文件转正，避免失败时污染知识库
        os.replace(tmp_path, os.path.join(upload_dir, filename))
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    write_log(f"文档入库成功：{storage}，切片数量：{chunk_num}")
    return {"code": 200, "msg": "文档入库成功", "filename": filename, "chunk_num": chunk_num}


@router.get("/kb/list")
def kb_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    current: dict = Depends(require_auth),
):
    """分页返回知识库文件列表及每个文件的切片数，可按分组过滤。"""
    files = get_all_files(category=category, owner=_scope_owner(current))
    total = len(files)
    start = (page - 1) * page_size
    return {
        "file_list": files[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "category": category,
    }


@router.get("/kb/categories")
def kb_categories(current: dict = Depends(require_auth)):
    """汇总所有文档的分组及数量，供前端分组筛选。"""
    counts = {}
    for item in get_all_files(owner=_scope_owner(current)):
        name = item.get("category") or DEFAULT_CATEGORY
        counts[name] = counts.get(name, 0) + 1
    return {
        "categories": [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda x: x[0])
        ]
    }


@router.get("/kb/preview")
def kb_preview(
    filename: str = Query(..., min_length=1, max_length=255),
    current: dict = Depends(require_auth),
):
    """返回文档提取后的纯文本，供前端预览与溯源跳转。"""
    safe_name = _safe_filename(filename)
    info = _find_file(safe_name, _scope_owner(current))
    if not info:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = storage_to_abs(info["storage"])
    suffix = os.path.splitext(safe_name)[1].lower()
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    text = read_file(path, suffix)
    return {
        "filename": safe_name,
        "category": info.get("category") or DEFAULT_CATEGORY,
        "size": os.path.getsize(path),
        "chunk_num": info.get("chunk_num", 0),
        "text": text,
    }


def kb_test(
    question: str,
    top_k: int = 3,
    category: str | None = None,
    owner: str | None = None,
):
    """检索测试器：只召回不问答，展示命中片段、相似度、BM25 与精排分数。"""
    try:
        cfg = get_config()
        use_rerank = bool(cfg.get("rerank_enabled", False))
        rerank_top_k = cfg.get("rerank_top_k", top_k)
        hits = (
            hybrid_search_with_rerank(
                question, top_k, category, use_rerank, rerank_top_k, owner=owner
            )
            if owner
            else hybrid_search_with_rerank(question, top_k, category, use_rerank, rerank_top_k)
        )
        results = []
        for hit in hits:
            results.append(
                {
                    "text": hit["document"],
                    "filename": hit.get("filename") or "未知来源",
                    "chunk_index": hit.get("chunk_index") if hit.get("chunk_index") is not None else -1,
                    "category": hit.get("category") or DEFAULT_CATEGORY,
                    "similarity": hit.get("similarity"),
                    "bm25_score": hit.get("bm25_score"),
                    "rerank_score": hit.get("rerank_score"),
                }
            )
        return {"results": results}
    except Exception as exc:
        write_log(f"检索测试失败：{exc}")
        raise HTTPException(status_code=500, detail=f"检索失败：{exc}") from exc


@router.get("/kb/test")
def kb_test_route(
    question: str = Query(..., min_length=1, max_length=2000),
    top_k: int = Query(3, ge=1, le=10),
    category: str | None = Query(None),
    current: dict = Depends(require_auth),
):
    """带登录态的检索测试接口。"""
    return kb_test(question, top_k, category, owner=_scope_owner(current))


@router.delete("/kb/delete")
def kb_delete(
    filename: str = Query(..., min_length=1, max_length=255),
    current: dict = Depends(require_auth),
):
    """删除单个文件：普通用户只能删自己的，管理员可删全站。"""
    safe_name = _safe_filename(filename)
    info = _find_file(safe_name, _scope_owner(current))
    if not info:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = storage_to_abs(info["storage"])
    has_file = os.path.isfile(path)
    ok = delete_file_vectors(
        storage=info["storage"],
        filename=info["name"],
        owner=info.get("owner"),
    )
    if not ok and not has_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    if has_file:
        os.remove(path)
    remove_file_meta(info["storage"])
    delete_graph_cache(safe_name, owner=info.get("owner"))
    return {"msg": f"{safe_name} 删除完成"}


@router.delete("/kb/clear_all")
def kb_clear(current: dict = Depends(require_auth)):
    """清空知识库：普通用户清空自己的，管理员清空全站。"""
    is_admin = current.get("role") == "admin"
    owner = None if is_admin else current.get("username")
    files = get_all_files(owner=owner)
    for item in files:
        delete_file_vectors(
            storage=item["storage"],
            filename=item["name"],
            owner=item.get("owner"),
        )
        path = storage_to_abs(item["storage"])
        if os.path.isfile(path):
            os.remove(path)
        remove_file_meta(item["storage"])
        delete_graph_cache(item["name"], owner=item.get("owner"))
    clear_graph_cache(owner=None if is_admin else current.get("username"))
    if is_admin:
        clear_file_meta()
    else:
        clear_file_meta(owner=current.get("username"))
    return {"msg": "全部知识库已清空" if is_admin else "我的知识库已清空"}


@router.post("/kb/reindex")
def kb_reindex(current: dict = Depends(require_auth)):
    """按当前切片配置重建文档向量：普通用户重建自己的，管理员重建全站。"""
    files = get_all_files(owner=_scope_owner(current))
    if not files:
        return {"msg": "知识库为空", "files": 0, "chunks": 0, "failed": []}

    total_chunks = 0
    ok = 0
    failed = []
    for item in files:
        path = storage_to_abs(item["storage"])
        suffix = os.path.splitext(item["storage"])[1].lower()
        try:
            text = read_file(path, suffix)
            if not text.strip():
                failed.append(item["name"])
                write_log(f"重建索引跳过空文档：{item['storage']}")
                continue
            total_chunks += file_to_vector(
                item["name"],
                text,
                item.get("category") or DEFAULT_CATEGORY,
                owner=item.get("owner"),
                storage=item["storage"],
            )
            ok += 1
        except Exception as exc:
            failed.append(item["name"])
            write_log(f"重建索引失败 {item['storage']}：{exc}")
    write_log(f"重建索引完成：成功 {ok} 个文件，共 {total_chunks} 段")
    return {
        "msg": f"重建完成，成功 {ok} 个文件，共 {total_chunks} 段",
        "files": ok,
        "chunks": total_chunks,
        "failed": failed,
    }


@router.post("/upload_text")
def upload_text(payload: TextUpload, current: dict = Depends(require_auth)):
    """手动粘贴文本入库：自动补 .txt/.md 后缀后走同样的切分入库流程。"""
    doc_name = _safe_filename(payload.doc_name)
    category = (payload.category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY
    owner = current.get("username") or "guest"
    storage = user_upload_rel(owner, doc_name)
    upload_dir = user_upload_dir(owner)
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(doc_name)[1]
    if ext.lower() not in (".txt", ".md"):
        doc_name = doc_name + ".txt"
        storage = user_upload_rel(owner, doc_name)
    content = payload.text_content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="文本内容不能为空")

    tmp_path = os.path.join(upload_dir, f".{uuid.uuid4().hex}.part")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        chunk_num = file_to_vector(doc_name, content, category, owner=owner, storage=storage)
        set_file_meta(storage, category=category, owner=owner, display_name=doc_name)
        os.replace(tmp_path, os.path.join(upload_dir, doc_name))
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    write_log(f"文本文档入库，名称：{doc_name}，切片数量：{chunk_num}")
    return {"code": 200, "msg": "文本录入成功", "filename": doc_name, "chunk_num": chunk_num}
