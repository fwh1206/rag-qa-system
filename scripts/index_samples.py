"""把 data 目录下的样例文档解析、切分并写入向量库，供评测与演示使用。"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import UPLOAD_PATH
from core.rag_engine import SUPPORTED_SUFFIXES, clear_all_vector, file_to_vector
from utils.file_parser import read_file


def main():
    clear_all_vector()
    total = 0
    for name in sorted(os.listdir(UPLOAD_PATH)):
        path = os.path.join(UPLOAD_PATH, name)
        suffix = os.path.splitext(name)[1].lower()
        if not os.path.isfile(path) or suffix not in SUPPORTED_SUFFIXES:
            continue
        text = read_file(path, suffix)
        chunk_num = file_to_vector(name, text)
        total += chunk_num
        print(f"{name}: {chunk_num} chunks")
    print(f"total chunks: {total}")


if __name__ == "__main__":
    main()
