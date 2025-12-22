"""
Neo4j意图解析器

基于关键词和规则识别图查询意图
"""

import re
from typing import Optional
from domain.models import Intent, IntentType
from domain.parsers.base_parser import BaseIntentParser
from core.exceptions import IntentParseError


class Neo4jIntentParser(BaseIntentParser):
    """
    Neo4j意图解析器

    识别适合使用图数据库查询的意图（关系、路径、层级等）
    """

    # Neo4j查询关键词（关系、路径、层级相关）
    NEO4J_KEYWORDS = [
        "关系", "关联", "相关性", "联系",
        "路径", "链接", "连接",
        "层级", "结构", "组织",
        "上下游", "依赖", "影响",
        "知识图谱", "图谱", "网络"
    ]

    # 实体关系词
    RELATION_KEYWORDS = [
        "之间", "和", "与", "到",
        "属于", "包含", "依赖于"
    ]

    def __init__(self):
        """初始化Neo4j意图解析器"""
        self.keyword_pattern = re.compile(
            "|".join(self.NEO4J_KEYWORDS),
            re.IGNORECASE
        )
        self.relation_pattern = re.compile(
            "|".join(self.RELATION_KEYWORDS),
            re.IGNORECASE
        )

    async def parse(self, query: str, context: Optional[dict] = None) -> Intent:
        """
        解析Neo4j查询意图

        Args:
            query: 用户查询
            context: 上下文信息

        Returns:
            Intent: Neo4j查询意图

        Raises:
            IntentParseError: 解析失败
        """
        try:
            # 预处理
            processed_query = self.preprocess_query(query)

            # 计算置信度
            confidence = self._calculate_confidence(processed_query)

            # 提取实体和关系
            entities, relations = self._extract_entities_and_relations(processed_query)

            return Intent(
                intent_type=IntentType.NEO4J_QUERY,
                confidence=confidence,
                query=query,
                parsed_query=processed_query,
                metadata={
                    "parser": "Neo4jIntentParser",
                    "keywords": self._find_keywords(processed_query),
                    "entities": entities,
                    "relations": relations
                }
            )

        except Exception as e:
            raise IntentParseError(
                f"Neo4j意图解析失败: {str(e)}",
                details={"query": query, "error": str(e)}
            )

    def can_handle(self, query: str) -> bool:
        """
        判断是否能处理该查询

        Args:
            query: 用户查询

        Returns:
            bool: 是否包含Neo4j关键词或关系词
        """
        has_neo4j_keywords = bool(self.keyword_pattern.search(query))
        has_relation_keywords = bool(self.relation_pattern.search(query))
        return has_neo4j_keywords or has_relation_keywords

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

        # Neo4j关键词权重
        neo4j_keywords_found = self._find_keywords(query)
        neo4j_boost = min(len(neo4j_keywords_found) * 0.2, 0.4)

        # 关系词权重
        relation_keywords_found = self._find_relation_keywords(query)
        relation_boost = min(len(relation_keywords_found) * 0.1, 0.2)

        confidence = base_confidence + neo4j_boost + relation_boost
        return min(confidence, 1.0)

    def _find_keywords(self, query: str) -> list:
        """
        查找Neo4j关键词

        Args:
            query: 查询文本

        Returns:
            list: 找到的关键词列表
        """
        found = []
        for keyword in self.NEO4J_KEYWORDS:
            if keyword in query:
                found.append(keyword)
        return found

    def _find_relation_keywords(self, query: str) -> list:
        """
        查找关系关键词

        Args:
            query: 查询文本

        Returns:
            list: 找到的关系词列表
        """
        found = []
        for keyword in self.RELATION_KEYWORDS:
            if keyword in query:
                found.append(keyword)
        return found

    def _extract_entities_and_relations(self, query: str) -> tuple:
        """
        提取实体和关系

        Args:
            query: 查询文本

        Returns:
            tuple: (实体列表, 关系列表)
        """
        # 简单的实体提取（可以后续用NER模型优化）
        # 这里使用基于分词的简单方法
        entities = []
        relations = self._find_relation_keywords(query)

        # 提取可能的实体（去除关键词和关系词后的主要词汇）
        cleaned_query = query
        for keyword in self.NEO4J_KEYWORDS + self.RELATION_KEYWORDS:
            cleaned_query = cleaned_query.replace(keyword, " ")

        # 分词提取实体（简单空格分割）
        potential_entities = [word.strip() for word in cleaned_query.split() if len(word.strip()) > 1]
        entities = potential_entities[:5]  # 限制最多5个实体

        return entities, relations
