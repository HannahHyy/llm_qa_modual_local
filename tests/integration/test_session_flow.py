"""
会话流程集成测试

测试SessionRepository的完整功能流程
"""

import pytest


@pytest.mark.asyncio
class TestSessionFlow:
    """会话流程集成测试"""

    async def test_create_session_flow(self, session_repository, test_user_id, test_session_name):
        """测试创建会话的完整流程"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, test_session_name)

        # 验证返回值
        assert session_id is not None
        assert len(session_id) > 0

        # 验证可以获取会话列表
        sessions = await session_repository.list_sessions(test_user_id)
        assert len(sessions) > 0
        assert any(s["session_id"] == session_id for s in sessions)

        # 清理
        await session_repository.delete_session(test_user_id, session_id)

    async def test_list_sessions_flow(self, session_repository, test_user_id):
        """测试获取会话列表流程"""
        # 创建多个会话
        session_ids = []
        for i in range(3):
            session_id = await session_repository.create_session(
                test_user_id,
                f"测试会话{i+1}"
            )
            session_ids.append(session_id)

        # 获取会话列表
        sessions = await session_repository.list_sessions(test_user_id)

        # 验证
        assert len(sessions) >= 3
        for session_id in session_ids:
            assert any(s["session_id"] == session_id for s in sessions)

        # 清理
        for session_id in session_ids:
            await session_repository.delete_session(test_user_id, session_id)

    async def test_delete_session_flow(self, session_repository, test_user_id):
        """测试删除会话流程"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, "待删除会话")

        # 删除会话
        await session_repository.delete_session(test_user_id, session_id)

        # 验证会话已删除（从MySQL查询）
        sessions = await session_repository.list_sessions(test_user_id)
        assert not any(s["session_id"] == session_id for s in sessions)

    async def test_redis_cache_flow(self, session_repository, redis_client, test_user_id):
        """测试Redis缓存流程"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, "缓存测试")

        # 验证Redis中存在
        sessions_key = session_repository._sessions_key(test_user_id)
        redis_data = await redis_client.hgetall(sessions_key)
        assert session_id in redis_data

        # 清理
        await session_repository.delete_session(test_user_id, session_id)

    async def test_mysql_persistence_flow(self, session_repository, mysql_client, test_user_id):
        """测试MySQL持久化流程"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, "持久化测试")

        # 直接从MySQL查询
        result = mysql_client.select_by_id("sessions", "session_id", session_id)
        assert result is not None
        assert result["user_id"] == test_user_id
        assert result["is_active"] == 1

        # 清理
        await session_repository.delete_session(test_user_id, session_id)
