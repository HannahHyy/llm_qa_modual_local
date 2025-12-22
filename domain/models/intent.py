"""
意图模型

定义意图识别的数据结构
"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """
    意图类型枚举

    定义系统支持的查询类型
    """
    ES_QUERY = "es_query"  # Elasticsearch查询
    NEO4J_QUERY = "neo4j_query"  # Neo4j图查询
    HYBRID_QUERY = "hybrid_query"  # 混合查询


class Intent(BaseModel):
    """
    意图数据模型

    表示从用户查询中识别出的意图
    """

    intent_type: IntentType = Field(..., description="意图类型")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    query: str = Field(..., description="原始查询")
    parsed_query: Optional[str] = Field(default=None, description="解析后的查询")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")

    class Config:
        use_enum_values = True

    def is_es_query(self) -> bool:
        """是否为ES查询"""
        return self.intent_type == IntentType.ES_QUERY

    def is_neo4j_query(self) -> bool:
        """是否为Neo4j查询"""
        return self.intent_type == IntentType.NEO4J_QUERY

    def is_hybrid_query(self) -> bool:
        """是否为混合查询"""
        return self.intent_type == IntentType.HYBRID_QUERY

    def is_confident(self, threshold: float = 0.7) -> bool:
        """
        是否达到置信度阈值

        Args:
            threshold: 置信度阈值，默认0.7

        Returns:
            bool: 是否达到阈值
        """
        return self.confidence >= threshold

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "intent_type": self.intent_type,
            "confidence": self.confidence,
            "query": self.query,
            "parsed_query": self.parsed_query,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Intent":
        """从字典创建意图"""
        return cls(**data)
