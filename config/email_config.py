"""邮箱 SMTP 配置：默认读取环境变量，管理员可在系统设置中持久化覆盖。

密码以 Fernet 加密后写入 JSON，加载时自动解密；兼容旧版明文存储。
"""

import json
import os

from config.settings import (
    BASE_DIR,
    EMAIL_FROM,
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PASSWORD,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USER,
    EMAIL_USE_SSL,
)
from core.secret_box import decrypt_stored_secret, encrypt_secret

EMAIL_CONFIG_PATH = os.path.join(BASE_DIR, "config", "email_config.json")
_KEYS = ("host", "port", "user", "password", "from_address", "use_ssl")


def _env_defaults() -> dict:
    return {
        "host": EMAIL_SMTP_HOST,
        "port": EMAIL_SMTP_PORT,
        "user": EMAIL_SMTP_USER,
        "password": EMAIL_SMTP_PASSWORD,
        "from_address": EMAIL_FROM,
        "use_ssl": EMAIL_USE_SSL,
    }


def load_email_config() -> dict:
    cfg = _env_defaults()
    if os.path.exists(EMAIL_CONFIG_PATH):
        try:
            with open(EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key in _KEYS:
                if key in saved:
                    cfg[key] = saved[key]
            if "password" in saved:
                cfg["password"] = decrypt_stored_secret(saved["password"], "SMTP 密码")
        except (OSError, ValueError):
            pass
    return cfg


def save_email_config(cfg: dict) -> dict:
    data = {key: cfg.get(key, _env_defaults()[key]) for key in _KEYS}
    if data.get("password"):
        data["password"] = encrypt_secret(data["password"])
    os.makedirs(os.path.dirname(EMAIL_CONFIG_PATH), exist_ok=True)
    tmp = EMAIL_CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, EMAIL_CONFIG_PATH)
    return load_email_config()


def is_email_configured() -> bool:
    return bool(load_email_config().get("host"))
