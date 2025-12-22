"""
消息模型

定义消息的数据结构
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    """
    消息数据模型

    表示用户或助手的一条消息
    """

    role: str = Field(..., description="角色：user或assistant")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow, description="时间戳")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """从字典创建消息"""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

    def is_user(self) -> bool:
        """是否是用户消息"""
        return self.role == "user"

    def is_assistant(self) -> bool:
        """是否是助手消息"""
        return self.role == "assistant"
