"""用户 API Key 本地加密存储：密钥文件仅保存在本机 config 目录。"""

import os

from cryptography.fernet import Fernet, InvalidToken

from config.settings import LLM_SECRET_KEY_PATH
from core.logger import write_log


def _get_key() -> bytes:
    if os.path.exists(LLM_SECRET_KEY_PATH):
        with open(LLM_SECRET_KEY_PATH, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(LLM_SECRET_KEY_PATH), exist_ok=True)
    with open(LLM_SECRET_KEY_PATH, "wb") as f:
        f.write(key)
    return key


def encrypt_secret(plain: str) -> str:
    return Fernet(_get_key()).encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    try:
        return Fernet(_get_key()).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("用户模型密钥无法解密，请重新保存 API Key") from exc


_warned_labels: set[str] = set()


def decrypt_stored_secret(token: str, label: str = "密钥") -> str:
    """解密持久化配置中的密钥，兼容旧版明文存储。

    - 旧版明文（非 Fernet 密文）：解密失败时按原值回退，仅提示一次；
    - Fernet 密文但解密失败（密钥文件丢失/更换）：返回空串并告警，避免把密文当 Key 使用。
    """
    if not token:
        return ""
    try:
        return decrypt_secret(token)
    except Exception as exc:
        if token.startswith("gAAAAA"):
            if label not in _warned_labels:
                _warned_labels.add(label)
                write_log(f"{label}解密失败（密钥文件可能丢失或更换），请重新保存：{exc}")
            return ""
        if label not in _warned_labels:
            _warned_labels.add(label)
            write_log(f"{label}为旧版明文存储，将在下次保存时自动加密")
        return token
