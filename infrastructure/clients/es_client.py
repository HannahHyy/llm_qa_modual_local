"""
Elasticsearch客户端

提供Elasticsearch连接和操作的封装。
"""

from typing import Optional, Dict, Any, List
import requests
import os

from core.config import ESSettings
from core.exceptions import ElasticsearchError
from core.logging import get_logger

logger = get_logger("ESClient")


class ESClient:
    """Elasticsearch客户端类"""

    def __init__(self, settings: ESSettings):
        """
        初始化ES客户端

        Args:
            settings: ES配置
        """
        self.settings = settings
        self.url = settings.url
        self.auth = settings.auth
        self.proxies = {'http': None, 'https': None}  # 禁用代理

    def connect(self) -> None:
        """测试ES连接"""
        # 临时禁用代理环境变量
        old_proxies = {}
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            old_proxies[key] = os.environ.pop(key, None)

        try:
            response = requests.get(
                f"{self.url}/_cluster/health",
                auth=self.auth,
                timeout=self.settings.timeout,
                proxies=self.proxies
            )
            response.raise_for_status()
            logger.info(f"Elasticsearch连接成功: {self.url}")
        except Exception as e:
            logger.error(f"Elasticsearch连接失败: {e}")
            raise ElasticsearchError(f"Elasticsearch连接失败: {e}", details=str(e))
        finally:
            # 恢复代理环境变量
            for key, value in old_proxies.items():
                if value:
                    os.environ[key] = value

    def search(
        self,
        index: str,
        query: Dict[str, Any],
        size: int = 10
    ) -> Dict[str, Any]:
        """
        执行搜索

        Args:
            index: 索引名称
            query: 查询DSL
            size: 返回结果数量

        Returns:
            搜索结果
        """
        try:
            url = f"{self.url}/{index}/_search"
            body = {"query": query, "size": size}
            response = requests.post(
                url,
                json=body,
                auth=self.auth,
                timeout=self.settings.timeout,
                proxies=self.proxies
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"ES搜索失败 index={index}: {e}")
            raise ElasticsearchError(f"ES搜索失败", details={"index": index, "error": str(e)})

    def index_document(
        self,
        index: str,
        document: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        索引文档

        Args:
            index: 索引名称
            document: 文档内容
            doc_id: 文档ID（可选）

        Returns:
            索引结果
        """
        try:
            if doc_id:
                url = f"{self.url}/{index}/_doc/{doc_id}"
            else:
                url = f"{self.url}/{index}/_doc"

            response = requests.post(
                url,
                json=document,
                auth=self.auth,
                timeout=self.settings.timeout,
                proxies=self.proxies
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"ES索引文档失败 index={index}: {e}")
            raise ElasticsearchError(f"ES索引文档失败", details={"index": index, "error": str(e)})

    def delete_document(self, index: str, doc_id: str) -> Dict[str, Any]:
        """
        删除文档

        Args:
            index: 索引名称
            doc_id: 文档ID

        Returns:
            删除结果
        """
        try:
            url = f"{self.url}/{index}/_doc/{doc_id}"
            response = requests.delete(
                url,
                auth=self.auth,
                timeout=self.settings.timeout,
                proxies=self.proxies
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"ES删除文档失败 index={index}, doc_id={doc_id}: {e}")
            raise ElasticsearchError(f"ES删除文档失败", details={"index": index, "doc_id": doc_id, "error": str(e)})
