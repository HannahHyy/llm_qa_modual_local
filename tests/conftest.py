"""
pytest配置文件

定义全局fixtures和配置
"""

import pytest
import asyncio
from typing import AsyncGenerator

# 添加项目根目录到sys.path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings, Settings
from core.logging import LoggerManager
from infrastructure.clients import RedisClient, MySQLClient, ESClient
from infrastructure.repositories import SessionRepository, MessageRepository


# ==================== Event Loop配置 ====================

@pytest.fixture(scope="session")
def event_loop():
    """创建event loop供整个测试会话使用"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== 配置fixtures ====================

@pytest.fixture(scope="session")
def settings() -> Settings:
    """全局配置实例"""
    return get_settings()


@pytest.fixture(scope="session", autouse=True)
def setup_logging(settings):
    """自动设置日志系统"""
    LoggerManager.setup_logging(
        log_level="DEBUG",  # 测试时使用DEBUG级别
        log_file_path="tests/logs/test.log",
        rotation="10 MB",
        retention="3 days",
    )


# ==================== 客户端fixtures ====================

@pytest.fixture(scope="function")
async def redis_client(settings) -> AsyncGenerator[RedisClient, None]:
    """Redis客户端fixture（每个测试函数独立实例）"""
    if not settings.redis.enabled:
        pytest.skip("Redis未启用")

    client = RedisClient(settings.redis)
    await client.connect()
    yield client
    await client.close()


@pytest.fixture(scope="function")
def mysql_client(settings) -> MySQLClient:
    """MySQL客户端fixture（每个测试函数独立实例）"""
    client = MySQLClient(settings.mysql)
    try:
        client.connect()
        yield client
    finally:
        client.close()


@pytest.fixture(scope="function")
def es_client(settings) -> ESClient:
    """ES客户端fixture（每个测试函数独立实例）"""
    client = ESClient(settings.es)
    try:
        client.connect()
        yield client
    except Exception:
        pytest.skip("Elasticsearch未启动")


# ==================== 仓储fixtures ====================

@pytest.fixture(scope="function")
async def session_repository(redis_client, mysql_client, es_client) -> SessionRepository:
    """会话仓储fixture"""
    return SessionRepository(redis_client, mysql_client, es_client)


@pytest.fixture(scope="function")
async def message_repository(redis_client, es_client, settings) -> MessageRepository:
    """消息仓储fixture"""
    return MessageRepository(redis_client, es_client, settings.es)


# ==================== 测试数据fixtures ====================

@pytest.fixture
def test_user_id() -> str:
    """测试用户ID"""
    return "test_user_pytest_001"


@pytest.fixture
def test_session_name() -> str:
    """测试会话名称"""
    return "pytest测试会话"


# ==================== 清理fixtures ====================

@pytest.fixture(autouse=True)
async def cleanup_test_data(redis_client, mysql_client, test_user_id):
    """自动清理测试数据（测试后执行）"""
    yield

    # 测试结束后清理
    try:
        # 清理Redis中的测试数据
        if redis_client:
            # 删除测试用户的所有会话
            sessions_key = f"chat:{test_user_id}:sessions"
            await redis_client.delete(sessions_key)

            # 删除测试消息（需要先获取所有session_id）
            # 简化处理：直接删除匹配的key

        # 清理MySQL中的测试数据
        if mysql_client:
            # 删除测试用户的会话
            mysql_client.execute_update(
                "DELETE FROM sessions WHERE user_id = %s",
                (test_user_id,)
            )
            # 删除测试用户
            mysql_client.execute_update(
                "DELETE FROM users WHERE user_id = %s",
                (test_user_id,)
            )
    except Exception as e:
        # 清理失败不影响测试结果
        print(f"清理测试数据失败: {e}")
