"""
消息仓储

负责消息的CRUD操作，实现Redis-ES双层存储。
"""

import json
from datetime import datetime
from typing import List, Dict, Any

from ..clients import RedisClient, ESClient
from core.config import ESSettings
from core.exceptions import DatabaseError
from core.logging import get_logger

logger = get_logger("MessageRepository")


class MessageRepository:
    """消息仓储类"""

    def __init__(
        self,
        redis_client: RedisClient,
        es_client: ESClient,
        es_settings: ESSettings,
    ):
        """
        初始化消息仓储

        Args:
            redis_client: Redis客户端
            es_client: ES客户端
            es_settings: ES配置
        """
        self.redis = redis_client
        self.es = es_client
        self.es_settings = es_settings

    def _messages_key(self, user_id: str, session_id: str) -> str:
        """生成消息列表的Redis key"""
        return f"chat:{user_id}:session:{session_id}:messages"

    async def get_messages(
        self,
        user_id: str,
        session_id: str
    ) -> List[Dict[str, Any]]:
        """
        获取会话的所有消息

        Args:
            user_id: 用户ID
            session_id: 会话ID

        Returns:
            消息列表

        数据流：Redis → ES（缓存未命中时）→ Redis（回填）
        """
        key = self._messages_key(user_id, session_id)

        try:
            # 1. 先从Redis获取
            items = await self.redis.lrange(key, 0, -1)
            if items:
                messages = []
                for item in items:
                    try:
                        messages.append(json.loads(item))
                    except json.JSONDecodeError:
                        logger.warning(f"解析消息失败: {item}")
                        continue
                logger.info(f"[Redis] 获取消息成功: count={len(messages)}")
                return messages

            # 2. Redis未命中，从ES获取
            messages = await self._get_messages_from_es(user_id, session_id)

            # 3. 回填Redis
            if messages:
                for msg in messages:
                    await self.redis.rpush(key, json.dumps(msg, ensure_ascii=False))
                await self.redis.expire(key, 86400)  # 24小时过期
                logger.info(f"[缓存回填] 从ES获取{len(messages)}条消息并回填到Redis")

            return messages

        except Exception as e:
            logger.error(f"获取消息失败: {e}")
            raise DatabaseError(f"获取消息失败: {e}", details=str(e))

    async def _get_messages_from_es(
        self,
        user_id: str,
        session_id: str
    ) -> List[Dict[str, Any]]:
        """从ES获取消息"""
        try:
            query = {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"term": {"session_id": session_id}}
                    ]
                }
            }

            result = self.es.search(
                index=self.es_settings.conversation_index,
                query=query,
                size=1000
            )

            messages = []
            for hit in result.get("hits", {}).get("hits", []):
                source = hit["_source"]
                for msg in source.get("messages", []):
                    messages.append({
                        "role": msg.get("role", ""),
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp", "")
                    })

            # 按时间排序
            messages.sort(key=lambda x: x.get("timestamp", ""))
            logger.info(f"[ES] 获取消息成功: count={len(messages)}")
            return messages

        except Exception as e:
            logger.warning(f"[ES] 获取消息失败: {e}")
            return []

    async def append_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str
    ) -> None:
        """
        追加消息

        Args:
            user_id: 用户ID
            session_id: 会话ID
            role: 角色（user/assistant）
            content: 消息内容

        数据流：Redis（实时） + ES（持久化）并行写入
        """
        timestamp = datetime.utcnow().isoformat()
        message = {
            "role": role,
            "content": content,
            "timestamp": timestamp
        }

        try:
            # 1. 写入Redis（实时缓存）
            key = self._messages_key(user_id, session_id)
            await self.redis.rpush(key, json.dumps(message, ensure_ascii=False))
            await self.redis.expire(key, 86400)  # 24小时过期
            logger.info(f"[Redis] 消息追加成功: role={role}")

            # 2. 写入ES（持久化）
            # 注意：实际应该通过后台任务异步写入
            try:
                message_id = f"msg_{session_id}_{int(datetime.utcnow().timestamp() * 1000)}"

                # 使用update API追加消息到messages数组
                # 这里简化处理，实际应该使用ES的update API
                self.es.index_document(
                    index=self.es_settings.conversation_index,
                    document={
                        "user_id": user_id,
                        "session_id": session_id,
                        "message_id": message_id,
                        "role": role,
                        "content": content,
                        "timestamp": timestamp,
                        "message_order": 0  # 简化处理
                    },
                    doc_id=message_id
                )
                logger.info(f"[ES] 消息索引成功: message_id={message_id}")
            except Exception as e:
                logger.warning(f"[ES] 消息索引失败（非致命错误）: {e}")

        except Exception as e:
            logger.error(f"追加消息失败: {e}")
            raise DatabaseError(f"追加消息失败: {e}", details=str(e))

    async def clear_messages(self, user_id: str, session_id: str) -> None:
        """
        清空会话消息

        Args:
            user_id: 用户ID
            session_id: 会话ID
        """
        try:
            key = self._messages_key(user_id, session_id)
            await self.redis.delete(key)
            logger.info(f"[Redis] 消息清空成功: session_id={session_id}")
        except Exception as e:
            logger.error(f"清空消息失败: {e}")
            raise DatabaseError(f"清空消息失败: {e}", details=str(e))
