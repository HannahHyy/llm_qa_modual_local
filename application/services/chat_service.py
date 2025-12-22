"""
对话服务

协调意图识别、知识检索、Prompt构建和LLM调用
"""

from typing import Dict, Any, Optional, List
from domain.models import Message, Intent, Knowledge
from domain.strategies import IntentRoutingStrategy
from domain.services import PromptBuilder, KnowledgeMatcher, MemoryService
from infrastructure.clients.llm_client import LLMClient
from infrastructure.repositories.session_repository import SessionRepository
from core.logging import logger


class ChatService:
    """
    对话服务

    负责完整的对话流程：
    1. 获取对话历史
    2. 意图识别和路由
    3. 知识检索和匹配
    4. Prompt构建
    5. LLM调用
    6. 结果保存
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
        初始化对话服务

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

    async def chat(
        self,
        user_id: str,
        session_id: str,
        query: str,
        enable_knowledge: bool = True,
        top_k: int = 5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        处理对话请求

        Args:
            user_id: 用户ID
            session_id: 会话ID
            query: 用户查询
            enable_knowledge: 是否启用知识检索
            top_k: 知识检索数量
            metadata: 额外元数据

        Returns:
            Dict: 对话结果
        """
        logger.info(f"开始对话: user={user_id}, session={session_id}, query='{query}'")

        try:
            # 1. 保存用户消息
            await self.memory_service.add_message(
                user_id, session_id, "user", query
            )

            # 2. 获取对话历史
            history = await self.memory_service.get_context(user_id, session_id)

            # 3. 意图识别和知识检索
            intent = None
            knowledge = []

            if enable_knowledge:
                intent, knowledge = await self.routing_strategy.route_with_fallback(
                    query=query,
                    context={"history": history},
                    top_k=top_k
                )

                # 4. 知识匹配和过滤
                knowledge = self.knowledge_matcher.match(
                    knowledge,
                    intent,
                    query
                )

            # 5. 构建Prompt
            messages = self.prompt_builder.build_prompt(
                current_query=query,
                history=history,
                knowledge=knowledge,
                metadata=metadata
            )

            # 6. 调用LLM
            llm_response = await self.llm_client.chat_completion(
                messages=messages,
                stream=False
            )

            assistant_reply = llm_response.get("content", "")

            # 7. 保存助手回复
            await self.memory_service.add_message(
                user_id, session_id, "assistant", assistant_reply
            )

            # 8. 更新会话时间戳
            await self.session_repository.update_session_timestamp(
                user_id, session_id
            )

            # 9. 构建返回结果
            result = {
                "session_id": session_id,
                "query": query,
                "response": assistant_reply,
                "intent": intent.to_dict() if intent else None,
                "knowledge_count": len(knowledge),
                "knowledge": [k.to_dict() for k in knowledge] if knowledge else [],
                "metadata": {
                    "llm_model": llm_response.get("model"),
                    "usage": llm_response.get("usage", {}),
                    "history_length": len(history)
                }
            }

            logger.info(
                f"对话完成: session={session_id}, "
                f"knowledge={len(knowledge)}, "
                f"response_length={len(assistant_reply)}"
            )

            return result

        except Exception as e:
            logger.error(f"对话失败: {str(e)}")
            raise

    async def chat_with_options(
        self,
        user_id: str,
        session_id: str,
        query: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        带选项的对话

        Args:
            user_id: 用户ID
            session_id: 会话ID
            query: 用户查询
            options: 对话选项

        Returns:
            Dict: 对话结果
        """
        options = options or {}

        return await self.chat(
            user_id=user_id,
            session_id=session_id,
            query=query,
            enable_knowledge=options.get("enable_knowledge", True),
            top_k=options.get("top_k", 5),
            metadata=options.get("metadata")
        )

    async def regenerate_response(
        self,
        user_id: str,
        session_id: str,
        enable_knowledge: bool = True,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        重新生成最后一次回复

        Args:
            user_id: 用户ID
            session_id: 会话ID
            enable_knowledge: 是否启用知识检索
            top_k: 知识检索数量

        Returns:
            Dict: 对话结果
        """
        logger.info(f"重新生成回复: session={session_id}")

        try:
            # 获取对话历史
            history = await self.memory_service.get_context(user_id, session_id)

            if not history:
                raise ValueError("没有对话历史，无法重新生成")

            # 找到最后一条用户消息
            last_user_message = None
            for msg in reversed(history):
                if msg.is_user():
                    last_user_message = msg
                    break

            if not last_user_message:
                raise ValueError("没有找到用户消息")

            # 移除最后一条助手回复（如果存在）
            if history[-1].is_assistant():
                # 这里简化处理，实际应该删除Redis/ES中的消息
                history = history[:-1]

            # 重新调用chat
            return await self.chat(
                user_id=user_id,
                session_id=session_id,
                query=last_user_message.content,
                enable_knowledge=enable_knowledge,
                top_k=top_k
            )

        except Exception as e:
            logger.error(f"重新生成失败: {str(e)}")
            raise

    async def get_conversation_summary(
        self,
        user_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        获取对话摘要

        Args:
            user_id: 用户ID
            session_id: 会话ID

        Returns:
            Dict: 对话摘要
        """
        try:
            # 获取对话历史
            history = await self.memory_service.get_context(user_id, session_id)

            # 获取统计信息
            stats = self.memory_service.get_conversation_stats(history)

            # 获取最近摘要
            summary = self.memory_service.get_recent_summary(history)

            return {
                "session_id": session_id,
                "summary": summary,
                "stats": stats
            }

        except Exception as e:
            logger.error(f"获取对话摘要失败: {str(e)}")
            raise
