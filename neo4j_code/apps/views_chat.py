# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/9/26 09:44
    Description: 
"""

import os
import uuid
import json
from datetime import datetime
from typing import Dict, List, Any
from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi import Depends, APIRouter
from sse_starlette import EventSourceResponse

from apps.base_models import CreateSession, DeleteSession, AskQuestion
from db.redis_conn import get_redis
from db.utils_llm import mdl
from settings.sence_question import scene_info

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个有帮助的中文智能助手，请用简洁、清晰的方式回答。")

router = APIRouter()


class RedisStorage():
    """
        Redis存储实现，用于对话上下文的持久化存储。
        每个用户的对话会话有一个hash存储元数据，消息列表用list存储。
        键设计：
          chat:{user_id}:sessions -> hash: id -> {name, created_at}
          chat:{user_id}:session:{sid}:messages -> list of messages
    """
    def __init__(self, r):
        self.r = r

    def sessions_key(self, user_id: str) -> str:
        return f"chat:{user_id}:sessions"

    def _sess_messages_key(self, user_id: str, sid: str) -> str:
        return f"chat:{user_id}:session:{sid}:messages"

    # 创建会话
    async def create_session(self, user_id: str, session_name: str) -> str:
        sid = str(uuid.uuid4())
        meta = {"session_id": sid, "session_name": session_name, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        await self.r.hset(self.sessions_key(user_id), sid, json.dumps(meta, ensure_ascii=False))
        return sid

    # 查询会话列表
    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        session_json_list = await self.r.hgetall(self.sessions_key(user_id))
        sessions = []
        for session_id, meta in session_json_list.items():
            session_data = json.loads(meta)
            sessions.append(session_data)
        return sessions

    async def get_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        key = self._sess_messages_key(user_id, session_id)
        items = await self.r.lrange(key, 0, -1)
        messages: List[Dict[str, Any]] = []
        for it in items:
            try:
                messages.append(json.loads(it))
            except Exception:
                pass
        return messages

    async def append_message(self, user_id: str, session_id: str, role: str, content: str) -> None:
        key = self._sess_messages_key(user_id, session_id)
        msg = {"role": role, "content": content, "ts": datetime.utcnow().isoformat()}
        await self.r.rpush(key, json.dumps(msg, ensure_ascii=False))

    async def ensure_session(self, user_id: str, session_id: str) -> None:
        exists = await self.r.hexists(self.sessions_key(user_id), session_id)
        if not exists:
            raise KeyError("session not found")

    async def delete_session(self, user_id: str, session_id: str) -> None:
        # 从哈希中删除会话元数据
        await self.r.hdel(self.sessions_key(user_id), session_id)
        # 删除与会话关联的消息列表
        await self.r.unlink(self._sess_messages_key(user_id, session_id))


# 构造带历史的prompt（简单拼接）
def build_prompt_with_history(history: List[Dict[str, str]], new_question: str) -> str:
    parts: List[str] = [SYSTEM_PROMPT, "\n以下是历史对话，请基于上下文回答用户的新问题。", "\n--- 历史对话开始 ---"]
    for msg in history[-20:]:  # 只带最近20条
        role = "用户" if msg.get("role") == "user" else "助手"
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")
    parts.append("--- 历史对话结束 ---\n")
    parts.append(f"用户: {new_question}\n助手:")
    print(parts)
    return "\n".join(parts)


# 创建会话
@router.post("/sessions")
async def create_session(session_info: CreateSession
                         , redis_conn=Depends(get_redis)):
    """

    """
    storage = RedisStorage(redis_conn)
    session_name = session_info.session_name
    user_id = session_info.user_id
    sid = await storage.create_session(user_id=user_id, session_name=session_name)
    # return {"session_id": sid, "name": name}
    return dict(code=0, msg="success", data={"session_id": sid, "session_name": session_name})


# 获取会话列表
@router.get("/sessions")
async def list_sessions(user_id: str = Query(..., description="用户ID"), redis_conn=Depends(get_redis)):
    storage = RedisStorage(redis_conn)
    sessions_list = await storage.list_sessions(user_id=user_id)
    sessions_list = sorted(sessions_list, key=lambda x: x["created_at"], reverse=True)
    return dict(code=0, msg="success", data=sessions_list)


# 获取会话详情
@router.get("/sessions/messages")
async def get_session_messages(session_id: str, user_id: str = Query(..., description="用户ID"),  redis_conn=Depends(get_redis)):
    try:
        storage = RedisStorage(redis_conn)
        await storage.ensure_session(user_id=user_id, session_id=session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = await storage.get_messages(user_id=user_id, session_id=session_id)
    return dict(code=0, msg="success", data=msgs)


# 删除会话
@router.delete("/sessions")
async def delete_session(session_info: DeleteSession, redis_conn=Depends(get_redis)):
    user_id = session_info.user_id
    session_id = session_info.session_id
    storage = RedisStorage(redis_conn)
    await storage.delete_session(user_id=user_id, session_id=session_id)
    return dict(code=0, msgs="success")


# 流式对话
# @router.post("/chat/stream")
async def chat_stream(chat_info: AskQuestion,
                      redis_conn=Depends(get_redis)):
    question = chat_info.question
    user_id = chat_info.user_id
    session_id = chat_info.session_id
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    try:
        storage = RedisStorage(redis_conn)
        await storage.ensure_session(user_id=user_id, session_id=session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")

    await storage.append_message(user_id=user_id, session_id=session_id, role="user", content=question)

    history = await storage.get_messages(user_id=user_id, session_id=session_id)
    prompt = build_prompt_with_history(history=[m for m in history if m["role"] in ("user", "assistant")], new_question=question)

    return EventSourceResponse(mdl.chat_streamly_cache(
            None,
            [{"role": "user", "content": prompt}],
            {"temperature": 0.0},
            user_id=user_id,
            storage=storage,
            session_id=session_id),
            media_type="text/event-stream")


# 获取场景问题
@router.get("/session/scene")
async def get_scene():
    return dict(code=0, msg="", data=scene_info)


@router.get("/")
async def index():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(current_dir, "static", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h3>前端页面不存在，请确认 static/index.html 是否已创建。</h3>")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html)


@router.get("/health")
async def health():
    return {"status": "ok"}