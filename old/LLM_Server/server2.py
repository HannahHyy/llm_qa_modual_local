import os
import sys
from pickle import FALSE
import uuid
import json
import asyncio
import pymysql
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator
from fastapi import FastAPI, Request, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from llm_client import LLMClient
import requests

# 将项目根目录添加到 sys.path 以支持绝对导入
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from neo4j_code.apps.views_intent.views_new import LLM as Neo4jLLM
    from neo4j_code.apps.views_intent.views import LoadVector as Neo4jLoadVector
    from neo4j_code.settings.config import Neo4jConfig
    NEO4J_ENABLED = True
    print("[Neo4j模块] 加载成功")
except ImportError as e:
    print(f"[Neo4j模块] 加载失败: {e}")
    NEO4J_ENABLED = False

# ==================== 环境配置 ====================
# Redis环境配置，用于检索history
REDIS_ENABLED = True
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

# MySQL配置，session表记录对话元数据表
MYSQL_HOST = "localhost"
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "chatuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "ChangeMe123!")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "chatdb")

# Elasticsearch配置
ES_HOST = "localhost"
ES_PORT = int(os.getenv("ES_PORT", "9200"))
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "password01")
ES_URL = f"http://{ES_HOST}:{ES_PORT}"
ES_KNOWLEDGE_INDEX = "kb_vector_store"  # 检索knowledge
ES_CONVERSATION_INDEX = "conversation_history"  # 检索历史上下文（redis没查到就查es）

neo4j_vector_stores = None
neo4j_llm_instance = None
if NEO4J_ENABLED:
    try:
        neo4j_llm_instance = Neo4jLLM()
        print("[Neo4j向量存储] 初始化成功")
    except Exception as e:
        print(f"[Neo4j向量存储] 初始化失败: {e}")
        NEO4J_ENABLED = False

# ==================== LLM客户端 ====================
# LLM配置
# LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1") 
# LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwq-32b")
# LLM_API_KEY = "sk-f9f3209599454a49ba6fb4f36c3c0434"

# 使用llm_client.py中的默认配置
import llm_client as llm_client_module
LLM_MODEL_NAME = llm_client_module.LlmConfig.model_name
llm_client = LLMClient()

# 知识匹配模块导入
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'retrieval_server'))
try:
    from knowledge_matcher import match_and_format_knowledge
    KNOWLEDGE_MATCHING_ENABLED = True
    print("[知识匹配] 模块加载成功")
except ImportError as e:
    print(f"[知识匹配] 模块加载失败: {e}")
    KNOWLEDGE_MATCHING_ENABLED = False

# 系统提示词配置
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个有帮助的中文网络等级保护智能助手，请用简洁、清晰的方式回答。")
ENHANCED_PROMPT_TEMPLATE = os.getenv("ENHANCED_PROMPT_TEMPLATE", """
{system_prompt}

以下是历史对话，请基于上下文回答用户的新问题。

--- 历史对话开始 ---
{history}
--- 历史对话结束 ---

--- 相关知识 ---
{knowledge}
--- 知识结束 ---

用户: {query}
助手:""")

# 会话超时配置（用于异步后台摘要生成任务）
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "300"))

# 检索服务配置
INTENT_PARSER_ENABLED = True
KNOWLEDGE_RETRIEVAL_ENABLED = True

# ==================== 数据库连接初始化 ====================
redis_async = None
if REDIS_ENABLED:
    try:
        import redis.asyncio as redis
        redis_async = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    except Exception as e:
        raise RuntimeError(f"启用Redis但导入/连接失败: {e}")

# MySQL连接池
mysql_pool = None
try:
    mysql_pool = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4',
        autocommit=True
    )
    print(f"[MySQL] 连接成功: {MYSQL_HOST}:{MYSQL_PORT}")
except Exception as e:
    print(f"[MySQL] 连接失败: {e}")

# Elasticsearch客户端
es_client = None
ES_BASE_URL = f"http://{ES_HOST}:{ES_PORT}"
ES_AUTH = (ES_USERNAME, ES_PASSWORD) if ES_USERNAME and ES_PASSWORD else None
# 绕过代理的 proxies 配置（用于所有本地 ES 请求）
ES_PROXIES = {'http': None, 'https': None}
try:
    from elasticsearch import Elasticsearch
    import os

    # 临时禁用代理（针对本地ES连接）
    old_http_proxy = os.environ.get('HTTP_PROXY')
    old_https_proxy = os.environ.get('HTTPS_PROXY')
    old_http_proxy_lower = os.environ.get('http_proxy')
    old_https_proxy_lower = os.environ.get('https_proxy')

    # 移除代理设置
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)

    try:
        # 使用 Elasticsearch 客户端进行连接测试
        es_test_client = Elasticsearch(
            hosts=[ES_BASE_URL],
            basic_auth=ES_AUTH,
            request_timeout=5,
            max_retries=3,
            retry_on_timeout=True
        )
        if es_test_client.ping():
            print(f"[ES] 连接测试成功: {ES_BASE_URL}")
            es_client = True  # 标记ES可用
        else:
            print(f"[ES] 连接测试失败: ping 返回 False")
            es_client = None
    finally:
        # 恢复代理设置
        if old_http_proxy:
            os.environ['HTTP_PROXY'] = old_http_proxy
        if old_https_proxy:
            os.environ['HTTPS_PROXY'] = old_https_proxy
        if old_http_proxy_lower:
            os.environ['http_proxy'] = old_http_proxy_lower
        if old_https_proxy_lower:
            os.environ['https_proxy'] = old_https_proxy_lower

