"""
缓存策略

提供多级缓存、缓存装饰器和缓存管理工具
"""

import asyncio
import hashlib
import json
import time
from functools import wraps
from typing import Callable, Optional, Any, Dict
from core.logging import logger


class CacheManager:
    """
    内存缓存管理器（L1缓存）

    使用LRU淘汰策略，支持TTL过期
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        初始化缓存管理器

        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认TTL（秒）
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_times: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        async with self._lock:
            if key not in self._cache:
                logger.debug(f"[缓存] Miss: {key}")
                return None

            # 检查是否过期
            entry = self._cache[key]
            if time.time() > entry["expires_at"]:
                logger.debug(f"[缓存] Expired: {key}")
                del self._cache[key]
                del self._access_times[key]
                return None

            # 更新访问时间（LRU）
            self._access_times[key] = time.time()
            logger.debug(f"[缓存] Hit: {key}")
            return entry["value"]

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存值"""
        async with self._lock:
            # 如果缓存已满，淘汰最久未使用的
            if len(self._cache) >= self.max_size and key not in self._cache:
                lru_key = min(self._access_times, key=self._access_times.get)
                del self._cache[lru_key]
                del self._access_times[lru_key]
                logger.debug(f"[缓存] Evicted (LRU): {lru_key}")

            ttl = ttl or self.default_ttl
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + ttl
            }
            self._access_times[key] = time.time()
            logger.debug(f"[缓存] Set: {key} (TTL={ttl}s)")

    async def delete(self, key: str):
        """删除缓存值"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                del self._access_times[key]
                logger.debug(f"[缓存] Deleted: {key}")

    async def clear(self):
        """清空所有缓存"""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._access_times.clear()
            logger.info(f"[缓存] Cleared {count} entries")

    def size(self) -> int:
        """获取当前缓存条目数"""
        return len(self._cache)


# 全局缓存管理器实例
_global_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器单例"""
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()
    return _global_cache_manager


def cache_key(*args, **kwargs) -> str:
    """
    生成缓存键

    Args:
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        str: MD5哈希键
    """
    # 将参数序列化为JSON字符串
    key_data = {
        "args": [str(arg) for arg in args],
        "kwargs": {k: str(v) for k, v in sorted(kwargs.items())}
    }
    key_str = json.dumps(key_data, sort_keys=True)

    # 计算MD5哈希
    return hashlib.md5(key_str.encode()).hexdigest()


def cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """
    异步函数缓存装饰器

    Args:
        ttl: 缓存TTL（秒），None表示使用默认值
        key_prefix: 缓存键前缀

    Example:
        @cached(ttl=300, key_prefix="user")
        async def get_user(user_id: str):
            # 耗时的数据库查询
            return await db.query(user_id)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_manager = get_cache_manager()

            # 生成缓存键
            key = f"{key_prefix}:{func.__name__}:{cache_key(*args, **kwargs)}"

            # 尝试从缓存获取
            cached_value = await cache_manager.get(key)
            if cached_value is not None:
                return cached_value

            # 缓存未命中，调用原函数
            result = await func(*args, **kwargs)

            # 存入缓存
            await cache_manager.set(key, result, ttl=ttl)

            return result

        # 添加清除缓存的方法
        wrapper.clear_cache = lambda: get_cache_manager().clear()

        return wrapper
    return decorator


def cache_sync(ttl: Optional[int] = None, key_prefix: str = ""):
    """
    同步函数缓存装饰器

    Args:
        ttl: 缓存TTL（秒），None表示使用默认值
        key_prefix: 缓存键前缀

    Example:
        @cache_sync(ttl=300, key_prefix="config")
        def get_config(config_name: str):
            # 耗时的配置读取
            return read_config_file(config_name)
    """
    cache_dict: Dict[str, Dict[str, Any]] = {}

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key = f"{key_prefix}:{func.__name__}:{cache_key(*args, **kwargs)}"

            # 检查缓存
            if key in cache_dict:
                entry = cache_dict[key]
                if time.time() < entry["expires_at"]:
                    logger.debug(f"[缓存] Hit: {key}")
                    return entry["value"]
                else:
                    logger.debug(f"[缓存] Expired: {key}")
                    del cache_dict[key]

            # 缓存未命中
            logger.debug(f"[缓存] Miss: {key}")
            result = func(*args, **kwargs)

            # 存入缓存
            cache_ttl = ttl or 3600
            cache_dict[key] = {
                "value": result,
                "expires_at": time.time() + cache_ttl
            }
            logger.debug(f"[缓存] Set: {key} (TTL={cache_ttl}s)")

            return result

        # 添加清除缓存的方法
        wrapper.clear_cache = lambda: cache_dict.clear()

        return wrapper
    return decorator


class CacheStats:
    """缓存统计"""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0

    def record_hit(self):
        self.hits += 1

    def record_miss(self):
        self.misses += 1

    def record_set(self):
        self.sets += 1

    def record_delete(self):
        self.deletes += 1

    def hit_rate(self) -> float:
        """计算缓存命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "hit_rate": f"{self.hit_rate():.2%}"
        }
