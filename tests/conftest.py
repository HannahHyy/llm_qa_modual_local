"""
Pytest配置文件

提供测试fixtures和全局配置
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import AsyncGenerator, Generator, Dict, List, Any
from datetime import datetime


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== Mock Client Fixtures ====================

@pytest.fixture
def mock_llm_client():
    """Mock LLM客户端"""
    from infrastructure.clients.llm_client import LLMClient

    mock = MagicMock(spec=LLMClient)

    # Mock同步非流式响应
    mock.sync_nonstream_chat.return_value = "Mock LLM response"

    # Mock同步流式响应
    def sync_stream_gen():
        for chunk in ["Mock ", "LLM ", "stream ", "response"]:
            yield chunk
    mock.sync_stream_chat.return_value = sync_stream_gen()

    # Mock异步非流式响应
    async def async_nonstream():
        return "Mock async LLM response"
    mock.async_nonstream_chat = AsyncMock(side_effect=async_nonstream)

    # Mock异步流式响应
    async def async_stream_gen():
        for chunk in ["Mock ", "async ", "LLM ", "stream"]:
            yield chunk
    mock.async_stream_chat.return_value = async_stream_gen()

    return mock


@pytest.fixture
def mock_es_client():
    """Mock ES客户端"""
    from infrastructure.clients.es_client import ESClient

    mock = MagicMock(spec=ESClient)

    # Mock搜索结果
    mock.search.return_value = {
        "hits": {
            "total": {"value": 10},
            "max_score": 1.5,
            "hits": [
                {
                    "_index": "kb_vector_store",
                    "_id": "1",
                    "_score": 1.5,
                    "_source": {
                        "content": "测试文档内容1",
                        "source": "测试来源1",
                        "metadata": {"type": "法规"}
                    }
                },
                {
                    "_index": "kb_vector_store",
                    "_id": "2",
                    "_score": 1.2,
                    "_source": {
                        "content": "测试文档内容2",
                        "source": "测试来源2",
                        "metadata": {"type": "标准"}
                    }
                }
            ]
        }
    }

    # Mock索引操作
    mock.index.return_value = {"_id": "test_id", "result": "created"}
    mock.delete.return_value = {"result": "deleted"}
    mock.update.return_value = {"result": "updated"}

    # Mock批量操作
    mock.bulk.return_value = {
        "took": 10,
        "errors": False,
        "items": []
    }

    return mock


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j客户端"""
    from infrastructure.clients.neo4j_client import Neo4jClient

    mock = MagicMock(spec=Neo4jClient)

    # Mock查询结果
    mock.query.return_value = [
        {
            "u.name": "河北单位",
            "n.name": "河北网络1",
            "type": "网络"
        },
        {
            "u.name": "河北单位",
            "n.name": "河北网络2",
            "type": "网络"
        }
    ]

    # Mock连接测试
    mock.test_connection.return_value = True

    # Mock关闭
    mock.close.return_value = None

    return mock


@pytest.fixture
def mock_redis_client():
    """Mock Redis客户端"""
    mock = MagicMock()

    # Mock基本操作
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = 1
    mock.exists.return_value = False

    # Mock过期时间
    mock.expire.return_value = True
    mock.ttl.return_value = -1

    return mock


@pytest.fixture
def mock_mysql_client():
    """Mock MySQL客户端"""
    mock = MagicMock()

    # Mock查询结果
    async def execute_mock(*args, **kwargs):
        return []

    mock.execute = AsyncMock(side_effect=execute_mock)
    mock.fetch_one = AsyncMock(return_value=None)
    mock.fetch_all = AsyncMock(return_value=[])

    return mock


# ==================== Mock Service Fixtures ====================

@pytest.fixture
def mock_neo4j_query_service(mock_llm_client, mock_neo4j_client, mock_es_client):
    """Mock Neo4j查询服务"""
    from domain.services.neo4j_query_service import Neo4jQueryService

    # 使用mock客户端创建服务
    service = Neo4jQueryService(
        llm_client=mock_llm_client,
        neo4j_client=mock_neo4j_client,
        es_client=mock_es_client
    )

    return service


@pytest.fixture
def mock_es_query_service(mock_llm_client, mock_es_client):
    """Mock ES查询服务"""
    from domain.services.es_query_service import ESQueryService

    service = ESQueryService(
        llm_client=mock_llm_client,
        es_client=mock_es_client
    )

    return service


