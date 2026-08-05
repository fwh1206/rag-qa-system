from utils.eval_metrics import compute_metrics, hit_pairs


def test_hit_pairs_normalizes_hits():
    hits = [{"filename": "a.txt", "chunk_index": 0}, {"filename": "b.txt", "chunk_index": 1}]
    assert hit_pairs(hits) == [("a.txt", 0), ("b.txt", 1)]


def test_compute_metrics_recall_precision_mrr():
    actual = [
        {"filename": "a.txt", "chunk_index": 0},
        {"filename": "b.txt", "chunk_index": 2},
        {"filename": "c.txt", "chunk_index": 3},
    ]
    expected = [
        {"filename": "b.txt", "chunk_index": 2},
        {"filename": "d.txt", "chunk_index": 5},
    ]
    metrics = compute_metrics(actual, expected, top_k=3)
    assert metrics["recall@k"] == 0.5
    assert metrics["precision@k"] == 0.3333
    assert metrics["mrr"] == 0.5


def test_compute_metrics_respects_top_k():
    actual = [
        {"filename": "a.txt", "chunk_index": 0},
        {"filename": "b.txt", "chunk_index": 1},
    ]
    expected = [{"filename": "b.txt", "chunk_index": 1}]
    metrics = compute_metrics(actual, expected, top_k=1)
    assert metrics["recall@k"] == 0.0
    assert metrics["mrr"] == 0.0
