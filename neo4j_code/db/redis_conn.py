# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/5/8 21:49
    Description:
        redis链接依赖
"""

from fastapi import Request

async def get_redis(request: Request):
    """获取 Redis 连接的依赖项"""
    return request.app.state.redis
