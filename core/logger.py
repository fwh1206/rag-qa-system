"""日志模块：统一向 logs/run_log.txt 写入带时间戳的滚动日志。"""  # 模块文档：说明本文件提供统一的日志写入能力

import logging  # 导入 Python 标准日志库
import os  # 导入操作系统模块，用于拼接日志文件路径
from logging.handlers import RotatingFileHandler  # 导入滚动文件处理器，支持按文件大小轮转

from config.settings import LOG_PATH  # 导入日志目录路径


_logger = logging.getLogger("rag_qa")  # 创建名为 rag_qa 的日志记录器
_logger.setLevel(logging.INFO)  # 设置日志级别为 INFO，只记录该级别及以上的日志

# 只初始化一次，避免重复添加 handler
if not _logger.handlers:  # 判断当前记录器是否已有处理器，防止重复初始化
    # 单文件最大 5MB，保留 3 个历史文件
    log_file = os.path.join(LOG_PATH, "run_log.txt")  # 拼接日志文件的完整路径
    handler = RotatingFileHandler(  # 创建滚动文件处理器
        log_file,  # 日志文件路径
        maxBytes=5 * 1024 * 1024,  # 单文件最大 5MB
        backupCount=3,  # 最多保留 3 个备份文件
        encoding="utf-8"  # 以 UTF-8 编码写入，避免中文乱码
    )
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))  # 设置日志格式：时间 + 消息
    _logger.addHandler(handler)  # 把处理器添加到日志记录器
    _logger.propagate = False  # 禁止日志向更上层记录器传播，避免重复输出


def write_log(content: str):  # 定义统一的日志写入函数，content 为要记录的文本
    # 供其他模块统一写入日志
    _logger.info(content)  # 以 INFO 级别记录日志内容
