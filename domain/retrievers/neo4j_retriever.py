"""
Neo4j检索器

使用Neo4j进行图查询和关系检索
"""

from typing import List, Optional, Dict, Any
from domain.models import Knowledge
from domain.retrievers.base_retriever import BaseRetriever
from infrastructure.clients.neo4j_client import Neo4jClient
from core.exceptions import RetrievalError
from core.logging import logger


class Neo4jRetriever(BaseRetriever):
    """
    Neo4j检索器

    基于图数据库的关系检索和路径查询
    """

    def __init__(self, neo4j_client: Neo4jClient):
        """
        初始化Neo4j检索器

        Args:
            neo4j_client: Neo4j客户端
        """
        self.neo4j_client = neo4j_client

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Knowledge]:
        """
        使用Neo4j检索知识

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

            # 构建Cypher查询
            cypher_query, params = self._build_cypher_query(
                processed_query,
                top_k,
                filters
            )

            # 执行查询
            results = self.neo4j_client.execute_query(cypher_query, params)

            # 转换为Knowledge对象
            knowledge_list = []
            for record in results:
                knowledge = Knowledge.from_neo4j_record(
                    record,
                    score=record.get("score", 1.0)
                )
                knowledge_list.append(knowledge)

            # 后处理
            knowledge_list = self.postprocess_results(knowledge_list)

            logger.info(f"Neo4j检索完成: query='{query}', 结果数={len(knowledge_list)}")
            return knowledge_list

        except Exception as e:
            logger.error(f"Neo4j检索失败: {str(e)}")
            raise RetrievalError(
                f"Neo4j检索失败: {str(e)}",
                details={"query": query, "error": str(e)}
            )

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: Neo4j服务是否健康
        """
        try:
            # 执行简单查询测试连接
            self.neo4j_client.execute_query("RETURN 1 AS test")
            return True
        except Exception as e:
            logger.error(f"Neo4j健康检查失败: {str(e)}")
            return False

    def _build_cypher_query(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """
        构建Cypher查询

        Args:
            query: 查询文本
            top_k: 返回数量
            filters: 过滤条件

        Returns:
            tuple: (cypher查询, 参数字典)
        """
        # 基础查询：全文搜索节点
        cypher = """
        CALL db.index.fulltext.queryNodes('knowledge_index', $query)
        YIELD node, score
        """

        # 添加过滤条件
        where_clauses = []
        if filters:
            for field, value in filters.items():
                if isinstance(value, list):
                    where_clauses.append(f"node.{field} IN ${field}")
                else:
                    where_clauses.append(f"node.{field} = ${field}")

        if where_clauses:
            cypher += "WHERE " + " AND ".join(where_clauses) + "\n"

        # 返回结果
        cypher += """
        RETURN node.content AS content,
               node.title AS title,
               node.id AS id,
               labels(node)[0] AS node_type,
               properties(node) AS properties,
               score
        ORDER BY score DESC
        LIMIT $limit
        """

        # 构建参数
        params = {"query": query, "limit": top_k}
        if filters:
            params.update(filters)

        return cypher, params

    async def retrieve_relationships(
        self,
        entity: str,
        relationship_type: Optional[str] = None,
        depth: int = 1,
        top_k: int = 10
    ) -> List[Knowledge]:
        """
        检索实体的关系

        Args:
            entity: 实体名称
            relationship_type: 关系类型（可选）
            depth: 查询深度
            top_k: 返回数量

        Returns:
            List[Knowledge]: 关系知识列表
        """
        try:
            # 构建关系查询
            if relationship_type:
                cypher = f"""
                MATCH (n)-[r:{relationship_type}*1..{depth}]-(m)
                WHERE n.name = $entity OR n.title = $entity
                RETURN DISTINCT m.content AS content,
                       m.title AS title,
                       m.id AS id,
                       type(r) AS relationship,
                       labels(m)[0] AS node_type,
                       properties(m) AS properties
                LIMIT $limit
                """
            else:
                cypher = f"""
                MATCH (n)-[r*1..{depth}]-(m)
                WHERE n.name = $entity OR n.title = $entity
                RETURN DISTINCT m.content AS content,
                       m.title AS title,
                       m.id AS id,
                       labels(m)[0] AS node_type,
                       properties(m) AS properties
                LIMIT $limit
                """

            params = {"entity": entity, "limit": top_k}

            # 执行查询
            results = self.neo4j_client.execute_query(cypher, params)

            # 转换为Knowledge对象
            knowledge_list = []
            for record in results:
                knowledge = Knowledge.from_neo4j_record(record, score=0.9)
                knowledge_list.append(knowledge)

            logger.info(f"Neo4j关系检索完成: entity='{entity}', 结果数={len(knowledge_list)}")
            return knowledge_list

        except Exception as e:
            logger.error(f"Neo4j关系检索失败: {str(e)}")
            raise RetrievalError(
                f"Neo4j关系检索失败: {str(e)}",
                details={"entity": entity, "error": str(e)}
            )

    async def retrieve_paths(
        self,
        start_entity: str,
        end_entity: str,
        max_depth: int = 3
    ) -> List[Knowledge]:
        """
        检索两个实体之间的路径

        Args:
            start_entity: 起始实体
            end_entity: 结束实体
            max_depth: 最大深度

        Returns:
            List[Knowledge]: 路径知识列表
        """
        try:
            cypher = f"""
            MATCH path = shortestPath(
                (start)-[*1..{max_depth}]-(end)
            )
            WHERE (start.name = $start OR start.title = $start)
              AND (end.name = $end OR end.title = $end)
            RETURN nodes(path) AS nodes,
                   relationships(path) AS relationships,
                   length(path) AS path_length
            LIMIT 5
            """

            params = {"start": start_entity, "end": end_entity}

            # 执行查询
            results = self.neo4j_client.execute_query(cypher, params)

            # 转换为Knowledge对象（路径摘要）
            knowledge_list = []
            for record in results:
                nodes = record.get("nodes", [])
                rels = record.get("relationships", [])
                path_length = record.get("path_length", 0)

                # 构建路径描述
                path_desc = self._build_path_description(nodes, rels)

                knowledge = Knowledge(
                    content=path_desc,
                    source="neo4j",
                    score=1.0 / (path_length + 1),  # 路径越短分数越高
                    title=f"路径: {start_entity} → {end_entity}",
                    metadata={
                        "path_length": path_length,
                        "nodes_count": len(nodes),
                        "relationships_count": len(rels)
                    }
                )
                knowledge_list.append(knowledge)

            logger.info(f"Neo4j路径检索完成: {start_entity} → {end_entity}, 路径数={len(knowledge_list)}")
            return knowledge_list

        except Exception as e:
            logger.error(f"Neo4j路径检索失败: {str(e)}")
            raise RetrievalError(
                f"Neo4j路径检索失败: {str(e)}",
                details={"start": start_entity, "end": end_entity, "error": str(e)}
            )

    def _build_path_description(self, nodes: list, relationships: list) -> str:
        """
        构建路径描述

        Args:
            nodes: 节点列表
            relationships: 关系列表

        Returns:
            str: 路径描述
        """
        if not nodes:
            return ""

        path_parts = []
        for i, node in enumerate(nodes):
            node_name = node.get("name") or node.get("title") or "节点"
            path_parts.append(node_name)

            if i < len(relationships):
                rel_type = relationships[i].get("type", "关联")
                path_parts.append(f" -{rel_type}→ ")

        return "".join(path_parts)
