# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/10/8 23:45
    Description:
        项目启动文件-
"""

import uvicorn
from db.neo_conn import Neo4jConnection
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

from settings import config
from utils.utils_log import logger
from apps.views_chat import router as router_chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("准备链接redis和neo4j")
    redis_conn = redis.Redis(
        host=config.RedisConfig.host,
        port=config.RedisConfig.port,
        db=config.RedisConfig.db,
        decode_responses=True
    )
    neo4j_conn = Neo4jConnection(
        uri=config.Neo4jConfig.uri,
        user=config.Neo4jConfig.user,
        password=config.Neo4jConfig.password
    )
    try:
        await redis_conn.ping()

        app.state.redis = redis_conn
        logger.info("redis链接成功")
        app.state.neo4j = neo4j_conn
        logger.info("neo4j链接成功")

        yield
    except Exception as e:
        print(e)

    finally:
        await redis_conn.aclose()
        logger.info("redis断开链接")

        neo4j_conn.close()
        logger.info("neo4j断开链接")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,  # 允许携带Cookie等凭证
    allow_methods=["*"],  # 允许所有HTTP方法 (GET, POST, PUT, etc.)
    allow_headers=["*"],  # 允许所有请求头
)

app.include_router(router_chat, prefix="/api")

# 固定问题版本
# from apps.views_static_question.views import router as router_static_question
# app.include_router(router_static_question)

from apps.views_intent.views import router as router_intent
app.include_router(router_intent)


if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=8000, workers=1)
