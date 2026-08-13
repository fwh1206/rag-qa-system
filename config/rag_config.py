"""运行配置模块：负责 RAG 参数默认值、校验、JSON 持久化与 Prompt 构建。"""

import json
import os
import threading

from config.settings import CONFIG_PATH

DEFAULT_CONFIG = {
    "prompt_template": (
        "你在和一个熟悉业务的朋友聊天。根据下方参考资料回答他的问题，语气自然、直接，像正常说话，"
        "不要用'根据资料显示''综上所述'这类书面腔，也不要给回答强行编号。"
        "资料里有的就肯定地说，可以说'文档里提到……'；资料没有的，直接说不知道或查不到，别硬编。"
        "如果资料之间有出入，点出来。回答控制在能讲清楚问题就好，别啰嗦。\n"
        "历史对话：{history}\n"
        "参考资料：\n{context}\n"
        "问题：{question}\n"
    ),
    "chunk_size": 400,
    "chunk_overlap": 50,
    "top_k": 5,
    "similarity_threshold": 0.70,
    "temperature": 0.6,
    "thinking_enabled": True,
    "rewrite_enabled": False,
    "rerank_enabled": True,
    "rerank_top_k": 3,
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
    if not isinstance(cfg.get("rerank_enabled"), bool):
        raise ValueError("精排开关需为布尔值")
    if not isinstance(cfg.get("rerank_top_k"), int) or not (1 <= cfg["rerank_top_k"] <= 10):
        raise ValueError("精排数量需在 1-10 之间")


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
