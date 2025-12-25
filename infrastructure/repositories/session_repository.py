"""
会话仓储

负责会话的CRUD操作，实现Redis-MySQL-ES三层数据同步。
"""

import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..clients import RedisClient, MySQLClient, ESClient
from core.exceptions import DatabaseError
from core.logging import get_logger

logger = get_logger("SessionRepository")


class SessionRepository:
    """会话仓储类"""

    def __init__(
        self,
        redis_client: RedisClient,
        mysql_client: MySQLClient,
        es_client: ESClient,
    ):
        """
        初始化会话仓储

        Args:
            redis_client: Redis客户端
            mysql_client: MySQL客户端
            es_client: ES客户端
        """
        self.redis = redis_client
        self.mysql = mysql_client
        self.es = es_client

    def _sessions_key(self, user_id: str) -> str:
        """生成会话列表的Redis key"""
        return f"chat:{user_id}:sessions"

    async def create_session(
        self,
        user_id: str,
        name: Optional[str] = None
    ) -> str:
        """
        创建新会话

        Args:
            user_id: 用户ID
            name: 会话名称

        Returns:
            会话ID

        数据流：MySQL → Redis → ES
        """
        session_id = str(uuid.uuid4())
        session_name = name or "对话"
        created_at = datetime.utcnow()

        try:
            # 1. 写入MySQL（主数据源）
            # 首先确保用户存在
            self.mysql.execute_update(
                "INSERT IGNORE INTO users (user_id, username, created_at) VALUES (%s, %s, %s)",
                (user_id, f"用户_{user_id[:8]}", created_at)
            )

            # 插入会话记录
            self.mysql.execute_update(
                "INSERT INTO sessions (session_id, user_id, name, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (session_id, user_id, session_name, created_at, created_at)
            )
            logger.info(f"[MySQL] 会话创建成功: session_id={session_id}")

            # 2. 写入Redis（缓存）
            meta = {
                "name": session_name,
                "created_at": created_at.isoformat()
            }
            await self.redis.hset(
                self._sessions_key(user_id),
                session_id,
                json.dumps(meta, ensure_ascii=False)
            )
            logger.info(f"[Redis] 会话缓存成功: session_id={session_id}")

            # 3. 写入ES（异步，用于检索）
            # 注意：实际应该通过后台任务异步写入
            try:
                self.es.index_document(
                    index=self.es.settings.conversation_index,
                    document={
                        "user_id": user_id,
                        "session_id": session_id,
                        "session_name": session_name,
                        "created_at": created_at.isoformat(),
                        "messages": []
                    },
                    doc_id=f"{user_id}_{session_id}"
                )
                logger.info(f"[ES] 会话索引成功: session_id={session_id}")
            except Exception as e:
                logger.warning(f"[ES] 会话索引失败（非致命错误）: {e}")

            return session_id

        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            raise DatabaseError(f"创建会话失败: {e}", details=str(e))

    async def get_session(
        self,
        user_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        获取单个会话详情

        Args:
            user_id: 用户ID
            session_id: 会话ID

        Returns:
            会话详情字典

        Raises:
            ValueError: 会话不存在时抛出
        """
        try:
            # 从MySQL获取会话信息
            rows = self.mysql.execute_query(
                "SELECT session_id, user_id, name, created_at, updated_at "
                "FROM sessions WHERE session_id = %s AND user_id = %s AND is_active = 1",
                (session_id, user_id)
            )

            if not rows:
                raise ValueError(f"会话不存在: {session_id}")

            row = rows[0]
            return {
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "name": row["name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
            }

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"获取会话失败: {e}")
            raise DatabaseError(f"获取会话失败: {e}", details=str(e))

    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有会话列表

        Args:
            user_id: 用户ID

        Returns:
            会话列表
        """
        try:
            # 直接从MySQL获取完整信息（包括updated_at）
            rows = self.mysql.execute_query(
                "SELECT session_id, name, created_at, updated_at FROM sessions "
                "WHERE user_id = %s AND is_active = 1 "
                "ORDER BY updated_at DESC",
                (user_id,)
            )

            sessions = []
            for row in rows:
                session = {
                    "session_id": row["session_id"],
                    "name": row["name"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                }
                sessions.append(session)

            logger.info(f"[MySQL] 获取会话列表成功: user_id={user_id}, count={len(sessions)}")
            return sessions

        except Exception as e:
            logger.error(f"获取会话列表失败: {e}")
            raise DatabaseError(f"获取会话列表失败: {e}", details=str(e))

    async def delete_session(self, user_id: str, session_id: str) -> None:
        """
        删除会话

        Args:
            user_id: 用户ID
            session_id: 会话ID
        """
        try:
            # 1. MySQL软删除
            self.mysql.execute_update(
                "UPDATE sessions SET is_active = 0 WHERE session_id = %s",
                (session_id,)
            )
            logger.info(f"[MySQL] 会话删除成功: session_id={session_id}")

            # 2. 删除Redis缓存
            await self.redis.hdel(self._sessions_key(user_id), session_id)
            logger.info(f"[Redis] 会话缓存删除成功: session_id={session_id}")

            # 3. 删除ES文档
            try:
                self.es.delete_document(
                    index=self.es.settings.conversation_index,
                    doc_id=f"{user_id}_{session_id}"
                )
                logger.info(f"[ES] 会话文档删除成功: session_id={session_id}")
            except Exception as e:
                logger.warning(f"[ES] 会话文档删除失败（非致命错误）: {e}")

        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            raise DatabaseError(f"删除会话失败: {e}", details=str(e))

    async def update_session_time(self, session_id: str) -> None:
        """
        更新会话的最后活跃时间

        Args:
            session_id: 会话ID
        """
        try:
            self.mysql.execute_update(
                "UPDATE sessions SET updated_at = %s WHERE session_id = %s",
                (datetime.utcnow(), session_id)
            )
        except Exception as e:
            logger.warning(f"更新会话时间失败（非致命错误）: {e}")

    async def update_session_timestamp(self, session_id: str) -> None:
        """
        更新会话时间戳(兼容old版本的方法名)

        Args:
            session_id: 会话ID
        """
        await self.update_session_time(session_id)
