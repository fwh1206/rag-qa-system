"""大模型客户端：封装 DeepSeek 的同步调用与流式调用。"""  # 模块文档：说明本文件封装大模型请求能力

import json  # 导入 JSON 模块，用于解析流式响应

import requests  # 导入 HTTP 请求库
from fastapi import HTTPException  # 导入 HTTP 异常类

from config.settings import DEEPSEEK_KEY, LLM_MODEL, LLM_URL  # 导入大模型相关配置
from core.logger import write_log  # 导入日志写入函数


def _headers():  # 定义构造请求头的函数
    # 构造 DeepSeek 请求头
    if not DEEPSEEK_KEY:  # 未配置 API Key
        raise HTTPException(status_code=500, detail="未配置 DEEPSEEK_API_KEY，请设置环境变量后重启服务")  # 返回清晰错误
    return {  # 返回请求头字典
        "Authorization": f"Bearer {DEEPSEEK_KEY}",  # 携带 Bearer 格式的 API 密钥
        "Content-Type": "application/json",  # 声明请求体为 JSON
    }


def _payload(prompt: str, temperature: float):  # 定义构造请求体的函数
    # 构造 Chat Completion 请求体
    return {  # 返回请求体字典
        "model": LLM_MODEL,  # 指定模型名称
        "messages": [{"role": "user", "content": prompt}],  # 把提示词作为用户消息发送
        "temperature": temperature,  # 设置生成温度
        "stream": False,  # 默认非流式
    }


def llm_chat(prompt: str, temperature: float = 0.6):  # 定义同步调用大模型的函数
    # 同步调用：等待完整回答返回，用于非流式问答和思考阶段
    try:  # 捕获调用异常
        resp = requests.post(LLM_URL, json=_payload(prompt, temperature), headers=_headers(), timeout=(10, 90))  # 发送 POST 请求，连接超时 10 秒、读取超时 90 秒
        resp.raise_for_status()  # 响应状态非 2xx 时抛出异常
        return resp.json()["choices"][0]["message"]["content"]  # 提取并返回模型回答文本
    except Exception as exc:  # 捕获任意异常
        write_log(f"大模型调用异常：{str(exc)}")  # 记录异常日志
        raise HTTPException(status_code=500, detail="AI服务调用失败") from exc  # 向上抛出 500 错误


def llm_chat_stream(prompt: str, temperature: float = 0.6):  # 定义流式调用大模型的生成器函数
    """流式调用 DeepSeek，逐段产出文本增量。"""  # 函数说明文档
    # 逐行解析 SSE 响应，把 content 增量 yield 给上层
    payload = _payload(prompt, temperature)  # 构造基础请求体
    payload["stream"] = True  # 开启流式模式
    resp = None  # 初始化响应对象为 None
    try:  # 捕获调用异常
        resp = requests.post(LLM_URL, json=payload, headers=_headers(), timeout=(10, 180), stream=True)  # 发送流式 POST 请求
        resp.raise_for_status()  # 响应状态非 2xx 时抛出异常
        for line in resp.iter_lines(decode_unicode=True):  # 逐行迭代 SSE 响应
            if not line:  # 空行跳过
                continue
            line = line.strip()  # 去除首尾空白
            if not line.startswith("data:"):  # 非 data 开头的行跳过
                continue
            data = line[len("data:"):].strip()  # 去掉 data: 前缀得到数据内容
            if data == "[DONE]":  # 遇到结束标记
                break  # 终止流式读取
            try:  # 尝试解析单条数据
                chunk = json.loads(data)  # 解析 JSON
                delta = chunk["choices"][0].get("delta", {}).get("content", "")  # 提取内容增量
            except (ValueError, KeyError, IndexError):  # 解析异常
                continue  # 跳过异常数据
            if delta:  # 增量非空
                yield delta  # 逐段产出文本
    except Exception as exc:  # 捕获调用异常
        write_log(f"大模型流式调用异常：{str(exc)}")  # 记录异常日志
        raise HTTPException(status_code=500, detail="AI服务调用失败") from exc  # 向上抛出 500 错误
    finally:  # 无论成功失败都执行
        if resp is not None:  # 如果响应对象存在
            resp.close()  # 关闭响应，释放连接
