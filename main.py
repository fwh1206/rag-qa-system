"""FastAPI 应用入口：负责组装路由、静态页面与全局初始化。"""

import os
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import auth_router, chat_router, config_router, file_router, history_router, kg_router, stats_router
from config.settings import BASE_DIR, CORS_ORIGINS
from core.auth import require_auth
from core.database import init_db
from core.rag_engine import get_embed_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 后台预热 embedding 模型，避免首次提问等待下载/加载
    threading.Thread(target=get_embed_model, daemon=True).start()
    yield


app = FastAPI(title="rag智能问答系统", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(static_path, "index.html"))


@app.get("/login")
def login_page():
    return FileResponse(os.path.join(static_path, "login.html"))


@app.get("/kb")
def kb_page():
    return FileResponse(os.path.join(static_path, "kb.html"))


@app.get("/stats")
def stats_page():
    return FileResponse(os.path.join(static_path, "stats.html"))


@app.get("/history")
def history_page():
    return FileResponse(os.path.join(static_path, "history.html"))


@app.get("/settings")
def settings_page():
    return FileResponse(os.path.join(static_path, "settings.html"))


@app.get("/profile")
def profile_page():
    return FileResponse(os.path.join(static_path, "profile.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router.router)
app.include_router(chat_router.router, dependencies=[Depends(require_auth)])
app.include_router(file_router.router, dependencies=[Depends(require_auth)])
app.include_router(history_router.router, dependencies=[Depends(require_auth)])
app.include_router(config_router.router, dependencies=[Depends(require_auth)])
app.include_router(stats_router.router, dependencies=[Depends(require_auth)])
app.include_router(kg_router.router, dependencies=[Depends(require_auth)])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
