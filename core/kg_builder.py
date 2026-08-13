"""知识图谱构建：调用大模型从文档中抽取实体与关系，并在本地缓存。"""

import json
import os
import re

from config.settings import KG_PATH
from core.llm_client import llm_chat
from core.logger import write_log

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
_KG_PROMPT = (
    "你是知识图谱构建器。请从下面的文档中提取关键实体和实体之间的关系。\n"
    "实体类型可以是：人物、组织、产品、技术、概念、地点、事件、指标等。\n"
    "只返回 JSON，不要解释，不要使用 Markdown 代码块。格式如下：\n"
    '{"entities":[{"id":"唯一ID","label":"实体名","type":"实体类型"}],'
    '"relations":[{"source":"实体ID","target":"实体ID","label":"关系名"}]}\n'
    "实体不超过 30 个，关系不超过 50 条，关系两端的 source/target 必须来自 entities。\n\n"
    "文档内容：\n{text}"
)


def _cache_path(filename: str, owner: str | None = None) -> str:
    safe = _SAFE_NAME.sub("_", filename)
    if owner:
        safe_owner = _SAFE_NAME.sub("_", owner)
        safe = f"{safe_owner}__{safe}"
    return os.path.join(KG_PATH, f"{safe}.json")


def _parse_graph(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    data = json.loads(text)
    entities = []
    seen = set()
    for item in (data.get("entities") or [])[:30]:
        entity_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        if not entity_id or not label or entity_id in seen:
            continue
        seen.add(entity_id)
        entities.append(
            {
                "id": entity_id,
                "label": label,
                "type": str(item.get("type") or "实体").strip() or "实体",
            }
        )
    entity_ids = {item["id"] for item in entities}
    relations = []
    for item in (data.get("relations") or [])[:50]:
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        label = str(item.get("label") or "").strip()
        if source in entity_ids and target in entity_ids and label:
            relations.append({"source": source, "target": target, "label": label})
    return {"entities": entities, "relations": relations}


def load_cached_graph(filename: str, owner: str | None = None) -> dict:
    path = _cache_path(filename, owner)
    if not os.path.exists(path):
        return {"status": "missing", "filename": filename, "entities": [], "relations": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "status": "cached",
            "filename": filename,
            "entities": data.get("entities") or [],
            "relations": data.get("relations") or [],
        }
    except (OSError, ValueError):
        return {"status": "missing", "filename": filename, "entities": [], "relations": []}


def save_graph(filename: str, graph: dict, owner: str | None = None):
    os.makedirs(KG_PATH, exist_ok=True)
    with open(_cache_path(filename, owner), "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)


def delete_graph_cache(filename: str, owner: str | None = None):
    path = _cache_path(filename, owner)
    if os.path.exists(path):
        os.remove(path)
    if owner:
        legacy = _cache_path(filename)
        if os.path.exists(legacy):
            os.remove(legacy)


def clear_graph_cache(owner: str | None = None):
    """清空图谱缓存；传入 owner 时只清空该用户的前缀缓存。"""
    if not os.path.isdir(KG_PATH):
        return
    prefix = f"{_SAFE_NAME.sub('_', owner)}__" if owner else ""
    for name in os.listdir(KG_PATH):
        if not name.endswith(".json"):
            continue
        if prefix and not name.startswith(prefix):
            continue
        try:
            os.remove(os.path.join(KG_PATH, name))
        except OSError:
            pass


def extract_knowledge_graph(filename: str, text: str, owner: str | None = None) -> dict:
    """调用大模型抽取实体关系；失败时返回空图并写日志。"""
    try:
        prompt = _KG_PROMPT.replace("{text}", (text or "")[:8000])
        raw = llm_chat(prompt, 0.2, read_timeout=60)
        graph = _parse_graph(raw)
        save_graph(filename, graph, owner)
        write_log(f"知识图谱生成成功：{filename}，实体 {len(graph['entities'])}，关系 {len(graph['relations'])}")
        return {
            "status": "ok",
            "filename": filename,
            "entities": graph["entities"],
            "relations": graph["relations"],
        }
    except Exception as exc:
        write_log(f"知识图谱生成失败：{filename}，{exc}")
        return {
            "status": "failed",
            "filename": filename,
            "message": str(exc),
            "entities": [],
            "relations": [],
        }
