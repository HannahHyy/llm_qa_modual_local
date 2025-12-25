"""
应用依赖注入

提供所有服务的依赖注入函数
"""

from functools import lru_cache
from core.config import get_settings, Settings
from infrastructure.clients import (
    RedisClient,
    MySQLClient,
    ESClient,
    Neo4jClient,
    LLMClient
)
from infrastructure.repositories import (
    SessionRepository,
    MessageRepository
)
from domain.parsers import ESIntentParser, Neo4jIntentParser
from domain.retrievers import ESRetriever, Neo4jRetriever, HybridRetriever
from domain.strategies import IntentRoutingStrategy
from domain.services import PromptBuilder, KnowledgeMatcher, MemoryService
from application.services import ChatService, SessionService, StreamingService


# ============= 配置 =============

@lru_cache()
def get_cached_settings() -> Settings:
    """获取缓存的配置"""
    return get_settings()


# ============= 基础设施层 - 客户端 =============

_redis_client = None


async def get_redis_client() -> RedisClient:
    """获取Redis客户端（单例）"""
    global _redis_client
    if _redis_client is None:
        settings = get_cached_settings()
        _redis_client = RedisClient(settings.redis)
        await _redis_client.connect()
    return _redis_client


_mysql_client = None


def get_mysql_client() -> MySQLClient:
    """获取MySQL客户端（单例）"""
    global _mysql_client
    if _mysql_client is None:
        settings = get_cached_settings()
        _mysql_client = MySQLClient(settings.mysql)
        _mysql_client.connect()
    return _mysql_client


_es_client = None


def get_es_client() -> ESClient:
    """获取ES客户端（单例）"""
    global _es_client
    if _es_client is None:
        settings = get_cached_settings()
        _es_client = ESClient(settings.es)
        _es_client.connect()
    return _es_client


_neo4j_client = None


def get_neo4j_client() -> Neo4jClient:
    """获取Neo4j客户端（单例）"""
    global _neo4j_client
    if _neo4j_client is None:
        settings = get_cached_settings()
        _neo4j_client = Neo4jClient(settings.neo4j)
        _neo4j_client.connect()
    return _neo4j_client


_llm_client = None


def get_llm_client() -> LLMClient:
    """获取LLM客户端（单例）"""
    global _llm_client
    if _llm_client is None:
        settings = get_cached_settings()
        _llm_client = LLMClient(settings.llm)
    return _llm_client


# ============= 基础设施层 - 仓储 =============

_session_repository = None


async def get_session_repository() -> SessionRepository:
    """获取会话仓储（单例）"""
    global _session_repository
    if _session_repository is None:
        redis_client = await get_redis_client()
        mysql_client = get_mysql_client()
        es_client = get_es_client()
        _session_repository = SessionRepository(redis_client, mysql_client, es_client)
    return _session_repository


_message_repository = None


async def get_message_repository() -> MessageRepository:
    """获取消息仓储（单例）"""
    global _message_repository
    if _message_repository is None:
        settings = get_cached_settings()
        redis_client = await get_redis_client()
        es_client = get_es_client()
        _message_repository = MessageRepository(redis_client, es_client, settings.es)
    return _message_repository


# ============= 领域层 - 解析器 =============

_es_parser = None


def get_es_parser() -> ESIntentParser:
    """获取ES意图解析器（单例）"""
    global _es_parser
    if _es_parser is None:
        _es_parser = ESIntentParser()
    return _es_parser


_neo4j_parser = None


def get_neo4j_parser() -> Neo4jIntentParser:
    """获取Neo4j意图解析器（单例）"""
    global _neo4j_parser
    if _neo4j_parser is None:
        settings = get_cached_settings()
        es_client = get_es_client()
        llm_client = get_llm_client()
        # 使用配置的Cypher示例索引(默认qa_system,可通过ES_CYPHER_INDEX配置)
        _neo4j_parser = Neo4jIntentParser(
            es_client=es_client,
            llm_client=llm_client,
            cypher_index=settings.es.cypher_index  # 从配置读取
        )
    return _neo4j_parser


# ============= 领域层 - 检索器 =============

_es_retriever = None


