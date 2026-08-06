"""向量检索引擎：负责文本切片、Embedding、Chroma 入库、召回与向量清理。"""

import os
import re
import threading
import uuid
from collections import OrderedDict

import chromadb
import jieba
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from config.rag_config import get_config
from config.settings import UPLOAD_PATH, VECTOR_PATH
from core.logger import write_log
from utils.file_meta import DEFAULT_CATEGORY, get_file_category
from utils.file_parser import read_file, split_text


COLLECTION_NAME = "knowledge_base"
SUPPORTED_SUFFIXES = {".pdf", ".txt", ".docx", ".md", ".xlsx", ".xls"}

_embed_model = None
_embed_cache = OrderedDict()
_embed_cache_limit = 1024

chroma_client = chromadb.PersistentClient(path=VECTOR_PATH)

_bm25_lock = threading.Lock()
_bm25_index = None
_bm25_texts = []
_bm25_metas = []


def get_embed_model():
    """懒加载本地嵌入模型，首次调用时加载 BAAI/bge-small-zh。"""
    global _embed_model
    if _embed_model is None:
        write_log("加载嵌入模型 BAAI/bge-small-zh")
        _embed_model = SentenceTransformer("BAAI/bge-small-zh", local_files_only=True)
    return _embed_model


def _encode_texts(texts: list[str]) -> list[list[float]]:
    """带缓存的批量编码，重复文本不重复计算向量。"""
    missing = [text for text in texts if text not in _embed_cache]
    if missing:
        vectors = get_embed_model().encode(missing).tolist()
        for text, vector in zip(missing, vectors):
            _embed_cache[text] = vector
            if len(_embed_cache) > _embed_cache_limit:
                _embed_cache.popitem(last=False)
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
    if not os.path.isdir(UPLOAD_PATH):
        return
    disk_names = set()
    for name in os.listdir(UPLOAD_PATH):
        path = os.path.join(UPLOAD_PATH, name)
        suffix = os.path.splitext(name)[1].lower()
        if os.path.isfile(path) and suffix in SUPPORTED_SUFFIXES:
            disk_names.add(name)
    result = col.get(include=["metadatas"])
    stale_ids = []
    for doc_id, meta in zip(result["ids"], result["metadatas"]):
        if meta and meta.get("filename") not in disk_names:
            stale_ids.append(doc_id)
    if stale_ids:
        col.delete(ids=stale_ids)
        write_log(f"清理失效文档向量：{len(stale_ids)} 条")
        _invalidate_bm25()


def _reindex_uploaded_files(col):
    """把磁盘上的文档全部重新切分并写入向量库。"""
    if not os.path.isdir(UPLOAD_PATH):
        return
    for name in os.listdir(UPLOAD_PATH):
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in SUPPORTED_SUFFIXES:
            continue
        path = os.path.join(UPLOAD_PATH, name)
        try:
            text = read_file(path, suffix)
            if text:
                _add_text(col, name, text, get_file_category(name))
            else:
                write_log(f"重建索引跳过空文档：{name}")
        except Exception as exc:
            write_log(f"重建索引失败 {name}：{exc}")


def _add_text(col, filename: str, file_text: str, category: str = DEFAULT_CATEGORY) -> int:
    """核心入库逻辑：按配置切分 -> 生成向量 -> 写入 Chroma。"""
    cfg = get_config()
    chunks = split_text(file_text, cfg["chunk_size"], cfg["chunk_overlap"])
    if not chunks:
        return 0
    ids = [f"{uuid.uuid4().hex}_{i}" for i in range(len(chunks))]
    metadatas = [
        {"filename": filename, "chunk_index": i, "category": category}
        for i in range(len(chunks))
    ]
    embeddings = _encode_texts(chunks)
    col.add(documents=chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)
    _invalidate_bm25()
    write_log(f"{filename} 切片数量：{len(chunks)}")
    return len(chunks)


collection = _ensure_cosine_collection()


