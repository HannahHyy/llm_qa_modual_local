"""
对话相关Schema定义
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., min_length=1, description="用户查询")
    user_id: str = Field(default="default_user", description="用户ID")
    enable_knowledge: bool = Field(default=True, description="是否启用知识检索")
    top_k: int = Field(default=5, ge=1, le=20, description="知识检索数量")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="额外元数据")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "query": "什么是等保三级？",
                "user_id": "user_001",
                "enable_knowledge": True,
                "top_k": 5
            }
        }


class KnowledgeItem(BaseModel):
    """知识条目"""
    content: str = Field(..., description="知识内容")
    source: str = Field(..., description="知识来源")
    score: float = Field(..., description="相关性分数")
    title: Optional[str] = Field(default=None, description="知识标题")


class IntentInfo(BaseModel):
    """意图信息"""
    intent_type: str = Field(..., description="意图类型")
    confidence: float = Field(..., description="置信度")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class ChatResponse(BaseModel):
    """对话响应"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="用户查询")
    response: str = Field(..., description="助手回复")
    intent: Optional[IntentInfo] = Field(default=None, description="识别的意图")
    knowledge_count: int = Field(default=0, description="使用的知识数量")
    knowledge: List[KnowledgeItem] = Field(default_factory=list, description="知识列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "query": "什么是等保三级？",
                "response": "等保三级是指国家信息安全等级保护的第三级...",
                "intent": {
                    "intent_type": "es_query",
                    "confidence": 0.85,
                    "metadata": {}
                },
                "knowledge_count": 3,
                "knowledge": [
                    {
                        "content": "等保三级要求...",
                        "source": "elasticsearch",
                        "score": 0.92,
                        "title": "等保三级介绍"
                    }
                ],
                "metadata": {
                    "llm_model": "gpt-3.5-turbo",
                    "usage": {"total_tokens": 150}
                }
            }
        }


class StreamChatRequest(BaseModel):
    """流式对话请求"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., min_length=1, description="用户查询")
    user_id: str = Field(default="default_user", description="用户ID")
    enable_knowledge: bool = Field(default=True, description="是否启用知识检索")
    top_k: int = Field(default=5, ge=1, le=20, description="知识检索数量")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "query": "什么是等保三级？",
                "user_id": "user_001",
                "enable_knowledge": True,
                "top_k": 5
            }
        }
