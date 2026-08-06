from api.chat_router import (
    ChatRequest,
    _build_answer_prompt,
    _labeled_context,
    _resolve_mode,
    _retrieve,
    _sse,
)


def test_retrieve_threshold_keeps_bm25_hits(monkeypatch):
    hits = [
        {"filename": "a.txt", "chunk_index": 0, "document": "高相似", "similarity": 0.9, "bm25_score": None, "category": "x"},
        {"filename": "b.txt", "chunk_index": 1, "document": "低相似纯向量", "similarity": 0.5, "bm25_score": None, "category": "x"},
        {"filename": "c.txt", "chunk_index": 2, "document": "低相似但BM25命中", "similarity": 0.5, "bm25_score": 8.0, "category": "x"},
        {"filename": "d.txt", "chunk_index": 3, "document": "仅BM25", "similarity": None, "bm25_score": 9.0, "category": "x"},
    ]
    monkeypatch.setattr("api.chat_router.hybrid_search", lambda q, k, c=None: hits)
    monkeypatch.setattr("api.chat_router.get_config", lambda: {"similarity_threshold": 0.7})

    contexts, sources = _retrieve("问题", top_k=3)
    assert contexts == ["高相似", "低相似但BM25命中", "仅BM25"]
    assert [s["filename"] for s in sources] == ["a.txt", "c.txt", "d.txt"]


def test_labeled_context_numbering():
    source_info = [
        {"text": "d1", "filename": "a.txt", "chunk_index": 0, "category": "x", "similarity": 0.9, "bm25_score": None},
        {"text": "d2", "filename": "b.txt", "chunk_index": 1, "category": "x", "similarity": None, "bm25_score": 3.0},
    ]
    labeled = _labeled_context(["d1", "d2"], source_info)
    assert labeled == "[来源1：a.txt#0] d1\n[来源2：b.txt#1] d2"


def test_answer_prompt_contains_thinking_and_placeholders():
    template = "历史：{history}\n资料：{context}\n问题：{question}"
    prompt = _build_answer_prompt(
        q="价格多少？",
        valid_context=["资料A"],
        source_info=[{"text": "资料A", "filename": "a.txt", "chunk_index": 0, "category": "x", "similarity": 0.9, "bm25_score": None}],
        memory_context="历史",
        template=template,
        thinking="需要对比套餐",
    )
    assert "价格多少？" in prompt
    assert "需要对比套餐" in prompt
    assert "[来源1：a.txt#0]" in prompt


def test_sse_event_format():
    event = _sse({"type": "token", "content": "你好"})
    assert event == 'data: {"type": "token", "content": "你好"}\n\n'


def test_resolve_mode_chat_skips_rewrite(monkeypatch):
    monkeypatch.setattr("api.chat_router.load_chat_memory", lambda session_id: "历史对话")
    payload = ChatRequest(question="今天适合去哪里散步", mode="chat")
    general, retrieve_q, memory = _resolve_mode(payload, {})
    assert general is True
    assert retrieve_q == "今天适合去哪里散步"
    assert memory == "历史对话"
