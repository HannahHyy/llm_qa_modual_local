"""
COMBINE_LLM 主应用程序

基于Clean Architecture的RAG对话系统
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.config import get_settings
from core.logging import LoggerManager
from api.routers import chat_router, session_router, health_router
from api.middleware import (
    logging_middleware,
    error_handler_middleware,
    rate_limit_middleware
)
from api.dependencies import cleanup_dependencies


# 配置日志
settings = get_settings()
LoggerManager.setup_logging(
    log_level=settings.log_level,
    log_file_path="logs/app.log"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    Args:
        app: FastAPI应用
    """
    # 启动时
    from core.logging import logger
    logger.info("应用启动中...")
    logger.info(f"环境: {settings.env}")
    logger.info(f"日志级别: {settings.log_level}")

    yield

    # 关闭时
    logger.info("应用关闭中...")
    await cleanup_dependencies()
    logger.info("应用已关闭")


# 创建FastAPI应用
app = FastAPI(
    title="COMBINE_LLM",
    description="基于Clean Architecture的RAG对话系统",
    version="1.0.0",
    lifespan=lifespan
)


# ============= 中间件配置 =============

# 1. CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 日志中间件
app.add_middleware(logging_middleware)

# 3. 错误处理中间件
app.add_middleware(error_handler_middleware)

# 4. 限流中间件
app.add_middleware(
    rate_limit_middleware(
        requests_per_minute=60,
        requests_per_hour=1000
    )
)


# ============= 路由注册 =============

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(session_router)


# ============= 根路由 =============

@app.get("/")
async def root():
    """根路由"""
    return {
        "service": "COMBINE_LLM",
        "version": "1.0.0",
        "description": "基于Clean Architecture的RAG对话系统",
        "docs": "/docs",
        "health": "/api/health"
    }


# ============= 启动命令 =============

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式，生产环境应设为False
        log_level="info"
    )
