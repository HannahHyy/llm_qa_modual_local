"""
Neo4j查询服务

封装旧版Neo4j模块的功能，提供Clean Architecture接口
这个服务复用old/neo4j_code模块的验证过的算法逻辑
"""

import sys
import os
import json
import asyncio
from typing import List, Dict, Optional, AsyncGenerator

from infrastructure.clients.llm_client import LLMClient
from core.logging import logger
from core.config import (
    get_settings,
    get_neo4j_intent_only_prompt,
    get_neo4j_batch_cypher_prompt,
    get_neo4j_summary_prompt,
    get_llm_model_settings
)

# 导入旧Neo4j模块（通过sys.path）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "old"))

try:
    from neo4j_code.apps.views_intent.views_new import LLM as Neo4jLLM
    NEO4J_MODULE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Neo4j模块不可用: {e}")
    NEO4J_MODULE_AVAILABLE = False


class Neo4jQueryService:
    """
    Neo4j查询服务 - Clean Architecture封装

    职责:
    - 封装old/neo4j_code模块的功能
    - 提供符合新架构的接口
    - 保持旧代码的算法逻辑不变
    """

    def __init__(self, llm_client: LLMClient):
        """
        初始化服务

        Args:
            llm_client: LLM客户端实例
        """
        self.llm_client = llm_client
        self.settings = get_settings()
        self.model_settings = get_llm_model_settings()

        # 初始化旧模块的Neo4jLLM实例
        self.neo4j_llm = None
        if NEO4J_MODULE_AVAILABLE:
            try:
                self.neo4j_llm = Neo4jLLM()
                logger.info("[Neo4j服务] 成功初始化Neo4j模块")
            except Exception as e:
                logger.error(f"[Neo4j服务] 初始化Neo4j模块失败: {e}")
                self.neo4j_llm = None

    def is_available(self) -> bool:
        """检查Neo4j模块是否可用"""
        return NEO4J_MODULE_AVAILABLE and self.neo4j_llm is not None

    async def query_stream(
        self,
        question: str,
        history_msgs: List[Dict[str, str]]
    ) -> AsyncGenerator[bytes, None]:
        """
        执行Neo4j查询并流式返回结果

        这个方法完全复用old/neo4j_code/apps/views_intent/views_new.py中的
        LLM.generate_answer_async方法的算法逻辑

        Args:
            question: 用户问题
            history_msgs: 历史消息列表

        Yields:
            bytes: 流式输出的字节数据，格式为:
                   data:{"content": "...", "msg_type": 1/2/3}
                   msg_type: 1=think, 2=data, 3=knowledge
        """
        if not self.is_available():
            error_data = {
                "content": "<data>\nNeo4j模块未启用或初始化失败，请检查配置和依赖\n</data>",
                "msg_type": 2
            }
            yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")
            return

        try:
            # 直接调用旧模块的generate_answer_async方法
            # 该方法已经实现了完整的Neo4j查询流程：
            # 1. 意图识别（流式输出）
            # 2. ES匹配示例
            # 3. Cypher生成（流式输出）
            # 4. 执行查询
            # 5. 生成摘要（流式输出）
            # 6. 输出知识结果
            async for chunk in self.neo4j_llm.generate_answer_async(question, history_msgs):
                if isinstance(chunk, bytes):
                    yield chunk
                else:
                    # 确保输出是bytes
                    chunk_str = str(chunk) if not isinstance(chunk, str) else chunk
                    yield chunk_str.encode("utf-8")

                # 小延迟确保流式效果
                await asyncio.sleep(0.01)

        except Exception as e:
            error_msg = f"Neo4j查询错误: {str(e)}"
            logger.error(f"[Neo4j服务] {error_msg}")
            error_data = {
                "content": f"<data>\n抱歉，处理您的请求时出现错误: {error_msg}\n</data>",
                "msg_type": 2
            }
            yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")


__all__ = ["Neo4jQueryService"]