except Exception as e:
    print(f"[ES] 连接失败: {e}")
    es_client = None

# ==================== 请求模型定义 ====================
class ChatRequest(BaseModel):
    user_query: str = Field(..., description="用户查询")
    history_msgs: List[Dict[str, str]] = Field(default=[], description="历史消息")
    user_id: str = Field(..., description="用户ID")
    session_id: str = Field(..., description="会话ID")

# ==================== 存储基类扩展 ====================
class ChatStorage:
    """对话信息存储基类"""
    async def create_session(self, user_id: str, name: Optional[str] = None) -> str:
        raise NotImplementedError

    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def get_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        """获取消息，支持Redis缓存未命中时从ES获取"""
        key = self._sess_messages_key(user_id, session_id)
        
        # 1. 先从Redis获取
        items = await self.r.lrange(key, 0, -1)
        if items:
            messages = []
            for it in items:
                try:
                    messages.append(json.loads(it))
                except Exception:
                    pass
            return messages

        # 2. Redis缓存未命中，从ES获取
        messages: List[Dict[str, Any]] = []
        if es_client:
            try:
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}}
                            ]
                        }
                    },
                    "sort": [{"timestamp": {"order": "asc"}}]
                }
                url = f"{ES_BASE_URL}/{ES_CONVERSATION_INDEX}/_search"
                resp = requests.post(url, json=query, auth=ES_AUTH, timeout=30, proxies=ES_PROXIES)
                resp.raise_for_status()
                data = resp.json()

                for hit in data.get("hits", {}).get("hits", []):
                    source = hit["_source"]
                    for msg in source.get("messages", []):
                        messages.append({
                            "role": msg.get("role", ""),
                            "content": msg.get("content", ""),
                            "timestamp": msg.get("timestamp", "")
                        })
                print(f"[ES] 获取历史消息成功: {len(messages)} 条")
            except Exception as e:
                print(f"[ES] 获取历史消息失败: {e}")

            # 3. 缓存回填到Redis（仅当有消息）
            if messages:
                for msg in messages:
                    await self.r.rpush(key, json.dumps(msg, ensure_ascii=False))
                await self.r.expire(key, 86400)  # 24小时过期
                print(f"[缓存回填] 从ES获取{len(messages)}条消息并回填到Redis")

        return messages

    async def append_message(self, user_id: str, session_id: str, role: str, content: str) -> None:
        raise NotImplementedError

    async def ensure_session(self, user_id: str, session_id: str) -> None:
        raise NotImplementedError

    async def delete_session(self, user_id: str, session_id: str) -> None:
        raise NotImplementedError


