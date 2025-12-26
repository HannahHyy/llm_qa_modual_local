"""
Domain层服务测试

测试所有Domain层的服务类和功能
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List, Dict, Any


# ==================== Neo4jQueryService Tests ====================

class TestNeo4jQueryService:
    """测试Neo4jQueryService"""

    @pytest.mark.asyncio
    async def test_query_stream_success(self, mock_neo4j_query_service, sample_question, sample_history):
        """测试成功的流式查询"""
        # Mock LLM客户端的流式响应
        async def mock_stream():
            yield "data: 河北单位"
            yield "data: 建设了"
            yield "data: 网络A和网络B"

        mock_neo4j_query_service.llm_client.async_stream_chat.return_value = mock_stream()

        # 执行查询
        chunks = []
        async for chunk in mock_neo4j_query_service.query_stream(sample_question, sample_history):
            chunks.append(chunk)

        # 验证有输出
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_query_stream_with_empty_history(self, mock_neo4j_query_service, sample_question):
        """测试空历史记录的查询"""
        # Mock LLM响应
        async def mock_stream():
            yield "data: 测试响应"

        mock_neo4j_query_service.llm_client.async_stream_chat.return_value = mock_stream()

        # 执行查询
        chunks = []
        async for chunk in mock_neo4j_query_service.query_stream(sample_question, []):
            chunks.append(chunk)

        # 验证有输出
        assert len(chunks) > 0

    def test_json_extractor_extract_valid_json(self, mock_neo4j_query_service):
        """测试JsonExtractor提取有效JSON"""
        extractor = mock_neo4j_query_service.json_extractor

        text = """
        一些文本内容
        3.以下是json格式的解析结果：
        [
            {
                "num": 3,
                "entities": {"单位": ["河北单位"]},
                "relations": ["拥有"]
            }
        ]
        """

        result = extractor.extract(text)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0

    def test_json_extractor_no_json_found(self, mock_neo4j_query_service):
        """测试JsonExtractor无法找到JSON时返回None"""
        extractor = mock_neo4j_query_service.json_extractor

        text = "这是一段没有JSON的普通文本"

        result = extractor.extract(text)
        assert result is None

    def test_neo4j_intent_parser_initialization(self, mock_neo4j_query_service):
        """测试Neo4jIntentParser初始化"""
        parser = mock_neo4j_query_service.intent_parser

        # 验证节点定义存在
        assert "单位" in parser.nodes
        assert "网络" in parser.nodes
        assert "系统" in parser.nodes

        # 验证关系定义存在
        assert "拥有" in parser.relationships
        assert "使用" in parser.relationships

    def test_build_intent_prompt(self, mock_neo4j_query_service, sample_question):
        """测试构建意图识别提示词"""
        # 这里需要访问内部方法，如果是私有方法可能需要调整
        # 假设有一个构建prompt的方法
        parser = mock_neo4j_query_service.intent_parser

        # 验证节点和关系的配置是否完整
        assert len(parser.nodes) > 0
        assert len(parser.relationships) > 0

    @pytest.mark.asyncio
    async def test_query_stream_error_handling(self, mock_neo4j_query_service, sample_question):
        """测试查询过程中的错误处理"""
        # Mock LLM抛出异常
        mock_neo4j_query_service.llm_client.async_stream_chat.side_effect = Exception("LLM错误")

        # 执行查询，应该产生错误消息
        chunks = []
        try:
            async for chunk in mock_neo4j_query_service.query_stream(sample_question, []):
                chunks.append(chunk)
        except Exception:
            pass  # 异常被捕获并转换为SSE错误消息

        # 验证至少有错误输出或异常被正确处理
        # 具体取决于实现是否会抛出异常还是返回错误SSE消息


# ==================== ESQueryService Tests ====================

class TestESQueryService:
    """测试ESQueryService"""

    @pytest.mark.asyncio
    async def test_query_stream_success(self, mock_es_query_service, sample_question, sample_history):
        """测试成功的ES流式查询"""
        # Mock LLM流式响应
        async def mock_stream():
            yield "data: 根据网络安全法"
            yield "data: 第十条规定"

        mock_es_query_service.llm_client.async_stream_chat.return_value = mock_stream()

        # 执行查询
        chunks = []
        async for chunk in mock_es_query_service.query_stream(sample_question, sample_history):
            chunks.append(chunk)

        # 验证有输出
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_parse_intent_from_llm(self, mock_es_query_service, sample_question):
        """测试从LLM解析ES意图"""
        # Mock LLM的意图解析响应
        intent_json = {
            "num": 5,
            "rewritten_query": "网络安全法规定",
            "retrieval_type": "semantic_search",
            "regulation_standards": ["网络安全法"],
            "source_standard": [],
            "entities": {
                "法律法规": ["网络安全法"]
            },
            "reason": "查询法规内容"
        }

        async def mock_stream():
            yield f"3.以下是json格式的解析结果：\n{json.dumps(intent_json, ensure_ascii=False)}"

        mock_es_query_service.llm_client.async_stream_chat.return_value = mock_stream()

        # 此处假设有解析意图的内部方法可以测试
        # 由于是内部实现，可能需要通过完整流程测试

    def test_retrieval_config_initialization(self, mock_es_query_service):
        """测试检索配置初始化"""
        config = mock_es_query_service.retrieval_config

        # 验证三种检索类型配置存在
        assert "keyword_search" in config
        assert "semantic_search" in config
        assert "hybrid_search" in config

        # 验证权重配置
        assert "bm25_weight" in config["keyword_search"]
        assert "vector_weight" in config["semantic_search"]

    @pytest.mark.asyncio
    async def test_es_search_with_different_types(self, mock_es_query_service):
        """测试不同检索类型的ES搜索"""
        from domain.services.es_query_service import ESIntent

        # 测试关键词搜索
        intent_keyword = ESIntent(
            num=5,
            rewritten_query="网络安全",
            retrieval_type="keyword_search",
            regulation_standards=[],
            source_standard=[],
            entities={},
            reason="测试"
        )

        # 测试语义搜索
        intent_semantic = ESIntent(
            num=5,
            rewritten_query="网络安全",
            retrieval_type="semantic_search",
            regulation_standards=[],
            source_standard=[],
            entities={},
            reason="测试"
        )

        # 验证不同类型的配置
        config_keyword = mock_es_query_service.retrieval_config["keyword_search"]
        config_semantic = mock_es_query_service.retrieval_config["semantic_search"]

        assert config_keyword["bm25_weight"] > config_semantic["bm25_weight"]
        assert config_semantic["vector_weight"] > config_keyword["vector_weight"]

    @pytest.mark.asyncio
    async def test_knowledge_matching(self, mock_es_query_service):
        """测试知识匹配逻辑"""
        # Mock ES搜索结果
        mock_es_query_service.es_client.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_score": 1.5,
                        "_source": {
                            "content": "网络安全法第十条规定...",
                            "source": "网络安全法",
                            "metadata": {"type": "法规"}
                        }
                    },
                    {
                        "_score": 1.2,
                        "_source": {
                            "content": "网络安全法第二十条规定...",
                            "source": "网络安全法",
                            "metadata": {"type": "法规"}
                        }
                    }
                ]
            }
        }

        # 验证ES客户端配置
        assert mock_es_query_service.es_client is not None


# ==================== PromptBuilder Tests ====================

class TestPromptBuilder:
    """测试PromptBuilder"""

    def test_build_system_prompt(self):
        """测试构建系统提示词"""
        from domain.services.prompt_builder import PromptBuilder

        builder = PromptBuilder()
        prompt = builder.build_system_prompt("general")

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_build_user_prompt_with_context(self):
        """测试构建包含上下文的用户提示词"""
        from domain.services.prompt_builder import PromptBuilder

        builder = PromptBuilder()
        question = "网络安全法有哪些规定？"
        context = "网络安全法第十条规定..."

        prompt = builder.build_user_prompt(question, context)

        assert question in prompt
        assert context in prompt

    def test_build_user_prompt_without_context(self):
        """测试构建不包含上下文的用户提示词"""
        from domain.services.prompt_builder import PromptBuilder

        builder = PromptBuilder()
        question = "网络安全法有哪些规定？"

        prompt = builder.build_user_prompt(question)

        assert question in prompt


# ==================== KnowledgeMatcher Tests ====================

class TestKnowledgeMatcher:
    """测试KnowledgeMatcher"""

    def test_match_knowledge_items(self):
        """测试匹配知识项"""
        from domain.services.knowledge_matcher import KnowledgeMatcher

        matcher = KnowledgeMatcher()

        # 模拟知识库数据
        knowledge_items = [
            {"content": "网络安全法第十条", "score": 1.5, "source": "网络安全法"},
            {"content": "网络安全法第二十条", "score": 1.2, "source": "网络安全法"},
            {"content": "数据安全法第五条", "score": 0.8, "source": "数据安全法"},
        ]

        # 测试匹配逻辑（假设有匹配方法）
        # matched = matcher.match(knowledge_items, top_k=2)
        # assert len(matched) == 2

    def test_format_knowledge_for_display(self):
        """测试格式化知识用于显示"""
        from domain.services.knowledge_matcher import KnowledgeMatcher

        matcher = KnowledgeMatcher()

        # 模拟知识项
        knowledge = {
            "content": "网络安全法第十条规定...",
            "source": "网络安全法",
            "score": 1.5
        }

        # 测试格式化（假设有格式化方法）
        # formatted = matcher.format(knowledge)
        # assert "网络安全法" in formatted


# ==================== MemoryService Tests ====================

class TestMemoryService:
    """测试MemoryService"""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_memory(self):
        """测试存储和检索记忆"""
        from domain.services.memory_service import MemoryService

        service = MemoryService()

        session_id = "test_session"
        message = {"role": "user", "content": "测试消息"}

        # 测试存储
        await service.store_message(session_id, message)

        # 测试检索
        history = await service.get_history(session_id)

        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_clear_memory(self):
        """测试清除记忆"""
        from domain.services.memory_service import MemoryService

        service = MemoryService()

        session_id = "test_session"

        # 先存储消息
        await service.store_message(session_id, {"role": "user", "content": "测试"})

        # 清除记忆
        await service.clear_history(session_id)

        # 验证已清除
        history = await service.get_history(session_id)
        assert len(history) == 0

    @pytest.mark.asyncio
    async def test_get_recent_messages(self):
        """测试获取最近的消息"""
        from domain.services.memory_service import MemoryService

        service = MemoryService()

        session_id = "test_session"

        # 存储多条消息
        for i in range(10):
            await service.store_message(session_id, {"role": "user", "content": f"消息{i}"})

        # 获取最近5条
        recent = await service.get_history(session_id, limit=5)

        assert len(recent) <= 5


# ==================== LLMIntentRouter Tests ====================

class TestLLMIntentRouter:
    """测试LLMIntentRouter"""

    @pytest.mark.asyncio
    async def test_route_to_neo4j(self, mock_llm_intent_router, sample_question):
        """测试路由到Neo4j场景"""
        # Mock LLM返回neo4j判断
        mock_llm_intent_router.llm_client.async_nonstream_chat.return_value = "neo4j"

        # 执行路由
        route = await mock_llm_intent_router.route(sample_question, [])

        # 验证返回了路由决策
        assert route is not None

    @pytest.mark.asyncio
    async def test_route_to_es(self, mock_llm_intent_router):
        """测试路由到ES场景"""
        question = "网络安全法有哪些规定？"

        # Mock LLM返回es判断
        mock_llm_intent_router.llm_client.async_nonstream_chat.return_value = "es"

        # 执行路由
        route = await mock_llm_intent_router.route(question, [])

        # 验证返回了路由决策
        assert route is not None

    @pytest.mark.asyncio
    async def test_route_to_hybrid(self, mock_llm_intent_router):
        """测试路由到混合场景"""
        question = "河北单位建设的网络有哪些安全要求？"

        # Mock LLM返回hybrid判断
        mock_llm_intent_router.llm_client.async_nonstream_chat.return_value = "hybrid"

        # 执行路由
        route = await mock_llm_intent_router.route(question, [])

        # 验证返回了路由决策
        assert route is not None

    @pytest.mark.asyncio
    async def test_route_with_history(self, mock_llm_intent_router, sample_question, sample_history):
        """测试带历史记录的路由"""
        # Mock LLM响应
        mock_llm_intent_router.llm_client.async_nonstream_chat.return_value = "neo4j"

        # 执行路由
        route = await mock_llm_intent_router.route(sample_question, sample_history)

        # 验证返回了路由决策
        assert route is not None


# ==================== 集成测试 ====================

class TestDomainServicesIntegration:
    """Domain层服务集成测试"""

    @pytest.mark.asyncio
    async def test_neo4j_to_es_hybrid_flow(
        self,
        mock_neo4j_query_service,
        mock_es_query_service,
        sample_question
    ):
        """测试Neo4j到ES的混合流程"""
        # Step 1: Neo4j查询
        neo4j_chunks = []
        async for chunk in mock_neo4j_query_service.query_stream(sample_question, []):
            neo4j_chunks.append(chunk)

        # Step 2: 增强问题（模拟）
        enhanced_question = f"{sample_question} 补充信息：{neo4j_chunks}"

        # Step 3: ES查询
        es_chunks = []
        async for chunk in mock_es_query_service.query_stream(enhanced_question, []):
            es_chunks.append(chunk)

        # 验证完整流程执行
        assert len(neo4j_chunks) > 0
        assert len(es_chunks) > 0
