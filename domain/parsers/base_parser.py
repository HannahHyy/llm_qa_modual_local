"""
基础意图解析器

定义意图解析器的抽象接口
"""

from abc import ABC, abstractmethod
from typing import Optional
from domain.models import Intent


class BaseIntentParser(ABC):
    """
    意图解析器基类

    定义意图解析的标准接口
    """

    @abstractmethod
    async def parse(self, query: str, context: Optional[dict] = None) -> Intent:
        """
        解析用户查询的意图

        Args:
            query: 用户查询
            context: 上下文信息（可选）

        Returns:
            Intent: 解析后的意图

        Raises:
            IntentParseError: 解析失败时抛出
        """
        pass

    @abstractmethod
    def can_handle(self, query: str) -> bool:
        """
        判断是否能处理该查询

        Args:
            query: 用户查询

        Returns:
            bool: 是否能处理
        """
        pass

    def preprocess_query(self, query: str) -> str:
        """
        预处理查询

        Args:
            query: 原始查询

        Returns:
            str: 预处理后的查询
        """
        # 去除首尾空格
        query = query.strip()
        # 可以添加更多预处理逻辑，如分词、去停用词等
        return query
