"""文档元数据：保存文件分组信息，保证重建索引后仍能恢复分类。"""  # 模块文档：说明本文件负责文件分组元数据的读写

import json  # 导入 JSON 模块，用于序列化和反序列化元数据
import os  # 导入操作系统模块，用于判断元数据文件是否存在
import threading  # 导入线程模块，用于给元数据写入加锁

from config.settings import UPLOAD_PATH  # 导入上传目录路径


DEFAULT_CATEGORY = "默认分组"  # 默认分组名称
META_PATH = os.path.join(UPLOAD_PATH, "file_meta.json")  # 元数据文件的保存路径
_lock = threading.Lock()  # 创建全局线程锁，避免并发写入冲突


def load_file_meta() -> dict:  # 定义读取元数据文件的函数，返回字典
    if not os.path.exists(META_PATH):  # 如果元数据文件不存在
        return {}  # 返回空字典
    try:  # 尝试读取文件
        with open(META_PATH, "r", encoding="utf-8") as f:  # 以 UTF-8 编码打开元数据文件
            data = json.load(f)  # 解析 JSON 内容
        return data if isinstance(data, dict) else {}  # 是字典则返回，否则返回空字典
    except (OSError, ValueError):  # 捕获文件读取或 JSON 解析异常
        return {}  # 异常时返回空字典，保证程序不崩溃


def save_file_meta(meta: dict):  # 定义保存元数据文件的函数，meta 为要写入的字典
    with _lock:  # 获取线程锁，保证同一时刻只有一个线程写入
        tmp = META_PATH + ".tmp"  # 先写临时文件，避免写坏原文件
        with open(tmp, "w", encoding="utf-8") as f:  # 以 UTF-8 编码打开临时文件
            json.dump(meta, f, ensure_ascii=False, indent=2)  # 把字典写入 JSON，保留中文并格式化
        os.replace(tmp, META_PATH)  # 用临时文件原子替换正式元数据文件


def get_file_category(filename: str) -> str:  # 定义查询文件分组名的函数
    info = load_file_meta().get(filename) or {}  # 读取元数据并取该文件的记录，没有则用空字典
    return info.get("category") or DEFAULT_CATEGORY  # 返回分组名，缺失时返回默认分组


def set_file_category(filename: str, category: str):  # 定义设置文件分组的函数
    meta = load_file_meta()  # 读取当前全部元数据
    old = meta.get(filename) or {}  # 获取该文件的旧记录，没有则用空字典
    old["category"] = (category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY  # 清洗分组名并写入记录
    meta[filename] = old  # 把更新后的记录放回元数据字典
    save_file_meta(meta)  # 保存元数据文件


def remove_file_meta(filename: str):  # 定义删除文件元数据记录的函数
    meta = load_file_meta()  # 读取当前全部元数据
    if filename in meta:  # 如果该文件存在记录
        meta.pop(filename, None)  # 删除该文件的记录
        save_file_meta(meta)  # 保存更新后的元数据


def clear_file_meta():  # 定义清空全部元数据的函数
    save_file_meta({})  # 写入空字典，等价于清空
