import os

from utils.file_parser import _read_txt, split_text


def test_split_text_chinese():
    chunks = split_text("第一段。第二段！第三段？", chunk_size=10, chunk_overlap=2)
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)


def test_split_text_empty():
    assert split_text("") == []
    assert split_text("   ") == []


def test_read_txt_utf8_and_gb18030(tmp_path):
    utf8_file = tmp_path / "a.txt"
    utf8_file.write_bytes("你好世界".encode("utf-8"))
    assert _read_txt(str(utf8_file)) == "你好世界"

    gb_file = tmp_path / "b.txt"
    gb_file.write_bytes("中文内容".encode("gb18030"))
    assert _read_txt(str(gb_file)) == "中文内容"
