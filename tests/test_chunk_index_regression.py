"""回归测试：chunk_index=0 的片段不得被 or -1 误判（falsy 陷阱）。"""
from unittest.mock import patch

from api import chat_router
from api.file_router import kb_test


def _fake_hybrid_search(question, top_k, category=None, rerank=False, rerank_top_k=None):
    return [
        {
            "document": "首个片段文本",
            "filename": "a.txt",
            "chunk_index": 0,
            "category": "默认分组",
            "similarity": 0.9,
            "bm25_score": 5.0,
        },
        {
            "document": "第二个片段文本",
            "filename": "b.txt",
            "chunk_index": 1,
            "category": "默认分组",
            "similarity": 0.8,
            "bm25_score": None,
        },
    ]


def test_retrieve_preserves_zero_chunk_index():
    """chunk_index=0 时来源信息必须显示 0，而不是被 or -1 替换为 -1。"""
    cfg = {"similarity_threshold": 0.7, "rerank_top_k": 3}
    with patch("api.chat_router.get_config", return_value=cfg), patch(
        "api.chat_router.hybrid_search_with_rerank", side_effect=_fake_hybrid_search
    ):
        _, source_info = chat_router._retrieve("问题", top_k=3)
    chunk_indices = [info["chunk_index"] for info in source_info]
    assert chunk_indices == [0, 1], f"chunk_index 被误替换: {chunk_indices}"


def test_kb_test_preserves_zero_chunk_index():
    """kb_test 接口返回的 chunk_index=0 不得被替换为 -1。"""
    with patch("api.file_router.hybrid_search_with_rerank", side_effect=_fake_hybrid_search):
        result = kb_test("问题", top_k=3)
    chunk_indices = [item["chunk_index"] for item in result["results"]]
    assert chunk_indices == [0, 1], f"kb_test chunk_index 被误替换: {chunk_indices}"
