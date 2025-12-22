"""
Redis客户端

提供Redis连接和操作的封装，支持异步操作。
"""

from typing import Optional, List, Any
import redis.asyncio as redis

from core.config import RedisSettings
from core.exceptions import RedisError
from core.logging import get_logger

logger = get_logger("RedisClient")


class RedisClient:
    """Redis客户端类"""

    def __init__(self, settings: RedisSettings):
        """
        初始化Redis客户端

        Args:
            settings: Redis配置
        """
        self.settings = settings
        self._client: Optional[redis.Redis] = None
        self._enabled = settings.enabled

    async def connect(self) -> None:
        """建立Redis连接"""
        if not self._enabled:
            logger.warning("Redis功能已禁用，跳过连接")
            return

        try:
            self._client = redis.from_url(
                self.settings.url,
                encoding="utf-8",
                decode_responses=True
            )
            # 测试连接
            await self._client.ping()
            logger.info(f"Redis连接成功: {self.settings.host}:{self.settings.port}")
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            raise RedisError(f"Redis连接失败: {e}", details=str(e))

    async def close(self) -> None:
        """关闭Redis连接"""
        if self._client:
            await self._client.close()
            logger.info("Redis连接已关闭")

    def get_client(self) -> redis.Redis:
        """
        获取Redis客户端实例

        Returns:
            Redis客户端实例

        Raises:
            RedisError: 如果客户端未初始化
        """
        if not self._enabled:
            raise RedisError("Redis功能已禁用")

        if self._client is None:
            raise RedisError("Redis客户端未初始化，请先调用connect()")

        return self._client

    # ==================== 常用操作封装 ====================

    async def get(self, key: str) -> Optional[str]:
        """
        获取键值

        Args:
            key: 键名

        Returns:
            键值，不存在返回None
        """
        try:
            client = self.get_client()
            return await client.get(key)
        except Exception as e:
            logger.error(f"Redis GET操作失败 key={key}: {e}")
            raise RedisError(f"Redis GET操作失败", details={"key": key, "error": str(e)})

    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None
    ) -> bool:
        """
        设置键值

        Args:
            key: 键名
            value: 键值
            ex: 过期时间（秒）

        Returns:
            是否成功
        """
        try:
            client = self.get_client()
            return await client.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Redis SET操作失败 key={key}: {e}")
            raise RedisError(f"Redis SET操作失败", details={"key": key, "error": str(e)})

    async def delete(self, *keys: str) -> int:
        """
        删除键

        Args:
            *keys: 键名列表

        Returns:
            删除的键数量
        """
        try:
            client = self.get_client()
            return await client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis DELETE操作失败 keys={keys}: {e}")
            raise RedisError(f"Redis DELETE操作失败", details={"keys": keys, "error": str(e)})

    async def exists(self, *keys: str) -> int:
        """
        检查键是否存在

        Args:
            *keys: 键名列表

        Returns:
            存在的键数量
        """
        try:
            client = self.get_client()
            return await client.exists(*keys)
        except Exception as e:
            logger.error(f"Redis EXISTS操作失败 keys={keys}: {e}")
            raise RedisError(f"Redis EXISTS操作失败", details={"keys": keys, "error": str(e)})

    async def expire(self, key: str, seconds: int) -> bool:
        """
        设置键过期时间

        Args:
            key: 键名
            seconds: 过期时间（秒）

        Returns:
            是否成功
        """
        try:
            client = self.get_client()
            return await client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis EXPIRE操作失败 key={key}: {e}")
            raise RedisError(f"Redis EXPIRE操作失败", details={"key": key, "error": str(e)})

    # ==================== Hash操作 ====================

    async def hset(self, name: str, key: str, value: str) -> int:
        """
        设置Hash字段值

        Args:
            name: Hash名称
            key: 字段名
            value: 字段值

        Returns:
            新增字段数量
        """
        try:
            client = self.get_client()
            return await client.hset(name, key, value)
        except Exception as e:
            logger.error(f"Redis HSET操作失败 name={name}, key={key}: {e}")
            raise RedisError(f"Redis HSET操作失败", details={"name": name, "key": key, "error": str(e)})

    async def hget(self, name: str, key: str) -> Optional[str]:
        """
        获取Hash字段值

        Args:
            name: Hash名称
            key: 字段名

        Returns:
            字段值，不存在返回None
        """
        try:
            client = self.get_client()
            return await client.hget(name, key)
        except Exception as e:
            logger.error(f"Redis HGET操作失败 name={name}, key={key}: {e}")
            raise RedisError(f"Redis HGET操作失败", details={"name": name, "key": key, "error": str(e)})

    async def hgetall(self, name: str) -> dict:
        """
        获取Hash所有字段

        Args:
            name: Hash名称

        Returns:
            字段字典
        """
        try:
            client = self.get_client()
            return await client.hgetall(name)
        except Exception as e:
            logger.error(f"Redis HGETALL操作失败 name={name}: {e}")
            raise RedisError(f"Redis HGETALL操作失败", details={"name": name, "error": str(e)})

    async def hdel(self, name: str, *keys: str) -> int:
        """
        删除Hash字段

        Args:
            name: Hash名称
            *keys: 字段名列表

        Returns:
            删除的字段数量
        """
        try:
            client = self.get_client()
            return await client.hdel(name, *keys)
        except Exception as e:
            logger.error(f"Redis HDEL操作失败 name={name}, keys={keys}: {e}")
            raise RedisError(f"Redis HDEL操作失败", details={"name": name, "keys": keys, "error": str(e)})

    # ==================== List操作 ====================

    async def lpush(self, name: str, *values: str) -> int:
        """
        从左侧插入List元素

        Args:
            name: List名称
            *values: 元素列表

        Returns:
            List长度
        """
        try:
            client = self.get_client()
            return await client.lpush(name, *values)
        except Exception as e:
            logger.error(f"Redis LPUSH操作失败 name={name}: {e}")
            raise RedisError(f"Redis LPUSH操作失败", details={"name": name, "error": str(e)})

    async def rpush(self, name: str, *values: str) -> int:
        """
        从右侧插入List元素

        Args:
            name: List名称
            *values: 元素列表

        Returns:
            List长度
        """
        try:
            client = self.get_client()
            return await client.rpush(name, *values)
        except Exception as e:
            logger.error(f"Redis RPUSH操作失败 name={name}: {e}")
            raise RedisError(f"Redis RPUSH操作失败", details={"name": name, "error": str(e)})

    async def lrange(self, name: str, start: int, end: int) -> List[str]:
        """
        获取List范围元素

        Args:
            name: List名称
            start: 起始索引
            end: 结束索引 (-1表示末尾)

        Returns:
            元素列表
        """
        try:
            client = self.get_client()
            return await client.lrange(name, start, end)
        except Exception as e:
            logger.error(f"Redis LRANGE操作失败 name={name}: {e}")
            raise RedisError(f"Redis LRANGE操作失败", details={"name": name, "error": str(e)})

    async def llen(self, name: str) -> int:
        """
        获取List长度

        Args:
            name: List名称

        Returns:
            List长度
        """
        try:
            client = self.get_client()
            return await client.llen(name)
        except Exception as e:
            logger.error(f"Redis LLEN操作失败 name={name}: {e}")
            raise RedisError(f"Redis LLEN操作失败", details={"name": name, "error": str(e)})
