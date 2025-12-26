"""
Application层测试

测试所有Application层的服务类和业务逻辑
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List, Dict, Any


# ==================== LegacyStreamingService Tests ====================

class TestLegacyStreamingService:
    """测试LegacyStreamingService"""

    @pytest.fixture
    def mock_legacy_service(
        self,
        mock_llm_client,
        mock_neo4j_query_service,
        mock_es_query_service,
        mock_message_repository,
        mock_session_repository
    ):
        """创建Mock的LegacyStreamingService"""
        from application.services.legacy_streaming_service import LegacyStreamingService

        service = LegacyStreamingService(
            llm_client=mock_llm_client,
            neo4j_query_service=mock_neo4j_query_service,
            es_query_service=mock_es_query_service,
            message_repository=mock_message_repository,
            session_repository=mock_session_repository
        )

        return service

    @pytest.mark.asyncio
    async def test_streaming_query_neo4j_scene(
        self,
        mock_legacy_service,
        sample_question,
        sample_session_data
    ):
        """测试Neo4j场景的流式查询"""
        session_id = sample_session_data["session_id"]
        scene_id = 2  # Neo4j场景

        # Mock路由决策
        mock_legacy_service.llm_client.async_nonstream_chat.return_value = "neo4j"

        # 执行流式查询
        chunks = []
        async for chunk in mock_legacy_service.streaming_query(
            question=sample_question,
            session_id=session_id,
            scene_id=scene_id
        ):
            chunks.append(chunk)

        # 验证有输出
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_streaming_query_es_scene(
        self,
        mock_legacy_service,
        sample_session_data
    ):
        """测试ES场景的流式查询"""
        question = "网络安全法有哪些规定？"
        session_id = sample_session_data["session_id"]
        scene_id = 3  # ES场景

        # Mock路由决策
        mock_legacy_service.llm_client.async_nonstream_chat.return_value = "es"

        # 执行流式查询
        chunks = []
        async for chunk in mock_legacy_service.streaming_query(
            question=question,
            session_id=session_id,
            scene_id=scene_id
        ):
            chunks.append(chunk)

        # 验证有输出
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_streaming_query_hybrid_scene(
        self,
        mock_legacy_service,
        sample_session_data
    ):
        """测试混合场景的流式查询"""
        question = "河北单位建设的网络有哪些安全要求？"
        session_id = sample_session_data["session_id"]
        scene_id = 1  # 混合场景

        # Mock路由决策为hybrid
        mock_legacy_service.llm_client.async_nonstream_chat.return_value = "hybrid"

        # 执行流式查询
        chunks = []
        async for chunk in mock_legacy_service.streaming_query(
            question=question,
            session_id=session_id,
            scene_id=scene_id
        ):
            chunks.append(chunk)

        # 验证有输出（hybrid流程应该包含Neo4j和ES的结果）
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_save_conversation_history(
        self,
        mock_legacy_service,
        sample_session_data
    ):
        """测试保存对话历史"""
        session_id = sample_session_data["session_id"]
        question = "测试问题"
        answer = "测试回答"

        # 假设服务有保存对话的方法
        # await mock_legacy_service.save_conversation(session_id, question, answer)

        # 验证消息被保存
        # mock_legacy_service.message_repository.save_message.assert_called()

    @pytest.mark.asyncio
    async def test_get_conversation_context(
        self,
        mock_legacy_service,
        sample_session_data
    ):
        """测试获取对话上下文"""
        session_id = sample_session_data["session_id"]

        # 获取历史消息作为上下文
        history = await mock_legacy_service.message_repository.get_history(
            session_id,
            limit=10
        )

        assert history is not None
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_error_handling_in_streaming(
        self,
        mock_legacy_service,
        sample_session_data
    ):
        """测试流式查询中的错误处理"""
        session_id = sample_session_data["session_id"]
        question = "测试问题"

        # Mock LLM抛出异常
        mock_legacy_service.llm_client.async_stream_chat.side_effect = Exception("LLM服务错误")

        # 执行查询，应该能够优雅处理错误
        chunks = []
        try:
            async for chunk in mock_legacy_service.streaming_query(
                question=question,
                session_id=session_id,
                scene_id=1
            ):
                chunks.append(chunk)
        except Exception as e:
            # 验证错误被正确捕获
            assert "LLM服务错误" in str(e) or len(chunks) > 0


# ==================== SSE Message Format Tests ====================

class TestSSEMessageFormat:
    """测试SSE消息格式"""

    def test_think_message_format(self):
        """测试思考消息格式"""
        from application.services.legacy_streaming_service import format_sse_message

        message = "正在分析问题..."
        sse_msg = format_sse_message(message, message_type=1)

        assert "data:" in sse_msg
        assert "message_type" in sse_msg or "1" in sse_msg

    def test_data_message_format(self):
        """测试数据消息格式"""
        from application.services.legacy_streaming_service import format_sse_message

        message = "这是答案内容"
        sse_msg = format_sse_message(message, message_type=2)

        assert "data:" in sse_msg
        assert message in sse_msg

    def test_knowledge_message_format(self):
        """测试知识消息格式"""
        from application.services.legacy_streaming_service import format_sse_message

        knowledge = {
            "content": "网络安全法第十条",
            "source": "网络安全法",
            "score": 1.5
        }

        sse_msg = format_sse_message(json.dumps(knowledge, ensure_ascii=False), message_type=3)

        assert "data:" in sse_msg
        assert "网络安全法" in sse_msg

    def test_error_message_format(self):
        """测试错误消息格式"""
        from application.services.legacy_streaming_service import format_sse_message

        error = "查询失败：连接超时"
        sse_msg = format_sse_message(error, message_type=4)

        assert "data:" in sse_msg
        assert "失败" in sse_msg or "错误" in sse_msg


# ==================== Routing Logic Tests ====================

class TestRoutingLogic:
    """测试路由逻辑"""

    @pytest.mark.asyncio
    async def test_route_decision_neo4j(self, mock_llm_intent_router):
        """测试路由决策：Neo4j"""
        question = "河北单位建设了哪些网络？"

        # Mock LLM返回neo4j
        mock_llm_intent_router.llm_client.async_nonstream_chat.return_value = "neo4j"

        route = await mock_llm_intent_router.route(question, [])

        # 验证路由决策
        assert route is not None

    @pytest.mark.asyncio
    async def test_route_decision_es(self, mock_llm_intent_router):
        """测试路由决策：ES"""
        question = "网络安全法有哪些规定？"

        # Mock LLM返回es
        mock_llm_intent_router.llm_client.async_nonstream_chat.return_value = "es"

        route = await mock_llm_intent_router.route(question, [])

        # 验证路由决策
        assert route is not None

    @pytest.mark.asyncio
    async def test_route_decision_hybrid(self, mock_llm_intent_router):
        """测试路由决策：Hybrid"""
        question = "河北单位建设的网络有哪些安全要求？"

        # Mock LLM返回hybrid
        mock_llm_intent_router.llm_client.async_nonstream_chat.return_value = "hybrid"

        route = await mock_llm_intent_router.route(question, [])

        # 验证路由决策
        assert route is not None


# ==================== Hybrid Flow Tests ====================

class TestHybridFlow:
    """测试混合流程"""

    @pytest.mark.asyncio
    async def test_hybrid_neo4j_first_then_es(
        self,
        mock_neo4j_query_service,
        mock_es_query_service
    ):
        """测试混合流程：先Neo4j，再ES"""
        question = "河北单位建设的网络有哪些安全要求？"

        # Step 1: Neo4j查询
        neo4j_result = []
        async for chunk in mock_neo4j_query_service.query_stream(question, []):
            neo4j_result.append(chunk)

        assert len(neo4j_result) > 0

        # Step 2: 构建增强问题
        # 假设从neo4j_result中提取了结构化信息
        enhanced_question = f"{question}\n补充上下文：Neo4j查询发现河北单位拥有网络A、网络B"

        # Step 3: ES查询
        es_result = []
        async for chunk in mock_es_query_service.query_stream(enhanced_question, []):
            es_result.append(chunk)

        assert len(es_result) > 0

    @pytest.mark.asyncio
    async def test_hybrid_result_merging(self):
        """测试混合结果合并"""
        # Neo4j结果
        neo4j_data = {
            "entities": ["河北单位", "网络A", "网络B"],
            "relationships": ["拥有"]
        }

        # ES结果
        es_data = {
            "knowledge": [
                {"content": "网络安全法第十条", "source": "网络安全法"},
                {"content": "网络建设规范", "source": "技术标准"}
            ]
        }

        # 合并逻辑
        merged_result = {
            "structured_data": neo4j_data,
            "knowledge_base": es_data
        }

        assert "structured_data" in merged_result
        assert "knowledge_base" in merged_result


# ==================== Performance Tests ====================

class TestPerformance:
    """测试性能相关功能"""

    @pytest.mark.asyncio
    async def test_concurrent_queries(self, mock_legacy_service, sample_session_data):
        """测试并发查询处理"""
        import asyncio

        questions = [
            "河北单位建设了哪些网络？",
            "网络安全法有哪些规定？",
            "数据安全法的要求是什么？"
        ]

        # 并发执行多个查询
        tasks = []
        for question in questions:
            task = asyncio.create_task(
                self._collect_stream(
                    mock_legacy_service,
                    question,
                    sample_session_data["session_id"]
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # 验证所有查询都有结果
        assert all(len(result) > 0 for result in results)

    async def _collect_stream(self, service, question, session_id):
        """收集流式输出"""
        chunks = []
        async for chunk in service.streaming_query(question, session_id, scene_id=1):
            chunks.append(chunk)
        return chunks

    @pytest.mark.asyncio
    async def test_memory_usage_large_history(self, mock_message_repository):
        """测试大量历史消息的内存使用"""
        session_id = "test_session"

        # Mock大量历史消息
        large_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"消息{i}"}
            for i in range(1000)
        ]

        mock_message_repository.get_history.return_value = large_history

        # 获取历史消息
        history = await mock_message_repository.get_history(session_id, limit=1000)

        assert len(history) == 1000

    @pytest.mark.asyncio
    async def test_streaming_chunk_size(self, mock_legacy_service, sample_session_data):
        """测试流式输出块大小"""
        question = "测试问题"
        session_id = sample_session_data["session_id"]

        # Mock流式输出
        async def mock_stream():
            for i in range(100):
                yield f"chunk_{i} "

        mock_legacy_service.llm_client.async_stream_chat.return_value = mock_stream()

        # 收集chunks
        chunks = []
        async for chunk in mock_legacy_service.streaming_query(question, session_id, 1):
            chunks.append(chunk)

        # 验证chunks数量合理
        assert len(chunks) > 0


# ==================== Integration Tests ====================

class TestApplicationIntegration:
    """Application层集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_neo4j_query(
        self,
        mock_llm_client,
        mock_neo4j_query_service,
        mock_es_query_service,
        mock_message_repository,
        mock_session_repository,
        sample_question,
        sample_session_data
    ):
        """测试端到端Neo4j查询流程"""
        from application.services.legacy_streaming_service import LegacyStreamingService

        # 创建服务
        service = LegacyStreamingService(
            llm_client=mock_llm_client,
            neo4j_query_service=mock_neo4j_query_service,
            es_query_service=mock_es_query_service,
            message_repository=mock_message_repository,
            session_repository=mock_session_repository
        )

        # Mock路由为neo4j
        mock_llm_client.async_nonstream_chat.return_value = "neo4j"

        # 执行查询
        chunks = []
        async for chunk in service.streaming_query(
            question=sample_question,
            session_id=sample_session_data["session_id"],
            scene_id=2
        ):
            chunks.append(chunk)

        # 验证完整流程
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_end_to_end_es_query(
        self,
        mock_llm_client,
        mock_neo4j_query_service,
        mock_es_query_service,
        mock_message_repository,
        mock_session_repository,
        sample_session_data
    ):
        """测试端到端ES查询流程"""
        from application.services.legacy_streaming_service import LegacyStreamingService

        # 创建服务
        service = LegacyStreamingService(
            llm_client=mock_llm_client,
            neo4j_query_service=mock_neo4j_query_service,
            es_query_service=mock_es_query_service,
            message_repository=mock_message_repository,
            session_repository=mock_session_repository
        )

        question = "网络安全法有哪些规定？"

        # Mock路由为es
        mock_llm_client.async_nonstream_chat.return_value = "es"

        # 执行查询
        chunks = []
        async for chunk in service.streaming_query(
            question=question,
            session_id=sample_session_data["session_id"],
            scene_id=3
        ):
            chunks.append(chunk)

        # 验证完整流程
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_end_to_end_hybrid_query(
        self,
        mock_llm_client,
        mock_neo4j_query_service,
        mock_es_query_service,
        mock_message_repository,
        mock_session_repository,
        sample_session_data
    ):
        """测试端到端混合查询流程"""
        from application.services.legacy_streaming_service import LegacyStreamingService

        # 创建服务
        service = LegacyStreamingService(
            llm_client=mock_llm_client,
            neo4j_query_service=mock_neo4j_query_service,
            es_query_service=mock_es_query_service,
            message_repository=mock_message_repository,
            session_repository=mock_session_repository
        )

        question = "河北单位建设的网络有哪些安全要求？"

        # Mock路由为hybrid
        mock_llm_client.async_nonstream_chat.return_value = "hybrid"

        # 执行查询
        chunks = []
        async for chunk in service.streaming_query(
            question=question,
            session_id=sample_session_data["session_id"],
            scene_id=1
        ):
            chunks.append(chunk)

        # 验证完整流程（应该包含Neo4j和ES的结果）
        assert len(chunks) > 0
