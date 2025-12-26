"""
Legacy流式服务 - 完全兼容server2.py的流式输出格式

这个服务复刻了server2.py的三种查询模式:
- scene_id=1: 混合查询（Neo4j + ES）
- scene_id=2: 仅Neo4j查询
- scene_id=3: 仅ES查询

流式输出格式:
data:{"content": "...", "message_type": 1}  // 1=think, 2=data, 3=knowledge, 4=error
"""

import json
import asyncio
from typing import AsyncGenerator, List, Dict, Optional
from fastapi import BackgroundTasks

from domain.strategies.llm_intent_router import LLMIntentRouter
from domain.services.neo4j_query_service import Neo4jQueryService
from infrastructure.clients.llm_client import LLMClient
from infrastructure.repositories.session_repository import SessionRepository
from infrastructure.repositories.message_repository import MessageRepository
from core.logging import logger
from core.config import get_settings, get_llm_model_settings, get_system_prompt


# 导入旧代码的模块（直接使用）
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "old"))

try:
    from retrieval_server.intent_parser import EnhancedIntentParser, IntentParseContext
    from retrieval_server.es_retriever_kbvector import search_clauses
    from retrieval_server.knowledge_matcher import match_and_format_knowledge
    LEGACY_MODULES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Legacy modules not available: {e}")
    LEGACY_MODULES_AVAILABLE = False


