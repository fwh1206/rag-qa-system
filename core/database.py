"""MySQL 数据层：管理用户、会话、问答历史与登录 token。"""

import hashlib
import secrets
import threading
from datetime import datetime

import pymysql
from dbutils.pooled_db import PooledDB
from fastapi import HTTPException
from pymysql.err import OperationalError

from config.settings import AUTH_PASSWORD, AUTH_USERNAME, DB_CONFIG, DB_POOL_SIZE

_pool = None
_pool_lock = threading.Lock()


def get_pool() -> PooledDB:
    """懒加载数据库连接池，避免模块导入时依赖 MySQL 已启动。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = PooledDB(
                    creator=pymysql,
                    maxconnections=DB_POOL_SIZE,
                    mincached=1,
                    maxcached=DB_POOL_SIZE,
                    blocking=True,
                    **DB_CONFIG,
                )
    return _pool


def get_db_conn():
    """从连接池取连接，失败时返回友好错误。"""
    try:
        return get_pool().connection()
    except OperationalError as exc:
        raise HTTPException(status_code=500, detail="数据库连接失败") from exc


def init_db():
    """建表并自动补齐字段，兼容旧库。"""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                    username VARCHAR(64) NOT NULL,
                    email VARCHAR(255) NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role ENUM('admin', 'user') NOT NULL DEFAULT 'user',
                    llm_enabled TINYINT(1) NOT NULL DEFAULT 0,
                    llm_url VARCHAR(512) NULL,
                    llm_model VARCHAR(128) NULL,
                    llm_api_key TEXT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    UNIQUE KEY uk_username (username),
                    UNIQUE KEY uk_email (email)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS email_verify_codes (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    email VARCHAR(255) NOT NULL,
                    code_hash CHAR(64) NOT NULL,
                    purpose VARCHAR(32) NOT NULL DEFAULT 'register',
                    expires_at DATETIME NOT NULL,
                    used TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    KEY idx_email_purpose (email, purpose)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id VARCHAR(128) NOT NULL,
                    name VARCHAR(200) NOT NULL DEFAULT '新会话',
                    owner VARCHAR(64) NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    session_id VARCHAR(128) NOT NULL,
                    question TEXT NOT NULL,
                    answer LONGTEXT NOT NULL,
                    thinking LONGTEXT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    KEY idx_session_id (session_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token_hash CHAR(64) NOT NULL,
                    username VARCHAR(64) NOT NULL,
                    role VARCHAR(16) NOT NULL DEFAULT 'user',
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (token_hash),
                    KEY idx_expires (expires_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='chat_history' AND COLUMN_NAME='thinking'",
                (DB_CONFIG["database"],),
            )
            if cur.fetchone()[0] == 0:
                cur.execute("ALTER TABLE chat_history ADD COLUMN thinking LONGTEXT NULL")
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='chat_history' AND COLUMN_NAME='created_at'",
                (DB_CONFIG["database"],),
            )
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "ALTER TABLE chat_history ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users' AND COLUMN_NAME='email'",
                (DB_CONFIG["database"],),
            )
            if cur.fetchone()[0] == 0:
                cur.execute("ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL AFTER username")
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users' AND INDEX_NAME='uk_email'",
                (DB_CONFIG["database"],),
            )
            if cur.fetchone()[0] == 0:
                cur.execute("ALTER TABLE users ADD UNIQUE KEY uk_email (email)")
            for column, ddl in [
                ("llm_enabled", "ALTER TABLE users ADD COLUMN llm_enabled TINYINT(1) NOT NULL DEFAULT 0"),
                ("llm_url", "ALTER TABLE users ADD COLUMN llm_url VARCHAR(512) NULL"),
                ("llm_model", "ALTER TABLE users ADD COLUMN llm_model VARCHAR(128) NULL"),
                ("llm_api_key", "ALTER TABLE users ADD COLUMN llm_api_key TEXT NULL"),
            ]:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users' AND COLUMN_NAME=%s",
                    (DB_CONFIG["database"], column),
                )
                if cur.fetchone()[0] == 0:
                    cur.execute(ddl)
            cur.execute("SELECT COUNT(*) FROM users")
            if int(cur.fetchone()[0]) == 0:
                cur.execute(
                    "INSERT INTO users(username, password_hash, role) VALUES(%s, %s, 'admin')",
                    (AUTH_USERNAME, hash_password(AUTH_PASSWORD)),
                )
        conn.commit()
    finally:
        conn.close()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return secrets.compare_digest(calc, digest)


def create_user(
    username: str,
    password: str,
    role: str = "user",
    email: str | None = None,
) -> bool:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            normalized_email = (email or "").strip().lower() or None
            cur.execute(
                "INSERT INTO users(username, email, password_hash, role) VALUES(%s, %s, %s, %s)",
                (username, normalized_email, hash_password(password), role),
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_user(username: str) -> dict | None:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, email, password_hash, role, created_at FROM users WHERE username=%s",
                (username,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "password_hash": row[3],
            "role": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, email, password_hash, role, created_at FROM users WHERE email=%s",
                (email.strip().lower(),),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "password_hash": row[3],
            "role": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }
    finally:
        conn.close()


def get_user_llm_config(username: str) -> dict | None:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT llm_enabled, llm_url, llm_model, llm_api_key "
                "FROM users WHERE username=%s",
                (username,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "llm_enabled": bool(row[0]),
            "llm_url": row[1],
            "llm_model": row[2],
            "llm_api_key": row[3],
        }
    finally:
        conn.close()


def save_user_llm_config(
    username: str,
    enabled: bool,
    url: str,
    model: str,
    encrypted_key: str | None,
):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET llm_enabled=%s, llm_url=%s, llm_model=%s, llm_api_key=%s "
                "WHERE username=%s",
                (int(enabled), url, model, encrypted_key, username),
            )
        conn.commit()
    finally:
        conn.close()


def list_users():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, email, role, created_at FROM users ORDER BY id")
            rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "role": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
            }
            for row in rows
        ]
    finally:
        conn.close()


def update_user_role(username: str, role: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET role=%s WHERE username=%s", (role, username))
        conn.commit()
    finally:
        conn.close()


def update_user_password(username: str, password: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash=%s WHERE username=%s",
                (hash_password(password), username),
            )
        conn.commit()
    finally:
        conn.close()


def update_user_email(username: str, email: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET email=%s WHERE username=%s",
                (email.strip().lower(), username),
            )
        conn.commit()
    finally:
        conn.close()


def delete_user(username: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username=%s", (username,))
        conn.commit()
    finally:
        conn.close()


def create_email_code(email: str, code: str, purpose: str, expires_at: datetime) -> int:
    """保存验证码哈希，同邮箱未使用的旧码先作废。"""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE email_verify_codes SET used=1 "
                "WHERE email=%s AND purpose=%s AND used=0",
                (email, purpose),
            )
            cur.execute(
                "INSERT INTO email_verify_codes(email, code_hash, purpose, expires_at) "
                "VALUES(%s, %s, %s, %s)",
                (email, hashlib.sha256(code.encode("utf-8")).hexdigest(), purpose, expires_at),
            )
            cur.execute("SELECT LAST_INSERT_ID()")
            code_id = int(cur.fetchone()[0])
        conn.commit()
        return code_id
    finally:
        conn.close()


def has_active_email_code(email: str, purpose: str) -> bool:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM email_verify_codes "
                "WHERE email=%s AND purpose=%s AND used=0 "
                "AND expires_at > UTC_TIMESTAMP() "
                "AND created_at > DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 60 SECOND)",
                (email, purpose),
            )
            return int(cur.fetchone()[0]) > 0
    finally:
        conn.close()


def get_email_code(email: str, purpose: str) -> dict | None:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, code_hash, expires_at FROM email_verify_codes "
                "WHERE email=%s AND purpose=%s AND used=0 AND expires_at > UTC_TIMESTAMP() "
                "ORDER BY id DESC LIMIT 1",
                (email, purpose),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "code_hash": row[1], "expires_at": row[2]}
    finally:
        conn.close()


def mark_email_code_used(code_id: int):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE email_verify_codes SET used=1 WHERE id=%s", (code_id,))
        conn.commit()
    finally:
        conn.close()


def count_admins() -> int:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def create_auth_token(token_hash: str, username: str, role: str, expires_at: datetime):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO auth_tokens(token_hash, username, role, expires_at) VALUES(%s, %s, %s, %s)",
                (token_hash, username, role, expires_at),
            )
        conn.commit()
    finally:
        conn.close()


def get_auth_token(token_hash: str) -> dict | None:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, role FROM auth_tokens WHERE token_hash=%s AND expires_at > UTC_TIMESTAMP()",
                (token_hash,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"username": row[0], "role": row[1]}
    finally:
        conn.close()


def delete_auth_token(token_hash: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_tokens WHERE token_hash=%s", (token_hash,))
        conn.commit()
    finally:
        conn.close()


def purge_expired_tokens():
    """清理过期 token，每次限制删除量，避免 token 量大时阻塞登录。"""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_tokens WHERE expires_at <= UTC_TIMESTAMP() LIMIT 500")
        conn.commit()
    finally:
        conn.close()


def get_session(session_id: str) -> dict | None:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id, name, owner FROM chat_sessions WHERE session_id=%s",
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"session_id": row[0], "name": row[1], "owner": row[2]}
    finally:
        conn.close()


def require_session_access(session_id: str, current: dict):
    """校验当前用户是否有权访问会话；会话不存在时放行，由后续逻辑创建。"""
    session = get_session(session_id)
    if session is None:
        return
    if current.get("role") == "admin":
        return
    owner = session.get("owner")
    if owner and owner != current.get("username"):
        raise HTTPException(status_code=403, detail="无权访问该会话")


def ensure_session(session_id: str, name: str | None = None, owner: str | None = None):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chat_sessions WHERE session_id=%s", (session_id,))
            exists = int(cur.fetchone()[0]) > 0
            if not exists:
                cur.execute(
                    "INSERT INTO chat_sessions(session_id, name, owner) VALUES(%s, %s, %s)",
                    (session_id, name or "新会话", owner),
                )
            elif owner:
                cur.execute(
                    "UPDATE chat_sessions SET owner=%s WHERE session_id=%s AND owner IS NULL",
                    (owner, session_id),
                )
        conn.commit()
    finally:
        conn.close()


def rename_session(session_id: str, name: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chat_sessions SET name=%s, updated_at=CURRENT_TIMESTAMP WHERE session_id=%s",
                (name, session_id),
            )
        conn.commit()
    finally:
        conn.close()


def list_sessions(owner: str | None = None):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT s.session_id, s.name, s.updated_at, COUNT(h.id)
                FROM chat_sessions s
                LEFT JOIN chat_history h ON h.session_id = s.session_id
            """
            params = []
            if owner:
                sql += " WHERE s.owner=%s"
                params.append(owner)
            sql += " GROUP BY s.session_id, s.name, s.updated_at ORDER BY s.updated_at DESC"
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            {
                "session_id": row[0],
                "name": row[1],
                "updated_at": row[2].isoformat() if row[2] else None,
                "message_count": int(row[3]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def save_chat_record(
    session_id: str,
    question: str,
    answer: str,
    thinking: str | None = None,
    owner: str | None = None,
):
    ensure_session(session_id, name=question[:30], owner=owner)
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history(question, answer, session_id, thinking) VALUES(%s, %s, %s, %s)",
                (question, answer, session_id, thinking),
            )
        conn.commit()
    finally:
        conn.close()


def load_chat_memory(session_id: str, max_turns: int = 8, max_chars: int = 2000) -> str:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT question, answer FROM chat_history "
                "WHERE session_id=%s ORDER BY id DESC LIMIT %s",
                (session_id, max_turns),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    lines = []
    for question, answer in reversed(rows):
        lines.append(f"用户：{question}\nAI：{answer}")
    text = "\n".join(lines)
    return text[-max_chars:] if len(text) > max_chars else text


def count_chat_history(session_id: str) -> int:
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chat_history WHERE session_id=%s", (session_id,))
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def list_chat_history(session_id: str, limit: int = 20, offset: int = 0):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, question, answer, thinking, created_at FROM chat_history "
                "WHERE session_id=%s ORDER BY id DESC LIMIT %s OFFSET %s",
                (session_id, limit, offset),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    history = []
    for row_id, question, answer, thinking, created_at in reversed(rows):
        history.append(
            {
                "id": row_id,
                "question": question,
                "answer": answer,
                "thinking": thinking,
                "created_at": created_at.isoformat() if created_at else None,
            }
        )
    return history


def clear_chat_history(session_id: str):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_history WHERE session_id=%s", (session_id,))
        conn.commit()
    finally:
        conn.close()
