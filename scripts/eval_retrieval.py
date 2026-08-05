"""检索效果评测：比较纯向量、纯 BM25 与混合检索三路基线，输出 Recall@K / Precision@K / MRR。"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.rag_engine import _bm25_search, hybrid_search, query_vector
from utils.eval_metrics import compute_metrics, hit_pairs


def load_eval(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _vector_hits(question: str, top_k: int) -> list[dict]:
    result = query_vector(question, top_k)
    hits = []
    for doc, dist, meta in zip(
        (result.get("documents") or [[]])[0],
        (result.get("distances") or [[]])[0],
        (result.get("metadatas") or [[]])[0],
    ):
        meta = meta or {}
        hits.append(
            {
                "filename": meta.get("filename"),
                "chunk_index": meta.get("chunk_index"),
                "document": doc,
            }
        )
    return hits


RETRIEVERS = {
    "hybrid": lambda q, k: hybrid_search(q, k),
    "vector": lambda q, k: _vector_hits(q, k),
    "bm25": lambda q, k: _bm25_search(q, k),
}


def run_eval(path: str, top_k: int, mode: str | None = None, report_path: str | None = None):
    cases = load_eval(path)
    modes = [mode] if mode else list(RETRIEVERS)
    summaries = {m: {"recall@k": [], "precision@k": [], "mrr": []} for m in modes}
    rows = []

    for case in cases:
        row = {"question": case["question"], "expected": case["expected"]}
        for m in modes:
            hits = RETRIEVERS[m](case["question"], top_k)
            metrics = compute_metrics(hits, case["expected"], top_k)
            row[m] = {"hits": hit_pairs(hits)[:top_k], **metrics}
            for key in ("recall@k", "precision@k", "mrr"):
                summaries[m][key].append(metrics[key])
        rows.append(row)

    print(f"评测集：{len(cases)} 条，Top-{top_k}\n")
    for row in rows:
        parts = [f"[{row['question']}]"]
        for m in modes:
            metric = row[m]
            parts.append(f"{m}: R@{top_k}={metric['recall@k']} MRR={metric['mrr']}")
        print("  ".join(parts))

    print("\n汇总：")
    for m in modes:
        vals = summaries[m]
        print(
            f"  {m:<6} Recall@{top_k}={sum(vals['recall@k']) / max(len(vals['recall@k']), 1):.4f}  "
            f"Precision@{top_k}={sum(vals['precision@k']) / max(len(vals['precision@k']), 1):.4f}  "
            f"MRR={sum(vals['mrr']) / max(len(vals['mrr']), 1):.4f}"
        )

    if report_path:
        report = {
            "top_k": top_k,
            "cases": len(cases),
            "summary": {
                m: {k: round(sum(v) / max(len(v), 1), 4) for k, v in vals.items()}
                for m, vals in summaries.items()
            },
            "rows": rows,
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已写入：{report_path}")


def main():
    parser = argparse.ArgumentParser(description="RAG 检索效果评测（三路基线对比）")
    parser.add_argument("--eval", default="data/eval_set.json")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--mode", choices=list(RETRIEVERS), default=None)
    parser.add_argument("--report", default="data/eval_report.json")
    args = parser.parse_args()
    run_eval(args.eval, args.top_k, args.mode, args.report)


if __name__ == "__main__":
    main()
