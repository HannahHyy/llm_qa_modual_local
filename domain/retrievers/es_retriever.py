"""
Elasticsearch检索器

使用ES进行全文检索
"""

from typing import List, Optional, Dict, Any
from domain.models import Knowledge
from domain.retrievers.base_retriever import BaseRetriever
from infrastructure.clients.es_client import ESClient
from core.exceptions import RetrievalError
from core.logging import logger


class ESRetriever(BaseRetriever):
    """
    Elasticsearch检索器

    基于ES的全文检索和语义检索
    """

    def __init__(self, es_client: ESClient, index_name: str = "knowledge"):
        """
        初始化ES检索器

        Args:
            es_client: ES客户端
            index_name: 索引名称
        """
        self.es_client = es_client
        self.index_name = index_name

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Knowledge]:
        """
        使用ES检索知识

        Args:
            query: 查询文本
            top_k: 返回结果数量
            filters: 过滤条件

        Returns:
            List[Knowledge]: 检索到的知识列表

        Raises:
            RetrievalError: 检索失败
        """
        try:
            # 预处理查询
            processed_query = self.preprocess_query(query)

            # 构建ES查询
            es_query = self._build_query(processed_query, filters)

            # 执行搜索
            results = self.es_client.search(
                index=self.index_name,
                query=es_query,
                size=top_k
            )

            # 转换为Knowledge对象
            knowledge_list = []
            hits = results.get("hits", {}).get("hits", [])
            for hit in hits:
                knowledge = Knowledge.from_es_hit(hit)
                knowledge_list.append(knowledge)

            # 后处理
            knowledge_list = self.postprocess_results(knowledge_list)

            logger.info(f"ES检索完成: query='{query}', 结果数={len(knowledge_list)}")
            return knowledge_list

        except Exception as e:
            logger.error(f"ES检索失败: {str(e)}")
            raise RetrievalError(
                f"ES检索失败: {str(e)}",
                details={"query": query, "error": str(e)}
            )

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: ES服务是否健康
        """
        try:
            return self.es_client.ping()
        except Exception as e:
            logger.error(f"ES健康检查失败: {str(e)}")
            return False

    def _build_query(self, query: str, filters: Optional[Dict[str, Any]] = None) -> dict:
        """
        构建ES查询DSL

        Args:
            query: 查询文本
            filters: 过滤条件

        Returns:
            dict: ES查询DSL
        """
        # 基础查询：多字段匹配
        base_query = {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["content^2", "title^3"],  # title权重更高
                            "type": "best_fields",
                            "fuzziness": "AUTO"
                        }
                    },
                    {
                        "match_phrase": {
                            "content": {
                                "query": query,
                                "boost": 2.0  # 短语匹配权重更高
                            }
                        }
                    }
                ],
                "minimum_should_match": 1
            }
        }

        # 添加过滤条件
        if filters:
            filter_clauses = []
            for field, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {field: value}})
                else:
                    filter_clauses.append({"term": {field: value}})

            if filter_clauses:
                base_query["bool"]["filter"] = filter_clauses

        return base_query

    async def retrieve_by_vector(
        self,
        vector: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Knowledge]:
        """
        向量检索（如果ES配置了向量字段）

        Args:
            vector: 查询向量
            top_k: 返回结果数量
            filters: 过滤条件

        Returns:
            List[Knowledge]: 检索到的知识列表
        """
        try:
            # 构建向量查询
            knn_query = {
                "field": "embedding",
                "query_vector": vector,
                "k": top_k,
                "num_candidates": top_k * 10
            }

            # 添加过滤条件
            if filters:
                knn_query["filter"] = []
                for field, value in filters.items():
                    if isinstance(value, list):
                        knn_query["filter"].append({"terms": {field: value}})
                    else:
                        knn_query["filter"].append({"term": {field: value}})

            # 执行KNN搜索
            results = self.es_client.client.search(
                index=self.index_name,
                knn=knn_query
            )

            # 转换为Knowledge对象
            knowledge_list = []
            hits = results.get("hits", {}).get("hits", [])
            for hit in hits:
                knowledge = Knowledge.from_es_hit(hit)
                knowledge_list.append(knowledge)

            logger.info(f"ES向量检索完成: 结果数={len(knowledge_list)}")
            return knowledge_list

        except Exception as e:
            logger.error(f"ES向量检索失败: {str(e)}")
            raise RetrievalError(
                f"ES向量检索失败: {str(e)}",
                details={"error": str(e)}
            )