def file_to_vector(filename: str, file_text: str, category: str = DEFAULT_CATEGORY) -> int:
    """同名文件重新上传时先删除旧切片，再写入新切片。"""
    old_ids = collection.get(where={"filename": filename})["ids"]
    if old_ids:
        collection.delete(ids=old_ids)
        write_log(f"替换同名文件旧切片：{filename}，共 {len(old_ids)} 条")
        _invalidate_bm25()
    return _add_text(collection, filename, file_text, category)


def query_vector(question: str, top_k: int, category: str | None = None):
    """纯向量查询：问题编码后召回最相似的 top_k 个片段。"""
    where = {"category": category} if category else None
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


def _bm25_search(question: str, top_k: int, category: str | None = None):
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
        hits.append(
            {
                "filename": meta.get("filename"),
                "chunk_index": meta.get("chunk_index"),
                "score": round(float(score), 4),
                "document": texts[i],
            }
        )
        if len(hits) >= top_k:
            break
    return hits


def bm25_search(question: str, top_k: int, category: str | None = None):
    """纯 BM25 快速召回，不依赖嵌入模型，用于自动模式的轻量预判。"""
    return _bm25_search(question, top_k, category)


def hybrid_search(
    question: str,
    top_k: int,
    category: str | None = None,
    vector_top_k: int | None = None,
    bm25_top_k: int | None = None,
):
    """向量 + BM25 混合召回，使用 RRF 融合排序。"""
    vector_top_k = vector_top_k or max(top_k * 2, top_k + 2)
    bm25_top_k = bm25_top_k or max(top_k * 2, top_k + 2)

    vec = query_vector(question, vector_top_k, category)
    vector_keys = []
    candidates = {}
    for doc, dist, meta in zip(
        (vec.get("documents") or [[]])[0],
        (vec.get("distances") or [[]])[0],
        (vec.get("metadatas") or [[]])[0],
    ):
        meta = meta or {}
        key = (meta.get("filename"), meta.get("chunk_index"))
        candidates[key] = {
            "document": doc,
            "filename": meta.get("filename"),
            "chunk_index": meta.get("chunk_index"),
            "category": meta.get("category"),
            "similarity": round(1 - dist, 4),
            "bm25_score": None,
        }
        vector_keys.append(key)

    bm25_keys = []
    for hit in _bm25_search(question, bm25_top_k, category):
        key = (hit["filename"], hit["chunk_index"])
        if key in candidates:
            candidates[key]["bm25_score"] = hit["score"]
        else:
            candidates[key] = {
                "document": hit["document"],
                "filename": hit["filename"],
                "chunk_index": hit["chunk_index"],
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
    final_keys = {(item["filename"], item["chunk_index"]) for item in final}
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
            final_keys.discard((removed["filename"], removed["chunk_index"]))
    return final


def delete_file_vectors(filename: str) -> bool:
    ids = collection.get(where={"filename": filename})["ids"]
    if ids:
        collection.delete(ids=ids)
        _invalidate_bm25()
        return True
    return False


def clear_all_vector():
    ids = collection.get()["ids"]
    if ids:
        collection.delete(ids=ids)
        _invalidate_bm25()


def get_all_files(category: str | None = None):
    """汇总磁盘文件信息与向量库切片数，供前端展示文档列表。"""
    files = []
    if not os.path.isdir(UPLOAD_PATH):
        return files
    counts = {}
    for meta in collection.get(include=["metadatas"])["metadatas"]:
        if meta:
            name = meta.get("filename")
            counts[name] = counts.get(name, 0) + 1
    for name in os.listdir(UPLOAD_PATH):
        path = os.path.join(UPLOAD_PATH, name)
        suffix = os.path.splitext(name)[1].lower()
        if not os.path.isfile(path) or suffix not in SUPPORTED_SUFFIXES:
            continue
        file_category = get_file_category(name)
        if category and file_category != category:
            continue
        stat = os.stat(path)
        files.append(
            {
                "name": name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "chunk_num": counts.get(name, 0),
                "category": file_category,
            }
        )
    files.sort(key=lambda item: item["name"].lower())
    return files
