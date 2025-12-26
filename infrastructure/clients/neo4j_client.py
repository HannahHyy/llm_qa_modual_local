"""
Neo4j客户端

封装Neo4j图数据库操作
"""

from typing import List, Dict, Any, Optional
from core.config import Neo4jSettings
from core.exceptions import Neo4jError
from core.logging import logger
from core.retry import retry_sync


class Neo4jClient:
    """
    Neo4j客户端

    提供Neo4j图数据库的基本操作
    """

    def __init__(self, settings: Neo4jSettings):
        """
        初始化Neo4j客户端

        Args:
            settings: Neo4j配置
        """
        self.settings = settings
        self._driver = None

    def connect(self) -> None:
        """建立Neo4j连接"""
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.settings.uri,
                auth=(self.settings.user, self.settings.password)
            )

            # 测试连接
            with self._driver.session() as session:
                session.run("RETURN 1")

            logger.info(f"Neo4j连接成功: {self.settings.uri}")

        except ImportError:
            logger.warning("neo4j包未安装，Neo4j功能将不可用")
            raise Neo4jError(
                "neo4j包未安装，请运行: pip install neo4j",
                details={"uri": self.settings.uri}
            )
        except Exception as e:
            logger.error(f"Neo4j连接失败: {str(e)}")
            raise Neo4jError(
                f"Neo4j连接失败: {str(e)}",
                details={"uri": self.settings.uri, "error": str(e)}
            )

    def close(self) -> None:
        """关闭Neo4j连接"""
        if self._driver:
            self._driver.close()
            logger.info("Neo4j连接已关闭")

    def get_driver(self):
        """
        获取Neo4j driver

        Returns:
            Neo4j driver实例

        Raises:
            Neo4jError: 如果未连接
        """
        if not self._driver:
            raise Neo4jError("Neo4j未连接，请先调用connect()")
        return self._driver

    @retry_sync(max_attempts=3, delay=0.5, backoff=2.0)
    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行Cypher查询

        Args:
            query: Cypher查询语句
            parameters: 查询参数

        Returns:
            List[Dict]: 查询结果列表

        Raises:
            Neo4jError: 查询失败时抛出
        """
        try:
            driver = self.get_driver()

            with driver.session() as session:
                result = session.run(query, parameters or {})

                # 转换为字典列表
                records = []
                for record in result:
                    records.append(dict(record))

                return records

        except Exception as e:
            logger.error(f"Neo4j查询失败: {str(e)}")
            raise Neo4jError(
                f"Neo4j查询失败: {str(e)}",
                details={"query": query, "parameters": parameters, "error": str(e)}
            )

    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行写入操作

        Args:
            query: Cypher查询语句
            parameters: 查询参数

        Returns:
            Dict: 操作结果

        Raises:
            Neo4jError: 操作失败时抛出
        """
        try:
            driver = self.get_driver()

            with driver.session() as session:
                result = session.write_transaction(
                    lambda tx: tx.run(query, parameters or {})
                )

                summary = result.consume()

                return {
                    "nodes_created": summary.counters.nodes_created,
                    "relationships_created": summary.counters.relationships_created,
                    "properties_set": summary.counters.properties_set
                }

        except Exception as e:
            logger.error(f"Neo4j写入失败: {str(e)}")
            raise Neo4jError(
                f"Neo4j写入失败: {str(e)}",
                details={"query": query, "parameters": parameters, "error": str(e)}
            )

    def is_connected(self) -> bool:
        """
        检查是否已连接

        Returns:
            bool: 是否已连接
        """
        return self._driver is not None

    def ping(self) -> bool:
        """
        测试连接

        Returns:
            bool: 连接是否正常
        """
        try:
            self.execute_query("RETURN 1 AS test")
            return True
        except Exception:
            return False
