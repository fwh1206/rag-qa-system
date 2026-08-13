"""把 data/samples 下的内置样例复制到上传区并入库，供评测与演示使用。

样例与用户上传区（data/ 根目录）分离：清空知识库不会影响内置样例，
需要时可随时重新执行本脚本恢复演示数据。
"""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import UPLOAD_PATH
from core.rag_engine import SUPPORTED_SUFFIXES, delete_file_vectors, file_to_vector
from utils.file_meta import DEFAULT_CATEGORY, set_file_meta
from utils.file_parser import read_file

SAMPLE_DIR = os.path.join(UPLOAD_PATH, "samples")


def main():
    if not os.path.isdir(SAMPLE_DIR):
        print(f"样例目录不存在：{SAMPLE_DIR}")
        return
    total = 0
    for name in sorted(os.listdir(SAMPLE_DIR)):
        src = os.path.join(SAMPLE_DIR, name)
        suffix = os.path.splitext(name)[1].lower()
        if not os.path.isfile(src) or suffix not in SUPPORTED_SUFFIXES:
            continue
        text = read_file(src, suffix)
        # 复制到上传区后入库，文件名保持一致（评测集按文件名匹配）
        dst = os.path.join(UPLOAD_PATH, name)
        if os.path.exists(dst):
            print(f"覆盖上传区同名文件：{name}")
        # 只清理样例本身对应的旧向量，不触碰各用户的私有知识库
        delete_file_vectors(storage=name, filename=name, owner="admin")
        shutil.copy2(src, dst)
        chunk_num = file_to_vector(
            name, text, DEFAULT_CATEGORY, owner="admin", storage=name
        )
        set_file_meta(name, category=DEFAULT_CATEGORY, owner="admin", display_name=name)
        total += chunk_num
        print(f"{name}: {chunk_num} chunks")
    print(f"total chunks: {total}")


if __name__ == "__main__":
    main()
