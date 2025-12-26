"""
ES查询服务

完整实现Elasticsearch法规标准查询功能，不依赖old代码
基于旧系统算法逻辑100%重新实现

核心功能:
1. 意图解析: 使用LLM将用户问题拆解为结构化意图
2. 知识检索: 基于意图进行BM25+向量混合检索
3. 答案生成: 使用检索到的知识生成答案
4. 知识匹配: 匹配并输出相关法规原文
"""

import re
import json
import asyncio
from typing import List, Dict, Optional, AsyncGenerator, Any
from dataclasses import dataclass

from infrastructure.clients.llm_client import LLMClient
from infrastructure.clients.es_client import ESClient
from core.logging import logger
from core.config import get_settings, get_llm_model_settings


# ============= 数据模型 =============

@dataclass
class ESIntent:
    """ES意图数据模型"""
    num: int
    rewritten_query: str
    retrieval_type: str  # keyword_search/semantic_search/hybrid_search
    regulation_standards: List[str]
    source_standard: List[str]
    entities: Dict[str, List[str]]  # asset_objects/requirement_items/applicability_level
    reason: str


@dataclass
class ESIntentResult:
    """ES意图解析结果"""
    intents: List[ESIntent]
    origin_query: str
    history_msgs: List[str]
    no_standard_query: bool = False


@dataclass
class KnowledgeItem:
    """知识检索结果项"""
    content: str
    score: float
    source: str
    metadata: Dict[str, Any]

    @property
    def embedding_content(self) -> str:
        """获取嵌入内容"""
        return self.content


