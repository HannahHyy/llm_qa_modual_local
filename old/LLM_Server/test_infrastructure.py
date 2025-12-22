"""
基础设施层测试脚本

验证配置管理、日志管理、数据库客户端和仓储层的基本功能。
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import get_settings
from core.logging import LoggerManager, get_logger
from infrastructure.clients import RedisClient, MySQLClient, ESClient
from infrastructure.repositories import SessionRepository, MessageRepository


async def test_config():
    """测试配置管理"""
    print("\n=== 测试配置管理 ===")
    settings = get_settings()

    print(f"Redis配置: {settings.redis.host}:{settings.redis.port}")
    print(f"MySQL配置: {settings.mysql.host}:{settings.mysql.port}/{settings.mysql.database}")
    print(f"ES配置: {settings.es.url}")
    print(f"日志级别: {settings.log_level}")
    print("✓ 配置管理测试通过")


async def test_logging():
    """测试日志管理"""
    print("\n=== 测试日志管理 ===")
    settings = get_settings()

    # 初始化日志系统
    LoggerManager.setup_logging(
        log_level=settings.log_level,
        log_file_path=settings.log_file_path,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
    )

    logger = get_logger("TestLogger")
    logger.info("这是一条INFO日志")
    logger.warning("这是一条WARNING日志")
    logger.debug("这是一条DEBUG日志")
    print("✓ 日志管理测试通过")


async def test_redis_client():
    """测试Redis客户端"""
    print("\n=== 测试Redis客户端 ===")
    settings = get_settings()

    if not settings.redis.enabled:
        print("⊘ Redis功能已禁用，跳过测试")
        return None

    redis_client = RedisClient(settings.redis)

    try:
        await redis_client.connect()
        print("✓ Redis连接成功")

        # 测试基本操作
        await redis_client.set("test_key", "test_value", ex=60)
        value = await redis_client.get("test_key")
        print(f"✓ Redis SET/GET测试: value={value}")

        # 测试Hash操作
        await redis_client.hset("test_hash", "field1", "value1")
        hash_value = await redis_client.hget("test_hash", "field1")
        print(f"✓ Redis HSET/HGET测试: value={hash_value}")

        # 测试List操作
        await redis_client.rpush("test_list", "item1", "item2")
        list_items = await redis_client.lrange("test_list", 0, -1)
        print(f"✓ Redis RPUSH/LRANGE测试: items={list_items}")

        # 清理测试数据
        await redis_client.delete("test_key", "test_hash", "test_list")

        return redis_client

    except Exception as e:
        print(f"✗ Redis测试失败: {e}")
        return None


def test_mysql_client():
    """测试MySQL客户端"""
    print("\n=== 测试MySQL客户端 ===")
    settings = get_settings()

    mysql_client = MySQLClient(settings.mysql)

    try:
        mysql_client.connect()
        print("✓ MySQL连接成功")

        # 测试查询
        result = mysql_client.execute_query("SELECT 1 as test")
        print(f"✓ MySQL查询测试: result={result}")

        # 测试查询用户表
        users = mysql_client.execute_query("SELECT * FROM users LIMIT 1")
        print(f"✓ MySQL查询users表: count={len(users)}")

        return mysql_client

    except Exception as e:
        print(f"✗ MySQL测试失败: {e}")
        print("  提示: 请确保MySQL服务已启动，并且chatdb数据库已创建")
        return None


def test_es_client():
    """测试ES客户端"""
    print("\n=== 测试ES客户端 ===")
    settings = get_settings()

    es_client = ESClient(settings.es)

    try:
        es_client.connect()
        print("✓ Elasticsearch连接成功")

        return es_client

    except Exception as e:
        print(f"✗ Elasticsearch测试失败: {e}")
        print("  提示: 请确保Elasticsearch服务已启动")
        return None


async def test_repositories(redis_client, mysql_client, es_client):
    """测试仓储层"""
    if not all([redis_client, mysql_client, es_client]):
        print("\n⊘ 仓储层测试跳过（某些客户端未就绪）")
        return

    print("\n=== 测试仓储层 ===")
    settings = get_settings()

    # 创建仓储实例
    session_repo = SessionRepository(redis_client, mysql_client, es_client)
    message_repo = MessageRepository(redis_client, es_client, settings.es)

    try:
        # 测试会话创建
        test_user_id = "test_user_001"
        session_id = await session_repo.create_session(test_user_id, "测试会话")
        print(f"✓ 创建会话成功: session_id={session_id}")

        # 测试会话列表
        sessions = await session_repo.list_sessions(test_user_id)
        print(f"✓ 获取会话列表成功: count={len(sessions)}")

        # 测试消息追加
        await message_repo.append_message(test_user_id, session_id, "user", "你好")
        await message_repo.append_message(test_user_id, session_id, "assistant", "你好！有什么可以帮助你的吗？")
        print("✓ 追加消息成功")

        # 测试消息获取
        messages = await message_repo.get_messages(test_user_id, session_id)
        print(f"✓ 获取消息成功: count={len(messages)}")

        # 清理测试数据
        await session_repo.delete_session(test_user_id, session_id)
        await message_repo.clear_messages(test_user_id, session_id)
        print("✓ 清理测试数据成功")

    except Exception as e:
        print(f"✗ 仓储层测试失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """主测试函数"""
    print("=" * 60)
    print("基础设施层测试")
    print("=" * 60)

    # 测试配置管理
    await test_config()

    # 测试日志管理
    await test_logging()

    # 测试数据库客户端
    redis_client = await test_redis_client()
    mysql_client = test_mysql_client()
    es_client = test_es_client()

    # 测试仓储层
    await test_repositories(redis_client, mysql_client, es_client)

    # 关闭连接
    if redis_client:
        await redis_client.close()
    if mysql_client:
        mysql_client.close()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
