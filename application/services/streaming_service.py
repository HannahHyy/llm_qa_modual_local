"""
流式输出服务 (完全重构以匹配old版本逻辑)

处理SSE流式对话,完整实现old版本的工作流程:
1. IntentRouter路由判断 (neo4j/es/hybrid/none)
2. 根据路由类型执行不同的意图识别和检索
3. 流式输出<think>标签的详细思考过程
4. 执行Cypher查询或ES检索
5. 基于结果生成LLM回答到<data>标签
6. 输出结构化知识到<knowledge>标签
"""

from typing import AsyncGenerator, Dict, Any, Optional, List
import json
import asyncio
from domain.models import Message, Knowledge
from domain.services import PromptBuilder, KnowledgeMatcher, MemoryService
from domain.services.intent_router import IntentRouter, RouteContext
from domain.parsers import Neo4jIntentParser
from domain.retrievers import Neo4jRetriever, ESRetriever
from infrastructure.clients.llm_client import LLMClient
from infrastructure.repositories.session_repository import SessionRepository
from infrastructure.clients.neo4j_client import Neo4jClient
from core.logging import logger
from core.config.prompts import get_llm_model_settings


class StreamingService:
    """
    流式输出服务 (重构版,完全匹配old版本逻辑)

    工作流程:
    1. 调用IntentRouter判断路由 (neo4j/es/hybrid/none)
    2. Neo4j路由: 调用Neo4jIntentParser流式识别意图 → 执行Cypher → 生成回答
    3. ES路由: 调用ES检索 → 生成回答
    4. Hybrid路由: 同时执行Neo4j和ES → 合并结果生成回答
    5. None路由: 直接LLM回答
    """

    def __init__(
        self,
        intent_router: IntentRouter,
        neo4j_parser: Neo4jIntentParser,
        neo4j_retriever: Neo4jRetriever,
        es_retriever: ESRetriever,
        neo4j_client: Neo4jClient,
        prompt_builder: PromptBuilder,
        knowledge_matcher: KnowledgeMatcher,
        memory_service: MemoryService,
        llm_client: LLMClient,
        session_repository: SessionRepository
    ):
        """
        初始化流式服务

        Args:
            intent_router: 意图路由器
            neo4j_parser: Neo4j意图解析器
            neo4j_retriever: Neo4j检索器
            es_retriever: ES检索器
            neo4j_client: Neo4j客户端
            prompt_builder: Prompt构建器
            knowledge_matcher: 知识匹配器
            memory_service: 记忆服务
            llm_client: LLM客户端
            session_repository: 会话仓储
        """
        self.intent_router = intent_router
        self.neo4j_parser = neo4j_parser
        self.neo4j_retriever = neo4j_retriever
        self.es_retriever = es_retriever
        self.neo4j_client = neo4j_client
        self.prompt_builder = prompt_builder
        self.knowledge_matcher = knowledge_matcher
        self.memory_service = memory_service
        self.llm_client = llm_client
        self.session_repository = session_repository

    async def chat_stream(
        self,
        user_id: str,
        session_id: str,
        query: str,
        enable_knowledge: bool = True,
        top_k: int = 5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式对话(完全匹配old版本的输出格式和逻辑)

        Args:
            user_id: 用户ID
            session_id: 会话ID
            query: 用户查询
            enable_knowledge: 是否启用知识检索
            top_k: 知识检索数量
            metadata: 额外元数据

        Yields:
            str: SSE格式的事件数据(data:{"content":"...", "msg_type":...})
        """
        logger.info(f"开始流式对话: user={user_id}, session={session_id}, query={query}")

        full_stream_content = []  # 收集完整内容用于保存历史

        try:
            # 1. 保存用户消息
            await self.memory_service.add_message(user_id, session_id, "user", query)

            # 2. 获取对话历史
            history = await self.memory_service.get_context(user_id, session_id)
            history_msgs = [
                {"role": msg.role, "content": msg.content}
                for msg in history
            ]

            # 3. 输出<think>开始标记
            think_start = "<think>开始对用户的提问进行深入解析...\n"
            yield self._format_data_event(think_start, msg_type=1)
            full_stream_content.append(think_start)

            # 4. 调用IntentRouter进行路由判断(流式输出思考过程)
            route_decision = "hybrid"  # 默认hybrid

            if enable_knowledge:
                try:
                    route_ctx = RouteContext(
                        user_query=query,
                        history_msgs=history_msgs
                    )

                    # 流式路由判断回调
                    async def router_callback(chunk: str):
                        """路由器流式输出回调"""
                        if chunk:
                            yield self._format_data_event(chunk, msg_type=1)
                            full_stream_content.append(chunk)

                    # 执行路由判断
                    route_decision = await self.intent_router.route(
                        ctx=route_ctx,
                        stream=True,
                        stream_callback=router_callback
                    )

                    logger.info(f"路由决策: {route_decision}")

                except Exception as e:
                    logger.error(f"路由判断失败: {e}, 使用默认hybrid")
                    route_decision = "hybrid"

            # 5. 根据路由决策执行不同的处理流程
            neo4j_results = []
            es_knowledge = []

            if route_decision == "neo4j" or route_decision == "hybrid":
                # 5.1 Neo4j意图识别和查询
                neo4j_results = await self._handle_neo4j_query(
                    query=query,
                    history_msgs=history_msgs,
                    full_stream_content=full_stream_content,
                    yield_callback=lambda event: (yield event)
                )

            if route_decision == "es" or route_decision == "hybrid":
                # 5.2 ES知识检索
                es_knowledge = await self._handle_es_query(
                    query=query,
                    top_k=top_k,
                    full_stream_content=full_stream_content,
                    yield_callback=lambda event: (yield event)
                )

            # 6. 输出</think>结束标记
            think_end = "\n完成对用户问题的详细解析分析。正在检索知识库中的内容并生成回答，请稍候....\n</think>\n"
            yield self._format_data_event(think_end, msg_type=1)
            full_stream_content.append(think_end)

            # 7. 输出<data>开始标记
            data_start = "<data>\n"
            yield self._format_data_event(data_start, msg_type=2)
            full_stream_content.append(data_start)

            # 8. 根据查询结果生成LLM回答
            llm_config = get_llm_model_settings()

            # 构建系统提示词
            system_prompt = "请关闭思考模式，直接使用业务专员查到的结果对你的领导的问题作出回答，业务专员的结果不需要进行筛选，也不需要逐条分析，微小的错误请忽略，名称不统一也请忽略，回答的方式是先生成100个字的总结摘要，然后再进行详细回答。"

            # 构建消息
            messages = [{"role": "system", "content": system_prompt}]

            # 添加查询结果
            if neo4j_results:
                messages.append({
                    "role": "user",
                    "content": f"以下是业务专员从业务图谱查到的结果：\n{json.dumps(neo4j_results, ensure_ascii=False, indent=2)}"
                })

            if es_knowledge:
                knowledge_text = "\n".join([k.content for k in es_knowledge[:3]])
                messages.append({
                    "role": "user",
                    "content": f"以下是从法规知识库检索到的相关内容：\n{knowledge_text}"
                })

            # 添加用户查询
            messages.append({
                "role": "user",
                "content": f"以下是你的领导的问题，请关闭思考模式直接回答：\n{query}"
            })

            # 流式调用LLM生成回答
            assistant_reply = ""
            async for chunk in self.llm_client.async_stream_chat_with_messages(
                messages=messages,
                model=llm_config.chat_generation_model,
                temperature=llm_config.chat_generation_temperature,
                max_tokens=llm_config.chat_generation_max_tokens
            ):
                if chunk:
                    assistant_reply += chunk
                    yield self._format_data_event(chunk, msg_type=2)
                    full_stream_content.append(chunk)
                    await asyncio.sleep(0.01)

            # 9. 输出</data>结束标记
            data_end = "\n</data>"
            yield self._format_data_event(data_end, msg_type=2)
            full_stream_content.append(data_end)

            # 10. 输出<knowledge>标签 - 结构化知识结果
            if neo4j_results or es_knowledge:
                knowledge_start = "\n<knowledge>\n"
                yield self._format_data_event(knowledge_start, msg_type=3)
                full_stream_content.append(knowledge_start)

                # 输出Neo4j结果
                if neo4j_results:
                    knowledge_dict = {
                        "title": "网络业务知识图谱",
                        "table_list": neo4j_results
                    }
                    knowledge_content = json.dumps(knowledge_dict, ensure_ascii=False, indent=2)
                    yield self._format_data_event(knowledge_content, msg_type=3)
                    full_stream_content.append(knowledge_content)

                # 输出ES结果
                if es_knowledge:
                    for i, k in enumerate(es_knowledge[:2], 1):
                        es_item = f"\n{i}. {k.title or 'ES知识'}\n{k.content[:300]}...\n"
                        yield self._format_data_event(es_item, msg_type=3)
                        full_stream_content.append(es_item)

                knowledge_end = "\n</knowledge>"
                yield self._format_data_event(knowledge_end, msg_type=3)
                full_stream_content.append(knowledge_end)

            # 11. 保存助手回复
            complete_reply = "".join(full_stream_content)
            await self.memory_service.add_message(
                user_id, session_id, "assistant", complete_reply
            )

            # 12. 更新会话时间戳
            await self.session_repository.update_session_timestamp(session_id)

            logger.info(f"流式对话完成: session={session_id}, length={len(complete_reply)}")

        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}", exc_info=True)
            error_msg = f"\n抱歉，处理您的请求时出现错误: {str(e)}\n"
            yield self._format_data_event(error_msg, msg_type=4)

    async def _handle_neo4j_query(
        self,
        query: str,
        history_msgs: List[Dict[str, str]],
        full_stream_content: List[str],
        yield_callback
    ) -> List[Dict]:
        """
        处理Neo4j查询(包含流式意图识别)

        Args:
            query: 用户查询
            history_msgs: 历史消息
            full_stream_content: 完整内容收集器
            yield_callback: 流式输出回调

        Returns:
            List[Dict]: Neo4j查询结果列表
        """
        try:
            info = "\n需要检索网络业务知识图谱辅助回答，请稍等....\n现在开始业务知识图谱检索\n"
            await yield_callback(self._format_data_event(info, msg_type=1))
            full_stream_content.append(info)

            # 调用Neo4jIntentParser进行流式意图识别
            intent_result = None
            intent_stream_content = []

            async def neo4j_intent_callback(chunk: str):
                """Neo4j意图识别流式回调"""
                if chunk:
                    await yield_callback(self._format_data_event(chunk, msg_type=1))
                    intent_stream_content.append(chunk)
                    full_stream_content.append(chunk)

            # 流式意图解析
            intent_result = await self.neo4j_parser.parse_with_stream(
                query=query,
                history_msgs=history_msgs,
                stream_callback=neo4j_intent_callback
            )

            # 执行Cypher查询
            all_results = []
            if intent_result and isinstance(intent_result, list):
                for intent_item in intent_result:
                    cypher = intent_item.get("cypher")
                    if cypher:
                        logger.info(f"执行Cypher: {cypher}")
                        try:
                            cypher_result = self.neo4j_client.query(cypher)
                            intent_item["intent_result"] = cypher_result
                            all_results.extend(cypher_result)
                        except Exception as e:
                            logger.error(f"Cypher执行失败: {e}")
                            intent_item["intent_result"] = []

            # 输出检索到的业务信息
            result_info = f"\n检索到的业务信息：\n{json.dumps(all_results[:3], ensure_ascii=False, indent=2)}\n"
            await yield_callback(self._format_data_event(result_info, msg_type=1))
            full_stream_content.append(result_info)

            return all_results

        except Exception as e:
            logger.error(f"Neo4j查询失败: {e}")
            return []

    async def _handle_es_query(
        self,
        query: str,
        top_k: int,
        full_stream_content: List[str],
        yield_callback
    ) -> List[Knowledge]:
        """
        处理ES查询

        Args:
            query: 用户查询
            top_k: 返回数量
            full_stream_content: 完整内容收集器
            yield_callback: 流式输出回调

        Returns:
            List[Knowledge]: ES检索结果
        """
        try:
            info = "\n现在开始法规标准检索\n"
            await yield_callback(self._format_data_event(info, msg_type=1))
            full_stream_content.append(info)

            # ES检索
            knowledge = await self.es_retriever.retrieve(query=query, top_k=top_k)

            result_info = f"检索到{len(knowledge)}条相关法规标准\n"
            await yield_callback(self._format_data_event(result_info, msg_type=1))
            full_stream_content.append(result_info)

            return knowledge

        except Exception as e:
            logger.error(f"ES查询失败: {e}")
            return []

    def _format_data_event(self, content: str, msg_type: int) -> str:
        """
        格式化数据事件(完全匹配old版本格式)

        Args:
            content: 内容
            msg_type: 消息类型
                1: <think>思考过程
                2: <data>LLM回答
                3: <knowledge>知识原文
                4: 错误信息

        Returns:
            str: SSE格式的数据事件 "data:{json}\n\n"
        """
        data = {
            "content": content,
            "msg_type": msg_type  # old版本使用msg_type而不是message_type
        }
        return f"data:{json.dumps(data, ensure_ascii=False)}\n\n"
