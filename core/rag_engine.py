"""向量检索引擎：负责文本切片、Embedding、Chroma 入库、召回、精排与向量清理。"""

import os
import re
import threading
import uuid
from collections import OrderedDict

import chromadb
import jieba
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

from config.rag_config import get_config
from config.settings import UPLOAD_PATH, VECTOR_PATH
from core.logger import write_log
from utils.file_meta import (
    DEFAULT_CATEGORY,
    LEGACY_OWNER,
    get_file_category,
    get_file_display_name,
    get_file_owner,
)
from utils.file_parser import read_file, split_text

COLLECTION_NAME = "knowledge_base"
SUPPORTED_SUFFIXES = {".pdf", ".txt", ".docx", ".doc", ".md", ".xlsx", ".xls", ".json"}
_ROOT_EXCLUDED_FILES = {"file_meta.json", "eval_set.json", "eval_report.json"}


def _metadata_where(category: str | None = None, owner: str | None = None) -> dict | None:
    """构造 Chroma where 条件，支持按分组和归属用户组合过滤。"""
    clauses = []
    if category:
        clauses.append({"category": category})
    if owner:
        clauses.append({"owner": owner})
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) > 1:
        return {"$and": clauses}
    return None

_embed_model = None
_embed_cache = OrderedDict()
_embed_cache_limit = 1024
_embed_lock = threading.Lock()

chroma_client = chromadb.PersistentClient(path=VECTOR_PATH)

_bm25_lock = threading.Lock()
_bm25_index = None
_bm25_texts = []
_bm25_metas = []


def get_embed_model():
    """懒加载本地嵌入模型，首次调用时加载 BAAI/bge-small-zh。"""
    global _embed_model
    if _embed_model is None:
        with _embed_lock:
            if _embed_model is None:
                write_log("加载嵌入模型 BAAI/bge-small-zh")
                _embed_model = SentenceTransformer("BAAI/bge-small-zh", local_files_only=True)
    return _embed_model


def _encode_texts(texts: list[str]) -> list[list[float]]:
    """带缓存的批量编码，重复文本不重复计算向量；缓存读写加锁保证线程安全。"""
    with _embed_lock:
        missing = [text for text in texts if text not in _embed_cache]
    if missing:
        vectors = get_embed_model().encode(missing).tolist()
        with _embed_lock:
            for text, vector in zip(missing, vectors):
                _embed_cache[text] = vector
                if len(_embed_cache) > _embed_cache_limit:
                    _embed_cache.popitem(last=False)
    with _embed_lock:
        return [_embed_cache[text] for text in texts]


def _invalidate_bm25():
    global _bm25_index, _bm25_texts, _bm25_metas
    _bm25_index = None
    _bm25_texts = []
    _bm25_metas = []


def _tokenize(text: str) -> list[str]:
    tokens = [token.strip().lower() for token in jieba.lcut_for_search(text) if token.strip()]
    # 补充英文/数字词元，统一小写，避免 SSE、RRF 等缩写因分词差异漏召回
    tokens.extend(re.findall(r"[a-z0-9]+", text.lower()))
    return tokens


def _iter_disk_files():
    """遍历上传区文件，返回 (存储相对路径, 绝对路径, 后缀)。"""
    if not os.path.isdir(UPLOAD_PATH):
        return
    for name in os.listdir(UPLOAD_PATH):
        if name in _ROOT_EXCLUDED_FILES:
            continue
        path = os.path.join(UPLOAD_PATH, name)
        suffix = os.path.splitext(name)[1].lower()
        if os.path.isfile(path) and suffix in SUPPORTED_SUFFIXES:
            yield name, path, suffix
    users_dir = os.path.join(UPLOAD_PATH, "users")
    if not os.path.isdir(users_dir):
        return
    for user_name in os.listdir(users_dir):
        user_path = os.path.join(users_dir, user_name)
        if not os.path.isdir(user_path):
            continue
        for name in os.listdir(user_path):
            path = os.path.join(user_path, name)
            suffix = os.path.splitext(name)[1].lower()
            if os.path.isfile(path) and suffix in SUPPORTED_SUFFIXES:
                yield f"users/{user_name}/{name}", path, suffix


def _ensure_cosine_collection():
    """确保集合使用余弦距离；若旧库不是 cosine 则重建。"""
    global collection
    existing = None
    for col in chroma_client.list_collections():
        if col.name == COLLECTION_NAME:
            existing = col
            break
    need_reindex = False
    if existing is not None and (existing.metadata or {}).get("hnsw:space") != "cosine":
        chroma_client.delete_collection(COLLECTION_NAME)
        existing = None
        need_reindex = True
    if existing is None:
        collection = chroma_client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    else:
        collection = existing
    _invalidate_bm25()
    if need_reindex:
        _reindex_uploaded_files(collection)
    _reconcile_stale_vectors(collection)
    return collection


