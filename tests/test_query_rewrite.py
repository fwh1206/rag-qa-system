from unittest.mock import patch

from core.query_rewrite import build_rewrite_prompt, rewrite_query


def test_build_rewrite_prompt_contains_history_and_question():
    prompt = build_rewrite_prompt("它多少钱？", "用户：云帆专业版\nAI：每月 499 元")
    assert "它多少钱？" in prompt
    assert "用户：云帆专业版" in prompt
    assert "独立检索" in prompt


def test_rewrite_query_uses_llm_result():
    with patch("core.query_rewrite.llm_chat", return_value="云帆专业版多少钱？"):
        assert rewrite_query("它多少钱？", "用户：云帆专业版") == "云帆专业版多少钱？"


def test_rewrite_query_falls_back_on_error():
    with patch("core.query_rewrite.llm_chat", side_effect=Exception("llm down")):
        assert rewrite_query("它多少钱？", "用户：云帆专业版") == "它多少钱？"


def test_rewrite_query_skipped_without_history():
    with patch("core.query_rewrite.llm_chat") as mock_llm:
        assert rewrite_query("它多少钱？", "") == "它多少钱？"
        mock_llm.assert_not_called()
