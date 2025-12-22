"""
混合检索器

结合ES和Neo4j进行混合检索
"""

from typing import List, Optional, Dict, Any
from domain.models import Knowledge
from domain.retrievers.base_retriever import BaseRetriever
from domain.retrievers.es_retriever import ESRetriever
from domain.retrievers.neo4j_retriever import Neo4jRetriever
from core.exceptions import RetrievalError
from core.logging import logger


class HybridRetriever(BaseRetriever):
    """
    混合检索器

    结合ES的全文检索和Neo4j的关系检索，提供更全面的结果
    """

    def __init__(
        self,
        es_retriever: ESRetriever,
        neo4j_retriever: Neo4jRetriever,
        es_weight: float = 0.6,
        neo4j_weight: float = 0.4
    ):
        """
        初始化混合检索器

        Args:
            es_retriever: ES检索器
            neo4j_retriever: Neo4j检索器
            es_weight: ES结果权重
            neo4j_weight: Neo4j结果权重
        """
        self.es_retriever = es_retriever
        self.neo4j_retriever = neo4j_retriever
        self.es_weight = es_weight
        self.neo4j_weight = neo4j_weight

        # 确保权重和为1
        total_weight = es_weight + neo4j_weight
        self.es_weight = es_weight / total_weight
        self.neo4j_weight = neo4j_weight / total_weight

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Knowledge]:
        """
        混合检索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            filters: 过滤条件

        Returns:
            List[Knowledge]: 混合检索结果

        Raises:
            RetrievalError: 检索失败
        """
        try:
            # 并行执行两种检索
            es_results = []
            neo4j_results = []

            # ES检索
            try:
                es_results = await self.es_retriever.retrieve(
                    query=query,
                    top_k=top_k * 2,  # 获取更多结果用于混合
                    filters=filters
                )
            except Exception as e:
                logger.warning(f"ES检索失败，仅使用Neo4j结果: {str(e)}")

            # Neo4j检索
            try:
                neo4j_results = await self.neo4j_retriever.retrieve(
                    query=query,
                    top_k=top_k * 2,
                    filters=filters
                )
            except Exception as e:
                logger.warning(f"Neo4j检索失败，仅使用ES结果: {str(e)}")

            # 如果两者都失败，抛出异常
            if not es_results and not neo4j_results:
                raise RetrievalError("ES和Neo4j检索均失败")

            # 重新计算分数并合并
            combined_results = self._combine_results(
                es_results,
                neo4j_results
            )

            # 后处理和截断
            combined_results = self.postprocess_results(combined_results)
            final_results = combined_results[:top_k]

            logger.info(
                f"混合检索完成: query='{query}', "
                f"ES结果={len(es_results)}, Neo4j结果={len(neo4j_results)}, "
                f"最终结果={len(final_results)}"
            )

            return final_results

        except Exception as e:
            logger.error(f"混合检索失败: {str(e)}")
            raise RetrievalError(
                f"混合检索失败: {str(e)}",
                details={"query": query, "error": str(e)}
            )

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: 至少一个检索器健康即可
        """
        es_healthy = await self.es_retriever.health_check()
        neo4j_healthy = await self.neo4j_retriever.health_check()

        if not es_healthy and not neo4j_healthy:
            logger.error("ES和Neo4j均不健康")
            return False

        if not es_healthy:
            logger.warning("ES不健康，仅Neo4j可用")
        if not neo4j_healthy:
            logger.warning("Neo4j不健康，仅ES可用")

        return True

    def _combine_results(
        self,
        es_results: List[Knowledge],
        neo4j_results: List[Knowledge]
    ) -> List[Knowledge]:
        """
        合并ES和Neo4j结果

        Args:
            es_results: ES检索结果
            neo4j_results: Neo4j检索结果

        Returns:
            List[Knowledge]: 合并后的结果
        """
        # 重新计算分数
        for knowledge in es_results:
            knowledge.score = knowledge.score * self.es_weight
            knowledge.metadata["source_retriever"] = "es"

        for knowledge in neo4j_results:
            knowledge.score = knowledge.score * self.neo4j_weight
            knowledge.metadata["source_retriever"] = "neo4j"

        # 合并结果
        combined = es_results + neo4j_results

        # 去重：如果内容相同，保留分数更高的
        content_map = {}
        for knowledge in combined:
            content = knowledge.content
            if content in content_map:
                # 如果已存在，比较分数
                existing = content_map[content]
                if knowledge.score > existing.score:
                    content_map[content] = knowledge
            else:
                content_map[content] = knowledge

        # 转换为列表并排序
        unique_results = list(content_map.values())
        unique_results.sort(key=lambda k: k.score, reverse=True)

        return unique_results

    async def retrieve_with_context(
        self,
        query: str,
        top_k: int = 5,
        include_relationships: bool = True,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        检索并包含上下文信息

        Args:
            query: 查询文本
            top_k: 返回结果数量
            include_relationships: 是否包含关系信息
            filters: 过滤条件

        Returns:
            Dict: 包含检索结果和上下文的字典
        """
        try:
            # 基础检索
            base_results = await self.retrieve(query, top_k, filters)

            # 构建结果字典
            result_dict = {
                "results": base_results,
                "total": len(base_results),
                "es_count": sum(1 for k in base_results if k.metadata.get("source_retriever") == "es"),
                "neo4j_count": sum(1 for k in base_results if k.metadata.get("source_retriever") == "neo4j"),
            }

            # 如果需要关系信息，尝试为每个结果获取相关实体
            if include_relationships and base_results:
                relationships = []
                for knowledge in base_results[:3]:  # 只为前3个结果获取关系
                    # 如果有标题，使用标题作为实体名
                    if knowledge.title:
                        try:
                            rel_results = await self.neo4j_retriever.retrieve_relationships(
                                entity=knowledge.title,
                                depth=1,
                                top_k=3
                            )
                            if rel_results:
                                relationships.append({
                                    "entity": knowledge.title,
                                    "related": rel_results
                                })
                        except Exception as e:
                            logger.warning(f"获取关系失败: {str(e)}")

                result_dict["relationships"] = relationships

            return result_dict

        except Exception as e:
            logger.error(f"上下文检索失败: {str(e)}")
            raise RetrievalError(
                f"上下文检索失败: {str(e)}",
                details={"query": query, "error": str(e)}
            )