def _reconcile_stale_vectors(col):
    """删除磁盘上已不存在文件对应的残留向量，避免文件系统与向量库漂移。"""
    disk_keys = {storage for storage, _path, _suffix in _iter_disk_files()}
    result = col.get(include=["metadatas"])
    stale_ids = []
    for doc_id, meta in zip(result["ids"], result["metadatas"]):
        key = meta.get("storage") or meta.get("filename") if meta else None
        if key is None or key not in disk_keys:
            stale_ids.append(doc_id)
    if stale_ids:
        col.delete(ids=stale_ids)
        write_log(f"清理失效文档向量：{len(stale_ids)} 条")
        _invalidate_bm25()


def _reindex_uploaded_files(col):
    """把磁盘上的文档全部重新切分并写入向量库。"""
    for storage, path, suffix in _iter_disk_files():
        try:
            text = read_file(path, suffix)
            if text:
                _add_text(
                    col,
                    get_file_display_name(storage),
                    text,
                    get_file_category(storage),
                    owner=get_file_owner(storage),
                    storage=storage,
                )
            else:
                write_log(f"重建索引跳过空文档：{storage}")
        except Exception as exc:
            write_log(f"重建索引失败 {storage}：{exc}")


def _add_text(
    col,
    filename: str,
    file_text: str,
    category: str = DEFAULT_CATEGORY,
    owner: str | None = None,
    storage: str | None = None,
) -> int:
    """核心入库逻辑：按配置切分 -> 生成向量 -> 写入 Chroma。"""
    cfg = get_config()
    chunks = split_text(file_text, cfg["chunk_size"], cfg["chunk_overlap"])
    if not chunks:
        return 0
    ids = [f"{uuid.uuid4().hex}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "filename": filename,
            "chunk_index": i,
            "category": category,
            "owner": owner or LEGACY_OWNER,
            "storage": storage or filename,
        }
        for i in range(len(chunks))
    ]
    embeddings = _encode_texts(chunks)
    col.add(documents=chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)
    _invalidate_bm25()
    write_log(f"{filename} 切片数量：{len(chunks)}")
    return len(chunks)


collection = _ensure_cosine_collection()


def file_to_vector(
    filename: str,
    file_text: str,
    category: str = DEFAULT_CATEGORY,
    owner: str | None = None,
    storage: str | None = None,
) -> int:
    """同一用户重新上传同名文件时先删除旧切片，再写入新切片。"""
    owner = owner or LEGACY_OWNER
    storage = storage or filename
    old_ids = collection.get(where={"storage": storage})["ids"]
    if not old_ids:
        # 兼容旧版没有 storage 字段的向量
        old_ids = collection.get(where={"filename": filename})["ids"]
    if old_ids:
        collection.delete(ids=old_ids)
        write_log(f"替换同名文件旧切片：{storage}，共 {len(old_ids)} 条")
        _invalidate_bm25()
    return _add_text(collection, filename, file_text, category, owner=owner, storage=storage)


def query_vector(
    question: str,
    top_k: int,
    category: str | None = None,
    owner: str | None = None,
):
    """纯向量查询：问题编码后召回最相似的 top_k 个片段。"""
    where = _metadata_where(category, owner)
    if where:
        total = len(collection.get(where=where)["ids"])
    else:
        total = collection.count()
    if total == 0:
        return {"documents": [[]], "distances": [[]], "ids": [[]], "metadatas": [[]]}
    query_vec = _encode_texts([question])[0]
    return collection.query(
        query_embeddings=[query_vec],
        n_results=min(top_k, total),
        include=["documents", "distances", "metadatas"],
        where=where,
    )


def _get_bm25():
    """按需构建 BM25 索引；文档增删后自动失效并重建。"""
    global _bm25_index, _bm25_texts, _bm25_metas
    if _bm25_index is None:
        with _bm25_lock:
            if _bm25_index is None:
                data = collection.get(include=["documents", "metadatas"])
                kept_texts = []
                kept_metas = []
                tokenized = []
                for text, meta in zip(data["documents"], data["metadatas"]):
                    tokens = _tokenize(text)
                    if tokens:
                        kept_texts.append(text)
                        kept_metas.append(meta or {})
                        tokenized.append(tokens)
                _bm25_texts = kept_texts
                _bm25_metas = kept_metas
                _bm25_index = BM25Okapi(tokenized) if tokenized else None
    return _bm25_index, _bm25_texts, _bm25_metas


