"""运行配置模块：负责 RAG 参数默认值、校验、JSON 持久化与 Prompt 构建。"""

import json
import os
import threading

from config.settings import CONFIG_PATH


DEFAULT_CONFIG = {
    "prompt_template": (
        "你是智能问答助手。请先理解用户真实意图，再基于参考资料并结合你的知识给出准确、有条理的回答；"
        "禁止照抄原文，要用自己的话综合表达；引用资料观点时标注 [来源N]。"
        "若参考资料不足，请明确说明，并结合常识给出合理推断。\n"
        "历史对话：{history}\n"
        "参考资料：\n{context}\n"
        "问题：{question}\n"
    ),
    "chunk_size": 400,
    "chunk_overlap": 50,
    "top_k": 3,
    "similarity_threshold": 0.70,
    "temperature": 0.6,
    "thinking_enabled": True,
    "rewrite_enabled": True,
}

_lock = threading.Lock()


def _validate(cfg: dict) -> None:
    template = cfg.get("prompt_template", "")
    if not isinstance(template, str) or not template.strip():
        raise ValueError("提示词模板不能为空")
    missing = [p for p in ("{context}", "{question}") if p not in template]
    if missing:
        raise ValueError("提示词模板必须包含 {context} 和 {question}")

    chunk_size = cfg.get("chunk_size")
    chunk_overlap = cfg.get("chunk_overlap", 0)
    if not isinstance(chunk_size, int) or not (100 <= chunk_size <= 2000):
        raise ValueError("切片大小需在 100-2000 之间")
    if not isinstance(chunk_overlap, int) or not (0 <= chunk_overlap < chunk_size):
        raise ValueError("切片重叠需小于切片大小且不小于 0")
    if not isinstance(cfg.get("top_k"), int) or not (1 <= cfg["top_k"] <= 10):
        raise ValueError("召回数量需在 1-10 之间")
    if not isinstance(cfg.get("similarity_threshold"), (int, float)) or not (
        0 <= cfg["similarity_threshold"] <= 1
    ):
        raise ValueError("相似度阈值需在 0-1 之间")
    if not isinstance(cfg.get("temperature"), (int, float)) or not (0 <= cfg["temperature"] <= 1):
        raise ValueError("温度需在 0-1 之间")
    if not isinstance(cfg.get("thinking_enabled"), bool):
        raise ValueError("思考开关需为布尔值")
    if not isinstance(cfg.get("rewrite_enabled"), bool):
        raise ValueError("多轮改写开关需为布尔值")


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                cfg.update({k: v for k, v in saved.items() if k in DEFAULT_CONFIG})
        except (OSError, ValueError):
            pass
    return cfg


def get_config() -> dict:
    return load_config()


def save_config(cfg: dict) -> dict:
    normalized = {key: cfg[key] for key in DEFAULT_CONFIG if key in cfg}
    _validate(normalized)
    with _lock:
        tmp_path = CONFIG_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CONFIG_PATH)
    merged = dict(DEFAULT_CONFIG)
    merged.update(normalized)
    return merged


def build_prompt(template: str, history: str, context: str, question: str) -> str:
    return template.format(history=history, context=context, question=question)
