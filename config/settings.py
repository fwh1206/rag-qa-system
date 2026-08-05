"""全局配置：集中定义路径、默认 RAG 参数、DeepSeek 与 MySQL 配置。"""

import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

UPLOAD_PATH = os.path.join(BASE_DIR, "data")
VECTOR_PATH = os.path.join(BASE_DIR, "vector_db")
LOG_PATH = os.path.join(BASE_DIR, "logs")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "rag_config.json")

os.makedirs(UPLOAD_PATH, exist_ok=True)
os.makedirs(VECTOR_PATH, exist_ok=True)
os.makedirs(LOG_PATH, exist_ok=True)

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
SIMILARITY_THRESHOLD = 0.70
DEFAULT_TOP_K = 3
TEMPERATURE = 0.6

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
LLM_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

AUTH_ENABLED = os.environ.get("RAG_AUTH_ENABLED", "1") == "1"
AUTH_USERNAME = os.environ.get("RAG_AUTH_USER", "admin")
AUTH_PASSWORD = os.environ.get("RAG_AUTH_PASSWORD", "admin123")
AUTH_TOKEN_TTL = int(os.environ.get("RAG_AUTH_TOKEN_TTL", 24 * 3600))

DB_CONFIG = {
    "host": os.environ.get("RAG_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("RAG_DB_PORT", 3306)),
    "user": os.environ.get("RAG_DB_USER", "root"),
    "password": os.environ.get("RAG_DB_PASSWORD", "root"),
    "database": os.environ.get("RAG_DB_NAME", "rag_qa_db"),
    "charset": os.environ.get("RAG_DB_CHARSET", "utf8mb4"),
}
DB_POOL_SIZE = int(os.environ.get("RAG_DB_POOL_SIZE", 8))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "RAG_CORS_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]
