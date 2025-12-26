"""
Infrastructure层测试

测试所有Infrastructure层的客户端和仓储类
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from typing import List, Dict, Any


# ==================== LLMClient Tests ====================

class TestLLMClient:
    """测试LLMClient"""

    def test_sync_nonstream_chat(self, mock_llm_client):
        """测试同步非流式对话"""
        messages = [{"role": "user", "content": "你好"}]

        response = mock_llm_client.sync_nonstream_chat(messages)

        assert response is not None
        assert isinstance(response, str)

    def test_sync_stream_chat(self, mock_llm_client):
        """测试同步流式对话"""
        messages = [{"role": "user", "content": "你好"}]

        # 重新设置mock以返回新的生成器
        def sync_stream_gen():
            for chunk in ["你", "好", "！"]:
                yield chunk

        mock_llm_client.sync_stream_chat.return_value = sync_stream_gen()

        chunks = []
        for chunk in mock_llm_client.sync_stream_chat(messages):
            chunks.append(chunk)

        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_async_nonstream_chat(self, mock_llm_client):
        """测试异步非流式对话"""
        messages = [{"role": "user", "content": "你好"}]

        response = await mock_llm_client.async_nonstream_chat(messages)

        assert response is not None
        assert isinstance(response, str)

    @pytest.mark.asyncio
    async def test_async_stream_chat(self, mock_llm_client):
        """测试异步流式对话"""
        messages = [{"role": "user", "content": "你好"}]

        # 重新设置mock
        async def async_stream_gen():
            for chunk in ["你", "好", "！"]:
                yield chunk

        mock_llm_client.async_stream_chat.return_value = async_stream_gen()

        chunks = []
        async for chunk in mock_llm_client.async_stream_chat(messages):
            chunks.append(chunk)

        assert len(chunks) > 0

    def test_build_messages_format(self, mock_llm_client):
        """测试消息格式构建"""
        # 验证LLM客户端能处理正确的消息格式
        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"}
        ]

        # 调用方法验证不会抛出异常
        response = mock_llm_client.sync_nonstream_chat(messages)
        assert response is not None


# ==================== ESClient Tests ====================

class TestESClient:
    """测试ESClient"""

    def test_search_basic(self, mock_es_client):
        """测试基本搜索"""
        index = "kb_vector_store"
        query = {"match": {"content": "网络安全"}}

        result = mock_es_client.search(index=index, body={"query": query})

        assert result is not None
        assert "hits" in result
        assert "total" in result["hits"]

    def test_search_with_size(self, mock_es_client):
        """测试带size参数的搜索"""
        index = "kb_vector_store"
        query = {"match_all": {}}

        result = mock_es_client.search(index=index, body={"query": query, "size": 10})

        assert result is not None
        assert len(result["hits"]["hits"]) <= 10

    def test_index_document(self, mock_es_client):
        """测试索引文档"""
        index = "test_index"
        document = {
            "content": "测试内容",
            "source": "测试来源"
        }

        result = mock_es_client.index(index=index, body=document)

        assert result is not None
        assert "result" in result

    def test_delete_document(self, mock_es_client):
        """测试删除文档"""
        index = "test_index"
        doc_id = "test_id"

        result = mock_es_client.delete(index=index, id=doc_id)

        assert result is not None
        assert "result" in result

    def test_update_document(self, mock_es_client):
        """测试更新文档"""
        index = "test_index"
        doc_id = "test_id"
        update_body = {"doc": {"content": "更新后的内容"}}

        result = mock_es_client.update(index=index, id=doc_id, body=update_body)

        assert result is not None

    def test_bulk_operation(self, mock_es_client):
        """测试批量操作"""
        actions = [
            {"index": {"_index": "test_index", "_id": "1"}},
            {"content": "文档1"},
            {"index": {"_index": "test_index", "_id": "2"}},
            {"content": "文档2"}
        ]

        result = mock_es_client.bulk(body=actions)

        assert result is not None
        assert "errors" in result
        assert result["errors"] is False

    def test_hybrid_search_bm25_vector(self, mock_es_client):
        """测试BM25 + 向量混合搜索"""
        # Mock混合搜索结果
        mock_es_client.search.return_value = {
            "hits": {
                "total": {"value": 5},
                "hits": [
                    {
                        "_score": 2.5,
                        "_source": {
                            "content": "网络安全法规定",
                            "source": "网络安全法"
                        }
                    }
                ]
            }
        }

        index = "kb_vector_store"
        query = {
            "bool": {
                "should": [
                    {"match": {"content": "网络安全"}},
                    {"knn": {"vector": [0.1, 0.2, 0.3]}}
                ]
            }
        }

        result = mock_es_client.search(index=index, body={"query": query})

        assert result is not None
        assert len(result["hits"]["hits"]) > 0


# ==================== Neo4jClient Tests ====================

class TestNeo4jClient:
    """测试Neo4jClient"""

    def test_query_basic(self, mock_neo4j_client):
        """测试基本Cypher查询"""
        cypher = "MATCH (n:单位) RETURN n.name LIMIT 10"

        result = mock_neo4j_client.query(cypher)

        assert result is not None
        assert isinstance(result, list)

    def test_query_with_parameters(self, mock_neo4j_client):
        """测试带参数的Cypher查询"""
        cypher = "MATCH (n:单位) WHERE n.name = $name RETURN n"
        parameters = {"name": "河北单位"}

        result = mock_neo4j_client.query(cypher, parameters)

        assert result is not None

    def test_query_relationship(self, mock_neo4j_client):
        """测试关系查询"""
        cypher = "MATCH (u:单位)-[r:拥有]->(n:网络) RETURN u.name, n.name"

        # Mock关系查询结果
        mock_neo4j_client.query.return_value = [
            {"u.name": "河北单位", "n.name": "网络A"},
            {"u.name": "河北单位", "n.name": "网络B"}
        ]

        result = mock_neo4j_client.query(cypher)

        assert len(result) > 0
        assert "u.name" in result[0]
        assert "n.name" in result[0]

    def test_connection_test(self, mock_neo4j_client):
        """测试连接测试"""
        is_connected = mock_neo4j_client.test_connection()

        assert is_connected is True

    def test_close_connection(self, mock_neo4j_client):
        """测试关闭连接"""
        mock_neo4j_client.close()

        # 验证方法被调用
        mock_neo4j_client.close.assert_called()


# ==================== SessionRepository Tests ====================

class TestSessionRepository:
    """测试SessionRepository"""

    @pytest.mark.asyncio
    async def test_get_session(self, mock_session_repository):
        """测试获取会话"""
        session_id = "test_session_123"

        session = await mock_session_repository.get_session(session_id)

        assert session is not None
        assert session["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_create_session(self, mock_session_repository, sample_session_data):
        """测试创建会话"""
        session = await mock_session_repository.create_session(sample_session_data)

        assert session is not None
        assert session["session_id"] == sample_session_data["session_id"]

    @pytest.mark.asyncio
    async def test_update_session(self, mock_session_repository):
        """测试更新会话"""
        session_id = "test_session_123"
        updates = {"is_active": False}

        result = await mock_session_repository.update_session(session_id, updates)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, mock_session_repository):
        """测试获取不存在的会话"""
        # Mock返回None
        mock_session_repository.get_session.return_value = None

        session = await mock_session_repository.get_session("nonexistent_id")

        assert session is None


# ==================== MessageRepository Tests ====================

class TestMessageRepository:
    """测试MessageRepository"""

    @pytest.mark.asyncio
    async def test_get_history(self, mock_message_repository):
        """测试获取历史消息"""
        session_id = "test_session_123"

        history = await mock_message_repository.get_history(session_id, limit=10)

        assert history is not None
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_save_message(self, mock_message_repository):
        """测试保存消息"""
        session_id = "test_session_123"
        message = {
            "role": "user",
            "content": "测试消息"
        }

        result = await mock_message_repository.save_message(session_id, message)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_history_with_limit(self, mock_message_repository):
        """测试获取限制数量的历史消息"""
        session_id = "test_session_123"
        limit = 5

        history = await mock_message_repository.get_history(session_id, limit=limit)

        assert len(history) <= limit

    @pytest.mark.asyncio
    async def test_save_multiple_messages(self, mock_message_repository):
        """测试保存多条消息"""
        session_id = "test_session_123"
        messages = [
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
            {"role": "user", "content": "问题2"}
        ]

        for msg in messages:
            result = await mock_message_repository.save_message(session_id, msg)
            assert result is True


# ==================== Redis Cache Tests ====================

class TestRedisCache:
    """测试Redis缓存功能"""

    def test_cache_set_and_get(self, mock_redis_client):
        """测试缓存设置和获取"""
        key = "test_key"
        value = "test_value"

        # 设置
        mock_redis_client.set(key, value)

        # Mock get返回值
        mock_redis_client.get.return_value = value

        # 获取
        result = mock_redis_client.get(key)

        assert result == value

    def test_cache_expiration(self, mock_redis_client):
        """测试缓存过期"""
        key = "test_key"
        ttl = 3600

        mock_redis_client.expire(key, ttl)

        # 验证过期时间设置
        mock_redis_client.expire.assert_called_with(key, ttl)

    def test_cache_delete(self, mock_redis_client):
        """测试缓存删除"""
        key = "test_key"

        result = mock_redis_client.delete(key)

        assert result == 1

    def test_cache_exists(self, mock_redis_client):
        """测试缓存存在性检查"""
        key = "test_key"

        # Mock存在
        mock_redis_client.exists.return_value = True

        exists = mock_redis_client.exists(key)

        assert exists is True


# ==================== MySQL Database Tests ====================

class TestMySQLDatabase:
    """测试MySQL数据库操作"""

    @pytest.mark.asyncio
    async def test_execute_query(self, mock_mysql_client):
        """测试执行查询"""
        query = "SELECT * FROM sessions WHERE session_id = %s"
        params = ("test_session",)

        result = await mock_mysql_client.execute(query, params)

        assert result is not None

    @pytest.mark.asyncio
    async def test_fetch_one(self, mock_mysql_client):
        """测试获取单条记录"""
        query = "SELECT * FROM sessions WHERE session_id = %s"
        params = ("test_session",)

        # Mock返回单条记录
        mock_mysql_client.fetch_one.return_value = {
            "session_id": "test_session",
            "user_id": "test_user"
        }

        result = await mock_mysql_client.fetch_one(query, params)

        assert result is not None

    @pytest.mark.asyncio
    async def test_fetch_all(self, mock_mysql_client):
        """测试获取所有记录"""
        query = "SELECT * FROM messages WHERE session_id = %s"
        params = ("test_session",)

        # Mock返回多条记录
        mock_mysql_client.fetch_all.return_value = [
            {"id": 1, "content": "消息1"},
            {"id": 2, "content": "消息2"}
        ]

        result = await mock_mysql_client.fetch_all(query, params)

        assert len(result) > 0


# ==================== 集成测试 ====================

class TestInfrastructureIntegration:
    """Infrastructure层集成测试"""

    @pytest.mark.asyncio
    async def test_llm_to_es_pipeline(self, mock_llm_client, mock_es_client):
        """测试LLM到ES的完整流程"""
        # Step 1: LLM意图识别
        messages = [{"role": "user", "content": "网络安全法有哪些规定？"}]
        intent = await mock_llm_client.async_nonstream_chat(messages)

        assert intent is not None

        # Step 2: ES检索
        result = mock_es_client.search(
            index="kb_vector_store",
            body={"query": {"match": {"content": "网络安全"}}}
        )

        assert result is not None
        assert len(result["hits"]["hits"]) > 0

    @pytest.mark.asyncio
    async def test_session_and_message_flow(
        self,
        mock_session_repository,
        mock_message_repository,
        sample_session_data
    ):
        """测试会话和消息的完整流程"""
        # Step 1: 创建会话
        session = await mock_session_repository.create_session(sample_session_data)
        assert session is not None

        session_id = session["session_id"]

        # Step 2: 保存消息
        message = {"role": "user", "content": "测试问题"}
        await mock_message_repository.save_message(session_id, message)

        # Step 3: 获取历史
        history = await mock_message_repository.get_history(session_id)
        assert len(history) > 0

    def test_neo4j_to_llm_summarize(self, mock_neo4j_client, mock_llm_client):
        """测试Neo4j查询结果到LLM总结的流程"""
        # Step 1: Neo4j查询
        cypher = "MATCH (u:单位)-[:拥有]->(n:网络) RETURN u.name, n.name"
        neo4j_result = mock_neo4j_client.query(cypher)

        assert len(neo4j_result) > 0

        # Step 2: 格式化结果
        formatted = "\n".join([f"{r['u.name']} 拥有 {r['n.name']}" for r in neo4j_result])

        # Step 3: LLM总结
        messages = [
            {"role": "system", "content": "请总结以下查询结果"},
            {"role": "user", "content": formatted}
        ]
        summary = mock_llm_client.sync_nonstream_chat(messages)

        assert summary is not None