@pytest.fixture
def mock_llm_intent_router(mock_llm_client):
    """Mock LLM意图路由器"""
    from domain.strategies.llm_intent_router import LLMIntentRouter

    router = LLMIntentRouter(llm_client=mock_llm_client)

    return router


# ==================== Mock Repository Fixtures ====================

@pytest.fixture
def mock_session_repository():
    """Mock会话仓储"""
    from infrastructure.repositories.session_repository import SessionRepository

    mock = MagicMock(spec=SessionRepository)

    # Mock查询会话
    async def get_session_mock(session_id: str):
        return {
            "session_id": session_id,
            "user_id": "test_user",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "is_active": True
        }

    mock.get_session = AsyncMock(side_effect=get_session_mock)

    # Mock创建会话
    async def create_session_mock(session_data: Dict):
        return session_data

    mock.create_session = AsyncMock(side_effect=create_session_mock)

    # Mock更新会话
    async def update_session_mock(session_id: str, updates: Dict):
        return True

    mock.update_session = AsyncMock(side_effect=update_session_mock)

    return mock


@pytest.fixture
def mock_message_repository():
    """Mock消息仓储"""
    from infrastructure.repositories.message_repository import MessageRepository

    mock = MagicMock(spec=MessageRepository)

    # Mock获取历史消息
    async def get_history_mock(session_id: str, limit: int = 10):
        return [
            {
                "role": "user",
                "content": "测试问题1",
                "timestamp": datetime.now()
            },
            {
                "role": "assistant",
                "content": "测试回答1",
                "timestamp": datetime.now()
            }
        ]

    mock.get_history = AsyncMock(side_effect=get_history_mock)

    # Mock保存消息
    async def save_message_mock(session_id: str, message: Dict):
        return True

    mock.save_message = AsyncMock(side_effect=save_message_mock)

    return mock


# ==================== Test Data Fixtures ====================

@pytest.fixture
def sample_question():
    """测试问题样本"""
    return "河北单位建设了哪些网络？"


@pytest.fixture
def sample_history():
    """测试历史消息样本"""
    return [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮助你的？"}
    ]


@pytest.fixture
def sample_session_data():
    """测试会话数据样本"""
    return {
        "session_id": "test_session_123",
        "user_id": "test_user",
        "scene_id": 1,
        "created_at": datetime.now(),
        "is_active": True
    }


@pytest.fixture
def sample_neo4j_intent():
    """测试Neo4j意图样本"""
    return {
        "num": 3,
        "entities": {
            "单位": ["河北单位"],
            "网络": []
        },
        "relations": ["拥有"],
        "properties": {},
        "additional_context": "查询单位拥有的网络资源"
    }


@pytest.fixture
def sample_es_intent():
    """测试ES意图样本"""
    return {
        "num": 5,
        "rewritten_query": "网络安全法规定",
        "retrieval_type": "semantic_search",
        "regulation_standards": ["网络安全法"],
        "source_standard": [],
        "entities": {
            "法律法规": ["网络安全法"],
            "技术术语": ["网络安全"]
        },
        "reason": "用户询问网络安全法的相关规定"
    }


@pytest.fixture
def sample_cypher_examples():
    """测试Cypher示例样本"""
    return [
        {
            "intent": "查询单位建设的网络",
            "example": "河北单位建设了哪些网络?",
            "cypher": "MATCH (u:单位)-[:拥有]->(n:网络) WHERE u.name CONTAINS '河北' RETURN u.name, n.name",
            "description": "查询特定单位拥有的网络资源"
        },
        {
            "intent": "查询网络使用的系统",
            "example": "某网络使用了哪些系统?",
            "cypher": "MATCH (n:网络)-[:使用]->(s:系统) WHERE n.name CONTAINS '某网络' RETURN n.name, s.name",
            "description": "查询网络所使用的系统"
        }
    ]


# ==================== Auto-cleanup Fixtures ====================

@pytest.fixture(autouse=True)
def reset_singletons():
    """每个测试后重置单例（如果有的话）"""
    yield
    # 清理逻辑可以在这里添加
    pass


@pytest.fixture(autouse=True)
def mock_environment(monkeypatch):
    """Mock环境变量"""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    yield
