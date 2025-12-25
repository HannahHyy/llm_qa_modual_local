"""
Neo4j意图解析器

基于关键词和规则识别图查询意图,并通过LLM生成Cypher查询
"""

import re
from typing import Optional, Dict, Any, List
from domain.models import Intent, IntentType
from domain.parsers.base_parser import BaseIntentParser
from core.exceptions import IntentParseError
from core.logging import logger
from core.config import get_cypher_generation_prompt, get_llm_model_settings


class Neo4jIntentParser(BaseIntentParser):
    """
    Neo4j意图解析器

    识别适合使用图数据库查询的意图（关系、路径、层级等）
    """

    # Neo4j查询关键词（关系、路径、层级相关）
    NEO4J_KEYWORDS = [
        "关系", "关联", "相关性", "联系",
        "路径", "链接", "连接",
        "层级", "结构", "组织",
        "上下游", "依赖", "影响",
        "知识图谱", "图谱", "网络",
        # 业务实体词（表示查询实体关系）
        "单位", "系统", "安全产品", "集成商",
        "建设", "部署", "运维", "管理",
        # 表示拥有/关联关系的词
        "有哪些", "拥有", "包括", "涉及"
    ]

    # 实体关系词
    RELATION_KEYWORDS = [
        "之间", "和", "与", "到",
        "属于", "包含", "依赖于",
        "有", "的", "是"
    ]

    def __init__(self, es_client=None, llm_client=None, cypher_index="qa_system"):
        """
        初始化Neo4j意图解析器

        Args:
            es_client: ES客户端,用于检索Cypher示例
            llm_client: LLM客户端,用于生成Cypher
            cypher_index: Cypher示例索引名称(默认qa_system)
        """
        self.es_client = es_client
        self.llm_client = llm_client
        self.cypher_index = cypher_index

        self.keyword_pattern = re.compile(
            "|".join(self.NEO4J_KEYWORDS),
            re.IGNORECASE
        )
        self.relation_pattern = re.compile(
            "|".join(self.RELATION_KEYWORDS),
            re.IGNORECASE
        )

    async def parse(self, query: str, context: Optional[dict] = None) -> Intent:
        """
        解析Neo4j查询意图并生成Cypher

        流程:
        1. 识别意图
        2. 从ES检索相似的Cypher示例
        3. 调用LLM生成Cypher查询
        4. 返回包含Cypher的Intent

        Args:
            query: 用户查询
            context: 上下文信息

        Returns:
            Intent: 包含生成Cypher的Neo4j查询意图

        Raises:
            IntentParseError: 解析失败
        """
        try:
            # 预处理
            processed_query = self.preprocess_query(query)

            # 计算置信度
            confidence = self._calculate_confidence(processed_query)

            # 提取实体和关系
            entities, relations = self._extract_entities_and_relations(processed_query)

            # 关键步骤: 生成Cypher查询
            generated_cypher = None
            cypher_examples = []

            if self.es_client and self.llm_client:
                try:
                    # 1. 从ES检索Cypher示例
                    cypher_examples = await self._retrieve_cypher_examples(query, top_k=3)
                    logger.info(f"检索到{len(cypher_examples)}个Cypher示例")

                    # 2. 使用LLM生成Cypher
                    if cypher_examples:
                        generated_cypher = await self._generate_cypher_with_llm(
                            query, cypher_examples
                        )
                        logger.info(f"LLM生成Cypher: {generated_cypher}")
                    else:
                        logger.warning("未找到Cypher示例,无法生成Cypher")

                except Exception as e:
                    logger.error(f"Cypher生成失败: {e}")

            return Intent(
                intent_type=IntentType.NEO4J_QUERY,
                confidence=confidence,
                query=query,
                parsed_query=processed_query,
                metadata={
                    "parser": "Neo4jIntentParser",
                    "keywords": self._find_keywords(processed_query),
                    "entities": entities,
                    "relations": relations,
                    "generated_cypher": generated_cypher,  # 核心:保存生成的Cypher
                    "cypher_examples_count": len(cypher_examples)
                }
            )

        except Exception as e:
            raise IntentParseError(
                f"Neo4j意图解析失败: {str(e)}",
                details={"query": query, "error": str(e)}
            )

    def can_handle(self, query: str) -> bool:
        """
        判断是否能处理该查询

        Args:
            query: 用户查询

        Returns:
            bool: 是否包含Neo4j关键词或关系词
        """
        has_neo4j_keywords = bool(self.keyword_pattern.search(query))
        has_relation_keywords = bool(self.relation_pattern.search(query))
        return has_neo4j_keywords or has_relation_keywords

    def _calculate_confidence(self, query: str) -> float:
        """
        计算置信度

        Args:
            query: 查询文本

        Returns:
            float: 置信度 (0.0-1.0)
        """
        # 基础置信度
        base_confidence = 0.5

        # Neo4j关键词权重
        neo4j_keywords_found = self._find_keywords(query)
        neo4j_boost = min(len(neo4j_keywords_found) * 0.2, 0.4)

        # 关系词权重
        relation_keywords_found = self._find_relation_keywords(query)
        relation_boost = min(len(relation_keywords_found) * 0.1, 0.2)

        confidence = base_confidence + neo4j_boost + relation_boost
        return min(confidence, 1.0)

    def _find_keywords(self, query: str) -> list:
        """
        查找Neo4j关键词

        Args:
            query: 查询文本

        Returns:
            list: 找到的关键词列表
        """
        found = []
        for keyword in self.NEO4J_KEYWORDS:
            if keyword in query:
                found.append(keyword)
        return found

    def _find_relation_keywords(self, query: str) -> list:
        """
        查找关系关键词

        Args:
            query: 查询文本

        Returns:
            list: 找到的关系词列表
        """
        found = []
        for keyword in self.RELATION_KEYWORDS:
            if keyword in query:
                found.append(keyword)
        return found

    def _extract_entities_and_relations(self, query: str) -> tuple:
        """
        提取实体和关系

        Args:
            query: 查询文本

        Returns:
            tuple: (实体列表, 关系列表)
        """
        # 简单的实体提取（可以后续用NER模型优化）
        # 这里使用基于分词的简单方法
        entities = []
        relations = self._find_relation_keywords(query)

        # 提取可能的实体（去除关键词和关系词后的主要词汇）
        cleaned_query = query
        for keyword in self.NEO4J_KEYWORDS + self.RELATION_KEYWORDS:
            cleaned_query = cleaned_query.replace(keyword, " ")

        # 分词提取实体（简单空格分割）
        potential_entities = [word.strip() for word in cleaned_query.split() if len(word.strip()) > 1]
        entities = potential_entities[:5]  # 限制最多5个实体

        return entities, relations

    async def _retrieve_cypher_examples(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        """
        从ES检索相似的Cypher示例

        Args:
            query: 用户查询
            top_k: 返回数量

        Returns:
            List[Dict]: Cypher示例列表,格式: [{"question": "...", "answer": "..."}]
        """
        if not self.es_client:
            logger.warning("ES客户端未配置,无法检索Cypher示例")
            return []

        try:
            # 使用ES的向量搜索检索相似问题
            results = self.es_client.search(
                index=self.cypher_index,
                query={"match": {"question": query}},
                size=top_k
            )

            examples = []
            hits = results.get("hits", {}).get("hits", [])
            for hit in hits:
                source = hit.get("_source", {})
                examples.append({
                    "question": source.get("question", ""),
                    "answer": source.get("answer", ""),  # answer字段存储的是Cypher
                    "score": hit.get("_score", 0.0)
                })

            logger.info(f"从ES检索到{len(examples)}个Cypher示例")
            return examples

        except Exception as e:
            logger.error(f"ES检索Cypher示例失败: {e}")
            return []

    async def _generate_cypher_with_llm(
        self,
        query: str,
        examples: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        使用LLM生成Cypher查询

        Args:
            query: 用户查询
            examples: Cypher示例列表

        Returns:
            str: 生成的Cypher查询,如果失败返回None
        """
        if not self.llm_client:
            logger.warning("LLM客户端未配置,无法生成Cypher")
            return None

        try:
            # 获取LLM模型配置
            llm_config = get_llm_model_settings()

            # 构建示例文本
            examples_text = "\n\n".join([
                f"示例{i+1}:\n问题: {ex['question']}\nCypher: {ex['answer']}"
                for i, ex in enumerate(examples[:3])
            ])

            # 使用配置化的提示词模板
            prompt = get_cypher_generation_prompt(query=query, examples=examples_text)

            # 调用LLM生成 - 使用流式模式收集完整响应
            # 因为某些模型只支持流式模式
            cypher_parts = []
            async for chunk in self.llm_client.async_stream_chat(
                prompt=prompt,
                model=llm_config.cypher_generation_model,  # 使用配置的模型
                temperature=llm_config.cypher_generation_temperature,  # 使用配置的温度
                max_tokens=llm_config.cypher_generation_max_tokens  # 使用配置的max_tokens
            ):
                if chunk:
                    cypher_parts.append(chunk)

            # 合并响应
            cypher = "".join(cypher_parts).strip()

            # 清理响应 - 移除可能的markdown代码块标记
            cypher = cypher.replace("```cypher", "").replace("```", "").strip()

            return cypher if cypher else None

        except Exception as e:
            logger.error(f"LLM生成Cypher失败: {e}")
            return None
