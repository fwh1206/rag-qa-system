"""多轮问题改写：把依赖上下文的追问改写为可独立检索的问题。"""

from core.llm_client import llm_chat
from core.logger import write_log


REWRITE_PROMPT = (
    "你是对话助手。请把用户最新问题改写成不依赖历史对话、可以独立检索的完整问题。\n"
    "要求：只输出改写后的问题，不要解释；保留专有名词和关键信息；若问题本身已经完整，直接原样输出。\n"
    "历史对话：\n{history}\n"
    "用户最新问题：{question}\n"
)


def build_rewrite_prompt(question: str, memory_context: str) -> str:
    return REWRITE_PROMPT.format(history=memory_context.strip(), question=question.strip())


def rewrite_query(question: str, memory_context: str, temperature: float = 0.2) -> str:
    """改写失败或没有历史时回退到原始问题，保证检索链路不中断。"""
    question = question.strip()
    if not question or not (memory_context or "").strip():
        return question
    try:
        result = (llm_chat(build_rewrite_prompt(question, memory_context), temperature) or "").strip()
        return result or question
    except Exception as exc:
        write_log(f"多轮问题改写失败，回退原问题：{exc}")
        return question
