"""数据统计接口：文档数、向量片段数、对话量、会话数、用户数等，供前端统计页展示。"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from core.auth import require_auth
from core.database import get_db_conn
from core.rag_engine import collection
from utils.file_meta import load_file_meta

router = APIRouter(prefix="/stats", tags=["数据统计"])


def _scope_sql(role: str):
    """按角色返回趋势查询 SQL 与参数，普通用户只统计自己的会话。"""
    if role == "admin":
        sql = (
            "SELECT DATE(created_at), COUNT(*) FROM chat_history "
            "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
            "GROUP BY DATE(created_at)"
        )
        return sql, None
    sql = (
        "SELECT DATE(h.created_at), COUNT(*) "
        "FROM chat_history h "
        "JOIN chat_sessions s ON h.session_id = s.session_id "
        "WHERE s.owner = %s AND h.created_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
        "GROUP BY DATE(h.created_at)"
    )
    return sql, None


def _kb_meta(owner: str | None):
    meta = load_file_meta()
    if owner is None:
        return meta
    return {key: info for key, info in meta.items() if (info or {}).get("owner") == owner}


@router.get("/trend")
def stats_trend(
    current: dict = Depends(require_auth),
    days: int = Query(7, ge=1, le=90),
):
    """最近 N 天对话趋势，缺失日期补零，返回可直接绘制图表的 labels/values。"""
    role = current.get("role")
    username = current.get("username")
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            sql, _ = _scope_sql(role)
            params = (username, days - 1) if role != "admin" else (days - 1,)
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    counts = {}
    for day, count in rows:
        key = str(day)[:10]
        counts[key] = int(count)

    labels = []
    values = []
    for offset in range(days - 1, -1, -1):
        day = date.today() - timedelta(days=offset)  # noqa: DTZ011 - 与 MySQL CURDATE() 保持一致
        key = day.strftime("%Y-%m-%d")
        labels.append(day.strftime("%m-%d"))
        values.append(counts.get(key, 0))
    return {"days": days, "labels": labels, "values": values, "total": sum(values)}


@router.get("/overview")
def stats_overview(current: dict = Depends(require_auth)):
    """系统运行概况统计。"""
    username = current.get("username")
    kb_owner = None if current.get("role") == "admin" else username
    # 文档与分组：来自 JSON 元数据（与知识库接口同一数据源）
    meta = _kb_meta(kb_owner)
    file_count = len(meta)
    categories = sorted({(info.get("category") or "默认分组") for info in meta.values()})

    # 向量片段数：来自 Chroma 向量库
    chunk_count = 0
    try:
        data = collection.get(include=[], where={"owner": kb_owner} if kb_owner else None)
        chunk_count = len(data["ids"])
    except Exception:
        chunk_count = 0

    # 对话与会话：来自 MySQL
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            if current.get("role") == "admin":
                cur.execute("SELECT COUNT(*) FROM chat_history")
                chat_count = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(DISTINCT session_id) FROM chat_history")
                session_count = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM users")
                user_count = int(cur.fetchone()[0])
                cur.execute("SELECT MAX(created_at) FROM chat_history")
                last_ts = cur.fetchone()[0]
            else:
                cur.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT h.session_id), MAX(h.created_at) "
                    "FROM chat_history h "
                    "JOIN chat_sessions s ON h.session_id = s.session_id "
                    "WHERE s.owner=%s",
                    (username,),
                )
                row = cur.fetchone()
                chat_count = int(row[0] or 0)
                session_count = int(row[1] or 0)
                last_ts = row[2]
                user_count = 0
    finally:
        conn.close()

    return {
        "files": file_count,
        "chunks": chunk_count,
        "chats": chat_count,
        "sessions": session_count,
        "users": user_count,
        "categories": len(categories),
        "last_chat_at": last_ts.isoformat() if last_ts else None,
    }


@router.get("/me")
def stats_me(current: dict = Depends(require_auth)):
    """个人中心使用统计：按登录用户汇总会话与消息，管理员可查看系统全量。"""
    username = current.get("username")
    role = current.get("role")
    meta = _kb_meta(None if role == "admin" else username)
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            if role == "admin":
                cur.execute(
                    "SELECT COUNT(DISTINCT session_id), COUNT(*), MAX(created_at) FROM chat_history"
                )
            else:
                cur.execute(
                    "SELECT COUNT(DISTINCT h.session_id), COUNT(*), MAX(h.created_at) "
                    "FROM chat_history h "
                    "JOIN chat_sessions s ON h.session_id = s.session_id "
                    "WHERE s.owner = %s",
                    (username,),
                )
            row = cur.fetchone()
            session_count = int(row[0] or 0) if row else 0
            chat_count = int(row[1] or 0) if row else 0
            last_chat_at = row[2].isoformat() if row and row[2] else None

            if role == "admin":
                cur.execute(
                    "SELECT question, answer, session_id, created_at "
                    "FROM chat_history ORDER BY id DESC LIMIT 5"
                )
            else:
                cur.execute(
                    "SELECT h.question, h.answer, h.session_id, h.created_at "
                    "FROM chat_history h "
                    "JOIN chat_sessions s ON h.session_id = s.session_id "
                    "WHERE s.owner = %s ORDER BY h.id DESC LIMIT 5",
                    (username,),
                )
            rows = cur.fetchall()
    finally:
        conn.close()

    chunk_count = 0
    try:
        where = {"owner": username} if role != "admin" else None
        data = collection.get(include=[], where=where)
        chunk_count = len(data["ids"])
    except Exception:
        chunk_count = 0

    recent = [
        {
            "question": question,
            "answer": (answer or "")[:120],
            "session_id": session_id,
            "created_at": created_at.isoformat() if created_at else None,
        }
        for question, answer, session_id, created_at in rows
    ]
    return {
        "scope": "admin" if role == "admin" else "user",
        "sessions": session_count,
        "chats": chat_count,
        "files": len(meta),
        "chunks": chunk_count,
        "last_chat_at": last_chat_at,
        "recent": recent,
    }


@router.get("/recent")
def stats_recent(
    current: dict = Depends(require_auth),
    limit: int = Query(8, ge=1, le=50),
):
    """最近对话摘要：管理员看全站，普通用户只看自己的会话。"""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            if current.get("role") == "admin":
                cur.execute(
                    "SELECT question, answer, session_id, created_at FROM chat_history "
                    "ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
            else:
                cur.execute(
                    "SELECT h.question, h.answer, h.session_id, h.created_at "
                    "FROM chat_history h "
                    "JOIN chat_sessions s ON h.session_id = s.session_id "
                    "WHERE s.owner = %s "
                    "ORDER BY h.id DESC LIMIT %s",
                    (current.get("username"), limit),
                )
            rows = cur.fetchall()
    finally:
        conn.close()
    items = []
    for question, answer, session_id, created_at in rows:
        items.append(
            {
                "question": question,
                "answer": (answer or "")[:120],
                "session_id": session_id,
                "created_at": created_at.isoformat() if created_at else None,
            }
        )
    return {"items": items}
