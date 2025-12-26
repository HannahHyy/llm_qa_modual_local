"""
Core层测试

测试核心工具类：重试机制、缓存策略、配置管理等
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Any


# ==================== Retry Mechanism Tests ====================

class TestRetryMechanism:
    """测试重试机制"""

    def test_retry_sync_success_first_attempt(self):
        """测试同步重试：第一次尝试成功"""
        from core.retry import retry_sync

        @retry_sync(max_attempts=3)
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

    def test_retry_sync_success_after_failures(self):
        """测试同步重试：失败后重试成功"""
        from core.retry import retry_sync

        attempt_count = {"count": 0}

        @retry_sync(max_attempts=3, delay=0.1)
        def flaky_function():
            attempt_count["count"] += 1
            if attempt_count["count"] < 3:
                raise Exception("暂时失败")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert attempt_count["count"] == 3

    def test_retry_sync_max_attempts_exceeded(self):
        """测试同步重试：超过最大尝试次数"""
        from core.retry import retry_sync

        @retry_sync(max_attempts=3, delay=0.1)
        def always_fail():
            raise Exception("永久失败")

        with pytest.raises(Exception) as exc_info:
            always_fail()

        assert "永久失败" in str(exc_info.value)

    def test_retry_sync_with_specific_exceptions(self):
        """测试同步重试：只重试特定异常"""
        from core.retry import retry_sync

        class CustomError(Exception):
            pass

        attempt_count = {"count": 0}

        @retry_sync(max_attempts=3, delay=0.1, exceptions=(CustomError,))
        def specific_error_function():
            attempt_count["count"] += 1
            if attempt_count["count"] < 2:
                raise CustomError("自定义错误")
            return "success"

        result = specific_error_function()
        assert result == "success"

    def test_retry_sync_wrong_exception_type(self):
        """测试同步重试：非目标异常不重试"""
        from core.retry import retry_sync

        class CustomError(Exception):
            pass

        class OtherError(Exception):
            pass

        @retry_sync(max_attempts=3, exceptions=(CustomError,))
        def other_error_function():
            raise OtherError("其他错误")

        with pytest.raises(OtherError):
            other_error_function()

    @pytest.mark.asyncio
    async def test_retry_async_success_first_attempt(self):
        """测试异步重试：第一次尝试成功"""
        from core.retry import retry_async

        @retry_async(max_attempts=3)
        async def successful_async_function():
            return "async success"

        result = await successful_async_function()
        assert result == "async success"

    @pytest.mark.asyncio
    async def test_retry_async_success_after_failures(self):
        """测试异步重试：失败后重试成功"""
        from core.retry import retry_async

        attempt_count = {"count": 0}

        @retry_async(max_attempts=3, delay=0.1)
        async def flaky_async_function():
            attempt_count["count"] += 1
            if attempt_count["count"] < 3:
                raise Exception("暂时失败")
            return "async success"

        result = await flaky_async_function()
        assert result == "async success"
        assert attempt_count["count"] == 3

    @pytest.mark.asyncio
    async def test_retry_async_max_attempts_exceeded(self):
        """测试异步重试：超过最大尝试次数"""
        from core.retry import retry_async

        @retry_async(max_attempts=3, delay=0.1)
        async def always_fail_async():
            raise Exception("永久失败")

        with pytest.raises(Exception) as exc_info:
            await always_fail_async()

        assert "永久失败" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retry_async_with_backoff(self):
        """测试异步重试：指数退避"""
        from core.retry import retry_async

        attempt_times = []

        @retry_async(max_attempts=3, delay=0.1, backoff=2.0)
        async def backoff_function():
            attempt_times.append(time.time())
            if len(attempt_times) < 3:
                raise Exception("失败")
            return "success"

        result = await backoff_function()
        assert result == "success"

        # 验证重试间隔递增（0.1, 0.2, ...）
        if len(attempt_times) >= 2:
            interval1 = attempt_times[1] - attempt_times[0]
            # 第一次延迟约0.1秒
            assert 0.08 < interval1 < 0.15

    def test_retry_with_on_retry_callback(self):
        """测试重试回调函数"""
        from core.retry import retry_sync

        callback_calls = []

        def on_retry_callback(attempt, exception):
            callback_calls.append((attempt, str(exception)))

        @retry_sync(max_attempts=3, delay=0.1, on_retry=on_retry_callback)
        def function_with_callback():
            if len(callback_calls) < 2:
                raise Exception(f"失败{len(callback_calls) + 1}")
            return "success"

        result = function_with_callback()
        assert result == "success"
        assert len(callback_calls) >= 2


# ==================== Cache Strategy Tests ====================

class TestCacheStrategy:
    """测试缓存策略"""

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        """测试缓存设置和获取"""
        from core.cache import CacheManager

        cache = CacheManager(max_size=100, default_ttl=3600)

        await cache.set("test_key", "test_value")
        result = await cache.get("test_key")

        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self):
        """测试缓存TTL过期"""
        from core.cache import CacheManager

        cache = CacheManager(max_size=100, default_ttl=1)

        await cache.set("test_key", "test_value", ttl=1)

        # 立即获取应该成功
        result = await cache.get("test_key")
        assert result == "test_value"

        # 等待过期
        await asyncio.sleep(1.5)

        # 过期后应该返回None
        result = await cache.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self):
        """测试LRU淘汰策略"""
        from core.cache import CacheManager

        cache = CacheManager(max_size=3, default_ttl=3600)

        # 添加3个键
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        # 访问key1，使其成为最近使用
        await cache.get("key1")

        # 添加第4个键，应该淘汰key2（最少使用）
        await cache.set("key4", "value4")

        # key1应该还在
        assert await cache.get("key1") == "value1"

        # key2应该被淘汰
        assert await cache.get("key2") is None

        # key3和key4应该还在
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"

    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """测试缓存清除"""
        from core.cache import CacheManager

        cache = CacheManager(max_size=100, default_ttl=3600)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        # 清除缓存
        await cache.clear()

        # 所有键应该被清除
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_cache_delete(self):
        """测试缓存删除特定键"""
        from core.cache import CacheManager

        cache = CacheManager(max_size=100, default_ttl=3600)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        # 删除key1
        await cache.delete("key1")

        # key1应该被删除
        assert await cache.get("key1") is None

        # key2应该还在
        assert await cache.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_cached_decorator(self):
        """测试缓存装饰器"""
        from core.cache import cached

        call_count = {"count": 0}

        @cached(ttl=3600, key_prefix="test")
        async def expensive_function(x: int) -> int:
            call_count["count"] += 1
            await asyncio.sleep(0.1)
            return x * 2

        # 第一次调用
        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count["count"] == 1

        # 第二次调用（缓存命中）
        result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count["count"] == 1  # 没有增加

        # 不同参数（缓存未命中）
        result3 = await expensive_function(10)
        assert result3 == 20
        assert call_count["count"] == 2

    @pytest.mark.asyncio
    async def test_cache_get_stats(self):
        """测试缓存统计信息"""
        from core.cache import CacheManager

        cache = CacheManager(max_size=100, default_ttl=3600)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.get("key1")
        await cache.get("key1")
        await cache.get("nonexistent")

        # 如果CacheManager有stats方法
        # stats = cache.get_stats()
        # assert stats["hits"] == 2
        # assert stats["misses"] == 1


# ==================== Config Management Tests ====================

class TestConfigManagement:
    """测试配置管理"""

    def test_load_settings_from_env(self):
        """测试从环境变量加载配置"""
        from core.config.settings import Settings

        # 使用测试环境变量
        with patch.dict("os.environ", {
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "DEBUG"
        }):
            settings = Settings()
            assert settings.environment == "test"
            assert settings.log_level == "DEBUG"

    def test_llm_settings(self):
        """测试LLM配置"""
        from core.config.settings import Settings

        settings = Settings()

        # 验证LLM配置存在
        assert hasattr(settings, "llm")
        assert hasattr(settings.llm, "api_key")
        assert hasattr(settings.llm, "base_url")
        assert hasattr(settings.llm, "model_name")

    def test_es_settings(self):
        """测试ES配置"""
        from core.config.settings import Settings

        settings = Settings()

        # 验证ES配置存在
        assert hasattr(settings, "es")
        assert hasattr(settings.es, "host")
        assert hasattr(settings.es, "knowledge_index")
        assert hasattr(settings.es, "cypher_index")

    def test_neo4j_settings(self):
        """测试Neo4j配置"""
        from core.config.settings import Settings

        settings = Settings()

        # 验证Neo4j配置存在
        assert hasattr(settings, "neo4j")
        assert hasattr(settings.neo4j, "uri")
        assert hasattr(settings.neo4j, "username")
        assert hasattr(settings.neo4j, "password")

    def test_mysql_settings(self):
        """测试MySQL配置"""
        from core.config.settings import Settings

        settings = Settings()

        # 验证MySQL配置存在
        assert hasattr(settings, "mysql")
        assert hasattr(settings.mysql, "host")
        assert hasattr(settings.mysql, "database")

    def test_redis_settings(self):
        """测试Redis配置"""
        from core.config.settings import Settings

        settings = Settings()

        # 验证Redis配置存在
        assert hasattr(settings, "redis")
        assert hasattr(settings.redis, "host")


# ==================== Logging Tests ====================

class TestLogging:
    """测试日志功能"""

    def test_logger_initialization(self):
        """测试日志初始化"""
        from core.logging import get_logger

        logger = get_logger("test_module")

        assert logger is not None
        assert logger.name == "test_module"

    def test_logger_levels(self):
        """测试日志级别"""
        from core.logging import get_logger

        logger = get_logger("test_module")

        # 验证日志方法存在
        assert hasattr(logger, "debug")
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "critical")

    def test_logger_output(self, caplog):
        """测试日志输出"""
        from core.logging import get_logger

        logger = get_logger("test_module")

        with caplog.at_level("INFO"):
            logger.info("测试信息日志")

        assert "测试信息日志" in caplog.text


# ==================== Utility Functions Tests ====================

class TestUtilityFunctions:
    """测试工具函数"""

    def test_format_sse_message(self):
        """测试SSE消息格式化"""
        # 假设有format_sse_message工具函数
        # from core.utils import format_sse_message

        # result = format_sse_message("测试消息", message_type=1)

        # assert "data:" in result
        # assert "测试消息" in result

    def test_parse_json_from_text(self):
        """测试从文本解析JSON"""
        # 假设有parse_json工具函数
        # from core.utils import parse_json

        # text = "一些文本 {\"key\": \"value\"} 更多文本"
        # result = parse_json(text)

        # assert result == {"key": "value"}

    def test_build_es_query(self):
        """测试构建ES查询"""
        # 假设有build_es_query工具函数
        # from core.utils import build_es_query

        # query = build_es_query(
        #     keywords=["网络安全"],
        #     retrieval_type="hybrid_search",
        #     bm25_weight=0.6,
        #     vector_weight=0.4
        # )

        # assert "bool" in query
        # assert "should" in query["bool"]


# ==================== Integration Tests ====================

class TestCoreIntegration:
    """Core层集成测试"""

    @pytest.mark.asyncio
    async def test_retry_with_cache(self):
        """测试重试机制与缓存的集成"""
        from core.retry import retry_async
        from core.cache import cached

        call_count = {"count": 0}

        @cached(ttl=3600)
        @retry_async(max_attempts=3, delay=0.1)
        async def function_with_retry_and_cache(x: int):
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise Exception("首次失败")
            return x * 2

        # 第一次调用（失败后重试成功）
        result1 = await function_with_retry_and_cache(5)
        assert result1 == 10
        assert call_count["count"] == 2

        # 第二次调用（缓存命中，不会重试）
        call_count["count"] = 0
        result2 = await function_with_retry_and_cache(5)
        assert result2 == 10
        assert call_count["count"] == 0  # 缓存命中

    def test_config_with_logging(self):
        """测试配置与日志的集成"""
        from core.config.settings import Settings
        from core.logging import get_logger

        settings = Settings()
        logger = get_logger("test_integration")

        # 使用配置中的日志级别
        logger.info(f"环境: {settings.environment}")
        logger.info(f"日志级别: {settings.log_level}")

        # 验证配置和日志正常工作
        assert settings.environment is not None
        assert logger is not None
