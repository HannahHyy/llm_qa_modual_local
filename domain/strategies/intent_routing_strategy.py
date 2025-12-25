"""
意图路由策略

根据意图选择合适的检索器和处理流程
"""

from typing import List, Optional, Dict, Any
from domain.models import Intent, IntentType, Knowledge
from domain.parsers import BaseIntentParser, ESIntentParser, Neo4jIntentParser
from domain.retrievers import BaseRetriever, ESRetriever, Neo4jRetriever, HybridRetriever
from core.logging import logger


class IntentRoutingStrategy:
    """
    意图路由策略

    根据解析的意图，智能路由到合适的检索器
    """

    def __init__(
        self,
        es_parser: ESIntentParser,
        neo4j_parser: Neo4jIntentParser,
        es_retriever: ESRetriever,
        neo4j_retriever: Neo4jRetriever,
        hybrid_retriever: HybridRetriever,
        confidence_threshold: float = 0.7
    ):
        """
        初始化路由策略

        Args:
            es_parser: ES意图解析器
            neo4j_parser: Neo4j意图解析器
            es_retriever: ES检索器
            neo4j_retriever: Neo4j检索器
            hybrid_retriever: 混合检索器
            confidence_threshold: 置信度阈值
        """
        self.parsers = {
            IntentType.ES_QUERY: es_parser,
            IntentType.NEO4J_QUERY: neo4j_parser
        }
        self.retrievers = {
            IntentType.ES_QUERY: es_retriever,
            IntentType.NEO4J_QUERY: neo4j_retriever,
            IntentType.HYBRID_QUERY: hybrid_retriever
        }
        self.hybrid_retriever = hybrid_retriever
        self.confidence_threshold = confidence_threshold

    async def route(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        top_k: int = 5
    ) -> tuple[Intent, List[Knowledge]]:
        """
        路由查询到合适的处理流程

        Args:
            query: 用户查询
            context: 上下文信息
            top_k: 返回结果数量

        Returns:
            tuple: (意图, 检索结果)
        """
        # 1. 解析意图
        intent = await self._parse_intent(query, context)

        logger.info(
            f"意图路由: query='{query}', "
            f"intent_type={intent.intent_type}, confidence={intent.confidence:.2f}"
        )

        # 2. 根据意图选择检索器
        retriever = self._select_retriever(intent)

        # 3. 执行检索
        try:
            # 检查是否是Neo4j查询且有生成的Cypher
            if (intent.intent_type == IntentType.NEO4J_QUERY and
                isinstance(retriever, Neo4jRetriever)):
                # 从intent metadata中获取生成的Cypher
                generated_cypher = intent.metadata.get("generated_cypher")
                logger.info(f"检测到Neo4j查询,generated_cypher={bool(generated_cypher)}")

                knowledge = await retriever.retrieve(
                    query=intent.parsed_query or query,
                    top_k=top_k,
                    generated_cypher=generated_cypher
                )
            else:
                # 普通检索
                knowledge = await retriever.retrieve(
                    query=intent.parsed_query or query,
                    top_k=top_k
                )
        except Exception as e:
            logger.error(f"检索失败: {str(e)}, 回退到混合检索")
            # 检索失败时回退到混合检索
            knowledge = await self.hybrid_retriever.retrieve(query, top_k)

        return intent, knowledge

    async def _parse_intent(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Intent:
        """
        解析查询意图

        Args:
            query: 用户查询
            context: 上下文信息

        Returns:
            Intent: 解析的意图
        """
        # 收集所有解析器的结果
        parse_results = []

        # ES意图解析
        es_parser = self.parsers[IntentType.ES_QUERY]
        if es_parser.can_handle(query):
            try:
                es_intent = await es_parser.parse(query, context)
                parse_results.append(es_intent)
            except Exception as e:
                logger.warning(f"ES意图解析失败: {str(e)}")

        # Neo4j意图解析
        neo4j_parser = self.parsers[IntentType.NEO4J_QUERY]
        if neo4j_parser.can_handle(query):
            try:
                neo4j_intent = await neo4j_parser.parse(query, context)
                parse_results.append(neo4j_intent)
            except Exception as e:
                logger.warning(f"Neo4j意图解析失败: {str(e)}")

        # 如果没有解析结果，默认使用混合查询
        if not parse_results:
            logger.info("未识别明确意图，使用混合查询")
            return Intent(
                intent_type=IntentType.HYBRID_QUERY,
                confidence=0.5,
                query=query,
                parsed_query=query,
                metadata={"parser": "default"}
            )

        # 如果只有一个结果
        if len(parse_results) == 1:
            return parse_results[0]

        # 如果有多个结果，选择置信度最高的
        best_intent = max(parse_results, key=lambda x: x.confidence)

        # 如果最高置信度低于阈值，使用混合查询
        if not best_intent.is_confident(self.confidence_threshold):
            logger.info(
                f"意图置信度不足（{best_intent.confidence:.2f} < {self.confidence_threshold}），"
                "使用混合查询"
            )
            return Intent(
                intent_type=IntentType.HYBRID_QUERY,
                confidence=best_intent.confidence,
                query=query,
                parsed_query=query,
                metadata={
                    "parser": "hybrid",
                    "candidates": [
                        {"type": r.intent_type, "confidence": r.confidence}
                        for r in parse_results
                    ]
                }
            )

        return best_intent

    def _select_retriever(self, intent: Intent) -> BaseRetriever:
        """
        根据意图选择检索器

        Args:
            intent: 意图对象

        Returns:
            BaseRetriever: 选择的检索器
        """
        # 根据意图类型选择检索器
        retriever = self.retrievers.get(
            intent.intent_type,
            self.hybrid_retriever  # 默认使用混合检索
        )

        logger.info(f"选择检索器: {retriever.__class__.__name__}")
        return retriever

    async def route_with_fallback(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        enable_fallback: bool = True
    ) -> tuple[Intent, List[Knowledge]]:
        """
        路由查询，支持回退机制

        Args:
            query: 用户查询
            context: 上下文信息
            top_k: 返回结果数量
            enable_fallback: 是否启用回退

        Returns:
            tuple: (意图, 检索结果)
        """
        # 首次尝试
        intent, knowledge = await self.route(query, context, top_k)

        # Neo4j查询不需要fallback - Neo4j通过执行Cypher直接返回结果
        # 即使返回0结果也是正常的(数据库中可能真的没有匹配数据)
        if intent and intent.intent_type == "neo4j_query":
            logger.info(f"Neo4j查询不启用fallback，直接返回结果: {len(knowledge)}条")
            return intent, knowledge

        # 如果结果不足且启用回退(仅对ES查询)
        if enable_fallback and len(knowledge) < top_k // 2:
            logger.info(f"检索结果不足（{len(knowledge)} < {top_k // 2}），尝试混合检索")

            try:
                # 使用混合检索器重试
                fallback_knowledge = await self.hybrid_retriever.retrieve(query, top_k)

                # 合并结果
                all_knowledge = knowledge + fallback_knowledge

                # 去重
                seen_content = set()
                unique_knowledge = []
                for k in all_knowledge:
                    if k.content not in seen_content:
                        seen_content.add(k.content)
                        unique_knowledge.append(k)

                # 排序和截断
                unique_knowledge.sort(key=lambda k: k.score, reverse=True)
                knowledge = unique_knowledge[:top_k]

                logger.info(f"回退检索完成，最终结果数: {len(knowledge)}")

            except Exception as e:
                logger.error(f"回退检索失败: {str(e)}")

        return intent, knowledge

    def get_routing_stats(self) -> Dict[str, Any]:
        """
        获取路由统计信息（预留接口）

        Returns:
            Dict: 统计信息
        """
        # 这里可以添加路由次数、成功率等统计
        return {
            "parsers": list(self.parsers.keys()),
            "retrievers": list(self.retrievers.keys()),
            "confidence_threshold": self.confidence_threshold
        }

    async def batch_route(
        self,
        queries: List[str],
        top_k: int = 5
    ) -> List[tuple[Intent, List[Knowledge]]]:
        """
        批量路由（预留接口，用于批量处理）

        Args:
            queries: 查询列表
            top_k: 每个查询的返回结果数

        Returns:
            List[tuple]: 每个查询的(意图, 检索结果)
        """
        results = []
        for query in queries:
            try:
                intent, knowledge = await self.route(query, top_k=top_k)
                results.append((intent, knowledge))
            except Exception as e:
                logger.error(f"批量路由失败: query='{query}', error={str(e)}")
                # 添加空结果
                results.append((
                    Intent(
                        intent_type=IntentType.HYBRID_QUERY,
                        confidence=0.0,
                        query=query,
                        parsed_query=query,
                        metadata={"error": str(e)}
                    ),
                    []
                ))

        return results
