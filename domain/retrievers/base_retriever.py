"""
基础检索器

定义检索器的抽象接口
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from domain.models import Knowledge


class BaseRetriever(ABC):
    """
    检索器基类

    定义知识检索的标准接口
    """

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Knowledge]:
        """
        检索相关知识

        Args:
            query: 查询文本
            top_k: 返回结果数量
            filters: 过滤条件

        Returns:
            List[Knowledge]: 检索到的知识列表

        Raises:
            RetrievalError: 检索失败时抛出
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: 服务是否健康
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
        # 可以添加更多预处理逻辑
        return query

    def postprocess_results(self, results: List[Knowledge]) -> List[Knowledge]:
        """
        后处理检索结果

        Args:
            results: 原始结果

        Returns:
            List[Knowledge]: 处理后的结果
        """
        # 去重
        seen_content = set()
        unique_results = []
        for knowledge in results:
            if knowledge.content not in seen_content:
                seen_content.add(knowledge.content)
                unique_results.append(knowledge)

        # 按分数排序
        unique_results.sort(key=lambda k: k.score, reverse=True)

        return unique_results
