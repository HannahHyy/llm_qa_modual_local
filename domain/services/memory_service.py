"""
记忆服务

负责管理对话历史和上下文记忆
"""

from typing import List, Optional, Dict, Any
from domain.models import Message
from infrastructure.repositories.message_repository import MessageRepository
from core.logging import logger


class MemoryService:
    """
    记忆服务

    管理对话历史、上下文窗口和记忆优化
    """

    def __init__(
        self,
        message_repository: MessageRepository,
        max_context_messages: int = 10,
        max_tokens: int = 4000
    ):
        """
        初始化记忆服务

        Args:
            message_repository: 消息仓储
            max_context_messages: 最大上下文消息数
            max_tokens: 最大token数（估算）
        """
        self.message_repository = message_repository
        self.max_context_messages = max_context_messages
        self.max_tokens = max_tokens

    async def get_context(
        self,
        user_id: str,
        session_id: str,
        include_system: bool = False
    ) -> List[Message]:
        """
        获取对话上下文

        Args:
            user_id: 用户ID
            session_id: 会话ID
            include_system: 是否包含系统消息

        Returns:
            List[Message]: 上下文消息列表
        """
        try:
            # 从repository获取消息
            messages_data = await self.message_repository.get_messages(
                user_id,
                session_id
            )

            # 转换为Message对象
            messages = [Message(**msg) for msg in messages_data]

            # 过滤系统消息
            if not include_system:
                messages = [msg for msg in messages if msg.role != "system"]

            # 应用上下文窗口限制
            context_messages = self._apply_context_window(messages)

            logger.info(
                f"获取上下文: user={user_id}, session={session_id}, "
                f"总消息数={len(messages)}, 上下文数={len(context_messages)}"
            )

            return context_messages

        except Exception as e:
            logger.error(f"获取上下文失败: {str(e)}")
            return []

    async def add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str
    ) -> None:
        """
        添加消息到记忆

        Args:
            user_id: 用户ID
            session_id: 会话ID
            role: 角色（user/assistant/system）
            content: 消息内容
        """
        try:
            await self.message_repository.append_message(
                user_id,
                session_id,
                role,
                content
            )
            logger.info(f"添加消息: user={user_id}, session={session_id}, role={role}")

        except Exception as e:
            logger.error(f"添加消息失败: {str(e)}")
            raise

    async def clear_context(self, user_id: str, session_id: str) -> None:
        """
        清空对话上下文

        Args:
            user_id: 用户ID
            session_id: 会话ID
        """
        try:
            await self.message_repository.clear_messages(user_id, session_id)
            logger.info(f"清空上下文: user={user_id}, session={session_id}")

        except Exception as e:
            logger.error(f"清空上下文失败: {str(e)}")
            raise

    def _apply_context_window(self, messages: List[Message]) -> List[Message]:
        """
        应用上下文窗口限制

        Args:
            messages: 原始消息列表

        Returns:
            List[Message]: 限制后的消息列表
        """
        if not messages:
            return []

        # 1. 按数量限制
        if len(messages) > self.max_context_messages:
            messages = messages[-self.max_context_messages:]

        # 2. 按token数限制（简单估算）
        messages = self._limit_by_tokens(messages)

        return messages

    def _limit_by_tokens(self, messages: List[Message]) -> List[Message]:
        """
        按token数限制消息

        Args:
            messages: 消息列表

        Returns:
            List[Message]: 限制后的消息列表
        """
        # 简单估算：2字符约等于1个token
        total_tokens = 0
        limited_messages = []

        # 从最新的消息开始计算
        for msg in reversed(messages):
            msg_tokens = len(msg.content) // 2
            if total_tokens + msg_tokens > self.max_tokens:
                break
            limited_messages.insert(0, msg)
            total_tokens += msg_tokens

        return limited_messages

    def get_recent_summary(self, messages: List[Message], max_length: int = 200) -> str:
        """
        获取最近对话的摘要

        Args:
            messages: 消息列表
            max_length: 最大摘要长度

        Returns:
            str: 对话摘要
        """
        if not messages:
            return "暂无对话历史"

        # 获取最近几条消息
        recent = messages[-4:] if len(messages) > 4 else messages

        # 构建摘要
        summary_parts = []
        for msg in recent:
            prefix = "用户" if msg.is_user() else "助手"
            content = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
            summary_parts.append(f"{prefix}: {content}")

        summary = " | ".join(summary_parts)

        # 截断到最大长度
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."

        return summary

    def get_conversation_stats(self, messages: List[Message]) -> Dict[str, Any]:
        """
        获取对话统计信息

        Args:
            messages: 消息列表

        Returns:
            Dict: 统计信息
        """
        if not messages:
            return {
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "avg_user_length": 0,
                "avg_assistant_length": 0
            }

        user_messages = [msg for msg in messages if msg.is_user()]
        assistant_messages = [msg for msg in messages if msg.is_assistant()]

        user_lengths = [len(msg.content) for msg in user_messages]
        assistant_lengths = [len(msg.content) for msg in assistant_messages]

        return {
            "total_messages": len(messages),
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages),
            "avg_user_length": sum(user_lengths) // len(user_lengths) if user_lengths else 0,
            "avg_assistant_length": sum(assistant_lengths) // len(assistant_lengths) if assistant_lengths else 0
        }

    async def get_context_with_summary(
        self,
        user_id: str,
        session_id: str,
        summarize_old: bool = True
    ) -> tuple[List[Message], Optional[str]]:
        """
        获取上下文，并为旧消息生成摘要

        Args:
            user_id: 用户ID
            session_id: 会话ID
            summarize_old: 是否对旧消息生成摘要

        Returns:
            tuple: (上下文消息列表, 旧消息摘要)
        """
        # 获取所有消息
        all_messages_data = await self.message_repository.get_messages(
            user_id,
            session_id
        )
        all_messages = [Message(**msg) for msg in all_messages_data]

        # 如果消息数量在限制内，不需要摘要
        if len(all_messages) <= self.max_context_messages:
            return all_messages, None

        # 分离旧消息和新消息
        old_messages = all_messages[:-self.max_context_messages]
        recent_messages = all_messages[-self.max_context_messages:]

        # 生成旧消息摘要
        summary = None
        if summarize_old and old_messages:
            summary = f"早期对话摘要（共{len(old_messages)}条）：" + self.get_recent_summary(old_messages)

        return recent_messages, summary