class EnhancedRedisStorage(ChatStorage):
    """Redis存储实现，集成MySQL和ES"""
    
    def __init__(self, r):
        self.r = r

    def sessions_key(self, user_id: str) -> str:
        return f"chat:{user_id}:sessions"

    def _sess_messages_key(self, user_id: str, sid: str) -> str:
        return f"chat:{user_id}:session:{sid}:messages"

    # create_session
    async def create_session(self, user_id: str, name: Optional[str] = None) -> str:
        sid = str(uuid.uuid4())
        session_name = name or "对话"
        created_at = datetime.utcnow()
        
        # 1. 写入Redis
        meta = {"name": session_name, "created_at": created_at.isoformat()}
        await self.r.hset(self.sessions_key(user_id), sid, json.dumps(meta, ensure_ascii=False))
        
        # 2. 写入MySQL元会话数据表
        if mysql_pool:
            try:
                cursor = mysql_pool.cursor()
                # 首先确保用户存在，如果不存在则创建
                cursor.execute(
                    "INSERT IGNORE INTO users (user_id, username, created_at) VALUES (%s, %s, %s)",
                    (user_id, f"用户_{user_id[:8]}", created_at)
                )
                
                # 然后创建会话
                cursor.execute(
                    "INSERT INTO sessions (session_id, user_id, name, created_at) VALUES (%s, %s, %s, %s)",
                    (sid, user_id, session_name, created_at)
                )
                cursor.close()
                print(f"[MySQL] 会话创建成功: {sid}")
            except Exception as e:
                print(f"[MySQL] 会话创建失败: {e}")
        
        # 3. 在ES中创建会话记录（使用requests方式）
        if es_client:
            try:
                doc = {
                    "user_id": user_id,
                    "session_id": sid,
                    "session_name": session_name,
                    "created_at": created_at.isoformat(),
                    "messages": []
                }
                url = f"{ES_BASE_URL}/{ES_CONVERSATION_INDEX}/_doc/{user_id}_{sid}"
                resp = requests.put(url, json=doc, auth=ES_AUTH, timeout=30, proxies=ES_PROXIES)
                resp.raise_for_status()
                print(f"[ES] 会话初始化成功: {sid}")
            except Exception as e:
                print(f"[ES] 会话初始化失败: {e}")
        
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
        """获取消息，支持Redis缓存未命中时从ES获取"""
        key = self._sess_messages_key(user_id, session_id)
        items = await self.r.lrange(key, 0, -1)
        if items:
            messages = []
            for it in items:
                try:
                    messages.append(json.loads(it))
                except Exception:
                    pass
            return messages

        # 2. Redis缓存未命中，从ES获取
        messages: List[Dict[str, Any]] = []
        if es_client:
            try:
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}}
                            ]
                        }
                    },
                    "sort": [{"timestamp": {"order": "asc"}}]
                }
                url = f"{ES_BASE_URL}/{ES_CONVERSATION_INDEX}/_search"
                resp = requests.post(url, json=query, auth=ES_AUTH, timeout=30, proxies=ES_PROXIES)
                resp.raise_for_status()
                data = resp.json()

                for hit in data.get("hits", {}).get("hits", []):
                    source = hit["_source"]
                    for msg in source.get("messages", []):
                        messages.append({
                            "role": msg.get("role", ""),
                            "content": msg.get("content", ""),
                            "timestamp": msg.get("timestamp", "")
                        })
                print(f"[ES] 获取历史消息成功: {len(messages)} 条")
            except Exception as e:
                print(f"[ES] 获取历史消息失败: {e}")

            # 3. 缓存回填到Redis（仅当有消息）
            if messages:
                for msg in messages:
                    await self.r.rpush(key, json.dumps(msg, ensure_ascii=False))
                await self.r.expire(key, 86400)  # 24小时过期
                print(f"[缓存回填] 从ES获取{len(messages)}条消息并回填到Redis")

        return messages

    async def append_message(self, user_id: str, session_id: str, role: str, content: str) -> None:
        """追加消息，同时写入Redis和ES"""
        timestamp = datetime.utcnow()
        msg = {"role": role, "content": content, "ts": timestamp.isoformat()}
        
        # 1. 写入Redis
        key = self._sess_messages_key(user_id, session_id)
        await self.r.rpush(key, json.dumps(msg, ensure_ascii=False))

        # 2. 写入ES
        if es_client:
            try:
                current_count = await self.r.llen(key)
                message_id = f"msg_{session_id}_{int(timestamp.timestamp() * 1000)}"
                doc = {
                    "user_id": user_id,
                    "session_id": session_id,
                    "message_id": message_id,
                    "role": role,
                    "content": content,
                    "timestamp": timestamp.isoformat(),
                    "message_order": current_count,
                }
                
                # 同步写入ES，确保消息立即持久化
                url = f"{ES_BASE_URL}/{ES_CONVERSATION_INDEX}/_doc"
                resp = requests.post(url, json=doc, auth=ES_AUTH, timeout=15, proxies=ES_PROXIES)
                resp.raise_for_status()
                print(f"[ES] 消息同步写入成功: {message_id}")
            except Exception as e:
                print(f"[ES] 消息写入失败: {e}") # 即使ES写入失败，也不影响Redis存储
               

    async def ensure_session(self, user_id: str, session_id: str) -> None:
        exists = await self.r.hexists(self.sessions_key(user_id), session_id)
        if not exists:
            raise KeyError("session not found")

    async def delete_session(self, user_id: str, session_id: str) -> None:
        # 从Redis删除
        await self.r.hdel(self.sessions_key(user_id), session_id)
        await self.r.delete(self._sess_messages_key(user_id, session_id))
        
        # 从MySQL删除
        if mysql_pool:
            try:
                cursor = mysql_pool.cursor()
                cursor.execute("DELETE FROM sessions WHERE session_id = %s AND user_id = %s", (session_id, user_id))
                cursor.close()
            except Exception as e:
                print(f"[MySQL] 会话删除失败: {e}")
        # 从ES删除（使用Delete By Query删除会话中的所有消息）
        if es_client:
            try:
                # 构建查询删除请求
                url = f"{ES_BASE_URL}/{ES_CONVERSATION_INDEX}/_delete_by_query"
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}}
                            ]
                        }
                    }
                }
                resp = requests.post(url, json=query, auth=ES_AUTH, timeout=30, proxies=ES_PROXIES)
                resp.raise_for_status()
                result = resp.json()
                deleted = result.get("deleted", 0)
                print(f"[ES] 会话删除成功: {session_id}, 共删除 {deleted} 条消息")
            except Exception as e:
                print(f"[ES] 会话删除失败: {e}")

class InMemoryStorage(ChatStorage):
    """内存存储实现，辅助"""
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

# 选择存储实现
storage: ChatStorage
if REDIS_ENABLED and redis_async is not None:
    storage = EnhancedRedisStorage(redis_async)
    print(f"[存储] 使用增强Redis存储: {REDIS_URL}")
else:
    storage = InMemoryStorage()
    print("[存储] 使用内存存储（开发/单机）")

# ==================== 检索和意图识别 ====================
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'retrieval_server'))

try:
    from intent_parser import EnhancedIntentParser, IntentParseContext
    from es_retriever_kbvector import search_clauses
    print("[检索模块] 导入成功")
except Exception as e:
    print(f"[检索模块] 导入失败: {e}")
    INTENT_PARSER_ENABLED = True
    KNOWLEDGE_RETRIEVAL_ENABLED = True

# 导入hybrid特有的独立的意图路由器
try:
    from intent_router import llm_based_intent_router
    print("[意图路由器] 导入成功")
except ImportError as e:
    print(f"[意图路由器] 导入失败: {e}")
    # 提供一个简单的fallback函数
    async def llm_based_intent_router(user_query: str, history_msgs: List[Dict[str, str]], 
                                     stream_callback: Optional[callable] = None, max_retries: int = 3) -> str:
        return "es"  # 默认使用ES

