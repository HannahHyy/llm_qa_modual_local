"""
健康检查路由
"""

from fastapi import APIRouter, Depends
from typing import Dict, Any
from api.dependencies import (
    get_redis_client,
    get_mysql_client,
    get_es_client
)
from infrastructure.clients import RedisClient, MySQLClient, ESClient
from core.logging import logger

# router初始化定义
router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """
    基础健康检查

    Returns:
        Dict: 健康状态
    """
    return {
        "status": "healthy",
        "service": "COMBINE_LLM",
        "version": "1.0.0"
    }


@router.get("/detailed")
async def detailed_health_check(
    redis_client: RedisClient = Depends(get_redis_client),
    mysql_client: MySQLClient = Depends(get_mysql_client),
    es_client: ESClient = Depends(get_es_client)
) -> Dict[str, Any]:
    """
    详细健康检查

    Args:
        redis_client: Redis客户端
        mysql_client: MySQL客户端
        es_client: ES客户端

    Returns:
        Dict: 详细健康状态
    """
    health_status = {
        "status": "healthy",
        "services": {}
    }

    # 检查Redis
    try:
        await redis_client.ping()
        health_status["services"]["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis健康检查失败: {str(e)}")
        health_status["services"]["redis"] = "unhealthy"
        health_status["status"] = "degraded"

    # 检查MySQL
    try:
        mysql_client.execute_query("SELECT 1")
        health_status["services"]["mysql"] = "healthy"
    except Exception as e:
        logger.error(f"MySQL健康检查失败: {str(e)}")
        health_status["services"]["mysql"] = "unhealthy"
        health_status["status"] = "degraded"

    # 检查ES
    try:
        if es_client.ping():
            health_status["services"]["elasticsearch"] = "healthy"
        else:
            health_status["services"]["elasticsearch"] = "unhealthy"
            health_status["status"] = "degraded"
    except Exception as e:
        logger.error(f"ES健康检查失败: {str(e)}")
        health_status["services"]["elasticsearch"] = "unhealthy"
        health_status["status"] = "degraded"

    return health_status


@router.get("/redis")
async def redis_health(
    redis_client: RedisClient = Depends(get_redis_client)
) -> Dict[str, str]:
    """
    Redis健康检查

    Args:
        redis_client: Redis客户端

    Returns:
        Dict: Redis状态
    """
    try:
        await redis_client.ping()
        return {"status": "healthy", "service": "redis"}
    except Exception as e:
        logger.error(f"Redis健康检查失败: {str(e)}")
        return {"status": "unhealthy", "service": "redis", "error": str(e)}


@router.get("/mysql")
async def mysql_health(
    mysql_client: MySQLClient = Depends(get_mysql_client)
) -> Dict[str, str]:
    """
    MySQL健康检查

    Args:
        mysql_client: MySQL客户端

    Returns:
        Dict: MySQL状态
    """
    try:
        mysql_client.execute_query("SELECT 1")
        return {"status": "healthy", "service": "mysql"}
    except Exception as e:
        logger.error(f"MySQL健康检查失败: {str(e)}")
        return {"status": "unhealthy", "service": "mysql", "error": str(e)}


@router.get("/elasticsearch")
async def elasticsearch_health(
    es_client: ESClient = Depends(get_es_client)
) -> Dict[str, str]:
    """
    Elasticsearch健康检查

    Args:
        es_client: ES客户端

    Returns:
        Dict: ES状态
    """
    try:
        if es_client.ping():
            return {"status": "healthy", "service": "elasticsearch"}
        else:
            return {"status": "unhealthy", "service": "elasticsearch"}
    except Exception as e:
        logger.error(f"ES健康检查失败: {str(e)}")
        return {"status": "unhealthy", "service": "elasticsearch", "error": str(e)}
