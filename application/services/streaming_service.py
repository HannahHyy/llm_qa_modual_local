"""
流式输出服务

处理SSE流式对话
"""

from typing import AsyncGenerator, Dict, Any, Optional, List
import json
import asyncio
from domain.models import Message
from domain.strategies import IntentRoutingStrategy
from domain.services import PromptBuilder, KnowledgeMatcher, MemoryService
from infrastructure.clients.llm_client import LLMClient
from infrastructure.repositories.session_repository import SessionRepository
from core.logging import logger


class StreamingService:
    """
    流式输出服务

    负责SSE流式对话：
    1. 流式意图识别和知识检索
    2. 流式Prompt构建
    3. 流式LLM调用
    4. 流式结果输出
    """

    def __init__(
        self,
        routing_strategy: IntentRoutingStrategy,
        prompt_builder: PromptBuilder,
        knowledge_matcher: KnowledgeMatcher,
        memory_service: MemoryService,
        llm_client: LLMClient,
        session_repository: SessionRepository
    ):
        """
        初始化流式服务

        Args:
            routing_strategy: 意图路由策略
            prompt_builder: Prompt构建器
            knowledge_matcher: 知识匹配器
            memory_service: 记忆服务
            llm_client: LLM客户端
            session_repository: 会话仓储
        """
        self.routing_strategy = routing_strategy
        self.prompt_builder = prompt_builder
        self.knowledge_matcher = knowledge_matcher
        self.memory_service = memory_service
        self.llm_client = llm_client
        self.session_repository = session_repository

    async def chat_stream(
        self,
        user_id: str,
        session_id: str,
        query: str,
        enable_knowledge: bool = True,
        top_k: int = 5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式对话

        Args:
            user_id: 用户ID
            session_id: 会话ID
            query: 用户查询
            enable_knowledge: 是否启用知识检索
            top_k: 知识检索数量
            metadata: 额外元数据

        Yields:
            str: SSE格式的事件数据
        """
        logger.info(f"开始流式对话: user={user_id}, session={session_id}")

        try:
            # 1. 保存用户消息
            await self.memory_service.add_message(user_id, session_id, "user", query)

            # 2. 发送开始事件
            yield self._format_sse_event("start", {"session_id": session_id})

            # 3. 获取对话历史
            history = await self.memory_service.get_context(user_id, session_id)

            # 4. 意图识别和知识检索
            intent = None
            knowledge = []

            if enable_knowledge:
                # 发送检索开始事件
                yield self._format_sse_event("retrieval_start", {})

                intent, knowledge = await self.routing_strategy.route_with_fallback(
                    query=query,
                    context={"history": history},
                    top_k=top_k
                )

                # 知识匹配
                knowledge = self.knowledge_matcher.match(knowledge, intent, query)

                # 发送检索完成事件
                yield self._format_sse_event("retrieval_done", {
                    "intent": intent.to_dict() if intent else None,
                    "knowledge_count": len(knowledge)
                })

            # 5. 构建Prompt
            messages = self.prompt_builder.build_streaming_prompt(
                current_query=query,
                history=history,
                knowledge=knowledge
            )

            # 6. 流式调用LLM
            assistant_reply = ""
            async for chunk in self.llm_client.chat_completion_stream(messages):
                # 提取内容
                content = chunk.get("delta", {}).get("content", "")
                if content:
                    assistant_reply += content

                    # 发送内容块
                    yield self._format_sse_event("content", {"text": content})

            # 7. 保存助手回复
            await self.memory_service.add_message(
                user_id, session_id, "assistant", assistant_reply
            )

            # 8. 更新会话时间戳
            await self.session_repository.update_session_timestamp(user_id, session_id)

            # 9. 发送完成事件
            yield self._format_sse_event("done", {
                "session_id": session_id,
                "total_length": len(assistant_reply)
            })

            logger.info(f"流式对话完成: session={session_id}, length={len(assistant_reply)}")

        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}")
            # 发送错误事件
            yield self._format_sse_event("error", {"message": str(e)})

    async def chat_stream_with_knowledge_streaming(
        self,
        user_id: str,
        session_id: str,
        query: str,
        top_k: int = 5
    ) -> AsyncGenerator[str, None]:
        """
        流式对话（包含知识检索流式输出）

        Args:
            user_id: 用户ID
            session_id: 会话ID
            query: 用户查询
            top_k: 知识检索数量

        Yields:
            str: SSE格式的事件数据
        """
        logger.info(f"开始知识流式对话: user={user_id}, session={session_id}")

        try:
            # 1. 保存用户消息并发送开始事件
            await self.memory_service.add_message(user_id, session_id, "user", query)
            yield self._format_sse_event("start", {"session_id": session_id})

            # 2. 获取历史
            history = await self.memory_service.get_context(user_id, session_id)

            # 3. 意图识别
            yield self._format_sse_event("intent_parsing", {})
            intent, knowledge = await self.routing_strategy.route(query, top_k=top_k)

            yield self._format_sse_event("intent_parsed", {
                "intent_type": intent.intent_type,
                "confidence": intent.confidence
            })

            # 4. 流式发送知识
            for i, k in enumerate(knowledge):
                yield self._format_sse_event("knowledge", {
                    "index": i,
                    "title": k.title,
                    "content": k.content[:100] + "..." if len(k.content) > 100 else k.content,
                    "score": k.score
                })

            # 5. 匹配知识
            knowledge = self.knowledge_matcher.match(knowledge, intent, query)

            # 6. 构建Prompt并流式生成
            messages = self.prompt_builder.build_streaming_prompt(query, history, knowledge)

            assistant_reply = ""
            async for chunk in self.llm_client.chat_completion_stream(messages):
                content = chunk.get("delta", {}).get("content", "")
                if content:
                    assistant_reply += content
                    yield self._format_sse_event("content", {"text": content})

            # 7. 保存并完成
            await self.memory_service.add_message(user_id, session_id, "assistant", assistant_reply)
            await self.session_repository.update_session_timestamp(user_id, session_id)

            yield self._format_sse_event("done", {
                "session_id": session_id,
                "knowledge_used": len(knowledge)
            })

        except Exception as e:
            logger.error(f"知识流式对话失败: {str(e)}")
            yield self._format_sse_event("error", {"message": str(e)})

    def _format_sse_event(self, event: str, data: Dict[str, Any]) -> str:
        """
        格式化SSE事件

        Args:
            event: 事件类型
            data: 事件数据

        Returns:
            str: SSE格式的字符串
        """
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def get_stream_status(
        self,
        user_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        获取流式输出状态（预留接口）

        Args:
            user_id: 用户ID
            session_id: 会话ID

        Returns:
            Dict: 状态信息
        """
        # 这里可以实现流状态追踪
        return {
            "session_id": session_id,
            "status": "idle"
        }

    async def cancel_stream(
        self,
        user_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        取消流式输出（预留接口）

        Args:
            user_id: 用户ID
            session_id: 会话ID

        Returns:
            Dict: 取消结果
        """
        # 这里可以实现流取消逻辑
        logger.info(f"取消流式输出: session={session_id}")
        return {
            "session_id": session_id,
            "cancelled": True
        }