async def parse_intent_with_stream(user_query: str, history_msgs: List[Dict[str, str]], 
                                   stream_callback: Optional[callable] = None) -> Optional[Dict]:
    """
    流式意图识别，支持实时输出思考过程
    """
    if not INTENT_PARSER_ENABLED:
        return None
    
    try:
        parser = EnhancedIntentParser()
        context = IntentParseContext(
            user_query=user_query,
            history_msgs=history_msgs
        )
        
        # 使用流式解析，传入回调函数
        result = await parser.parse(context, stream=True, stream_callback=stream_callback)
        print(f"[意图识别] 流式解析成功: {len(result.get('intents', []))} 个意图")
        return result
        
    except Exception as e:
        print(f"[意图识别] 流式解析失败: {e}")
        return None

async def parse_intent(user_query: str, history_msgs: List[Dict[str, str]]) -> Optional[Dict]:
    if not INTENT_PARSER_ENABLED:
        return None
    
    try:
        # 构建IntentParseContext对象
        context = IntentParseContext(
            user_query=user_query,
            history_msgs=history_msgs
        )
        
        # 调用意图解析器 - 添加await
        parser = EnhancedIntentParser()
        result = await parser.parse(context)
        
        # 将IntentParseResult转换为字典格式返回
        return result.dict() if result else None
    except Exception as e:
        print(f"[意图识别] 失败: {e}")
        return None

def retrieve_knowledge(intent_result: Dict) -> List[Dict]:
    """知识检索 - 返回完整的检索结果列表"""
    if not KNOWLEDGE_RETRIEVAL_ENABLED or not intent_result:
        return []
    
    try:
        results = search_clauses(intent_result)
        if not results:
            return []
        
        # 将RetrievalResult对象转换为字典格式
        formatted_results = []
        for result in results:
            formatted_result = {
                "clause_key_en": result.clause_key_en,
                "content": result.content,
                "source_standard": result.source_standard,
                "identifier": result.identifier,
                "section_levels": result.section_levels,
                "applicability_level": result.applicability_level,
                "score": result.score,
                "retrieval_path": result.retrieval_path,
                "embedding_content": result.embedding_content
            }
            formatted_results.append(formatted_result)
        # for i, result in enumerate(formatted_results,1):
        #     print(result['content'])
        
        return formatted_results
    except Exception as e:
        print(f"[知识检索] 失败: {e}")
        return []

# ==================== 用于history只保留<data>内容 ====================
def filter_content(content: str) -> str:
    """过滤掉包含think和knowledge标签的内容"""
    import re
    if not content:
        return content
    
    # 移除 <think> </think> 标签及其内容
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    # 移除 <knowledge> </knowledge> 标签及其内容
    content = re.sub(r'<knowledge>.*?</knowledge>', '', content, flags=re.DOTALL)
    
    # 清理多余的空白字符
    content = re.sub(r'\n\s*\n', '\n', content.strip())
    
    return content

# ==================== 增强的Prompt构建 ====================
def build_enhanced_prompt(history: List[Dict[str, str]], query: str, 
                         knowledge: str = "") -> str:
    """构建增强的prompt"""
    
    # 格式化历史对话（保留最近2条）
    history_parts = []
    for msg in history[-2:]:
        role = "用户" if msg.get("role") == "user" else "助手"
        content = msg.get("content", "")
        # 历史对话只保留<data>内容
        filtered_content = filter_content(content)
        if filtered_content.strip():  # 只有在过滤后还有内容时才添加
            history_parts.append(f"{role}: {filtered_content}")
    history_text = "\n".join(history_parts) if history_parts else "无历史对话"

    # 安全截断各段，避免触发 98304 上限
    MAX_LLM_INPUT_LEN = 98304
    knowledge_safe = (knowledge or "无相关知识")[:60000]
    query_safe = (query or "")[:8000]

    prompt = ENHANCED_PROMPT_TEMPLATE.format(
        system_prompt=SYSTEM_PROMPT,
        history=history_text,
        knowledge=knowledge_safe,
        query=query_safe,
    )
    # 兜底截断整体 prompt，预留少量冗余
    if len(prompt) > (MAX_LLM_INPUT_LEN - 200):
        prompt = prompt[:(MAX_LLM_INPUT_LEN - 200)]
    return prompt

# ==================== FastAPI应用 ====================
app = FastAPI(title="Enhanced Async Streaming Chat API")
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

