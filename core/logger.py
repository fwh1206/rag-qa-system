"""日志模块：统一向 logs/run_log.txt 写入带时间戳的滚动日志。"""

import logging
import os
from logging.handlers import RotatingFileHandler

from config.settings import LOG_PATH

_logger = logging.getLogger("rag_qa")
_logger.setLevel(logging.INFO)

# 只初始化一次，避免重复添加 handler
if not _logger.handlers:
    log_file = os.path.join(LOG_PATH, "run_log.txt")
    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
    _logger.addHandler(handler)
    _logger.propagate = False


def write_log(content: str):
    """供各模块统一写入日志。"""
    _logger.info(content)
