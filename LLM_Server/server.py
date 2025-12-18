import os
import uuid
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, AsyncGenerator
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from llm_client import LLMClient

# Redis环境配置
REDIS_ENABLED = True
REDIS_URL = os.getenv("REDIS_URL", "redis://10.26.52.2:6379/0")  # 部署redis服务6379，存储对话上下文
redis_async = None
if REDIS_ENABLED:
    try:
        import redis.asyncio as redis
        # 异步Redis连接客户端
        redis_async = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    except Exception as e:
        raise RuntimeError(f"启用Redis但导入/连接失败: {e}")

# LLM配置
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1") 
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v3.1")
LLM_API_KEY = "sk-f9f3209599454a49ba6fb4f36c3c0434"  # 百度云api
# LLM_BASE_URL = "http://10.26.52.105:8002/v1"   # 改成对应api地址即可
# LLM_API_KEY = "empty"
# LLM_MODEL_NAME = "/data/model/QwQ-32B/"
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个有帮助的中文智能助手，请用简洁、清晰的方式回答。")

# ---- 存储多轮对话上下文基类 ----
class ChatStorage:
    """
    对话信息存储基类，定义存储上下文的基础操作，包括：
    1.对话会话的创建
    2.会话列表
    3.获取会话中的消息
    4.追加消息
    5.确认会话存在
    6.删除会话
    """
    async def create_session(self, user_id: str, name: Optional[str] = None) -> str:
        raise NotImplementedError

    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def get_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def append_message(self, user_id: str, session_id: str, role: str, content: str) -> None:
        raise NotImplementedError

    async def ensure_session(self, user_id: str, session_id: str) -> None:
        raise NotImplementedError

    async def delete_session(self, user_id: str, session_id: str) -> None:
        raise NotImplementedError


class InMemoryStorage(ChatStorage):
    """
    直接在内存中用字典_sessions直接存储对话上下文，不用Redis，不支持持久化。
    结构: { user_id: { session_id: {name, created_at, messages: []} } }
    """
    def __init__(self) -> None:
        self._user_sessions: Dict[str, Dict[str, Dict[str, Any]]] = {}

    async def create_session(self, user_id: str, name: Optional[str] = None) -> str:
        sid = str(uuid.uuid4())
        user_map = self._user_sessions.setdefault(user_id, {})
        user_map[sid] = {
            "name": name or f"对话 {len(user_map) + 1}",
            "created_at": datetime.utcnow().isoformat(),
            "messages": []
        }
        return sid

    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        user_map = self._user_sessions.get(user_id, {})
        return [
            {"id": sid, "name": meta.get("name"), "created_at": meta.get("created_at")}
            for sid, meta in user_map.items()
        ]

    async def get_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        sess = self._user_sessions.get(user_id, {}).get(session_id)
        if not sess:
            raise KeyError("session not found")
        return sess["messages"]

    async def append_message(self, user_id: str, session_id: str, role: str, content: str) -> None:
        sess = self._user_sessions.get(user_id, {}).get(session_id)
        if not sess:
            raise KeyError("session not found")
        sess["messages"].append({
            "role": role,
            "content": content,
            "ts": datetime.utcnow().isoformat()
        })

    async def ensure_session(self, user_id: str, session_id: str) -> None:
        if session_id not in self._user_sessions.get(user_id, {}):
            raise KeyError("session not found")

    async def delete_session(self, user_id: str, session_id: str) -> None:
        user_map = self._user_sessions.get(user_id, {})
        if session_id in user_map:
            del user_map[session_id]


class RedisStorage(ChatStorage):
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

    async def create_session(self, user_id: str, name: Optional[str] = None) -> str:
        sid = str(uuid.uuid4())
        meta = {"name": name or "对话", "created_at": datetime.utcnow().isoformat()}
        await self.r.hset(self.sessions_key(user_id), sid, json.dumps(meta, ensure_ascii=False))
        return sid

    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        data = await self.r.hgetall(self.sessions_key(user_id))
        result = []
        for sid, meta_json in data.items():
            try:
                meta = json.loads(meta_json)
            except Exception:
                meta = {"name": "对话", "created_at": None}
            result.append({"id": sid, **meta})
        return result

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
        await self.r.delete(self._sess_messages_key(user_id, session_id))


# 选择存储实现
storage: ChatStorage
if REDIS_ENABLED and redis_async is not None:
    # 默认使用Redis存储上下文，支持持久化
    storage = RedisStorage(redis_async)
    print(f"[存储] 使用Redis: {REDIS_URL}")
else:
    storage = InMemoryStorage()
    print("[存储] 使用内存存储（开发/单机）。线上需启用Redis持久化。")


# LLM 客户端
# 设置全局配置
import llm_client as llm_client_module
llm_client_module.base_url = LLM_BASE_URL
llm_client_module.api_key = LLM_API_KEY

llm_client = LLMClient()

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


app = FastAPI(title="Async Streaming Chat API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建会话
@app.post("/api/sessions")
async def create_session(payload: Optional[Dict[str, Any]] = None, user_id: str = Query(..., description="用户ID")):
    name = (payload or {}).get("name") if payload else None
    sid = await storage.create_session(user_id=user_id, name=name)
    return {"session_id": sid, "name": name}

# 获取会话列表
@app.get("/api/sessions")
async def list_sessions(user_id: str = Query(..., description="用户ID")):
    return await storage.list_sessions(user_id=user_id)

# 获取特定会话中消息
@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, user_id: str = Query(..., description="用户ID")):
    try:
        await storage.ensure_session(user_id=user_id, session_id=session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = await storage.get_messages(user_id=user_id, session_id=session_id)
    return msgs


# 删除会话
@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = Query(..., description="用户ID")):
    try:
        await storage.ensure_session(user_id=user_id, session_id=session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")
    await storage.delete_session(user_id=user_id, session_id=session_id)
    return {"status": "ok", "message": f"会话 {session_id} 已删除"}


# 流式对话
@app.post("/api/chat/stream")
async def chat_stream(request: Request, session_id: str = Query(..., description="会话ID"), user_id: str = Query(..., description="用户ID")):
    data = await request.json()
    question = (data or {}).get("message", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        await storage.ensure_session(user_id=user_id, session_id=session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在")

    await storage.append_message(user_id=user_id, session_id=session_id, role="user", content=question)

    history = await storage.get_messages(user_id=user_id, session_id=session_id)
    prompt = build_prompt_with_history(history=[m for m in history if m["role"] in ("user", "assistant")], new_question=question)

    async def stream_gen() -> AsyncGenerator[bytes, None]:
        reply_buffer: List[str] = []
        try:
            async for chunk in llm_client.async_stream_chat(
                prompt=prompt,
                model=LLM_MODEL_NAME,
                max_tokens=4000,
                temperature=0.7,
                system_prompt=None,
            ):
                if chunk:
                    reply_buffer.append(chunk)
                    yield chunk.encode("utf-8")
                    await asyncio.sleep(0)
        except Exception as e:
            err = f"[LLM错误]: {e}\n"
            yield err.encode("utf-8")
        finally:
            full_reply = "".join(reply_buffer).strip()
            if full_reply:
                await storage.append_message(user_id=user_id, session_id=session_id, role="assistant", content=full_reply)

    return StreamingResponse(stream_gen(), media_type="text/event-stream")


@app.get("/")
async def index():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(current_dir, "static", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h3>前端页面不存在，请确认 es-llm/static/index.html 是否已创建。</h3>")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8010"))
    print(f"Starting server on 0.0.0.0:{port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)