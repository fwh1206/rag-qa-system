"""大模型服务配置：支持任意 OpenAI 兼容接口，默认读取环境变量，管理员可界面持久化。

API Key 以 Fernet 加密后写入 JSON，加载时自动解密；兼容旧版明文存储。
"""

import json
import os

from config.settings import BASE_DIR, DEEPSEEK_KEY, LLM_MODEL, LLM_URL
from core.secret_box import decrypt_stored_secret, encrypt_secret

LLM_CONFIG_PATH = os.path.join(BASE_DIR, "config", "llm_config.json")
_KEYS = ("api_key", "url", "model")


def _env_defaults() -> dict:
    return {
        "api_key": DEEPSEEK_KEY,
        "url": LLM_URL,
        "model": LLM_MODEL,
    }


def load_llm_config() -> dict:
    cfg = _env_defaults()
    if os.path.exists(LLM_CONFIG_PATH):
        try:
            with open(LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key in _KEYS:
                if key in saved:
                    cfg[key] = saved[key]
            if "api_key" in saved:
                cfg["api_key"] = decrypt_stored_secret(saved["api_key"], "系统大模型 Key")
        except (OSError, ValueError):
            pass
    return cfg


def save_llm_config(cfg: dict) -> dict:
    data = {key: cfg.get(key, _env_defaults()[key]) for key in _KEYS}
    if data.get("api_key"):
        data["api_key"] = encrypt_secret(data["api_key"])
    os.makedirs(os.path.dirname(LLM_CONFIG_PATH), exist_ok=True)
    tmp = LLM_CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LLM_CONFIG_PATH)
    return load_llm_config()
