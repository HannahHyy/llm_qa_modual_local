"""
Neo4j查询服务

完整实现Neo4j图数据库查询功能
"""

import re
import json
import asyncio
from typing import List, Dict, Optional, AsyncGenerator

from infrastructure.clients.llm_client import LLMClient
from infrastructure.clients.neo4j_client import Neo4jClient
from infrastructure.clients.es_client import ESClient
from core.logging import logger
from core.config import get_settings, get_llm_model_settings


class JsonExtractor:
    """JSON提取器 - 从LLM输出中提取JSON"""

    def extract(self, text: str) -> Optional[List]:
        """
        从文本中提取JSON列表 - 增强版，更健壮

        查找标识符：'3.以下是json格式的解析结果：'之后的JSON
        """
        if not text:
            return None

        try:
            # 查找JSON标识符
            if '3.以下是json格式的解析结果：' in text:
                # 提取标识符后的内容
                parts = text.split('3.以下是json格式的解析结果：')
                if len(parts) > 1:
                    json_part = parts[1].strip()

                    # 调试：显示提取到的JSON部分长度
                    logger.info(f"[JSON提取DEBUG] 提取到JSON部分长度: {len(json_part)}")
                    logger.info(f"[JSON提取DEBUG] JSON前100字符: {json_part[:100]}")

                    # 方法1：使用非贪婪匹配提取JSON数组
                    match = re.search(r'\[.*?\]', json_part, re.DOTALL)
                    if not match:
                        # 方法2：使用贪婪匹配（可能包含嵌套）
                        match = re.search(r'\[[\s\S]*\]', json_part)

                    if match:
                        json_str = match.group(0)
                        logger.info(f"[JSON提取DEBUG] 匹配到JSON字符串长度: {len(json_str)}")
                        logger.info(f"[JSON提取DEBUG] JSON字符串: {json_str[:200]}...")
                        return json.loads(json_str)

            # 尝试直接解析整个文本
            match = re.search(r'\[[\s\S]*\]', text)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)

            logger.warning(f"[JSON提取] 未找到JSON数组")
            return None

        except json.JSONDecodeError as e:
            logger.warning(f"[JSON提取] JSON解析失败: {e}")
            logger.warning(f"[JSON提取] 尝试解析的文本前500字符: {text[:500]}")
            return None
        except Exception as e:
            logger.warning(f"[JSON提取] 提取失败: {e}")
            return None


class Neo4jIntentParser:
    """Neo4j意图解析器配置"""

    def __init__(self):
        # Neo4j图数据库结构定义（从配置或数据库schema获取）
        self.nodes = {
            "单位": {
                "description": "组织单位节点",
                "properties": ["name", "type", "address"]
            },
            "网络": {
                "description": "网络节点",
                "properties": ["name", "type", "ip_range"]
            },
            "系统": {
                "description": "系统节点",
                "properties": ["name", "type", "version"]
            },
            "设备": {
                "description": "设备节点",
                "properties": ["name", "type", "model", "ip"]
            },
            "安全产品": {
                "description": "安全产品节点",
                "properties": ["name", "type", "vendor"]
            },
            "集成商": {
                "description": "集成商节点",
                "properties": ["name", "contact"]
            }
        }

        self.relationships = {
            "拥有": {
                "from": "单位",
                "to": "网络/系统/设备",
                "description": "拥有关系"
            },
            "包含": {
                "from": "网络",
                "to": "系统/设备",
                "description": "包含关系"
            },
            "部署": {
                "from": "网络/系统",
                "to": "安全产品",
                "description": "部署关系"
            },
            "集成": {
                "from": "集成商",
                "to": "单位",
                "description": "集成关系"
            }
        }


