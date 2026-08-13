"""用户 API Key 本地加密存储：密钥文件仅保存在本机 config 目录。"""

import os

from cryptography.fernet import Fernet, InvalidToken

from config.settings import LLM_SECRET_KEY_PATH


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