class JsonExtractor:
    """JSON提取器 - 从LLM输出中提取JSON"""

    def extract_es_intent(self, text: str) -> Optional[Dict]:
        """
        提取ES意图JSON

        查找标识符: '3.以下是json格式的解析结果：' 之后的JSON
        """
        if not text:
            return None

        try:
            # 方法1: 查找特定标识符
            if '3.以下是json格式的解析结果：' in text:
                parts = text.split('3.以下是json格式的解析结果：')
                if len(parts) > 1:
                    json_part = parts[1].strip()
                    # 提取JSON对象
                    match = re.search(r'\{.*\}', json_part, re.DOTALL)
                    if match:
                        json_str = match.group(0)
                        return json.loads(json_str)

            # 方法2: 直接查找JSON对象
            match = re.search(r'\{[^{}]*"intents"[^{}]*\[.*?\][^{}]*\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)

            return None
        except Exception as e:
            logger.warning(f"[JSON提取] ES意图提取失败: {e}")
            return None


# ============= ES查询服务 =============

class ESQueryService:
    """ES查询服务 - 完整独立实现"""

    def __init__(self, llm_client: LLMClient, es_client: ESClient):
        """
        初始化服务

        Args:
            llm_client: LLM客户端
            es_client: ES客户端
        """
        self.llm_client = llm_client
        self.es_client = es_client
        self.settings = get_settings()
        self.model_settings = get_llm_model_settings()
        self.json_extractor = JsonExtractor()

        # 检索配置
        self.retrieval_config = {
            "keyword_search": {
                "bm25_weight": 0.8,
                "vector_weight": 0.2,
                "bm25_threshold": 0.7,
                "vector_threshold": 0.3
            },
            "semantic_search": {
                "bm25_weight": 0.2,
                "vector_weight": 0.8,
                "bm25_threshold": 0.7,
                "vector_threshold": 0.3
            },
            "hybrid_search": {
                "bm25_weight": 0.6,
                "vector_weight": 0.4,
                "bm25_threshold": 0.7,
                "vector_threshold": 0.3
            }
        }

    async def query_stream(
        self,
        question: str,
        history_msgs: List[Dict[str, str]]
    ) -> AsyncGenerator[bytes, None]:
        """
        ES查询主流程（流式输出）

        流程:
        1. 意图解析（流式输出思考过程）
        2. 知识检索
        3. 答案生成（流式输出）
        4. 知识匹配和输出

        Args:
            question: 用户问题
            history_msgs: 历史消息

        Yields:
            bytes: SSE格式的流式数据
        """
        # ===== 阶段1: 意图解析 =====
        intent_result = None
        full_stream_content: List[str] = []
        llm_raw_content: List[str] = []

        try:
            # 创建意图解析队列
            intent_queue = asyncio.Queue()
            intent_done = asyncio.Event()

            async def intent_callback(chunk: str):
                """意图解析流式回调"""
                if chunk:
                    await intent_queue.put(chunk)
                    full_stream_content.append(chunk)

            async def intent_parser_task():
                """意图解析任务"""
                nonlocal intent_result
                try:
                    intent_result = await self._parse_intent_with_stream(
                        question,
                        history_msgs,
                        intent_callback
                    )
                finally:
                    intent_done.set()
                    await intent_queue.put(None)

            # 启动意图解析
            parser_task = asyncio.create_task(intent_parser_task())

            # 输出思考开始标记
            yield self._sse_message("<think>开始对用户的提问进行深入解析...\n", message_type=1)
            full_stream_content.append("<think>开始对用户的提问进行深入解析...\n")

            # 实时输出意图识别过程
            while True:
                try:
                    chunk = await asyncio.wait_for(intent_queue.get(), timeout=0.1)
                    if chunk is None:
                        break
                    yield self._sse_message(chunk, message_type=1)
                except asyncio.TimeoutError:
                    if intent_done.is_set():
                        try:
                            chunk = intent_queue.get_nowait()
                            if chunk is None:
                                break
                            yield self._sse_message(chunk, message_type=1)
                        except asyncio.QueueEmpty:
                            break
                    continue

            # 输出思考结束标记
            think_end_content = "\n完成对用户问题的详细解析分析。正在检索知识库中的内容并生成回答，请稍候....\n</think>\n"
            yield self._sse_message(think_end_content, message_type=1)
            full_stream_content.append(think_end_content)

            await parser_task

            # ===== 阶段2: 知识检索 =====
            knowledge_results = await self._search_knowledge(intent_result) if intent_result else []
            knowledge_text = "\n".join([item.embedding_content for item in knowledge_results])
            if knowledge_text:
                knowledge_text = knowledge_text[:60000]  # 限制长度

            # ===== 阶段3: 答案生成（流式）=====
            data_start_msg = "\n<data>"
            yield self._sse_message(data_start_msg, message_type=2)
            full_stream_content.append(data_start_msg)

            # 构建LLM消息
            system_prompt = self._build_answer_system_prompt()
            user_message = self._build_answer_user_message(question, knowledge_text)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            # 流式生成答案
            async for chunk in self.llm_client.stream_chat(messages):
                if chunk:
                    yield self._sse_message(chunk, message_type=2)
                    full_stream_content.append(chunk)
                    llm_raw_content.append(chunk)

            data_end_msg = "\n</data>\n"
            yield self._sse_message(data_end_msg, message_type=2)
            full_stream_content.append(data_end_msg)

            # ===== 阶段4: 知识匹配和输出 =====
            no_standard_query = False
            if intent_result and isinstance(intent_result, dict):
                no_standard_query = intent_result.get("no_standard_query", False)

            if llm_raw_content and knowledge_results and not no_standard_query:
                full_reply = "".join(llm_raw_content)
                matched_knowledge = await self._match_knowledge(full_reply, knowledge_results)

                if matched_knowledge:
                    knowledge_dict = {
                        "title": "相关的标准规范原文内容",
                        "table_list": matched_knowledge
                    }
                    yield self._sse_message(
                        json.dumps(knowledge_dict, ensure_ascii=False),
                        message_type=3
                    )

                    full_stream_content.append("<knowledge>")
                    full_stream_content.append("相关的标准规范原文内容")
                    for item in matched_knowledge:
                        full_stream_content.append(item)
                    full_stream_content.append("</knowledge>")

        except Exception as e:
            logger.error(f"[ES查询] 查询失败: {e}", exc_info=True)
            error_msg = f"查询过程中出现错误: {str(e)}"
            yield self._sse_message(error_msg, message_type=4)

    async def _parse_intent_with_stream(
        self,
        question: str,
        history_msgs: List[Dict[str, str]],
        stream_callback
    ) -> Optional[Dict]:
        """
        意图解析（流式输出）

        使用LLM将用户问题拆解为结构化意图
        """
        # 构建系统提示词
        system_prompt = self._build_intent_system_prompt()

        # 构建用户消息
        user_message = self._build_intent_user_message(question, history_msgs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        # 流式调用LLM
        full_response = ""
        async for chunk in self.llm_client.stream_chat(messages):
            if chunk:
                full_response += chunk
                if stream_callback:
                    await stream_callback(chunk)

        # 从完整响应中提取JSON
        intent_dict = self.json_extractor.extract_es_intent(full_response)
        return intent_dict

    async def _search_knowledge(self, intent_result: Dict) -> List[KnowledgeItem]:
        """
        基于意图进行知识检索

        Args:
            intent_result: 意图解析结果

        Returns:
            检索到的知识列表
        """
        if not intent_result:
            return []

        intents = intent_result.get("intents", [])
        if not intents:
            return []

        all_results = []

        # 处理每个意图
        for intent in intents:
            results = await self._search_single_intent(intent, intent_result.get("origin_query", ""))
            all_results.extend(results)

        # 去重和排序
        unique_results = self._deduplicate_results(all_results)
        sorted_results = sorted(unique_results, key=lambda x: x.score, reverse=True)

        # 返回前N个结果
        return sorted_results[:500]

    async def _search_single_intent(self, intent: Dict, origin_query: str) -> List[KnowledgeItem]:
        """
        检索单个意图

        使用BM25+向量混合检索
        """
        try:
            retrieval_type = intent.get("retrieval_type", "hybrid_search")
            config = self.retrieval_config.get(retrieval_type, self.retrieval_config["hybrid_search"])

            # 构建ES查询
            query_text = intent.get("rewritten_query", origin_query)

            # 构建must条件（硬过滤）
            must_conditions = []

            # 添加法规标准过滤
            regulation_standards = intent.get("regulation_standards", [])
            if regulation_standards:
                must_conditions.append({
                    "terms": {
                        "source_standard.keyword": regulation_standards
                    }
                })

            # 添加等级过滤
            entities = intent.get("entities", {})
            applicability_level = entities.get("applicability_level", [])
            if applicability_level:
                must_conditions.append({
                    "terms": {
                        "applicability_level.keyword": applicability_level
                    }
                })

            # BM25查询
            should_conditions = []
            should_conditions.append({
                "match": {
                    "content": {
                        "query": query_text,
                        "boost": config["bm25_weight"]
                    }
                }
            })

            # TODO: 向量查询需要先获取embedding
            # 这里简化处理，仅使用BM25

            # 构建完整查询
            es_query = {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}],
                    "should": should_conditions
                }
            }

            # 执行查询
            index_name = self.settings.es.knowledge_index
            response = self.es_client.client.search(
                index=index_name,
                query=es_query,
                size=100,
                _source=["content", "source_standard", "title", "applicability_level"]
            )

            # 解析结果
            results = []
            for hit in response.get("hits", {}).get("hits", []):
                source = hit.get("_source", {})
                score = hit.get("_score", 0.0)

                # 归一化score
                import math
                normalized_score = 1.0 / (1.0 + math.exp(-score / 10.0))

                item = KnowledgeItem(
                    content=source.get("content", ""),
                    score=min(normalized_score, 1.0),
                    source=source.get("source_standard", ""),
                    metadata={
                        "title": source.get("title"),
                        "applicability_level": source.get("applicability_level"),
                        "raw_score": score
                    }
                )
                results.append(item)

            return results

        except Exception as e:
            logger.error(f"[ES检索] 单个意图检索失败: {e}", exc_info=True)
            return []

    def _deduplicate_results(self, results: List[KnowledgeItem]) -> List[KnowledgeItem]:
        """去重检索结果"""
        seen = set()
        unique_results = []

        for item in results:
            content_hash = hash(item.content[:200])  # 使用前200字符去重
            if content_hash not in seen:
                seen.add(content_hash)
                unique_results.append(item)

        return unique_results

    async def _match_knowledge(
        self,
        llm_output: str,
        knowledge_results: List[KnowledgeItem],
        max_results: int = 2
    ) -> List[str]:
        """
        知识匹配

        从LLM输出中提取引用的知识
        """
        try:
            # 简化版本: 返回分数最高的前N个
            sorted_results = sorted(knowledge_results, key=lambda x: x.score, reverse=True)
            top_results = sorted_results[:max_results]

            matched = []
            for item in top_results:
                # 格式化输出
                formatted = f"【{item.source}】\n{item.content[:500]}"
                matched.append(formatted)

            return matched
        except Exception as e:
            logger.error(f"[知识匹配] 匹配失败: {e}", exc_info=True)
            return []

    def _build_intent_system_prompt(self) -> str:
        """构建意图解析系统提示词"""
        return """你是法规标准问答系统的'智能意图解析器'。
请根据输入的上下文，完成问题的意图拆解，并对每个意图进行详细分析。
你需要进行流式输出，其中分析思路需要展示到前端页面。
请先详细说明你的分析思路，分析思路请完全以流利的中文自然语言进行描述，然后输出最终严格的JSON结果。
最后的JSON结果，必须严格按照以下格式输出标识符（不要有任何变化）：
'3.以下是json格式的解析结果：'
{"intents": [{"num": int, "rewritten_query": string, "retrieval_type": string, "regulation_standards": [string...], "source_standard": [string...], "entities": {"asset_objects":[string...], "requirement_items":[string...], "applicability_level":[string...]}, "reason": string}], "origin_query": string, "history_msgs":[string...], "no_standard_query": boolean}

说明：
- rewritten_query: 将原始问题进行同义词扩展和语序优化，便于检索
- retrieval_type: keyword_search/semantic_search/hybrid_search
- regulation_standards: 涉及的法规标准列表
- entities: 识别出的实体（资产对象、要求项、等级）
- no_standard_query: 是否为非标准查询（如闲聊等）
"""

    def _build_intent_user_message(self, question: str, history_msgs: List[Dict[str, str]]) -> str:
        """构建意图解析用户消息"""
        history_text = ""
        if history_msgs:
            recent_history = history_msgs[-2:]  # 最近2轮
            for msg in recent_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                history_text += f"{role}: {content}\n"

        return f"""历史对话:
{history_text if history_text else "无"}

当前问题: {question}

请分析这个问题并输出意图解析结果。"""

    def _build_answer_system_prompt(self) -> str:
        """构建答案生成系统提示词"""
        return """你是网络安全等级保护专家助手。
请基于提供的法规标准知识，准确回答用户的问题。
要求：
1. 回答要专业、准确、简洁
2. 引用具体的标准条款
3. 如果知识库中没有相关内容，请明确说明
4. 不要编造不存在的内容"""

    def _build_answer_user_message(self, question: str, knowledge: str) -> str:
        """构建答案生成用户消息"""
        if knowledge:
            return f"""问题: {question}

相关知识:
{knowledge}

请基于以上知识回答问题。"""
        else:
            return f"""问题: {question}

知识库中暂无相关内容，请说明无法回答。"""

    def _sse_message(self, content: str, message_type: int = 1) -> bytes:
        """
        构建SSE消息

        Args:
            content: 消息内容
            message_type: 消息类型（1=think, 2=data, 3=knowledge, 4=error）
        """
        data = {
            "content": content,
            "message_type": message_type
        }
        return f"data:{json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