# 流式返回
@app.post("/api/chat/stream")
async def chat_stream(request: Request, background_tasks: BackgroundTasks,
                     session_id: str = Query(..., description="会话ID"), 
                     user_id: str = Query(..., description="用户ID"),
                     scene_id: int = Query(1, description="场景ID: 1=混合查询(Neo4j+ES), 2=仅Neo4j, 3=仅ES")):
    try:
        body = await request.json()
        question = body.get("message", "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="用户查询不能为空")

        # await storage.ensure_session(user_id, session_id)
        history = await storage.get_messages(user_id, session_id)
        history_msgs = [m for m in history if m["role"] in ("user", "assistant")]
        
        # 根据scene_id选择不同的处理逻辑
        if scene_id == 1:
            # 混合查询：使用llm_based_intent_router判断，如果都要用的话，Neo4j完全运行完毕后再运行ES。
            return StreamingResponse(
                hybrid_stream_gen(question, history_msgs, user_id, session_id, background_tasks),
                media_type="text/plain; charset=utf-8"
            )
        elif scene_id == 2:
            # 仅Neo4j查询：完全调用neo4j_code模块
            return StreamingResponse(
                neo4j_stream_gen(question, history_msgs, user_id, session_id, background_tasks),
                media_type="text/plain; charset=utf-8"
            )
        else:
            # 默认使用ES查询 (scene_id=3 或其他值)：完全调用现有的es_stream_gen
            return StreamingResponse(
                es_stream_gen(question, history_msgs, user_id, session_id, background_tasks),
                media_type="text/plain; charset=utf-8"
            )

    except Exception as e:
        print(f"[聊天流式] 错误: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


async def es_stream_gen(question: str, history_msgs: List[Dict[str, str]], 
                      user_id: str, session_id: str, background_tasks: BackgroundTasks,
                      save_messages: bool = True) -> AsyncGenerator[bytes, None]:
    """ES查询流式生成器 (scene_id=3，默认场景)"""
    intent_result = None
    knowledge_results = []
    full_stream_content: List[str] = []  # 完整的用户可见流式内容（包括所有标签,用于存储历史会话记录）
    llm_raw_content: List[str] = []   # 大模型纯净流式内容（意图识别 + LLM生成，用于分析）
    
    try:
        # 1. 意图识别阶段 - 使用流式输出
        intent_queue = asyncio.Queue()
        intent_done = asyncio.Event()
        
        async def intent_callback(chunk: str):
            """意图识别流式回调"""
            if chunk:
                await intent_queue.put(chunk)
                full_stream_content.append(chunk)  # 收集思考过程
        
        async def intent_parser_task():
            """意图解析任务"""
            nonlocal intent_result
            try:
                intent_result = await parse_intent_with_stream(
                    question, history_msgs, intent_callback
                )
            finally:
                intent_done.set()
                await intent_queue.put(None)  # 结束标记
        
        # 启动意图解析任务
        parser_task = asyncio.create_task(intent_parser_task())
        think_start_data = {
            "content": "<think>开始对用户的提问进行深入解析...\n",
            "message_type": 1
        }
        yield f"data:{json.dumps(think_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
        full_stream_content.append(think_start_data["content"])

        # 实时输出意图识别过程
        while True:
            try:
                chunk = await asyncio.wait_for(intent_queue.get(), timeout=0.1)
                if chunk is None:  # 解析完成
                    break
                chunk_data = {
                    "content": chunk,
                    "message_type": 1
                }
                yield f"data:{json.dumps(chunk_data, ensure_ascii=False)}\n\n".encode("utf-8")
                full_stream_content.append(chunk)  # 收集完整内容（包含思考过程）
            except asyncio.TimeoutError:
                if intent_done.is_set():
                    # 检查队列是否还有数据
                    try:
                        chunk = intent_queue.get_nowait()
                        if chunk is None:
                            break
                        chunk_data = {
                            "content": chunk,
                            "message_type": 1
                        }
                        yield f"data:{json.dumps(chunk_data, ensure_ascii=False)}\n\n".encode("utf-8")
                        full_stream_content.append(chunk)
                    except asyncio.QueueEmpty:
                        break
                continue

        # 输出思考过程标签结束
        think_end_content = "\n完成对用户问题的详细解析分析。正在检索知识库中的内容并生成回答，请稍候....\n</think>\n"
        think_end_data = {
            "content": think_end_content,
            "message_type": 1
        }
        yield f"data:{json.dumps(think_end_data, ensure_ascii=False)}\n\n".encode("utf-8")
        full_stream_content.append(think_end_content)
        llm_raw_content.append(str(intent_result)) # 大模型思考结果

        # 等待意图解析完成
        await parser_task
        
        # 2. 知识检索
        knowledge_results = retrieve_knowledge(intent_result) if intent_result else []
        knowledge = "\n".join([item.get("embedding_content", "") for item in knowledge_results])
        # 额外保护：知识内容先做一次截断（与 build_enhanced_prompt 配合）
        if knowledge:
            knowledge = knowledge[:60000]
        
        # 3. 构建增强prompt
        prompt = build_enhanced_prompt(history_msgs, question, knowledge)

        # 4. LLM响应流
        data_start_data = {
            "content": "<data>\n",
            "message_type": 2
        }
        yield f"data:{json.dumps(data_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
        full_stream_content.append(data_start_data["content"])
        
        async for chunk in llm_client.async_stream_chat(
            prompt=prompt,
            model=LLM_MODEL_NAME,
            max_tokens=4000,
            temperature=0.7,
            system_prompt=SYSTEM_PROMPT,
        ):
            if chunk:
                llm_raw_content.append(chunk)  # 收集大模型原始生成内容（无标签）
                full_stream_content.append(chunk)  # 收集完整内容
                chunk_data = {
                    "content": chunk,
                    "message_type": 2
                }
                yield f"data:{json.dumps(chunk_data, ensure_ascii=False)}\n\n".encode("utf-8")
                await asyncio.sleep(0.01)  # 小延迟确保流式效果
        
        data_end_data = {
            "content": "\n</data>",
            "message_type": 2
        }
        yield f"data:{json.dumps(data_end_data, ensure_ascii=False)}\n\n".encode("utf-8")
        full_stream_content.append(data_end_data["content"])
        
        # 5. 知识匹配和输出
        no_standard_query = False
        if intent_result and isinstance(intent_result, dict):
            no_standard_query = intent_result.get("no_standard_query", False)
        if KNOWLEDGE_MATCHING_ENABLED and llm_raw_content and knowledge_results and not no_standard_query:
            # 从llm_raw_content中提取LLM生成的内容
            full_reply = "".join(llm_raw_content)
            try:
                # 异步匹配知识，返回List[str]
                matched_knowledge = await match_and_format_knowledge(
                    llm_output=full_reply,
                    knowledge_results=knowledge_results,
                    max_results=2  # 返回top 50条匹配的知识
                )
                if matched_knowledge:  # matched_knowledge是List[str]
                    # 构建完整的知识字典结构
                    knowledge_dict = {
                        "title": "相关的标准规范原文内容",
                        "table_list": matched_knowledge
                    }
                    
                    # 流式输出完整的字典结构
                    knowledge_data = {
                        "content": json.dumps(knowledge_dict, ensure_ascii=False),
                        "message_type": 3
                    }
                    yield f"data:{json.dumps(knowledge_data, ensure_ascii=False)}\n\n".encode("utf-8")
                    
                    # 更新full_stream_content（保存为可读格式）
                    full_stream_content.append("<knowledge>")
                    full_stream_content.append("相关的标准规范原文内容")
                    for item in matched_knowledge:
                        full_stream_content.append(item)
                    full_stream_content.append("</knowledge>")
                
            except Exception as e:
                print(f"[知识匹配] 错误: {e}")
                # 知识匹配失败不影响主流程
        
    except Exception as e:
        error_msg = f"流式处理错误: {str(e)}"
        print(f"[流式错误] {error_msg}")
        error_content = f"<data>\n抱歉，处理您的请求时出现错误: {error_msg}\n</data>"
        error_data = {
            "content": error_content,
            "message_type": 4
        }
        yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")
        full_stream_content.append(error_content)
        llm_raw_content.append(f"抱歉，处理您的请求时出现错误: {error_msg}")
    
    finally:
        # 异步保存消息（只在独立调用时保存，被hybrid调用时不保存）
        if save_messages and full_stream_content:
            # 保存完整的用户可见内容（包括所有标签）
            complete_assistant_reply = "".join(full_stream_content)
            background_tasks.add_task(storage.append_message, user_id, session_id, "user", question)
            background_tasks.add_task(storage.append_message, user_id, session_id, "assistant", complete_assistant_reply)
        if llm_raw_content:
            llm_pure_content = "".join(llm_raw_content)
            print(f"[调试] 大模型纯净内容长度: {len(llm_pure_content)}")



async def hybrid_stream_gen(question: str, history_msgs: List[Dict[str, str]], 
                           user_id: str, session_id: str, background_tasks: BackgroundTasks,
                           save_messages: bool = True) -> AsyncGenerator[bytes, None]:
    """混合查询流式生成器 (scene_id=1)
    使用llm_based_intent_router判断，然后根据decision调用相应的函数
    """
    full_stream_content: List[str] = []
    
    try:
        # 1. 使用大模型进行意图路由判断
        think_start = "<think>开始对用户的提问进行深入解析...\n"
        think_data = json.dumps({"content": think_start, "message_type": 1}, ensure_ascii=False)
        yield f"data:{think_data}\n\n".encode("utf-8")
        full_stream_content.append(think_start)
        
        # 收集路由决策的reasoning
        routing_reasoning = ""
        routing_chunks = []
        
        # 流式输出路由决策过程
        async def router_callback(chunk: str):
            nonlocal routing_reasoning, routing_chunks
            if chunk:
                routing_reasoning += chunk
                routing_chunks.append(chunk)
                full_stream_content.append(chunk)
        
        routing_decision = await llm_based_intent_router(question, history_msgs, router_callback)
        
        # 输出收集到的推理内容
        if routing_chunks:
            reasoning_content = "".join(routing_chunks)
            reasoning_data = json.dumps({"content": reasoning_content, "message_type": 1}, ensure_ascii=False)
            yield f"data:{reasoning_data}\n\n".encode("utf-8")
            full_stream_content.append(reasoning_content)
        
        # 输出路由决策结果
        if routing_decision == "neo4j":
            decision_text = "需要检索网络业务知识图谱辅助回答，请稍等...."
        elif routing_decision == "es":
            decision_text = "需要检索法规标准知识辅助回答，请稍等...."
        elif routing_decision == "hybrid":
            decision_text = "需要同时检索网络业务知识图谱以及法规标准知识辅助回答，请稍等...."
        elif routing_decision == "none":
            decision_text = "大模型直接生成回答，请稍等...."
        else:
            decision_text = "检索法规标准知识辅助回答，请稍等...."  # 默认
            
        decision_output = f"{decision_text}\n"
        decision_data = json.dumps({"content": decision_output, "message_type": 1}, ensure_ascii=False)
        yield f"data:{decision_data}\n\n".encode("utf-8")
        full_stream_content.append(decision_output)
        
        # 2. 根据路由决策调用相应的函数
        if routing_decision == "es":
            # 调用ES查询，但过滤掉开始的<think>标签
            async for chunk in es_stream_gen(question, history_msgs, user_id, session_id, background_tasks, save_messages=False):
                chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                
                # 过滤掉重复的<think>开始标签
                if "data:" in chunk_str:
                    try:
                        # 解析JSON数据
                        data_part = chunk_str.split("data:")[1].strip()
                        chunk_json = json.loads(data_part)
                        content = chunk_json.get("content", "")
                        
                        # 跳过重复的think开始标签
                        if "<think>开始对用户的提问进行深入解析..." in content:
                            continue
                            
                        yield chunk
                        full_stream_content.append(content)
                    except:
                        yield chunk
                else:
                    yield chunk
                    
        elif routing_decision == "neo4j":
            # 调用Neo4j查询，但过滤掉整个<think>标签块
            in_think_block = False
            async for chunk in neo4j_stream_gen(question, history_msgs, user_id, session_id, background_tasks, save_messages=False):
                chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                
                # 过滤掉整个<think>标签块
                if "data:" in chunk_str:
                    try:
                        # 解析JSON数据
                        data_part = chunk_str.split("data:")[1].strip()
                        chunk_json = json.loads(data_part)
                        content = chunk_json.get("content", "")
                        
                        # 检查是否进入think块
                        if "<think>" in content:
                            in_think_block = True
                            continue
        
                        # 检查是否退出think块
                        if "</think>" in content:
                            in_think_block = False
                            continue
                        
                        # 如果在think块内，跳过所有内容
                        if in_think_block:
                            continue
                            
                        yield chunk
                        full_stream_content.append(content)
                    except:
                        yield chunk
                else:
                    yield chunk
                    
        elif routing_decision == "hybrid":
            # 混合调用逻辑：先使用Neo4j查询，然后ES查询法规
            
            # 1. 先输出"现在开始业务知识图谱检索"
            neo4j_start_msg = "\n现在开始业务知识图谱检索\n"
            neo4j_start_data = {
                "content": neo4j_start_msg,
                "message_type": 1
            }
            yield f"data:{json.dumps(neo4j_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
            full_stream_content.append(neo4j_start_msg)
            
            # 2. 调用Neo4j查询并收集<data>内容
            neo4j_data_content = ""
            in_data_section = False
            in_think_section = False
            
            # 需改成调用最新的
            async for chunk in neo4j_stream_gen(question, history_msgs, user_id, session_id, background_tasks, save_messages=False):
                chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                
                if "data:" in chunk_str:
                    try:
                        # 解析JSON数据
                        data_part = chunk_str.split("data:")[1].strip()
                        chunk_json = json.loads(data_part)
                        content = chunk_json.get("content", "")
                        message_type = chunk_json.get("message_type", 0)
                        
                        # 检测<think>标签的开始和结束，过滤掉原始的think标签
                        if "<think>" in content:
                            in_think_section = True
                            continue  # 跳过<think>标签
                        elif "</think>" in content:
                            in_think_section = False
                            continue  # 跳过</think>标签
                        
                        # 如果在原始think标签内，跳过不输出
                        if in_think_section:
                            continue
                        
                        # 检测<data>标签的开始和结束
                        if "<data>" in content:
                            in_data_section = True
                            continue  # 跳过<data>标签本身
                        elif "</data>" in content:
                            in_data_section = False
                            continue  # 跳过</data>标签本身
                        elif in_data_section:
                            # 在<data>标签内的内容，只收集起来用于后续合并，不在这里输出
                            neo4j_data_content += content
                    except:
                        # 解析失败时也不输出
                        continue
                else:
                    # 非data格式的chunk也不输出
                    continue
            
            # 3. 输出Neo4j检索到的数据内容（如果有的话）
            if neo4j_data_content.strip():
                neo4j_result_msg = f"\n检索到的业务信息：\n{neo4j_data_content.strip()}\n"
                neo4j_result_data = {
                    "content": neo4j_result_msg,
                    "message_type": 1
                }
                yield f"data:{json.dumps(neo4j_result_data, ensure_ascii=False)}\n\n".encode("utf-8")
                full_stream_content.append(neo4j_result_msg)
            else:
                no_neo4j_msg = "\n未检索到相关业务信息\n"
                no_neo4j_data = {
                    "content": no_neo4j_msg,
                    "message_type": 1
                }
                yield f"data:{json.dumps(no_neo4j_data, ensure_ascii=False)}\n\n".encode("utf-8")
                full_stream_content.append(no_neo4j_msg)
            
            # 4. 输出"现在开始法规标准检索"
            es_start_msg = "\n现在开始法规标准检索\n"
            es_start_data = {
                "content": es_start_msg,
                "message_type": 1
            }
            yield f"data:{json.dumps(es_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
            full_stream_content.append(es_start_msg)
            
            # 5. 将Neo4j结果拼接到问题中，调用ES查询
            enhanced_question = question
            if neo4j_data_content.strip():
                enhanced_question = question + "以下是检索到的具体业务信息：" + neo4j_data_content.strip()
            
            # 6. 调用ES查询，过滤掉开始的<think>标签，并准备合并<data>内容
            es_data_content = ""
            in_es_data_section = False
            data_section_started = False
            
            async for chunk in es_stream_gen(enhanced_question, history_msgs, user_id, session_id, background_tasks, save_messages=False):
                chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                
                # 过滤掉重复的<think>开始标签
                if "data:" in chunk_str:
                    try:
                        # 解析JSON数据
                        data_part = chunk_str.split("data:")[1].strip()
                        chunk_json = json.loads(data_part)
                        content = chunk_json.get("content", "")
                        
                        # 跳过重复的think开始标签
                        if "<think>开始对用户的提问进行深入解析..." in content:
                            continue
                        
                        # 处理<data>标签
                        if "<data>" in content and not data_section_started:
                            # 第一次遇到<data>标签，输出合并的内容
                            data_section_started = True
                            merged_data_start = "<data>\n"
                            if neo4j_data_content.strip():
                                merged_data_start += neo4j_data_content.strip() + "\n\n"
                            
                            merged_start_data = {
                                "content": merged_data_start,
                                "message_type": 2
                            }
                            yield f"data:{json.dumps(merged_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
                            full_stream_content.append(merged_data_start)
                            continue
                        elif "<data>" in content:
                            # 跳过后续的<data>开始标签
                            continue
                        elif "</data>" in content:
                            # 保持</data>结束标签
                            yield chunk
                            full_stream_content.append(content)
                        else:
                            # 正常内容
                            yield chunk
                            full_stream_content.append(content)
                    except:
                        yield chunk
                else:
                    yield chunk
                    
        else:  # 其他情况
            # 调用ES查询，但过滤掉开始的<think>标签
            async for chunk in es_stream_gen(question, history_msgs, user_id, session_id, background_tasks):
                chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                
                # 过滤掉重复的<think>开始标签
                if "data:" in chunk_str:
                    try:
                        # 解析JSON数据
                        data_part = chunk_str.split("data:")[1].strip()
                        chunk_json = json.loads(data_part)
                        content = chunk_json.get("content", "")
                        
                        # 跳过重复的think开始标签
                        if "<think>开始对用户的提问进行深入解析..." in content:
                            continue
                            
                        yield chunk
                        full_stream_content.append(content)
                    except:
                        yield chunk
                else:
                    yield chunk
                    
    except Exception as e:
        error_msg = f"查询错误: {str(e)}"
        print(f"[查询错误] {error_msg}")
        error_output = f"<data>\n抱歉，处理您的请求时出现错误: {error_msg}\n</data>"
        error_data = json.dumps({"content": error_output, "message_type": 4}, ensure_ascii=False)
        yield f"data:{error_data}\n\n".encode("utf-8")
        full_stream_content.append(error_output)
    
    finally:
        # 异步保存消息（只在独立调用时保存，被hybrid调用时不保存）
        if save_messages and full_stream_content:
            # 保存完整的用户可见内容（包括所有标签）
            complete_assistant_reply = "".join(full_stream_content)
            background_tasks.add_task(storage.append_message, user_id, session_id, "user", question)
            background_tasks.add_task(storage.append_message, user_id, session_id, "assistant", complete_assistant_reply)


"""请改成最新代码"""
async def neo4j_stream_gen(question: str, history_msgs: List[Dict[str, str]], 
                          user_id: str, session_id: str, background_tasks: BackgroundTasks,
                          save_messages: bool = True) -> AsyncGenerator[bytes, None]:
    """Neo4j专用流式生成器 (scene_id=2)
    完全调用neo4j_code模块的功能，不需要llm_based_intent_router
    """
    full_stream_content: List[str] = []
    
    try:
        # 检查Neo4j模块是否可用
        if not NEO4J_ENABLED or neo4j_llm_instance is None:
            error_msg = "Neo4j模块未启用或初始化失败"
            error_output = f"<data>\n{error_msg}\n</data>"
            error_data = json.dumps({"content": error_output, "message_type": 4}, ensure_ascii=False)
            yield f"data:{error_data}\n\n".encode("utf-8")
            full_stream_content.append(error_output)
            return
        
        # 复用neo4j_code/apps/views_intent/views.py中的LLM.generate_answer_async方法，调用最新的
        neo4j_stream_gen_func = neo4j_llm_instance.generate_answer_async(question, history_msgs)
        
        async for chunk in neo4j_stream_gen_func:
            if isinstance(chunk, bytes):
                # Neo4j模块已经返回正确格式的JSON数据，直接输出
                yield chunk
                # 解码用于收集完整内容
                chunk_str = chunk.decode("utf-8")
                full_stream_content.append(chunk_str)
            else:
                chunk_str = str(chunk)
                yield chunk_str.encode("utf-8")
                full_stream_content.append(chunk_str)
            
            # 小延迟确保流式效果
            await asyncio.sleep(0.01)
        
    except Exception as e:
        error_msg = f"Neo4j查询错误: {str(e)}"
        print(f"[Neo4j查询错误] {error_msg}")
        error_output = f"<data>\n抱歉，处理您的请求时出现错误: {error_msg}\n</data>"
        error_data = json.dumps({"content": error_output, "message_type": 4}, ensure_ascii=False)
        yield f"data:{error_data}\n\n".encode("utf-8")
        full_stream_content.append(error_output)
    
    finally:
        # 异步保存消息（只在独立调用时保存）
        if save_messages and full_stream_content:
            # 保存完整的用户可见内容（包括所有标签）
            complete_assistant_reply = "".join(full_stream_content)
            background_tasks.add_task(storage.append_message, user_id, session_id, "user", question)
            background_tasks.add_task(storage.append_message, user_id, session_id, "assistant", complete_assistant_reply)

@app.get("/")
async def index():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(current_dir, "static", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h3>前端页面不存在，请确认 LLM_Server/static/index.html 是否已创建。</h3>")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "redis": REDIS_ENABLED,
        "mysql": mysql_pool is not None,
        "elasticsearch": es_client is not None,
        "intent_parser": INTENT_PARSER_ENABLED,
        "knowledge_retrieval": KNOWLEDGE_RETRIEVAL_ENABLED
    }

# 手动触发摘要生成的API（用于测试）
@app.post("/api/admin/generate-summary")
async def manual_generate_summary(user_id: str = Query(...), session_id: str = Query(...)):
    # await generate_session_summary(user_id, session_id)
    return {"status": "ok", "message": "摘要生成任务已启动"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8011"))  # 使用不同端口避免冲突
    print(f"Starting enhanced server on 0.0.0.0:{port}")
    uvicorn.run("server2:app", host="0.0.0.0", port=port, reload=False)