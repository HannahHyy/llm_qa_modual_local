"""
异常定义模块

定义系统中使用的所有自定义异常，形成异常层次结构。
"""

from typing import Optional, Any


class BaseAppException(Exception):
    """
    应用基础异常类

    所有自定义异常的基类，提供统一的异常处理接口。
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Any] = None,
    ):
        """
        初始化异常

        Args:
            message: 异常消息
            error_code: 错误代码（可选）
            details: 详细信息（可选）
        """
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"[{self.error_code}] {self.message} | Details: {self.details}"
        return f"[{self.error_code}] {self.message}"


# ==================== 配置相关异常 ====================


class ConfigError(BaseAppException):
    """配置错误异常"""

    pass


# ==================== 数据库相关异常 ====================


class DatabaseError(BaseAppException):
    """数据库基础异常"""

    pass


class RedisError(DatabaseError):
    """Redis相关异常"""

    pass


class MySQLError(DatabaseError):
    """MySQL相关异常"""

    pass


class ElasticsearchError(DatabaseError):
    """Elasticsearch相关异常"""

    pass


class Neo4jError(DatabaseError):
    """Neo4j相关异常"""

    pass


# ==================== LLM相关异常 ====================


class LLMClientError(BaseAppException):
    """LLM客户端异常"""

    pass


# ==================== 业务逻辑异常 ====================


class IntentParseError(BaseAppException):
    """意图解析异常"""

    pass


class RetrievalError(BaseAppException):
    """知识检索异常"""

    pass
