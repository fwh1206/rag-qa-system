"""文档元数据：按存储相对路径保存分组、归属用户与显示文件名。"""

import json
import os
import re
import threading

from config.settings import UPLOAD_PATH

DEFAULT_CATEGORY = "默认分组"
LEGACY_OWNER = "admin"
META_PATH = os.path.join(UPLOAD_PATH, "file_meta.json")
USERS_DIR = os.path.join(UPLOAD_PATH, "users")
_lock = threading.Lock()
_SAFE_USER = re.compile(r"[^A-Za-z0-9_.\u4e00-\u9fff-]+")


def _safe_user_dir(username: str) -> str:
    """把用户名转成安全的目录名，避免路径穿越。"""
    safe = _SAFE_USER.sub("_", str(username or "guest")).strip("._-")
    return safe or "guest"


def user_upload_dir(username: str) -> str:
    """返回某用户自己的上传目录，例如 data/users/alice。"""
    return os.path.join(USERS_DIR, _safe_user_dir(username))


def user_upload_rel(username: str, filename: str) -> str:
    """返回用户上传文件在 data 下的存储相对路径，例如 users/alice/a.pdf。"""
    name = os.path.basename((filename or "").strip())
    return f"users/{_safe_user_dir(username)}/{name}"


def storage_to_abs(storage: str) -> str:
    """把存储相对路径还原为磁盘绝对路径，只允许 data 根文件或 users 子目录。"""
    parts = [p for p in (storage or "").replace("\\", "/").split("/") if p and p not in (".", "..")]
    if not parts:
        raise ValueError("无效的存储路径")
    if parts[0] == "users":
        return os.path.join(UPLOAD_PATH, *parts)
    if len(parts) != 1:
        raise ValueError("无效的存储路径")
    return os.path.join(UPLOAD_PATH, parts[0])


def load_file_meta() -> dict:
    """读取元数据文件，缺失或解析失败时返回空字典。"""
    if not os.path.exists(META_PATH):
        return {}
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_file_meta(meta: dict):
    """先写临时文件再原子替换，避免并发或中断写坏元数据文件。"""
    with _lock:
        tmp = META_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp, META_PATH)


def _normalize_storage(storage: str) -> str:
    return (storage or "").replace("\\", "/")


def get_file_meta(storage: str) -> dict:
    key = _normalize_storage(storage)
    return load_file_meta().get(key) or {}


def get_file_category(storage: str) -> str:
    return get_file_meta(storage).get("category") or DEFAULT_CATEGORY


def get_file_owner(storage: str) -> str:
    """未记录归属的旧文件默认视为管理员上传。"""
    info = get_file_meta(storage)
    return info.get("owner") or LEGACY_OWNER


def get_file_display_name(storage: str) -> str:
    info = get_file_meta(storage)
    if info.get("display_name"):
        return info["display_name"]
    return os.path.basename(_normalize_storage(storage).rstrip("/"))


def set_file_meta(
    storage: str,
    category: str | None = None,
    owner: str | None = None,
    display_name: str | None = None,
):
    key = _normalize_storage(storage)
    meta = load_file_meta()
    old = meta.get(key) or {}
    if category is not None:
        old["category"] = (category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY
    if owner is not None:
        old["owner"] = owner
    if display_name is not None:
        old["display_name"] = display_name
    meta[key] = old
    save_file_meta(meta)


def set_file_category(storage: str, category: str):
    set_file_meta(storage, category=category)


def remove_file_meta(storage: str):
    key = _normalize_storage(storage)
    meta = load_file_meta()
    if key in meta:
        meta.pop(key, None)
        save_file_meta(meta)


def clear_file_meta(owner: str | None = None):
    """清空全部元数据；传入 owner 时只清空该用户的元数据。"""
    if owner is None:
        save_file_meta({})
        return
    meta = load_file_meta()
    kept = {key: info for key, info in meta.items() if (info or {}).get("owner") != owner}
    save_file_meta(kept)
