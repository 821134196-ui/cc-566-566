"""城市道路积雪撒盐与路段复核系统 —— FastAPI 入口。

后端：Python + FastAPI + SQLAlchemy + SQLite
前端：Vue 3（无构建，本地 vendor），由本服务静态托管
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_DIR
from .routers import auth, breakdown, dispatch, meta, photo, review, trace, work
from .seed import init_db

FRONTEND_DIR = PROJECT_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(seed=True)
    yield


app = FastAPI(title="城市道路积雪撒盐与路段复核系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 业务接口
for r in (auth, meta, dispatch, work, breakdown, review, trace, photo):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 静态前端（vendor / app 资源）
app.mount(
    "/static",
    StaticFiles(directory=str(FRONTEND_DIR)),
    name="static",
)


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
