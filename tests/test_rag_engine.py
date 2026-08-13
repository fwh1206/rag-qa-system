from unittest.mock import patch

from rank_bm25 import BM25Okapi

import core.rag_engine as rag


def test_tokenize_keeps_non_empty_tokens():
    tokens = rag._tokenize("RAG 智能问答系统支持 PDF 上传")
    assert tokens
    assert all(token.strip() for token in tokens)


def test_iter_disk_files_excludes_metadata_json(monkeypatch, tmp_path):
    monkeypatch.setattr(rag, "UPLOAD_PATH", str(tmp_path))
    (tmp_path / "file_meta.json").write_text("{}", encoding="utf-8")
    (tmp_path / "eval_set.json").write_text("[]", encoding="utf-8")
    (tmp_path / "eval_report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "real_doc.json").write_text("{}", encoding="utf-8")

    keys = [storage for storage, _path, _suffix in rag._iter_disk_files()]
    assert "file_meta.json" not in keys
    assert "eval_set.json" not in keys
    assert "eval_report.json" not in keys
    assert "real_doc.json" in keys


def test_bm25_search_category_filter(monkeypatch):
    index = BM25Okapi([["苹果", "价格"], ["香蕉", "产地"]])
    texts = ["苹果价格", "香蕉产地"]
    metas = [
        {"filename": "a.txt", "chunk_index": 0, "category": "产品"},
        {"filename": "b.txt", "chunk_index": 1, "category": "水果"},
    ]
    monkeypatch.setattr(rag, "_get_bm25", lambda: (index, texts, metas))

    hits = rag._bm25_search("苹果价格", top_k=5, category="产品")
    assert [h["filename"] for h in hits] == ["a.txt"]


def test_hybrid_search_rrf_fusion_and_dedupe():
    vector_result = {
        "documents": [["向量A", "向量B"]],
        "distances": [[0.1, 0.2]],
        "metadatas": [
            [
                {"filename": "a.txt", "chunk_index": 0, "category": "x"},
                {"filename": "b.txt", "chunk_index": 0, "category": "x"},
            ]
        ],
    }
    bm25_hits = [
        {"filename": "b.txt", "chunk_index": 0, "score": 10.0, "document": "关键词B"},
        {"filename": "c.txt", "chunk_index": 1, "score": 8.0, "document": "仅BM25C"},
        {"filename": "a.txt", "chunk_index": 0, "score": 5.0, "document": "关键词A"},
    ]

    with (
        patch.object(rag, "query_vector", return_value=vector_result),
        patch.object(rag, "_bm25_search", return_value=bm25_hits),
    ):
        results = rag.hybrid_search("问题", top_k=3)

    assert [r["filename"] for r in results] == ["b.txt", "a.txt", "c.txt"]
    merged_b = next(r for r in results if r["filename"] == "b.txt")
    assert merged_b["similarity"] == 0.8
    assert merged_b["bm25_score"] == 10.0
    assert merged_b["rrf_score"] == round(1 / 61 + 1 / 62, 6)
    assert len(results) == 3


def test_hybrid_search_keeps_each_source_top1():
    vector_result = {
        "documents": [["向量A", "向量B"]],
        "distances": [[0.1, 0.2]],
        "metadatas": [
            [
                {"filename": "a.txt", "chunk_index": 0, "category": "x"},
                {"filename": "b.txt", "chunk_index": 0, "category": "x"},
            ]
        ],
    }
    bm25_hits = [
        {"filename": "c.txt", "chunk_index": 2, "score": 20.0, "document": "BM25独家命中"},
        {"filename": "b.txt", "chunk_index": 0, "score": 5.0, "document": "关键词B"},
        {"filename": "a.txt", "chunk_index": 0, "score": 4.0, "document": "关键词A"},
    ]
    with (
        patch.object(rag, "query_vector", return_value=vector_result),
        patch.object(rag, "_bm25_search", return_value=bm25_hits),
    ):
        results = rag.hybrid_search("问题", top_k=2)

    filenames = [r["filename"] for r in results]
    assert "a.txt" in filenames
    assert "c.txt" in filenames
