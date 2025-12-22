"""
会话模型

定义会话的数据结构
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Session(BaseModel):
    """
    会话数据模型

    表示一次完整的对话会话
    """

    session_id: str = Field(..., description="会话ID")
    user_id: str = Field(..., description="用户ID")
    name: str = Field(default="对话", description="会话名称")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="更新时间")
    is_active: bool = Field(default=True, description="是否活跃")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """从字典创建会话"""
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)
