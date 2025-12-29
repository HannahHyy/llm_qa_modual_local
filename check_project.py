"""
项目配置检查工具

检查项目模块、配置文件、数据库连接等是否正常。
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import List, Tuple, Optional


# ============= 项目模块列表 =============

PROJECT_MODULES = [
    # 核心模块
    "core.config",
    "core.logging",
    "core.exceptions",
    "core.cache",
    "core.retry",

    # 领域层
    "domain.models.message",
    "domain.models.session",
    "domain.models.intent",
    "domain.models.knowledge",
    "domain.parsers.base_parser",
    "domain.parsers.es_intent_parser",
    "domain.parsers.neo4j_intent_parser",
    "domain.retrievers.base_retriever",
    "domain.retrievers.es_retriever",
    "domain.retrievers.hybrid_retriever",
    "domain.retrievers.neo4j_retriever",
    "domain.services.prompt_builder",
    "domain.services.knowledge_matcher",
    "domain.services.memory_service",
    "domain.services.intent_router",
    "domain.strategies.intent_routing_strategy",
    "domain.strategies.llm_intent_router",

    # 应用层
    "application.services.chat_service",
    "application.services.session_service",
    "application.services.streaming_service",

    # 基础设施层
    "infrastructure.clients.redis_client",
    "infrastructure.clients.mysql_client",
    "infrastructure.clients.es_client",
    "infrastructure.repositories.message_repository",
    "infrastructure.repositories.session_repository",

    # API层
    "api.schemas.common_schemas",
    "api.schemas.chat_schemas",
    "api.schemas.session_schemas",
    "api.routers.health_router",
    "api.routers.chat_router",
    "api.routers.session_router",
    "api.middleware.logging_middleware",
    "api.middleware.error_handler_middleware",
    "api.middleware.rate_limit_middleware",
    "api.dependencies.app_dependencies",
]


# ============= 必需文件列表 =============

REQUIRED_FILES = [
    "main.py",
    "requirements.txt",
    ".env",
    "logs/",
    "static/",
]


def check_file_exists(file_path: str) -> Tuple[bool, str]:
    """
    检查文件或目录是否存在

    Args:
        file_path: 文件路径

    Returns:
        (是否存在, 消息)
    """
    path = Path(file_path)

    if path.exists():
        if path.is_dir():
            return True, f"✓ 目录: {file_path}"
        else:
            size = path.stat().st_size
            return True, f"✓ 文件: {file_path:30s} ({size} bytes)"
    else:
        return False, f"✗ 缺失: {file_path}"


def check_module_import(module_name: str) -> Tuple[bool, str]:
    """
    检查模块是否可以导入

    Args:
        module_name: 模块名

    Returns:
        (是否成功, 消息)
    """
    try:
        __import__(module_name)
        return True, f"✓ {module_name}"
    except ImportError as e:
        return False, f"✗ {module_name:50s} 导入失败: {str(e)[:50]}"
    except Exception as e:
        return False, f"✗ {module_name:50s} 错误: {str(e)[:50]}"


def check_env_file() -> Tuple[bool, str]:
    """
    检查.env配置文件

    Returns:
        (是否通过, 消息)
    """
    env_path = Path(".env")

    if not env_path.exists():
        return False, "✗ .env文件不存在，请从.env.example复制并配置"

    # 检查必需的环境变量
    required_vars = [
        "LLM_API_KEY",
        "MYSQL_HOST",
        "REDIS_HOST",
        "ES_HOST",
    ]

    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    missing_vars = []
    for var in required_vars:
        if var not in content:
            missing_vars.append(var)

    if missing_vars:
        return False, f"✗ .env缺少配置: {', '.join(missing_vars)}"

    return True, "✓ .env配置文件存在且包含必需变量"


async def check_redis_connection() -> Tuple[bool, str]:
    """
    检查Redis连接

    Returns:
        (是否成功, 消息)
    """
    try:
        from core.config import get_settings
        from infrastructure.clients.redis_client import RedisClient

        settings = get_settings()

        if not settings.redis.enabled:
            return True, "⊘ Redis已禁用（跳过检查）"

        client = RedisClient(settings.redis)
        await client.connect()
        await client.close()

        return True, f"✓ Redis连接成功: {settings.redis.host}:{settings.redis.port}"

    except Exception as e:
        return False, f"✗ Redis连接失败: {str(e)[:100]}"


def check_mysql_connection() -> Tuple[bool, str]:
    """
    检查MySQL连接

    Returns:
        (是否成功, 消息)
    """
    try:
        from core.config import get_settings
        from infrastructure.clients.mysql_client import MySQLClient

        settings = get_settings()
        client = MySQLClient(settings.mysql)
        client.connect()
        client.close()

        return True, f"✓ MySQL连接成功: {settings.mysql.host}:{settings.mysql.port}/{settings.mysql.database}"

    except Exception as e:
        return False, f"✗ MySQL连接失败: {str(e)[:100]}"


def check_es_connection() -> Tuple[bool, str]:
    """
    检查Elasticsearch连接

    Returns:
        (是否成功, 消息)
    """
    try:
        from core.config import get_settings
        from infrastructure.clients.es_client import ESClient

        settings = get_settings()
        client = ESClient(settings.es)
        client.connect()

        return True, f"✓ Elasticsearch连接成功: {settings.es.url}"

    except Exception as e:
        return False, f"✗ Elasticsearch连接失败: {str(e)[:100]}"


async def check_neo4j_connection() -> Tuple[bool, str]:
    """
    检查Neo4j连接

    Returns:
        (是否成功, 消息)
    """
    try:
        from core.config import get_settings
        from neo4j import AsyncGraphDatabase

        settings = get_settings()

        if not settings.neo4j.enabled:
            return True, "⊘ Neo4j已禁用（跳过检查）"

        driver = AsyncGraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.user, settings.neo4j.password)
        )

        async with driver.session() as session:
            result = await session.run("RETURN 1")
            await result.consume()

        await driver.close()

        return True, f"✓ Neo4j连接成功: {settings.neo4j.uri}"

    except Exception as e:
        return False, f"✗ Neo4j连接失败: {str(e)[:100]}"


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80 + "\n")


def print_results(passed: List[str], failed: List[str], section: str):
    """打印检查结果"""
    if passed:
        for msg in passed:
            print(f"  {msg}")

    if failed:
        for msg in failed:
            print(f"  {msg}")

    if passed or failed:
        print(f"\n  {section}: {len(passed)} 通过, {len(failed)} 失败")


async def main():
    """主函数"""
    print("\n🔍 开始检查项目配置...\n")

    all_passed = 0
    all_failed = 0

    # ===== 1. 检查必需文件 =====
    print_section("1️⃣  检查必需文件")
    passed, failed = [], []

    for file_path in REQUIRED_FILES:
        success, message = check_file_exists(file_path)
        (passed if success else failed).append(message)

    # 额外检查.env文件
    success, message = check_env_file()
    (passed if success else failed).append(message)

    print_results(passed, failed, "文件检查")
    all_passed += len(passed)
    all_failed += len(failed)

    # ===== 2. 检查项目模块 =====
    print_section("2️⃣  检查项目模块导入")
    passed, failed = [], []

    for module in PROJECT_MODULES:
        success, message = check_module_import(module)
        (passed if success else failed).append(message)

    print_results(passed, failed, "模块导入")
    all_passed += len(passed)
    all_failed += len(failed)

    # ===== 3. 检查数据库连接 =====
    print_section("3️⃣  检查数据库连接")
    db_results = []

    # Redis (异步)
    success, message = await check_redis_connection()
    db_results.append((success, message))

    # MySQL (同步)
    success, message = check_mysql_connection()
    db_results.append((success, message))

    # Elasticsearch (同步)
    success, message = check_es_connection()
    db_results.append((success, message))

    # Neo4j (异步)
    success, message = await check_neo4j_connection()
    db_results.append((success, message))

    passed = [msg for success, msg in db_results if success]
    failed = [msg for success, msg in db_results if not success]

    print_results(passed, failed, "数据库连接")
    all_passed += len(passed)
    all_failed += len(failed)

    # ===== 最终统计 =====
    print_section("📊 检查结果汇总")
    print(f"  ✓ 通过: {all_passed}")
    print(f"  ✗ 失败: {all_failed}")
    print(f"  总计: {all_passed + all_failed}")
    print("\n" + "=" * 80)

    if all_failed > 0:
        print("\n⚠️  存在问题，请检查上述失败项")
        print("\n💡 常见解决方法:")
        print("  1. 确保所有依赖已安装: pip install -r requirements.txt")
        print("  2. 检查.env配置文件是否正确")
        print("  3. 确保数据库服务已启动 (MySQL, Redis, Elasticsearch, Neo4j)")
        print("  4. 检查数据库连接信息是否正确\n")
        sys.exit(1)
    else:
        print("\n✅ 所有检查通过！项目配置正常")
        print("\n🚀 下一步: 运行 python main.py 启动应用\n")
        sys.exit(0)


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
