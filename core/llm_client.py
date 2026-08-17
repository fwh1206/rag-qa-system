"""大模型客户端：封装任意 OpenAI 兼容接口的同步调用与流式调用。"""

import json
import time

import requests
from fastapi import HTTPException

from config.llm_config import load_llm_config
from core.logger import write_log
from core.secret_box import decrypt_secret


def resolve_user_llm_config(raw: dict | None) -> dict | None:
    """把用户数据库里的加密模型配置解析为可调用配置；未启用或缺失字段时返回 None。"""
    if not raw or not raw.get("llm_enabled"):
        return None
    url = raw.get("llm_url") or ""
    model = raw.get("llm_model") or ""
    encrypted_key = raw.get("llm_api_key") or ""
    if not url or not model or not encrypted_key:
        return None
    try:
        api_key = decrypt_secret(encrypted_key)
    except ValueError as exc:
        write_log(f"用户模型密钥解密失败：{exc}")
        return None
    return {"api_key": api_key, "url": url, "model": model}


def _get_llm_config(user_config: dict | None = None) -> dict:
    if user_config and user_config.get("api_key") and user_config.get("url") and user_config.get("model"):
        return user_config
    cfg = load_llm_config()
    if not cfg.get("api_key"):
        raise HTTPException(status_code=500, detail="未配置大模型 API Key，请先在系统设置中完成模型配置")
    return cfg


def _headers(cfg: dict) -> dict:
    """构造 OpenAI 兼容请求头。"""
    return {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }


def _payload(prompt: str, temperature: float, cfg: dict) -> dict:
    """构造 Chat Completion 请求体，默认非流式。"""
    return {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": False,
    }


def llm_chat(
    prompt: str,
    temperature: float = 0.6,
    llm_config: dict | None = None,
    read_timeout: int = 90,
) -> str:
    """同步调用大模型，返回完整回答；用于非流式问答和思考阶段。"""
    cfg = _get_llm_config(llm_config)
    last_exc: Exception | None = None
    for attempt in range(3):
        resp = None
        try:
            resp = requests.post(
                cfg["url"],
                json=_payload(prompt, temperature, cfg),
                headers=_headers(cfg),
                timeout=(10, read_timeout),
            )
            if resp.status_code in (408, 429) or resp.status_code >= 500:
                raise RuntimeError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            # 部分 OpenAI 兼容端点不声明 charset，requests 默认按 ISO-8859-1 解码会乱码
            resp.encoding = "utf-8"
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            last_exc = exc
            if resp is not None:
                resp.close()
            if attempt < 2:
                time.sleep(0.4 * (2**attempt))
                continue
            break
    write_log(f"大模型调用异常（重试后仍失败）：{last_exc!s}")
    raise HTTPException(status_code=500, detail="AI服务调用失败") from last_exc


def llm_chat_stream(prompt: str, temperature: float = 0.6, llm_config: dict | None = None):
    """流式调用 OpenAI 兼容模型，逐段产出文本增量。"""
    cfg = _get_llm_config(llm_config)
    payload = _payload(prompt, temperature, cfg)
    payload["stream"] = True
    resp = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                cfg["url"],
                json=payload,
                headers=_headers(cfg),
                timeout=(10, 180),
                stream=True,
            )
            if resp.status_code in (408, 429) or resp.status_code >= 500:
                raise RuntimeError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            # 流式按 UTF-8 解码，避免端点未声明 charset 时中文乱码
            resp.encoding = "utf-8"
            break
        except Exception as exc:
            last_exc = exc
            if resp is not None:
                resp.close()
                resp = None
            if attempt < 2:
                time.sleep(0.4 * (2**attempt))
                continue
            write_log(f"大模型流式连接异常（重试后仍失败）：{last_exc!s}")
            raise HTTPException(status_code=500, detail="AI服务调用失败") from last_exc

    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {}).get("content", "")
            except (ValueError, KeyError, IndexError):
                continue
            if delta:
                yield delta
    except Exception as exc:
        write_log(f"大模型流式调用异常：{exc!s}")
        raise HTTPException(status_code=500, detail="AI服务调用失败") from exc
    finally:
        if resp is not None:
            resp.close()
