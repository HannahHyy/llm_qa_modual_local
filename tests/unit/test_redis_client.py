"""
Redis客户端单元测试
"""

import pytest


@pytest.mark.asyncio
class TestRedisClient:
    """RedisClient类测试"""

    async def test_connect(self, redis_client):
        """测试Redis连接"""
        # fixture已经连接，测试获取客户端
        client = redis_client.get_client()
        assert client is not None

    async def test_set_and_get(self, redis_client):
        """测试SET和GET操作"""
        key = "test:key:1"
        value = "test_value"

        # 设置值
        result = await redis_client.set(key, value, ex=60)
        assert result is True

        # 获取值
        retrieved = await redis_client.get(key)
        assert retrieved == value

        # 清理
        await redis_client.delete(key)

    async def test_delete(self, redis_client):
        """测试DELETE操作"""
        key = "test:key:2"
        await redis_client.set(key, "value")

        # 删除
        deleted_count = await redis_client.delete(key)
        assert deleted_count == 1

        # 验证已删除
        value = await redis_client.get(key)
        assert value is None

    async def test_exists(self, redis_client):
        """测试EXISTS操作"""
        key = "test:key:3"

        # 不存在
        exists = await redis_client.exists(key)
        assert exists == 0

        # 创建
        await redis_client.set(key, "value")
        exists = await redis_client.exists(key)
        assert exists == 1

        # 清理
        await redis_client.delete(key)

    async def test_expire(self, redis_client):
        """测试EXPIRE操作"""
        key = "test:key:4"
        await redis_client.set(key, "value")

        # 设置过期时间
        result = await redis_client.expire(key, 1)
        assert result is True

        # 清理
        await redis_client.delete(key)

    async def test_hash_operations(self, redis_client):
        """测试Hash操作"""
        hash_name = "test:hash:1"
        field1 = "field1"
        value1 = "value1"

        # HSET
        result = await redis_client.hset(hash_name, field1, value1)
        assert result >= 0

        # HGET
        retrieved = await redis_client.hget(hash_name, field1)
        assert retrieved == value1

        # HGETALL
        all_data = await redis_client.hgetall(hash_name)
        assert field1 in all_data
        assert all_data[field1] == value1

        # HDEL
        deleted = await redis_client.hdel(hash_name, field1)
        assert deleted == 1

        # 清理
        await redis_client.delete(hash_name)

    async def test_list_operations(self, redis_client):
        """测试List操作"""
        list_name = "test:list:1"

        # RPUSH
        length = await redis_client.rpush(list_name, "item1", "item2", "item3")
        assert length == 3

        # LRANGE
        items = await redis_client.lrange(list_name, 0, -1)
        assert len(items) == 3
        assert items[0] == "item1"
        assert items[2] == "item3"

        # LLEN
        list_length = await redis_client.llen(list_name)
        assert list_length == 3

        # LPUSH
        await redis_client.lpush(list_name, "item0")
        items = await redis_client.lrange(list_name, 0, -1)
        assert items[0] == "item0"

        # 清理
        await redis_client.delete(list_name)