def _bm25_search(
    question: str,
    top_k: int,
    category: str | None = None,
    owner: str | None = None,
):
    index, texts, metas = _get_bm25()
    if index is None:
        return []
    scores = index.get_scores(_tokenize(question))
    ranked = sorted(
        ((i, score) for i, score in enumerate(scores)),
        key=lambda item: item[1],
        reverse=True,
    )
    hits = []
    for i, score in ranked:
        meta = metas[i]
        if category and meta.get("category") != category:
            continue
        if owner and meta.get("owner") != owner:
            continue
        hits.append(
            {
                "filename": meta.get("filename"),
                "chunk_index": meta.get("chunk_index"),
                "storage": meta.get("storage"),
                "owner": meta.get("owner"),
                "score": round(float(score), 4),
                "document": texts[i],
            }
        )
        if len(hits) >= top_k:
            break
    return hits


def bm25_search(
    question: str,
    top_k: int,
    category: str | None = None,
    owner: str | None = None,
):
    """纯 BM25 快速召回，不依赖嵌入模型，用于自动模式的轻量预判。"""
    return _bm25_search(question, top_k, category, owner)


def hybrid_search(
    question: str,
    top_k: int,
    category: str | None = None,
    owner: str | None = None,
    vector_top_k: int | None = None,
    bm25_top_k: int | None = None,
):
    """向量 + BM25 混合召回，使用 RRF 融合排序。"""
    vector_top_k = vector_top_k or max(top_k * 2, top_k + 2)
    bm25_top_k = bm25_top_k or max(top_k * 2, top_k + 2)

    vec = query_vector(question, vector_top_k, category, owner)
    vector_keys = []
    candidates = {}
    for doc, dist, meta in zip(
        (vec.get("documents") or [[]])[0],
        (vec.get("distances") or [[]])[0],
        (vec.get("metadatas") or [[]])[0],
    ):
        meta = meta or {}
        key = (meta.get("storage") or meta.get("filename"), meta.get("chunk_index"))
        candidates[key] = {
            "document": doc,
            "filename": meta.get("filename"),
            "chunk_index": meta.get("chunk_index"),
            "storage": meta.get("storage"),
            "owner": meta.get("owner"),
            "category": meta.get("category"),
            "similarity": round(1 - dist, 4),
            "bm25_score": None,
        }
        vector_keys.append(key)

    bm25_keys = []
    for hit in _bm25_search(question, bm25_top_k, category, owner):
        key = (hit.get("storage") or hit["filename"], hit["chunk_index"])
        if key in candidates:
            candidates[key]["bm25_score"] = hit["score"]
        else:
            candidates[key] = {
                "document": hit["document"],
                "filename": hit["filename"],
                "chunk_index": hit["chunk_index"],
                "storage": hit.get("storage"),
                "owner": hit.get("owner"),
                "category": category,
                "similarity": None,
                "bm25_score": hit["score"],
            }
        bm25_keys.append(key)

    for rank, key in enumerate(vector_keys, 1):
        candidates[key]["vector_rank"] = rank
    for rank, key in enumerate(bm25_keys, 1):
        candidates[key]["bm25_rank"] = rank

    results = []
    for cand in candidates.values():
        rrf = 0.0
        if cand.get("vector_rank"):
            rrf += 1.0 / (60 + cand["vector_rank"])
        if cand.get("bm25_rank"):
            rrf += 1.0 / (60 + cand["bm25_rank"])
        cand["rrf_score"] = round(rrf, 6)
        cand["_both"] = bool(cand.get("vector_rank") and cand.get("bm25_rank"))
        cand["_bm25_rank"] = cand.get("bm25_rank") or 10**9
        results.append(cand)
    results.sort(
        key=lambda item: (
            -item["rrf_score"],
            -int(item["_both"]),
            item["_bm25_rank"],
            item.get("vector_rank") or 10**9,
        )
    )
    return _source_guaranteed(results, candidates, vector_keys, bm25_keys, top_k)


def _source_guaranteed(results, candidates, vector_keys, bm25_keys, top_k):
    """RRF 排序后保底：两路检索各自的第一名都进入最终结果，避免单路强命中被挤出。"""
    final = []
    for item in results:
        if item not in final:
            final.append(item)
        if len(final) == top_k:
            break
    top1_keys = []
    if vector_keys:
        top1_keys.append(vector_keys[0])
    if bm25_keys:
        top1_keys.append(bm25_keys[0])
    final_keys = {
        (item.get("storage") or item.get("filename"), item["chunk_index"])
        for item in final
    }
    for key in top1_keys:
        if key in final_keys:
            continue
        cand = candidates.get(key)
        if cand is None or cand in final:
            continue
        final.insert(1, cand)
        final_keys.add(key)
        if len(final) > top_k:
            removed = final.pop()
            final_keys.discard(
                (removed.get("storage") or removed.get("filename"), removed["chunk_index"])
            )
    return final


