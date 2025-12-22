"""
知识匹配器

负责对检索到的知识进行过滤、排序和匹配
"""

from typing import List, Optional, Callable
from domain.models import Knowledge, Intent


class KnowledgeMatcher:
    """
    知识匹配器

    对检索结果进行智能匹配和筛选
    """

    def __init__(
        self,
        relevance_threshold: float = 0.5,
        max_results: int = 5,
        diversity_weight: float = 0.3
    ):
        """
        初始化知识匹配器

        Args:
            relevance_threshold: 相关性阈值
            max_results: 最大返回数量
            diversity_weight: 多样性权重
        """
        self.relevance_threshold = relevance_threshold
        self.max_results = max_results
        self.diversity_weight = diversity_weight

    def match(
        self,
        knowledge_list: List[Knowledge],
        intent: Optional[Intent] = None,
        query: Optional[str] = None
    ) -> List[Knowledge]:
        """
        匹配知识

        Args:
            knowledge_list: 原始知识列表
            intent: 用户意图
            query: 查询文本

        Returns:
            List[Knowledge]: 匹配后的知识列表
        """
        if not knowledge_list:
            return []

        # 1. 过滤低相关性结果
        filtered = self._filter_by_relevance(knowledge_list)

        # 2. 根据意图调整分数
        if intent:
            filtered = self._adjust_scores_by_intent(filtered, intent)

        # 3. 去重（保留分数高的）
        filtered = self._deduplicate(filtered)

        # 4. 多样性调整
        filtered = self._ensure_diversity(filtered)

        # 5. 排序和截断
        filtered.sort(key=lambda k: k.score, reverse=True)
        final = filtered[:self.max_results]

        return final

    def _filter_by_relevance(self, knowledge_list: List[Knowledge]) -> List[Knowledge]:
        """
        按相关性过滤

        Args:
            knowledge_list: 知识列表

        Returns:
            List[Knowledge]: 过滤后的列表
        """
        return [k for k in knowledge_list if k.is_relevant(self.relevance_threshold)]

    def _adjust_scores_by_intent(
        self,
        knowledge_list: List[Knowledge],
        intent: Intent
    ) -> List[Knowledge]:
        """
        根据意图调整分数

        Args:
            knowledge_list: 知识列表
            intent: 用户意图

        Returns:
            List[Knowledge]: 调整后的列表
        """
        # 如果意图是ES查询，提升ES来源的知识分数
        if intent.is_es_query():
            for k in knowledge_list:
                if k.is_from_es():
                    k.score = min(k.score * 1.2, 1.0)

        # 如果意图是Neo4j查询，提升Neo4j来源的知识分数
        elif intent.is_neo4j_query():
            for k in knowledge_list:
                if k.is_from_neo4j():
                    k.score = min(k.score * 1.2, 1.0)

        return knowledge_list

    def _deduplicate(self, knowledge_list: List[Knowledge]) -> List[Knowledge]:
        """
        去重

        Args:
            knowledge_list: 知识列表

        Returns:
            List[Knowledge]: 去重后的列表
        """
        seen_content = {}
        unique_list = []

        for k in knowledge_list:
            # 使用内容的前100字符作为去重键
            content_key = k.content[:100]

            if content_key in seen_content:
                # 如果已存在，保留分数更高的
                existing = seen_content[content_key]
                if k.score > existing.score:
                    # 替换为新的
                    unique_list.remove(existing)
                    unique_list.append(k)
                    seen_content[content_key] = k
            else:
                unique_list.append(k)
                seen_content[content_key] = k

        return unique_list

    def _ensure_diversity(self, knowledge_list: List[Knowledge]) -> List[Knowledge]:
        """
        确保结果多样性

        Args:
            knowledge_list: 知识列表

        Returns:
            List[Knowledge]: 多样化后的列表
        """
        if len(knowledge_list) <= 1:
            return knowledge_list

        # 计算内容相似度（简单方法：基于共同词汇）
        diverse_list = [knowledge_list[0]]  # 保留第一个（分数最高）

        for k in knowledge_list[1:]:
            # 计算与已选结果的平均相似度
            avg_similarity = self._calculate_avg_similarity(k, diverse_list)

            # 根据多样性调整分数
            diversity_penalty = avg_similarity * self.diversity_weight
            k.score = k.score * (1 - diversity_penalty)

            diverse_list.append(k)

        return diverse_list

    def _calculate_avg_similarity(
        self,
        knowledge: Knowledge,
        reference_list: List[Knowledge]
    ) -> float:
        """
        计算平均相似度

        Args:
            knowledge: 待比较的知识
            reference_list: 参考列表

        Returns:
            float: 平均相似度 (0-1)
        """
        if not reference_list:
            return 0.0

        # 简单的词汇重叠相似度
        k_words = set(knowledge.content.split())

        similarities = []
        for ref in reference_list:
            ref_words = set(ref.content.split())
            if k_words and ref_words:
                intersection = len(k_words & ref_words)
                union = len(k_words | ref_words)
                similarity = intersection / union if union > 0 else 0.0
                similarities.append(similarity)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def filter_by_metadata(
        self,
        knowledge_list: List[Knowledge],
        metadata_filter: Callable[[dict], bool]
    ) -> List[Knowledge]:
        """
        根据元数据过滤

        Args:
            knowledge_list: 知识列表
            metadata_filter: 元数据过滤函数

        Returns:
            List[Knowledge]: 过滤后的列表
        """
        return [k for k in knowledge_list if metadata_filter(k.metadata)]

    def rerank(
        self,
        knowledge_list: List[Knowledge],
        query: str,
        rerank_model: Optional[Callable] = None
    ) -> List[Knowledge]:
        """
        重排序（预留接口，可集成重排序模型）

        Args:
            knowledge_list: 知识列表
            query: 查询文本
            rerank_model: 重排序模型

        Returns:
            List[Knowledge]: 重排序后的列表
        """
        if not rerank_model:
            # 如果没有重排序模型，保持原顺序
            return knowledge_list

        # 使用重排序模型
        try:
            # 这里是预留接口，实际需要根据具体模型实现
            reranked_scores = rerank_model(query, [k.content for k in knowledge_list])

            # 更新分数
            for k, new_score in zip(knowledge_list, reranked_scores):
                k.score = new_score

            # 重新排序
            knowledge_list.sort(key=lambda k: k.score, reverse=True)

        except Exception as e:
            # 重排序失败，返回原列表
            pass

        return knowledge_list

    def merge_knowledge_sources(
        self,
        es_knowledge: List[Knowledge],
        neo4j_knowledge: List[Knowledge],
        intent: Optional[Intent] = None
    ) -> List[Knowledge]:
        """
        合并多个知识源

        Args:
            es_knowledge: ES检索结果
            neo4j_knowledge: Neo4j检索结果
            intent: 用户意图

        Returns:
            List[Knowledge]: 合并后的知识列表
        """
        # 合并所有知识
        all_knowledge = es_knowledge + neo4j_knowledge

        # 使用match方法进行统一处理
        matched = self.match(all_knowledge, intent)

        return matched