class Neo4jQueryService:
    """
    Neo4j查询服务 - 完整独立实现

    算法流程（100%基于old/neo4j_code/apps/views_intent/views_new.py）：
    1. 意图识别：使用LLM解析用户问题，拆分为1-3个查询意图
    2. ES示例匹配：为每个意图从ES中匹配最相似的Cypher示例
    3. Cypher生成：使用LLM基于意图和示例批量生成Cypher语句
    4. 查询执行：在Neo4j中执行Cypher查询
    5. 结果摘要：使用LLM将查询结果转换为自然语言回答
    """

    def __init__(self, llm_client: LLMClient, neo4j_client: Neo4jClient, es_client: ESClient):
        """
        初始化服务

        Args:
            llm_client: LLM客户端
            neo4j_client: Neo4j客户端
            es_client: Elasticsearch客户端
        """
        self.llm_client = llm_client
        self.neo4j_client = neo4j_client
        self.es_client = es_client
        self.settings = get_settings()
        self.model_settings = get_llm_model_settings()
        self.intent_parser = Neo4jIntentParser()
        self.json_extractor = JsonExtractor()

    def is_available(self) -> bool:
        """检查Neo4j模块是否可用"""
        return self.neo4j_client.is_connected()

    # ==================== 阶段1：意图识别 ====================

    async def _parse_intent_only_with_stream(
        self,
        user_query: str,
        history_msgs: List[Dict[str, str]],
        stream_callback: Optional[callable] = None
    ) -> Optional[List[Dict]]:
        """
        只生成意图（不生成cypher），支持流式输出

        对应old代码：parse_intent_only_with_stream方法
        """
        try:
            # 构建意图识别Prompt
            system_prompt = (
                "你是Neo4j图数据库的'智能意图解析器'。\n"
                "请根据输入的上下文，完成Neo4j查询的意图拆解，并对每个意图进行详细分析。\n"
                "你需要进行流式输出，其中分析思路需要展示到前端页面。\n"
                "请先详细说明你的分析思路，分析思路请完全以流利的中文自然语言进行描述，然后输出最终严格的JSON结果。\n"
                "最后的JSON结果，必须严格按照以下格式输出标识符（不要有任何变化）：\n"
                "'3.以下是json格式的解析结果：'\n"
                "[{\"intent_item\": \"意图描述字符串\"}, {\"intent_item\": \"意图描述字符串\"}, ...] \n"
                "说明:\n"
                "- intent_item: Neo4j查询的意图拆解的意图描述\n"
                "- 最多给出3个意图；若用户问题非常明确，则仅输出1个意图，能不拆分的尽量不拆分。\n"
                "\n在流式输出时，请按以下格式组织你的回答：\n"
                "1. 首先分析用户问题可以拆分成哪几个意图\n"
                "2. 以流利的中文输出每个意图的具体含义\n"
                "3. 最后输出完整的JSON结果。（在JSON之前必须输出标识符）。\n"
            )

            prompt = f"{system_prompt}\n\n[用户问题]\n{user_query}\n\n"

            # 流式调用LLM
            raw = ""
            async for chunk in self.llm_client.async_stream_chat(
                prompt=prompt,
                model=self.model_settings.neo4j_model,
                max_tokens=self.model_settings.neo4j_max_tokens,
                temperature=0,
                system_prompt=system_prompt,
            ):
                raw += chunk
                if stream_callback:
                    await stream_callback(chunk)

            # 解析JSON结果
            intent_list = self.json_extractor.extract(raw)
            if not intent_list:
                logger.warning("[Neo4j意图识别] LLM未返回有效意图列表")
                return None

            # 转换为统一格式
            if isinstance(intent_list, list):
                result = []
                for item in intent_list:
                    if isinstance(item, dict):
                        intent_item = item.get("intent_item", "")
                        if intent_item:
                            result.append({"intent_item": intent_item})
                    elif isinstance(item, str):
                        result.append({"intent_item": item})
                return result if result else None

            return None

        except Exception as e:
            logger.error(f"[Neo4j意图识别] 失败: {e}")
            return None

    # ==================== 阶段2：ES示例匹配 ====================

    async def _match_examples_from_es(self, intent_item: str, top_k: int = 1) -> List[Dict]:
        """
        从ES中匹配Cypher示例 - 基于old代码逻辑

        Args:
            intent_item: 意图描述
            top_k: 返回Top-K个示例

        Returns:
            示例列表: [{"question": "...", "answer": "Cypher语句", "score": 0.9}]
        """
        try:
            # 使用BM25文本匹配搜索Cypher示例
            # 注意：query参数应该是查询DSL的内部结构（不包含外层"query"键）
            query_dsl = {
                "match": {
                    "question": intent_item
                }
            }

            # 搜索Cypher示例索引（使用配置中的索引名）
            index_name = self.settings.es.cypher_index  # qa_system索引
            response = self.es_client.search(
                index=index_name,
                query=query_dsl,  # 传递查询DSL内部结构
                size=top_k
            )

            # 解析响应（response是完整的ES响应字典）
            examples = []
            hits = response.get("hits", {}).get("hits", [])
            for hit in hits:
                source = hit.get("_source", {})
                # 从_source中获取cypher字段（而非answer字段）
                answer = source.get("cypher", source.get("answer", ""))
                answer = answer.strip().replace(' ', '')
                examples.append({
                    'question': source.get('question', ''),
                    'answer': answer,
                    'score': hit.get('_score', 0.0)
                })

            logger.info(f"[Neo4j示例匹配] 为意图'{intent_item}'匹配到 {len(examples)} 个示例")
            return examples

        except Exception as e:
            logger.warning(f"[Neo4j示例匹配] ES匹配失败: {e}", exc_info=True)
            return []

    # ==================== 阶段3：批量Cypher生成 ====================

    async def _generate_cyphers_batch_with_stream(
        self,
        intent_with_examples: List[Dict],
        user_query: str,
        stream_callback: Optional[callable] = None
    ) -> List[Dict]:
        """
        批量生成cypher，支持流式输出

        Args:
            intent_with_examples: 意图和示例列表
            user_query: 原始用户问题
            stream_callback: 流式回调

        Returns:
            生成的Cypher列表: [{"intent_item": "...", "cypher": "...", "examples": [...]}]
        """
        try:
            # 构建所有意图和示例的文本
            intents_text = ""
            for i, item in enumerate(intent_with_examples, 1):
                intent_item = item.get("intent_item", "")
                examples = item.get("examples", [])

                examples_text = ""
                for j, example in enumerate(examples, 1):
                    question = example.get('question', '')
                    answer = example.get('answer', '')
                    examples_text += f"  示例{j}:\n  问题: {question}\n  Cypher: {answer}\n\n"

                intents_text += f"意图{i}: {intent_item}\n参考示例:\n{examples_text}\n"

            # 构建详细的节点信息
            nodes_info = []
            for node_type, node_info in self.intent_parser.nodes.items():
                properties = node_info.get("properties", [])
                description = node_info.get("description", "")
                properties_str = ", ".join(properties) if properties else "无"
                nodes_info.append(f"  - {node_type}: {description}\n    属性: [{properties_str}]")

            # 构建详细的关系信息
            relationships_info = []
            for rel_type, rel_info in self.intent_parser.relationships.items():
                from_node = rel_info.get("from", "")
                to_node = rel_info.get("to", "")
                description = rel_info.get("description", "")
                relationships_info.append(
                    f"  - {rel_type}: {description}\n    起始节点: {from_node} -> 目标节点: {to_node}"
                )

            # 构建批量Cypher生成Prompt
            system_prompt = (
                "你是Neo4j图数据库的Cypher查询生成专家。\n"
                "请根据多个用户意图和提供的示例，为每个意图生成一条完整可执行的Cypher查询语句。\n"
                "要求：\n"
                "1. 为每个意图生成对应的Cypher语句，必须可以直接执行\n"
                "2. 参考每个意图对应的示例中的Cypher语法和模式\n"
                "3. 输出格式必须为严格的JSON格式，标识符为：'3.以下是json格式的解析结果：'\n"
                "4. JSON格式：[{\"intent_item\": \"意图描述\", \"cypher\": \"Cypher语句\"}, ...]\n"
                "5. 如果某个意图不明确或无法生成有效的Cypher，该意图的cypher字段返回空字符串\n"
                "6. 请先简要说明分析思路，然后输出JSON结果（在JSON之前必须输出标识符）\n"
            )

            prompt = (
                f"[用户原始问题]\n{user_query}\n\n"
                f"[需要生成Cypher的意图列表]\n{intents_text}\n"
                f"[Neo4j图数据库结构]\n"
                f"节点类型及属性:\n" + "\n".join(nodes_info) + "\n\n"
                f"关系类型:\n" + "\n".join(relationships_info) + "\n\n"
                f"重要提示: 请严格按照上述定义的节点类型、节点属性和关系类型进行Cypher生成, "
                f"重要提示: 如果要匹配节点属性,一定要使用where 节点.属性 contains 'xx'"
                f"严禁创建或使用上述结构中没有定义的节点类型、节点属性或关系类型。"
                f"如果用户问题中提到了未定义的节点/属性/关系，请忽略这些信息或将其从意图中排除。\n"
                f"请为每个意图生成对应的Cypher查询语句。"
            )

            # 流式调用LLM
            raw = ""
            async for chunk in self.llm_client.async_stream_chat(
                prompt=prompt,
                model=self.model_settings.neo4j_model,
                max_tokens=self.model_settings.neo4j_max_tokens,
                temperature=0.0,
                system_prompt=system_prompt,
            ):
                raw += chunk
                if stream_callback:
                    await stream_callback(chunk)

            logger.info(f"[Neo4j Cypher生成] LLM输出: {raw[:500]}...")

            # 解析JSON结果
            intent_cypher_list = self.json_extractor.extract(raw)
            if not intent_cypher_list:
                logger.warning(f"[Neo4j Cypher生成] 未解析到结果")
                return []

            # 转换为统一格式
            result = []
            intent_cypher_map = {}
            if isinstance(intent_cypher_list, list):
                for item in intent_cypher_list:
                    if isinstance(item, dict):
                        intent_item = item.get("intent_item", "")
                        cypher = item.get("cypher", "")
                        if intent_item:
                            # 清理cypher（去除markdown代码块标记）
                            if cypher:
                                cypher = cypher.strip()
                                if cypher.startswith("```"):
                                    lines = cypher.split("\n")
                                    cypher = "\n".join(lines[1:-1]) if len(lines) > 2 else cypher
                                if cypher.startswith("```cypher"):
                                    lines = cypher.split("\n")
                                    cypher = "\n".join(lines[1:-1]) if len(lines) > 2 else cypher
                            intent_cypher_map[intent_item] = cypher.strip() if cypher else ""

            # 按照原始意图顺序构建结果
            for item in intent_with_examples:
                intent_item = item.get("intent_item", "")
                examples = item.get("examples", [])
                cypher = intent_cypher_map.get(intent_item, "")

                if cypher:
                    result.append({
                        "intent_item": intent_item,
                        "cypher": cypher,
                        "examples": examples
                    })
                    logger.info(f"[Neo4j Cypher] 意图: {intent_item}")
                    logger.info(f"[Neo4j Cypher] 生成: {cypher}")

            return result

        except Exception as e:
            logger.error(f"[Neo4j Cypher生成] 失败: {e}")
            return []

    # ==================== 主流程：完整查询 ====================

    async def query_stream(
        self,
        question: str,
        history_msgs: List[Dict[str, str]]
    ) -> AsyncGenerator[bytes, None]:
        """
        执行Neo4j查询并流式返回结果（完整实现）

        流程（100%基于old/neo4j_code/apps/views_intent/views_new.py:generate_answer_async）：
        1. 意图识别阶段（流式输出think）
        2. ES匹配示例
        3. Cypher生成（流式输出think）
        4. 执行查询
        5. 生成摘要（流式输出data）
        6. 输出知识结果
        """
        if not self.is_available():
            error_data = {
                "content": "<data>\nNeo4j服务未启用，请检查配置\n</data>",
                "msg_type": 2
            }
            yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")
            return

        try:
            # ==================== 阶段1：意图识别 ====================
            intent_result = None
            intent_queue = asyncio.Queue()
            intent_done = asyncio.Event()

            async def intent_callback(chunk: str):
                """意图识别流式回调"""
                if chunk:
                    await intent_queue.put(chunk)

            async def intent_parser_task():
                """意图解析任务"""
                nonlocal intent_result
                try:
                    intent_result = await self._parse_intent_only_with_stream(
                        question, history_msgs, stream_callback=intent_callback
                    )
                finally:
                    intent_done.set()
                    await intent_queue.put(None)

            # 启动意图解析任务
            parser_task = asyncio.create_task(intent_parser_task())

            # 输出思考过程开始标记
            think_start_data = {"content": "<think>\n", "msg_type": 1}
            yield f"data:{json.dumps(think_start_data, ensure_ascii=False)}\n\n".encode("utf-8")

            # 实时输出意图识别过程
            while True:
                try:
                    chunk = await asyncio.wait_for(intent_queue.get(), timeout=0.1)
                    if chunk is None:
                        break
                    think_data = {"content": chunk, "msg_type": 1}
                    yield f"data:{json.dumps(think_data, ensure_ascii=False)}\n\n".encode("utf-8")
                except asyncio.TimeoutError:
                    if intent_done.is_set():
                        try:
                            chunk = intent_queue.get_nowait()
                            if chunk is None:
                                break
                            think_data = {"content": chunk, "msg_type": 1}
                            yield f"data:{json.dumps(think_data, ensure_ascii=False)}\n\n".encode("utf-8")
                        except asyncio.QueueEmpty:
                            break
                    continue

            # 等待意图解析完成
            await parser_task
            logger.info(f"[Neo4j查询] 意图识别结果: {intent_result}")

            if not intent_result or not isinstance(intent_result, list):
                logger.error("[Neo4j查询] 未获取到有效的意图列表")
                error_data = {"content": "<data>\n未能识别有效的查询意图\n</data>", "msg_type": 2}
                yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")
                return

            # ==================== 阶段2：ES匹配示例 ====================
            intent_with_examples = []
            for intent_item_dict in intent_result:
                intent_item = intent_item_dict.get("intent_item", "")
                if not intent_item:
                    continue

                examples = await self._match_examples_from_es(intent_item, top_k=1)
                intent_with_examples.append({
                    "intent_item": intent_item,
                    "examples": examples
                })
                logger.info(f"[Neo4j查询] 意图: {intent_item}, 匹配示例数: {len(examples)}")

            # ==================== 阶段3：批量Cypher生成 ====================
            cypher_queue = asyncio.Queue()
            cypher_done = asyncio.Event()

            async def cypher_stream_callback(chunk: str):
                """Cypher生成流式回调"""
                if chunk:
                    await cypher_queue.put(chunk)

            intent_with_cypher_result = []

            async def cypher_generation_task():
                """批量Cypher生成任务"""
                nonlocal intent_with_cypher_result
                try:
                    intent_with_cypher_result = await self._generate_cyphers_batch_with_stream(
                        intent_with_examples, question, stream_callback=cypher_stream_callback
                    )
                finally:
                    cypher_done.set()
                    await cypher_queue.put(None)

            # 启动批量Cypher生成任务
            cypher_task = asyncio.create_task(cypher_generation_task())

            # 实时输出Cypher生成过程
            while True:
                try:
                    chunk = await asyncio.wait_for(cypher_queue.get(), timeout=0.1)
                    if chunk is None:
                        break
                    cypher_think_data = {"content": chunk, "msg_type": 1}
                    yield f"data:{json.dumps(cypher_think_data, ensure_ascii=False)}\n\n".encode("utf-8")
                except asyncio.TimeoutError:
                    if cypher_done.is_set():
                        try:
                            chunk = cypher_queue.get_nowait()
                            if chunk is None:
                                break
                            cypher_think_data = {"content": chunk, "msg_type": 1}
                            yield f"data:{json.dumps(cypher_think_data, ensure_ascii=False)}\n\n".encode("utf-8")
                        except asyncio.QueueEmpty:
                            break
                    continue

            # 输出Cypher生成完成标记
            cypher_end_data = {"content": "\nCypher生成完成。\n</think>\n", "msg_type": 1}
            yield f"data:{json.dumps(cypher_end_data, ensure_ascii=False)}\n\n".encode("utf-8")

            # 等待批量Cypher生成完成
            await cypher_task
            intent_with_cypher = intent_with_cypher_result

            # ==================== 阶段4：执行Cypher查询 ====================
            prompt_result = []
            knowledge_result = []

            for item in intent_with_cypher:
                cypher = item.get("cypher", "")
                if not cypher:
                    continue

                try:
                    cypher_result = self.neo4j_client.query(cypher)
                    item["intent_result"] = cypher_result
                    prompt_result.append(item)
                    knowledge_result += cypher_result
                    logger.info(f"[Neo4j查询] 执行成功，返回 {len(cypher_result)} 条结果")
                except Exception as e:
                    logger.error(f"[Neo4j查询] 执行失败: {e}")
                    item["intent_result"] = []
                    prompt_result.append(item)

            # ==================== 阶段5：生成摘要 ====================
            summary_system_prompt = (
                "请关闭思考模式，直接使用业务专员查到的结果对你的领导的问题作出回答，"
                "业务专员的结果不需要进行筛选，也不需要逐条分析，微小的错误请忽略，名称不统一也请忽略，"
                "回答的方式是先生成100个字的总结摘要，然后再进行详细回答。"
                "请参考以下模板回答。\n以下是根据涉密网业务图谱查询到的结果作出的回答："
            )

            content_with_prompt = f"以下是业务专员查到的结果：\n{prompt_result}"
            content_with_query = (
                f"以下是你的领导的问题，你的思考过程和输出都会被他看见，"
                f"千万不要重复思考或者重复输出，回答请关闭思考模式：\n{question}"
            )

            # 输出数据开始标记
            data_start_data = {"content": "<data>\n", "msg_type": 2}
            yield f"data:{json.dumps(data_start_data, ensure_ascii=False)}\n\n".encode("utf-8")

            # 流式生成摘要（使用同步流式）
            for chunk in self.llm_client.sync_stream_chat(
                prompt=content_with_prompt + "\n\n" + content_with_query,
                model=self.model_settings.neo4j_model,
                max_tokens=self.model_settings.neo4j_max_tokens,
                temperature=0.0,
                system_prompt=summary_system_prompt,
            ):
                data_content = {"content": chunk, "msg_type": 2}
                yield f"data:{json.dumps(data_content, ensure_ascii=False)}\n\n".encode("utf-8")

            # 输出数据结束标记
            data_end_data = {"content": "\n</data>\n", "msg_type": 2}
            yield f"data:{json.dumps(data_end_data, ensure_ascii=False)}\n\n".encode("utf-8")

            # ==================== 阶段6：输出知识结果 ====================
            if knowledge_result:
                knowledge_data = {
                    "content": f"<knowledge>\n检索到{len(knowledge_result)}条相关信息\n</knowledge>\n",
                    "msg_type": 3
                }
                yield f"data:{json.dumps(knowledge_data, ensure_ascii=False)}\n\n".encode("utf-8")

        except Exception as e:
            error_msg = f"Neo4j查询错误: {str(e)}"
            logger.error(f"[Neo4j服务] {error_msg}")
            error_data = {
                "content": f"<data>\n抱歉，处理您的请求时出现错误: {error_msg}\n</data>",
                "msg_type": 2
            }
            yield f"data:{json.dumps(error_data, ensure_ascii=False)}\n\n".encode("utf-8")


__all__ = ["Neo4jQueryService"]
