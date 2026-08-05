import pytest

from config import rag_config


def test_save_and_load_config(tmp_path, monkeypatch):
    target = tmp_path / "rag_config.json"
    monkeypatch.setattr(rag_config, "CONFIG_PATH", str(target))

    cfg = dict(rag_config.DEFAULT_CONFIG)
    cfg["chunk_size"] = 500
    saved = rag_config.save_config(cfg)
    assert saved["chunk_size"] == 500
    assert rag_config.load_config()["chunk_size"] == 500


def test_save_config_rejects_bad_value(tmp_path, monkeypatch):
    target = tmp_path / "rag_config.json"
    monkeypatch.setattr(rag_config, "CONFIG_PATH", str(target))

    cfg = dict(rag_config.DEFAULT_CONFIG)
    cfg["chunk_size"] = 99999
    with pytest.raises(ValueError):
        rag_config.save_config(cfg)


def test_load_config_falls_back_on_corrupt_file(tmp_path, monkeypatch):
    target = tmp_path / "rag_config.json"
    target.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(rag_config, "CONFIG_PATH", str(target))
    assert rag_config.load_config()["chunk_size"] == rag_config.DEFAULT_CONFIG["chunk_size"]