def get_es_retriever() -> ESRetriever:
    """获取ES检索器（单例）"""
    global _es_retriever
    if _es_retriever is None:
        settings = get_cached_settings()
        es_client = get_es_client()
        # 使用配置中的知识库索引名
        _es_retriever = ESRetriever(es_client, index_name=settings.es.knowledge_index)
    return _es_retriever


_neo4j_retriever = None


def get_neo4j_retriever() -> Neo4jRetriever:
    """获取Neo4j检索器（单例）"""
    global _neo4j_retriever
    if _neo4j_retriever is None:
        neo4j_client = get_neo4j_client()
        _neo4j_retriever = Neo4jRetriever(neo4j_client)
    return _neo4j_retriever


_hybrid_retriever = None


def get_hybrid_retriever() -> HybridRetriever:
    """获取混合检索器（单例）"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        es_retriever = get_es_retriever()
        neo4j_retriever = get_neo4j_retriever()
        _hybrid_retriever = HybridRetriever(es_retriever, neo4j_retriever)
    return _hybrid_retriever


# ============= 领域层 - 策略和服务 =============

_routing_strategy = None


def get_routing_strategy() -> IntentRoutingStrategy:
    """获取路由策略（单例）"""
    global _routing_strategy
    if _routing_strategy is None:
        es_parser = get_es_parser()
        neo4j_parser = get_neo4j_parser()
        es_retriever = get_es_retriever()
        neo4j_retriever = get_neo4j_retriever()
        hybrid_retriever = get_hybrid_retriever()
        _routing_strategy = IntentRoutingStrategy(
            es_parser,
            neo4j_parser,
            es_retriever,
            neo4j_retriever,
            hybrid_retriever
        )
    return _routing_strategy


_prompt_builder = None


def get_prompt_builder() -> PromptBuilder:
    """获取Prompt构建器（单例）"""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
    return _prompt_builder


_knowledge_matcher = None


def get_knowledge_matcher() -> KnowledgeMatcher:
    """获取知识匹配器（单例）"""
    global _knowledge_matcher
    if _knowledge_matcher is None:
        _knowledge_matcher = KnowledgeMatcher()
    return _knowledge_matcher


_memory_service = None


async def get_memory_service() -> MemoryService:
    """获取记忆服务（单例）"""
    global _memory_service
    if _memory_service is None:
        message_repository = await get_message_repository()
        _memory_service = MemoryService(message_repository)
    return _memory_service


# ============= 应用层 - 服务 =============

_chat_service = None


async def get_chat_service() -> ChatService:
    """获取对话服务（单例）"""
    global _chat_service
    if _chat_service is None:
        routing_strategy = get_routing_strategy()
        prompt_builder = get_prompt_builder()
        knowledge_matcher = get_knowledge_matcher()
        memory_service = await get_memory_service()
        llm_client = get_llm_client()
        session_repository = await get_session_repository()

        _chat_service = ChatService(
            routing_strategy,
            prompt_builder,
            knowledge_matcher,
            memory_service,
            llm_client,
            session_repository
        )
    return _chat_service


_session_service = None


async def get_session_service() -> SessionService:
    """获取会话服务（单例）"""
    global _session_service
    if _session_service is None:
        session_repository = await get_session_repository()
        message_repository = await get_message_repository()
        _session_service = SessionService(session_repository, message_repository)
    return _session_service


_streaming_service = None


async def get_streaming_service() -> StreamingService:
    """获取流式服务（单例）"""
    global _streaming_service
    if _streaming_service is None:
        routing_strategy = get_routing_strategy()
        prompt_builder = get_prompt_builder()
        knowledge_matcher = get_knowledge_matcher()
        memory_service = await get_memory_service()
        llm_client = get_llm_client()
        session_repository = await get_session_repository()

        _streaming_service = StreamingService(
            routing_strategy,
            prompt_builder,
            knowledge_matcher,
            memory_service,
            llm_client,
            session_repository
        )
    return _streaming_service


# ============= 清理函数 =============

async def cleanup_dependencies():
    """清理所有依赖（应用关闭时调用）"""
    global _redis_client, _mysql_client, _es_client, _neo4j_client

    if _redis_client:
        await _redis_client.close()

    if _mysql_client:
        _mysql_client.close()

    if _es_client:
        _es_client.close()

    if _neo4j_client:
        _neo4j_client.close()
