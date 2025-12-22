"""
Elasticsearch意图解析器

基于关键词和规则识别ES查询意图
"""

import re
from typing import Optional
from domain.models import Intent, IntentType
from domain.parsers.base_parser import BaseIntentParser
from core.exceptions import IntentParseError


class ESIntentParser(BaseIntentParser):
    """
    Elasticsearch意图解析器

    识别适合使用ES进行全文检索的查询
    """

    # ES查询关键词
    ES_KEYWORDS = [
        "查询", "搜索", "检索", "查找", "找到",
        "文档", "内容", "资料", "信息",
        "包含", "关于", "相关"
    ]

    def __init__(self):
        """初始化ES意图解析器"""
        self.keyword_pattern = re.compile(
            "|".join(self.ES_KEYWORDS),
            re.IGNORECASE
        )

    async def parse(self, query: str, context: Optional[dict] = None) -> Intent:
        """
        解析ES查询意图

        Args:
            query: 用户查询
            context: 上下文信息

        Returns:
            Intent: ES查询意图

        Raises:
            IntentParseError: 解析失败
        """
        try:
            # 预处理
            processed_query = self.preprocess_query(query)

            # 计算置信度
            confidence = self._calculate_confidence(processed_query)

            # 提取关键词作为解析后的查询
            parsed_query = self._extract_keywords(processed_query)

            return Intent(
                intent_type=IntentType.ES_QUERY,
                confidence=confidence,
                query=query,
                parsed_query=parsed_query,
                metadata={
                    "parser": "ESIntentParser",
                    "keywords": self._find_keywords(processed_query)
                }
            )

        except Exception as e:
            raise IntentParseError(
                f"ES意图解析失败: {str(e)}",
                details={"query": query, "error": str(e)}
            )

    def can_handle(self, query: str) -> bool:
        """
        判断是否能处理该查询

        Args:
            query: 用户查询

        Returns:
            bool: 是否包含ES关键词
        """
        return bool(self.keyword_pattern.search(query))

    def _calculate_confidence(self, query: str) -> float:
        """
        计算置信度

        Args:
            query: 查询文本

        Returns:
            float: 置信度 (0.0-1.0)
        """
        # 基础置信度
        base_confidence = 0.5

        # 如果包含ES关键词，增加置信度
        keywords_found = self._find_keywords(query)
        keyword_boost = min(len(keywords_found) * 0.15, 0.4)

        # 查询长度适中时增加置信度
        length = len(query)
        if 10 <= length <= 100:
            length_boost = 0.1
        else:
            length_boost = 0.0

        confidence = base_confidence + keyword_boost + length_boost
        return min(confidence, 1.0)

    def _find_keywords(self, query: str) -> list:
        """
        查找查询中的关键词

        Args:
            query: 查询文本

        Returns:
            list: 找到的关键词列表
        """
        found = []
        for keyword in self.ES_KEYWORDS:
            if keyword in query:
                found.append(keyword)
        return found

    def _extract_keywords(self, query: str) -> str:
        """
        提取查询关键词

        Args:
            query: 查询文本

        Returns:
            str: 提取的关键词
        """
        # 移除常见的ES查询关键词，保留实际搜索内容
        result = query
        for keyword in self.ES_KEYWORDS:
            result = result.replace(keyword, "")

        # 清理多余空格
        result = " ".join(result.split())
        return result.strip() or query
