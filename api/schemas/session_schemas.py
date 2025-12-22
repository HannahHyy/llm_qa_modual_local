"""
会话相关Schema定义
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    user_id: str = Field(default="default_user", description="用户ID")
    name: Optional[str] = Field(default=None, description="会话名称")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_001",
                "name": "技术咨询"
            }
        }


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    session_id: str = Field(..., description="会话ID")
    user_id: str = Field(..., description="用户ID")
    name: str = Field(..., description="会话名称")
    created_at: str = Field(..., description="创建时间")
    message_count: int = Field(default=0, description="消息数量")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "user_001",
                "name": "技术咨询",
                "created_at": "2024-01-01T10:00:00",
                "message_count": 0
            }
        }


class SessionItem(BaseModel):
    """会话条目"""
    session_id: str = Field(..., description="会话ID")
    name: str = Field(..., description="会话名称")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    message_count: int = Field(default=0, description="消息数量")


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionItem] = Field(default_factory=list, description="会话列表")
    total: int = Field(..., description="总数")
    limit: Optional[int] = Field(default=None, description="限制数量")
    offset: int = Field(default=0, description="偏移量")

    class Config:
        json_schema_extra = {
            "example": {
                "sessions": [
                    {
                        "session_id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "技术咨询",
                        "created_at": "2024-01-01T10:00:00",
                        "updated_at": "2024-01-01T11:00:00",
                        "message_count": 10
                    }
                ],
                "total": 1,
                "limit": 10,
                "offset": 0
            }
        }


class MessageItem(BaseModel):
    """消息条目"""
    role: str = Field(..., description="角色")
    content: str = Field(..., description="内容")
    timestamp: str = Field(..., description="时间戳")


class SessionDetailResponse(BaseModel):
    """会话详情响应"""
    session_id: str = Field(..., description="会话ID")
    user_id: str = Field(..., description="用户ID")
    name: str = Field(..., description="会话名称")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    message_count: int = Field(default=0, description="消息数量")
    messages: Optional[List[MessageItem]] = Field(default=None, description="消息列表")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "user_001",
                "name": "技术咨询",
                "created_at": "2024-01-01T10:00:00",
                "updated_at": "2024-01-01T11:00:00",
                "message_count": 2,
                "messages": [
                    {
                        "role": "user",
                        "content": "你好",
                        "timestamp": "2024-01-01T10:00:00"
                    },
                    {
                        "role": "assistant",
                        "content": "你好！有什么可以帮助你的？",
                        "timestamp": "2024-01-01T10:00:05"
                    }
                ]
            }
        }


class RenameSessionRequest(BaseModel):
    """重命名会话请求"""
    name: str = Field(..., min_length=1, max_length=100, description="新名称")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "等保三级咨询"
            }
        }
