"""
通用Schema定义
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    details: Optional[Any] = Field(default=None, description="错误详情")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "参数验证失败",
                "details": {"field": "query", "issue": "不能为空"}
            }
        }


class SuccessResponse(BaseModel):
    """成功响应"""
    success: bool = Field(default=True, description="是否成功")
    message: str = Field(..., description="成功消息")
    data: Optional[Any] = Field(default=None, description="响应数据")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "操作成功",
                "data": {}
            }
        }