class LegacyStreamingService:
    """
    Legacy流式服务 - 完全复刻server2.py的逻辑

    职责:
    - 根据scene_id选择不同的查询模式
    - 使用旧版本的流式输出格式
    - 保持与server2.py完全一致的行为
    """

    def __init__(
        self,
        llm_client: LLMClient,
        message_repository: MessageRepository,
        session_repository: SessionRepository,
    ):
        """
        初始化服务

        Args:
            llm_client: LLM客户端
            message_repository: 消息仓储
            session_repository: 会话仓储
        """
        self.llm_client = llm_client
        self.message_repo = message_repository
        self.session_repo = session_repository
        self.settings = get_settings()
        self.model_settings = get_llm_model_settings()

        # 初始化LLM路由器
        self.intent_router = LLMIntentRouter(llm_client)

        # 初始化Neo4j查询服务
        self.neo4j_service = Neo4jQueryService(llm_client)

        # 使用配置化的系统提示词
        self.system_prompt = get_system_prompt()

    async def chat_stream_by_scene(
        self,
        user_id: str,
        session_id: str,
        query: str,
        scene_id: int,
        background_tasks: BackgroundTasks
    ) -> AsyncGenerator[bytes, None]:
        """
        根据scene_id执行不同的流式查询

        Args:
            user_id: 用户ID
            session_id: 会话ID
            query: 用户查询
            scene_id: 场景ID (1=混合, 2=Neo4j, 3=ES)
            background_tasks: 后台任务

        Yields:
            bytes: 流式输出的字节数据
        """
        # 获取历史消息
        history = await self.message_repo.get_messages(user_id, session_id)
        history_msgs = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in history
            if msg["role"] in ("user", "assistant")
        ]

        if scene_id == 1:
            # 混合查询
            async for chunk in self._hybrid_stream_gen(
                query, history_msgs, user_id, session_id, background_tasks
            ):
                yield chunk

        elif scene_id == 2:
            # 仅Neo4j查询
            async for chunk in self._neo4j_stream_gen(
                query, history_msgs, user_id, session_id, background_tasks
            ):
                yield chunk

        else:
            # 默认ES查询 (scene_id=3 或其他)
            async for chunk in self._es_stream_gen(
                query, history_msgs, user_id, session_id, background_tasks
            ):
                yield chunk

    async def _es_stream_gen(
        self,
        question: str,
        history_msgs: List[Dict[str, str]],
        user_id: str,
        session_id: str,
        background_tasks: BackgroundTasks,
        save_messages: bool = True
    ) -> AsyncGenerator[bytes, None]:
        """
        ES查询流式生成器 - 完全复刻server2.py的es_stream_gen

        Args:
            question: 用户问题
            history_msgs: 历史消息
            user_id: 用户ID
            session_id: 会话ID
            background_tasks: 后台任务
            save_messages: 是否保存消息

        Yields:
            bytes: 流式输出
        """
        if not LEGACY_MODULES_AVAILABLE:
            error_data = {
                "content": "Legacy模块不可用，请检查配置",
                "message_type": 4
            }
            yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")
            return

        intent_result = None
        knowledge_results = []
        full_stream_content: List[str] = []
        llm_raw_content: List[str] = []

        try:
            # 1. 意图识别阶段 - 使用流式输出
            intent_queue = asyncio.Queue()
            intent_done = asyncio.Event()

            async def intent_callback(chunk: str):
                """意图识别流式回调"""
                if chunk:
                    await intent_queue.put(chunk)
                    full_stream_content.append(chunk)

            async def intent_parser_task():
                """意图解析任务"""
                nonlocal intent_result
                try:
                    parser = EnhancedIntentParser()
                    context = IntentParseContext(
                        user_query=question,
                        history_msgs=history_msgs
                    )
                    intent_result = await parser.parse(context, stream=True, stream_callback=intent_callback)
                finally:
                    intent_done.set()
                    await intent_queue.put(None)

            # 启动意图解析任务
            parser_task = asyncio.create_task(intent_parser_task())
            think_start_data = {
                "content": "<think>开始对用户的提问进行深入解析...\n",
                "message_type": 1
            }
            yield f"data:{json.dumps(think_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
            full_stream_content.append(think_start_data["content"])

            # 实时输出意图识别过程
            while True:
                try:
                    chunk = await asyncio.wait_for(intent_queue.get(), timeout=0.1)
                    if chunk is None:
                        break
                    chunk_data = {
                        "content": chunk,
                        "message_type": 1
                    }
                    yield f"data:{json.dumps(chunk_data, ensure_ascii=False)}\n\n".encode("utf-8")
                    full_stream_content.append(chunk)
                except asyncio.TimeoutError:
                    if intent_done.is_set():
                        try:
                            chunk = intent_queue.get_nowait()
                            if chunk is None:
                                break
                            chunk_data = {
                                "content": chunk,
                                "message_type": 1
                            }
                            yield f"data:{json.dumps(chunk_data, ensure_ascii=False)}\n\n".encode("utf-8")
                            full_stream_content.append(chunk)
                        except asyncio.QueueEmpty:
                            break
                    continue

            # 输出思考过程结束
            think_end_content = "\n完成对用户问题的详细解析分析。正在检索知识库中的内容并生成回答，请稍候....\n</think>\n"
            think_end_data = {
                "content": think_end_content,
                "message_type": 1
            }
            yield f"data:{json.dumps(think_end_data, ensure_ascii=False)}\n\n".encode("utf-8")
            full_stream_content.append(think_end_content)
            llm_raw_content.append(str(intent_result))

            # 等待意图解析完成
            await parser_task

            # 2. 知识检索
            knowledge_results = search_clauses(intent_result) if intent_result else []
            knowledge = "\n".join([
                getattr(item, "embedding_content", "")
                for item in knowledge_results
            ])
            if knowledge:
                knowledge = knowledge[:60000]

            # 3. 构建prompt
            prompt = self._build_enhanced_prompt(history_msgs, question, knowledge)

            # 4. LLM响应流
            data_start_data = {
                "content": "<data>\n",
                "message_type": 2
            }
            yield f"data:{json.dumps(data_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
            full_stream_content.append(data_start_data["content"])

            async for chunk in self.llm_client.async_stream_chat(
                prompt=prompt,
                model=self.model_settings.chat_generation_model,
                max_tokens=self.model_settings.chat_generation_max_tokens,
                temperature=self.model_settings.chat_generation_temperature,
                system_prompt=self.system_prompt,
            ):
                if chunk:
                    llm_raw_content.append(chunk)
                    full_stream_content.append(chunk)
                    chunk_data = {
                        "content": chunk,
                        "message_type": 2
                    }
                    yield f"data:{json.dumps(chunk_data, ensure_ascii=False)}\n\n".encode("utf-8")
                    await asyncio.sleep(0.01)

            data_end_data = {
                "content": "\n</data>",
                "message_type": 2
            }
            yield f"data:{json.dumps(data_end_data, ensure_ascii=False)}\n\n".encode("utf-8")
            full_stream_content.append(data_end_data["content"])

            # 5. 知识匹配和输出
            no_standard_query = False
            if intent_result and isinstance(intent_result, dict):
                no_standard_query = intent_result.get("no_standard_query", False)

            if llm_raw_content and knowledge_results and not no_standard_query:
                full_reply = "".join(llm_raw_content)
                try:
                    matched_knowledge = await match_and_format_knowledge(
                        llm_output=full_reply,
                        knowledge_results=knowledge_results,
                        max_results=2
                    )
                    if matched_knowledge:
                        knowledge_dict = {
                            "title": "相关的标准规范原文内容",
                            "table_list": matched_knowledge
                        }
                        knowledge_data = {
                            "content": json.dumps(knowledge_dict, ensure_ascii=False),
                            "message_type": 3
                        }
                        yield f"data:{json.dumps(knowledge_data, ensure_ascii=False)}\n\n".encode("utf-8")

                        full_stream_content.append("<knowledge>")
                        full_stream_content.append("相关的标准规范原文内容")
                        for item in matched_knowledge:
                            full_stream_content.append(item)
                        full_stream_content.append("</knowledge>")

                except Exception as e:
                    logger.error(f"[知识匹配] 错误: {e}")

        except Exception as e:
            error_msg = f"流式处理错误: {str(e)}"
            logger.error(f"[ES流式] {error_msg}")
            error_content = f"<data>\n抱歉，处理您的请求时出现错误: {error_msg}\n</data>"
            error_data = {
                "content": error_content,
                "message_type": 4
            }
            yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")
            full_stream_content.append(error_content)

        finally:
            # 异步保存消息
            if save_messages and full_stream_content:
                complete_assistant_reply = "".join(full_stream_content)
                background_tasks.add_task(
                    self.message_repo.append_message,
                    user_id, session_id, "user", question
                )
                background_tasks.add_task(
                    self.message_repo.append_message,
                    user_id, session_id, "assistant", complete_assistant_reply
                )

    async def _hybrid_stream_gen(
        self,
        question: str,
        history_msgs: List[Dict[str, str]],
        user_id: str,
        session_id: str,
        background_tasks: BackgroundTasks,
        save_messages: bool = True
    ) -> AsyncGenerator[bytes, None]:
        """
        混合查询流式生成器 - 使用LLM路由判断

        Args:
            question: 用户问题
            history_msgs: 历史消息
            user_id: 用户ID
            session_id: 会话ID
            background_tasks: 后台任务
            save_messages: 是否保存消息

        Yields:
            bytes: 流式输出
        """
        full_stream_content: List[str] = []

        try:
            # 1. 使用大模型进行意图路由判断
            think_start = "<think>开始对用户的提问进行深入解析...\n"
            think_data = json.dumps({"content": think_start, "message_type": 1}, ensure_ascii=False)
            yield f"data:{think_data}\n\n".encode("utf-8")
            full_stream_content.append(think_start)

            routing_chunks = []

            async def router_callback(chunk: str):
                if chunk:
                    routing_chunks.append(chunk)
                    full_stream_content.append(chunk)

            routing_decision = await self.intent_router.route(
                question, history_msgs, router_callback
            )

            # 输出推理内容
            if routing_chunks:
                reasoning_content = "".join(routing_chunks)
                reasoning_data = json.dumps({
                    "content": reasoning_content,
                    "message_type": 1
                }, ensure_ascii=False)
                yield f"data:{reasoning_data}\n\n".encode("utf-8")

            # 输出路由决策结果
            decision_texts = {
                "neo4j": "需要检索网络业务知识图谱辅助回答，请稍等....",
                "es": "需要检索法规标准知识辅助回答，请稍等....",
                "hybrid": "需要同时检索网络业务知识图谱以及法规标准知识辅助回答，请稍等....",
                "none": "大模型直接生成回答，请稍等...."
            }
            decision_text = decision_texts.get(routing_decision, "检索法规标准知识辅助回答，请稍等....")
            decision_output = f"{decision_text}\n"
            decision_data = json.dumps({
                "content": decision_output,
                "message_type": 1
            }, ensure_ascii=False)
            yield f"data:{decision_data}\n\n".encode("utf-8")
            full_stream_content.append(decision_output)

            # 2. 根据路由决策调用相应的函数
            if routing_decision == "es":
                async for chunk in self._es_stream_gen(
                    question, history_msgs, user_id, session_id, background_tasks, save_messages=False
                ):
                    chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                    if "data:" in chunk_str:
                        try:
                            data_part = chunk_str.split("data:")[1].strip()
                            chunk_json = json.loads(data_part)
                            content = chunk_json.get("content", "")
                            if "<think>开始对用户的提问进行深入解析..." in content:
                                continue
                            yield chunk
                            full_stream_content.append(content)
                        except:
                            yield chunk
                    else:
                        yield chunk

            elif routing_decision == "neo4j":
                # 调用Neo4j查询，但过滤掉整个<think>标签块
                in_think_block = False
                async for chunk in self._neo4j_stream_gen(
                    question, history_msgs, user_id, session_id, background_tasks, save_messages=False
                ):
                    chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

                    # 过滤掉整个<think>标签块
                    if "data:" in chunk_str:
                        try:
                            # 解析JSON数据
                            data_part = chunk_str.split("data:")[1].strip()
                            chunk_json = json.loads(data_part)
                            content = chunk_json.get("content", "")

                            # 检查是否进入think块
                            if "<think>" in content:
                                in_think_block = True
                                continue

                            # 检查是否退出think块
                            if "</think>" in content:
                                in_think_block = False
                                continue

                            # 如果在think块内，跳过所有内容
                            if in_think_block:
                                continue

                            yield chunk
                            full_stream_content.append(content)
                        except:
                            yield chunk
                    else:
                        yield chunk

            elif routing_decision == "hybrid":
                # 实现混合查询 - 完全复刻server2.py的hybrid逻辑
                # 1. 先调用Neo4j查询并收集结果
                neo4j_start_msg = "\n现在开始业务知识图谱检索\n"
                neo4j_start_data = {"content": neo4j_start_msg, "message_type": 1}
                yield f"data:{json.dumps(neo4j_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
                full_stream_content.append(neo4j_start_msg)

                neo4j_data_content = ""
                in_data_section = False
                in_think_section = False

                async for chunk in self._neo4j_stream_gen(
                    question, history_msgs, user_id, session_id, background_tasks, save_messages=False
                ):
                    chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

                    if "data:" in chunk_str:
                        try:
                            # 解析JSON数据
                            data_part = chunk_str.split("data:")[1].strip()
                            chunk_json = json.loads(data_part)
                            content = chunk_json.get("content", "")

                            # 检测<think>标签的开始和结束，过滤掉原始的think标签
                            if "<think>" in content:
                                in_think_section = True
                                continue  # 跳过<think>标签
                            elif "</think>" in content:
                                in_think_section = False
                                continue  # 跳过</think>标签

                            # 如果在原始think标签内，跳过不输出
                            if in_think_section:
                                continue

                            # 检测<data>标签的开始和结束
                            if "<data>" in content:
                                in_data_section = True
                                continue  # 跳过<data>标签本身
                            elif "</data>" in content:
                                in_data_section = False
                                continue  # 跳过</data>标签本身
                            elif in_data_section:
                                # 在<data>标签内的内容，只收集起来用于后续合并，不在这里输出
                                neo4j_data_content += content
                        except:
                            # 解析失败时也不输出
                            continue
                    else:
                        # 非data格式的chunk也不输出
                        continue

                # 2. 输出Neo4j结果
                if neo4j_data_content.strip():
                    neo4j_result_msg = f"\n检索到的业务信息：\n{neo4j_data_content.strip()}\n"
                else:
                    neo4j_result_msg = "\n未检索到相关业务信息\n"
                neo4j_result_data = {"content": neo4j_result_msg, "message_type": 1}
                yield f"data:{json.dumps(neo4j_result_data, ensure_ascii=False)}\n\n".encode("utf-8")
                full_stream_content.append(neo4j_result_msg)

                # 3. 输出"现在开始法规标准检索"
                es_start_msg = "\n现在开始法规标准检索\n"
                es_start_data = {"content": es_start_msg, "message_type": 1}
                yield f"data:{json.dumps(es_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
                full_stream_content.append(es_start_msg)

                # 4. 将Neo4j结果拼接到问题中，调用ES查询
                enhanced_question = question
                if neo4j_data_content.strip():
                    enhanced_question = question + "以下是检索到的具体业务信息：" + neo4j_data_content.strip()

                # 5. 调用ES查询
                async for chunk in self._es_stream_gen(
                    enhanced_question, history_msgs, user_id, session_id, background_tasks, save_messages=False
                ):
                    chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                    if "data:" in chunk_str:
                        try:
                            data_part = chunk_str.split("data:")[1].strip()
                            chunk_json = json.loads(data_part)
                            content = chunk_json.get("content", "")

                            # 跳过重复的think标签
                            if "<think>开始对用户的提问进行深入解析..." in content:
                                continue

                            yield chunk
                            full_stream_content.append(content)
                        except:
                            yield chunk
                    else:
                        yield chunk

            else:  # none或其他
                # 调用ES查询，但过滤掉开始的<think>标签
                async for chunk in self._es_stream_gen(
                    question, history_msgs, user_id, session_id, background_tasks, save_messages=False
                ):
                    chunk_str = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

                    # 过滤掉重复的<think>开始标签
                    if "data:" in chunk_str:
                        try:
                            # 解析JSON数据
                            data_part = chunk_str.split("data:")[1].strip()
                            chunk_json = json.loads(data_part)
                            content = chunk_json.get("content", "")

                            # 跳过重复的think开始标签
                            if "<think>开始对用户的提问进行深入解析..." in content:
                                continue

                            yield chunk
                            full_stream_content.append(content)
                        except:
                            yield chunk
                    else:
                        yield chunk

        except Exception as e:
            error_msg = f"混合查询错误: {str(e)}"
            logger.error(error_msg)
            error_output = f"<data>\n抱歉，处理您的请求时出现错误: {error_msg}\n</data>"
            error_data = json.dumps({
                "content": error_output,
                "message_type": 4
            }, ensure_ascii=False)
            yield f"data:{error_data}\n\n".encode("utf-8")

        finally:
            if save_messages and full_stream_content:
                complete_assistant_reply = "".join(full_stream_content)
                background_tasks.add_task(
                    self.message_repo.append_message,
                    user_id, session_id, "user", question
                )
                background_tasks.add_task(
                    self.message_repo.append_message,
                    user_id, session_id, "assistant", complete_assistant_reply
                )

    async def _neo4j_stream_gen(
        self,
        question: str,
        history_msgs: List[Dict[str, str]],
        user_id: str,
        session_id: str,
        background_tasks: BackgroundTasks,
        save_messages: bool = True
    ) -> AsyncGenerator[bytes, None]:
        """
        Neo4j查询流式生成器 - 使用Neo4jQueryService

        完全复刻server2.py的neo4j_stream_gen逻辑
        """
        full_stream_content: List[str] = []

        try:
            # 使用Neo4jQueryService执行查询
            # 该服务内部调用old/neo4j_code模块的完整流程
            async for chunk in self.neo4j_service.query_stream(question, history_msgs):
                if isinstance(chunk, bytes):
                    yield chunk
                    # 解码用于收集完整内容
                    try:
                        chunk_str = chunk.decode("utf-8")
                        # 解析data部分
                        if "data:" in chunk_str:
                            data_part = chunk_str.split("data:")[1].strip()
                            chunk_json = json.loads(data_part)
                            content = chunk_json.get("content", "")
                            full_stream_content.append(content)
                    except:
                        pass
                else:
                    chunk_str = str(chunk)
                    yield chunk_str.encode("utf-8")
                    full_stream_content.append(chunk_str)

                # 小延迟确保流式效果
                await asyncio.sleep(0.01)

        except Exception as e:
            error_msg = f"Neo4j查询错误: {str(e)}"
            logger.error(f"[Neo4j流式] {error_msg}")
            error_data = {
                "content": f"<data>\n抱歉，处理您的请求时出现错误: {error_msg}\n</data>",
                "message_type": 4
            }
            yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")
            full_stream_content.append(error_data["content"])

        finally:
            # 异步保存消息（只在独立调用时保存）
            if save_messages and full_stream_content:
                complete_assistant_reply = "".join(full_stream_content)
                background_tasks.add_task(
                    self.message_repo.append_message,
                    user_id, session_id, "user", question
                )
                background_tasks.add_task(
                    self.message_repo.append_message,
                    user_id, session_id, "assistant", complete_assistant_reply
                )

    def _filter_content(self, content: str) -> str:
        """过滤掉包含think和knowledge标签的内容"""
        import re
        if not content:
            return content

        # 移除 <think> </think> 标签及其内容
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        # 移除 <knowledge> </knowledge> 标签及其内容
        content = re.sub(r'<knowledge>.*?</knowledge>', '', content, flags=re.DOTALL)

        # 清理多余的空白字符
        content = re.sub(r'\n\s*\n', '\n', content.strip())

        return content

    def _build_enhanced_prompt(
        self,
        history: List[Dict[str, str]],
        query: str,
        knowledge: str = ""
    ) -> str:
        """构建增强的prompt"""
        # 格式化历史对话（保留最近2条）
        history_parts = []
        for msg in history[-2:]:
            role = "用户" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")
            # 历史对话只保留<data>内容
            filtered_content = self._filter_content(content)
            if filtered_content.strip():
                history_parts.append(f"{role}: {filtered_content}")
        history_text = "\n".join(history_parts) if history_parts else "无历史对话"

        # 安全截断
        knowledge_safe = (knowledge or "无相关知识")[:60000]
        query_safe = (query or "")[:8000]

        prompt_template = """
{system_prompt}

以下是历史对话，请基于上下文回答用户的新问题。

--- 历史对话开始 ---
{history}
--- 历史对话结束 ---

--- 相关知识 ---
{knowledge}
--- 知识结束 ---

用户: {query}
助手:"""

        prompt = prompt_template.format(
            system_prompt=self.system_prompt,
            history=history_text,
            knowledge=knowledge_safe,
            query=query_safe,
        )

        # 兜底截断
        MAX_LEN = 98304 - 200
        if len(prompt) > MAX_LEN:
            prompt = prompt[:MAX_LEN]

        return prompt