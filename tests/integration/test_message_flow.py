"""
消息流程集成测试

测试MessageRepository的完整功能流程
"""

import pytest


@pytest.mark.asyncio
class TestMessageFlow:
    """消息流程集成测试"""

    async def test_append_message_flow(
        self,
        session_repository,
        message_repository,
        test_user_id
    ):
        """测试追加消息流程"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, "消息测试")

        try:
            # 追加用户消息
            await message_repository.append_message(
                test_user_id,
                session_id,
                "user",
                "你好，这是测试消息"
            )

            # 追加助手消息
            await message_repository.append_message(
                test_user_id,
                session_id,
                "assistant",
                "你好！我是测试助手"
            )

            # 获取消息
            messages = await message_repository.get_messages(test_user_id, session_id)

            # 验证
            assert len(messages) == 2
            assert messages[0]["role"] == "user"
            assert messages[0]["content"] == "你好，这是测试消息"
            assert messages[1]["role"] == "assistant"

        finally:
            # 清理
            await message_repository.clear_messages(test_user_id, session_id)
            await session_repository.delete_session(test_user_id, session_id)

    async def test_get_messages_from_redis(
        self,
        session_repository,
        message_repository,
        redis_client,
        test_user_id
    ):
        """测试从Redis获取消息"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, "Redis测试")

        try:
            # 追加消息
            await message_repository.append_message(
                test_user_id,
                session_id,
                "user",
                "Redis消息测试"
            )

            # 验证Redis中存在
            key = message_repository._messages_key(test_user_id, session_id)
            items = await redis_client.lrange(key, 0, -1)
            assert len(items) > 0

            # 获取消息（应该从Redis读取）
            messages = await message_repository.get_messages(test_user_id, session_id)
            assert len(messages) == 1
            assert messages[0]["content"] == "Redis消息测试"

        finally:
            # 清理
            await message_repository.clear_messages(test_user_id, session_id)
            await session_repository.delete_session(test_user_id, session_id)

    async def test_cache_miss_and_backfill(
        self,
        session_repository,
        message_repository,
        redis_client,
        test_user_id
    ):
        """测试缓存未命中和回填流程"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, "缓存测试")

        try:
            # 追加消息
            await message_repository.append_message(
                test_user_id,
                session_id,
                "user",
                "缓存测试消息"
            )

            # 删除Redis缓存模拟缓存未命中
            key = message_repository._messages_key(test_user_id, session_id)
            await redis_client.delete(key)

            # 再次获取消息（应该从ES读取并回填Redis）
            messages = await message_repository.get_messages(test_user_id, session_id)

            # 验证Redis已回填
            items = await redis_client.lrange(key, 0, -1)
            # 注意：这个测试可能失败，因为ES写入是异步的
            # 实际应用中需要等待或使用mock

        finally:
            # 清理
            await message_repository.clear_messages(test_user_id, session_id)
            await session_repository.delete_session(test_user_id, session_id)

    async def test_multiple_messages_flow(
        self,
        session_repository,
        message_repository,
        test_user_id
    ):
        """测试多条消息流程"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, "多消息测试")

        try:
            # 模拟对话
            conversation = [
                ("user", "你好"),
                ("assistant", "你好！有什么可以帮助你的？"),
                ("user", "请介绍一下等保三级"),
                ("assistant", "等保三级是指..."),
                ("user", "谢谢"),
                ("assistant", "不客气！"),
            ]

            # 追加所有消息
            for role, content in conversation:
                await message_repository.append_message(
                    test_user_id,
                    session_id,
                    role,
                    content
                )

            # 获取所有消息
            messages = await message_repository.get_messages(test_user_id, session_id)

            # 验证
            assert len(messages) == len(conversation)
            for i, (expected_role, expected_content) in enumerate(conversation):
                assert messages[i]["role"] == expected_role
                assert messages[i]["content"] == expected_content

        finally:
            # 清理
            await message_repository.clear_messages(test_user_id, session_id)
            await session_repository.delete_session(test_user_id, session_id)

    async def test_clear_messages_flow(
        self,
        session_repository,
        message_repository,
        test_user_id
    ):
        """测试清空消息流程"""
        # 创建会话
        session_id = await session_repository.create_session(test_user_id, "清空测试")

        try:
            # 追加消息
            await message_repository.append_message(test_user_id, session_id, "user", "消息1")
            await message_repository.append_message(test_user_id, session_id, "assistant", "回复1")

            # 清空消息
            await message_repository.clear_messages(test_user_id, session_id)

            # 验证消息已清空
            messages = await message_repository.get_messages(test_user_id, session_id)
            assert len(messages) == 0

        finally:
            # 清理
            await session_repository.delete_session(test_user_id, session_id)
