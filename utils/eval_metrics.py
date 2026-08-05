"""检索评测指标：Recall@K、Precision@K 与 MRR 的纯函数实现。"""


def hit_pairs(hits: list[dict]) -> list[tuple]:
    return [(h.get("filename"), h.get("chunk_index")) for h in hits]


def compute_metrics(actual: list[dict], expected: list[dict], top_k: int) -> dict:
    """基于召回片段与标注片段计算指标，actual 保持检索返回顺序。"""
    actual = hit_pairs(actual)[:top_k]
    expected_set = set(hit_pairs(expected))
    hit_count = sum(1 for item in actual if item in expected_set)
    recall = hit_count / max(len(expected_set), 1)
    precision = hit_count / max(len(actual), 1)
    mrr = 0.0
    for rank, item in enumerate(actual, 1):
        if item in expected_set:
            mrr = 1.0 / rank
            break
    return {
        "recall@k": round(recall, 4),
        "precision@k": round(precision, 4),
        "mrr": round(mrr, 4),
    }
