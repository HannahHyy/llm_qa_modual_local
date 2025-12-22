"""
知识模型

定义知识检索的数据结构
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class KnowledgeSource(str):
    """知识来源常量"""
    ELASTICSEARCH = "elasticsearch"
    NEO4J = "neo4j"
    HYBRID = "hybrid"


class Knowledge(BaseModel):
    """
    知识数据模型

    表示从知识库检索到的知识条目
    """

    content: str = Field(..., description="知识内容")
    source: str = Field(..., description="知识来源")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="相关性分数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    title: Optional[str] = Field(default=None, description="知识标题")
    doc_id: Optional[str] = Field(default=None, description="文档ID")

    def is_from_es(self) -> bool:
        """是否来自Elasticsearch"""
        return self.source == KnowledgeSource.ELASTICSEARCH

    def is_from_neo4j(self) -> bool:
        """是否来自Neo4j"""
        return self.source == KnowledgeSource.NEO4J

    def is_relevant(self, threshold: float = 0.5) -> bool:
        """
        是否达到相关性阈值

        Args:
            threshold: 相关性阈值，默认0.5

        Returns:
            bool: 是否相关
        """
        return self.score >= threshold

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "content": self.content,
            "source": self.source,
            "score": self.score,
            "metadata": self.metadata,
            "title": self.title,
            "doc_id": self.doc_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Knowledge":
        """从字典创建知识"""
        return cls(**data)

    @classmethod
    def from_es_hit(cls, hit: Dict[str, Any]) -> "Knowledge":
        """
        从Elasticsearch命中结果创建知识

        Args:
            hit: ES的hit对象

        Returns:
            Knowledge: 知识对象
        """
        source = hit.get("_source", {})
        return cls(
            content=source.get("content", ""),
            source=KnowledgeSource.ELASTICSEARCH,
            score=hit.get("_score", 0.0),
            title=source.get("title"),
            doc_id=hit.get("_id"),
            metadata={
                "index": hit.get("_index"),
                "type": hit.get("_type"),
                **source.get("metadata", {})
            }
        )

    @classmethod
    def from_neo4j_record(cls, record: Dict[str, Any], score: float = 1.0) -> "Knowledge":
        """
        从Neo4j记录创建知识

        Args:
            record: Neo4j的记录
            score: 相关性分数

        Returns:
            Knowledge: 知识对象
        """
        return cls(
            content=record.get("content", ""),
            source=KnowledgeSource.NEO4J,
            score=score,
            title=record.get("title"),
            doc_id=record.get("id"),
            metadata={
                "node_type": record.get("node_type"),
                "properties": record.get("properties", {}),
                **record.get("metadata", {})
            }
        )