def delete_file_vectors(
    storage: str | None = None,
    filename: str | None = None,
    owner: str | None = None,
) -> bool:
    """删除指定文件向量；优先按唯一存储路径，兼容旧数据按文件名删除。"""
    if storage:
        where = {"storage": storage}
    elif filename:
        where = {"filename": filename}
    else:
        return False
    ids = collection.get(where=where)["ids"]
    if not ids and filename:
        # 兼容旧版没有 storage 字段的向量：仅在没有新向量命中时按文件名清理
        if owner:
            ids = collection.get(
                where={"$and": [{"filename": filename}, {"owner": owner}]}
            )["ids"]
        if not ids:
            ids = collection.get(where={"filename": filename})["ids"]
    if ids:
        collection.delete(ids=ids)
        _invalidate_bm25()
        return True
    return False


def clear_vectors(owner: str | None = None):
    """清空指定用户的向量；owner 为空时清空全部。"""
    where = {"owner": owner} if owner else None
    ids = collection.get(where=where)["ids"]
    if ids:
        collection.delete(ids=ids)
        _invalidate_bm25()


def clear_all_vector():
    clear_vectors()


def get_all_files(category: str | None = None, owner: str | None = None):
    """汇总磁盘文件信息与向量库切片数；owner 传入时只返回该用户的文件。"""
    files = []
    if not os.path.isdir(UPLOAD_PATH):
        return files
    counts = {}
    for meta in collection.get(include=["metadatas"])["metadatas"]:
        if meta:
            key = meta.get("storage") or meta.get("filename")
            counts[key] = counts.get(key, 0) + 1
    for storage, path, _suffix in _iter_disk_files():
        file_owner = get_file_owner(storage)
        if owner and file_owner != owner:
            continue
        file_category = get_file_category(storage)
        if category and file_category != category:
            continue
        stat = os.stat(path)
        files.append(
            {
                "name": get_file_display_name(storage),
                "storage": storage,
                "owner": file_owner,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "chunk_num": counts.get(storage, 0),
                "category": file_category,
            }
        )
    files.sort(key=lambda item: item["name"].lower())
    return files


RERANK_MODEL_NAME = "BAAI/bge-reranker-v2-m3"

_rerank_model = None


def get_rerank_model():
    """懒加载精排模型（CrossEncoder），失败时返回 None 由上层降级。"""
    global _rerank_model
    if _rerank_model is None:
        try:
            write_log(f"加载精排模型 {RERANK_MODEL_NAME}")
            _rerank_model = CrossEncoder(RERANK_MODEL_NAME, local_files_only=True)
        except Exception as exc:
            write_log(f"精排模型加载失败，精排功能降级：{exc}")
            _rerank_model = None
    return _rerank_model


def rerank_results(question: str, results: list, top_k: int) -> list:
    """二阶段精排：CrossEncoder 对候选（问题, 文档）对打分，按分数降序取 top_k。

    精排失败（模型缺失/推理异常）时回退到原始顺序，保证链路不中断。
    """
    if not results or top_k <= 0:
        return results
    model = get_rerank_model()
    if model is None:
        return results[:top_k]
    try:
        pairs = [[question, r.get("document", "")] for r in results]
        scores = model.predict(pairs)
        for result, score in zip(results, scores):
            result["rerank_score"] = round(float(score), 4)
        reranked = sorted(results, key=lambda r: r.get("rerank_score", 0.0), reverse=True)
        return reranked[:top_k]
    except Exception as exc:
        write_log(f"精排推理失败，回退混合检索结果：{exc}")
        return results[:top_k]


def hybrid_search_with_rerank(
    question: str,
    top_k: int,
    category: str | None = None,
    rerank: bool = False,
    rerank_top_k: int | None = None,
    owner: str | None = None,
) -> list:
    """混合召回 + 可选精排：开启时先扩大召回候选，精排后截断到 top_k。"""
    if not rerank:
        return hybrid_search(question, top_k, category, owner)
    candidate_k = max(top_k * 3, top_k + 2)
    candidates = hybrid_search(question, candidate_k, category, owner)
    return rerank_results(question, candidates, rerank_top_k or top_k)
