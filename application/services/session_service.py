"""
会话服务

管理会话的创建、查询、删除等操作
"""

from typing import List, Dict, Any, Optional
from infrastructure.repositories.session_repository import SessionRepository
from infrastructure.repositories.message_repository import MessageRepository
from core.logging import logger


class SessionService:
    """
    会话服务

    负责会话管理：
    1. 创建会话
    2. 查询会话列表
    3. 获取会话详情
    4. 删除会话
    5. 重命名会话
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        message_repository: MessageRepository
    ):
        """
        初始化会话服务

        Args:
            session_repository: 会话仓储
            message_repository: 消息仓储
        """
        self.session_repository = session_repository
        self.message_repository = message_repository

    async def create_session(
        self,
        user_id: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建新会话

        Args:
            user_id: 用户ID
            name: 会话名称（可选）

        Returns:
            Dict: 会话信息
        """
        logger.info(f"创建会话: user={user_id}, name={name}")

        try:
            # 创建会话
            session_id = await self.session_repository.create_session(
                user_id,
                name or "新对话"
            )

            # 获取会话信息
            session = await self.session_repository.get_session(user_id, session_id)

            logger.info(f"会话创建成功: session_id={session_id}")

            return {
                "session_id": session_id,
                "user_id": user_id,
                "name": session.get("name"),
                "created_at": session.get("created_at"),
                "message_count": 0
            }

        except Exception as e:
            logger.error(f"创建会话失败: {str(e)}")
            raise

    async def list_sessions(
        self,
        user_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取用户会话列表

        Args:
            user_id: 用户ID
            limit: 限制数量
            offset: 偏移量

        Returns:
            Dict: 会话列表和统计信息
        """
        logger.info(f"获取会话列表: user={user_id}, limit={limit}, offset={offset}")

        try:
            # 获取所有会话
            all_sessions = await self.session_repository.list_sessions(user_id)

            # 应用分页
            total = len(all_sessions)
            sessions = all_sessions[offset:]
            if limit:
                sessions = sessions[:limit]

            # 为每个会话添加消息数量
            enriched_sessions = []
            for session in sessions:
                session_id = session.get("session_id")

                # 获取消息数量
                messages = await self.message_repository.get_messages(user_id, session_id)
                message_count = len(messages)

                enriched_sessions.append({
                    **session,
                    "message_count": message_count
                })

            return {
                "sessions": enriched_sessions,
                "total": total,
                "limit": limit,
                "offset": offset
            }

        except Exception as e:
            logger.error(f"获取会话列表失败: {str(e)}")
            raise

    async def get_session(
        self,
        user_id: str,
        session_id: str,
        include_messages: bool = False
    ) -> Dict[str, Any]:
        """
        获取会话详情

        Args:
            user_id: 用户ID
            session_id: 会话ID
            include_messages: 是否包含消息历史

        Returns:
            Dict: 会话详情
        """
        logger.info(f"获取会话详情: user={user_id}, session={session_id}")

        try:
            # 获取会话信息
            session = await self.session_repository.get_session(user_id, session_id)

            if not session:
                raise ValueError(f"会话不存在: {session_id}")

            # 获取消息
            messages = await self.message_repository.get_messages(user_id, session_id)

            result = {
                **session,
                "message_count": len(messages)
            }

            # 如果需要包含消息
            if include_messages:
                result["messages"] = messages

            return result

        except Exception as e:
            logger.error(f"获取会话详情失败: {str(e)}")
            raise

    async def delete_session(
        self,
        user_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        删除会话

        Args:
            user_id: 用户ID
            session_id: 会话ID

        Returns:
            Dict: 删除结果
        """
        logger.info(f"删除会话: user={user_id}, session={session_id}")

        try:
            # 先清空消息
            await self.message_repository.clear_messages(user_id, session_id)

            # 删除会话
            await self.session_repository.delete_session(user_id, session_id)

            logger.info(f"会话删除成功: session_id={session_id}")

            return {
                "session_id": session_id,
                "deleted": True
            }

        except Exception as e:
            logger.error(f"删除会话失败: {str(e)}")
            raise

    async def rename_session(
        self,
        user_id: str,
        session_id: str,
        new_name: str
    ) -> Dict[str, Any]:
        """
        重命名会话

        Args:
            user_id: 用户ID
            session_id: 会话ID
            new_name: 新名称

        Returns:
            Dict: 更新后的会话信息
        """
        logger.info(f"重命名会话: session={session_id}, new_name={new_name}")

        try:
            # 更新会话名称
            await self.session_repository.rename_session(user_id, session_id, new_name)

            # 获取更新后的会话
            session = await self.session_repository.get_session(user_id, session_id)

            logger.info(f"会话重命名成功: session_id={session_id}")

            return session

        except Exception as e:
            logger.error(f"重命名会话失败: {str(e)}")
            raise

    async def clear_session_messages(
        self,
        user_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        清空会话消息

        Args:
            user_id: 用户ID
            session_id: 会话ID

        Returns:
            Dict: 清空结果
        """
        logger.info(f"清空会话消息: session={session_id}")

        try:
            # 清空消息
            await self.message_repository.clear_messages(user_id, session_id)

            logger.info(f"会话消息清空成功: session_id={session_id}")

            return {
                "session_id": session_id,
                "cleared": True
            }

        except Exception as e:
            logger.error(f"清空会话消息失败: {str(e)}")
            raise

    async def get_active_sessions(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取最近活跃的会话

        Args:
            user_id: 用户ID
            limit: 限制数量

        Returns:
            List[Dict]: 活跃会话列表
        """
        logger.info(f"获取活跃会话: user={user_id}, limit={limit}")

        try:
            # 获取所有会话
            sessions = await self.session_repository.list_sessions(user_id)

            # 按更新时间排序
            sessions.sort(
                key=lambda s: s.get("updated_at", ""),
                reverse=True
            )

            # 限制数量
            active_sessions = sessions[:limit]

            return active_sessions

        except Exception as e:
            logger.error(f"获取活跃会话失败: {str(e)}")
            raise
