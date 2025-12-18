# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/11/9 22:12
    Description: 
"""
import json
import asyncio
from fastapi import APIRouter
import os
from typing import List, Dict, Optional

from neo4j_code.db.neo_conn import Neo4jConnection
from neo4j_code.settings.config import Neo4jConfig, LlmConfig
from neo4j_code.apps.views_intent.neo4j_intent_parser import Neo4jIntentParser
import sys

model_name = LlmConfig.model_name

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from LLM_Server.llm_client import LLMClient
from neo4j_code.documents.es_embedding import QASearchEngine
from neo4j_code.apps.views_intent.json_extractor import JsonExtractor

LENGTH_NOTIFICATION_CN = "······\n由于模型支持的上下文长度的原因，回答被截断了"

os.environ["TOKENIZERS_PARALLELISM"] = "false"

router = APIRouter()

# 只生成意图的提示词（不生成cypher）
INTENT_ONLY_SYSTEM_PROMPT = (
    "你是Neo4j图数据库的'智能意图解析器'。\n"
    "请根据输入的上下文，完成Neo4j查询的意图拆解，并对每个意图进行详细分析。\n"
    "你需要进行流式输出，其中分析思路需要展示到前端页面。\n"
    "请先详细说明你的分析思路，分析思路请完全以流利的中文自然语言进行描述，然后输出最终严格的JSON结果。\n"
    "最后的JSON结果，必须严格按照以下格式输出标识符（不要有任何变化）：\n"
    "'3.以下是json格式的解析结果：'\n"
    "[{intent_item: string}, {intent_item: string}, ...] \n"
    "说明:\n"
    "- intent_item: Neo4j查询的意图拆解的意图描述\n"
    "- 最多给出3个意图；若用户问题非常明确，则仅输出1个意图，能不拆分的尽量不拆分。\n"
    "\n在流式输出时，请按以下格式组织你的回答：\n"
    "1. 首先分析用户问题可以拆分成哪几个意图\n"
    "2. 以流利的中文输出每个意图的具体含义，\n"
    # "**特别要明确指出识别到的节点类型、关系类型及其识别依据**\n"
    "3. 最后输出完整的JSON结果。（在JSON之前必须输出标识符）。\n"
)

# 基于意图和示例生成cypher的提示词
CYPHER_GENERATION_SYSTEM_PROMPT = (
    "你是Neo4j图数据库的Cypher查询生成专家。\n"
    "请根据用户意图和提供的示例，生成一条完整可执行的Cypher查询语句。\n"
    "要求：\n"
    "1. 生成的Cypher语句必须可以直接执行\n"
    "2. 参考示例中的Cypher语法和模式\n"
    "3. 只返回Cypher语句，不要返回其他解释性文字\n"
    "4. 如果意图不明确或无法生成有效的Cypher，返回空字符串\n"
)

# 批量生成cypher的提示词
BATCH_CYPHER_GENERATION_SYSTEM_PROMPT = (
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


class LLM():
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.language = "Chinese"
        self.field = "neo4j cypher query generation"
        self.conn = Neo4jConnection(
            uri=Neo4jConfig.uri,
            user=Neo4jConfig.user,
            password=Neo4jConfig.password
        )
        self.intent_parser = Neo4jIntentParser() if Neo4jIntentParser else None
        self.es_search_engine = QASearchEngine()

    async def parse_intent_only_with_stream(self, user_query: str, history_msgs: List[Dict[str, str]],
                                            stream_callback: Optional[callable] = None) -> Optional[List[Dict]]:
        """
        只生成意图（不生成cypher），支持流式输出
        """
        if not self.intent_parser:
            return None

        try:
            prompt = (
                f"{INTENT_ONLY_SYSTEM_PROMPT}\n\n"
                f"[用户问题]\n{user_query}\n\n"
            )
            # 流式调用LLM
            raw = ""
            llm_client_intent = LLMClient()
            async for chunk in llm_client_intent.async_stream_chat(
                    prompt=prompt,
                    model=self.intent_parser.model_name,
                    max_tokens=8000,
                    temperature=0,
                    system_prompt=INTENT_ONLY_SYSTEM_PROMPT,
            ):
                raw += chunk
                if stream_callback:
                    await stream_callback(chunk)

            # 解析JSON结果
            intent_list = JsonExtractor().extract(raw)
            if not intent_list:
                raise ValueError("LLM未返回意图列表")

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
            print(f"[意图识别] 流式解析失败: {e}")
            return None

    async def match_examples_from_es(self, intent_item: str, top_k: int = 1) -> List[Dict]:
        """
        从ES中匹配示例
        """
        try:
            results = self.es_search_engine.vector_similarity_search(intent_item, top_k=top_k, min_score=0.0)
            examples = []
            for result in results.get('results', []):
                answer = result.get('answer', '')
                answer = answer.strip().replace(' ', '')
                examples.append({
                    'question': result.get('question', ''),
                    'answer': answer,
                    'score': result.get('score', 0.0)
                })
            return examples
        except Exception as e:
            print(f"[ES匹配] 匹配失败: {e}")
            return []

    async def generate_cyphers_batch_with_stream(self, intent_with_examples: List[Dict], 
                                                  user_query: str,
                                                  stream_callback: Optional[callable] = None) -> List[Dict]:
        """
        批量生成cypher，支持流式输出并实时返回结果
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

            # 构建详细的节点信息（包含属性）
            nodes_info = []
            for node_type, node_info in self.intent_parser.expert_expander.nodes.items():
                properties = node_info.get("properties", [])
                description = node_info.get("description", "")
                properties_str = ", ".join(properties) if properties else "无"
                nodes_info.append(f"  - {node_type}: {description}\n    属性: [{properties_str}]")

            # 构建详细的关系信息
            relationships_info = []
            for rel_type, rel_info in self.intent_parser.expert_expander.relationships.items():
                from_node = rel_info.get("from", "")
                to_node = rel_info.get("to", "")
                description = rel_info.get("description", "")
                relationships_info.append(f"  - {rel_type}: {description}\n    起始节点: {from_node} -> 目标节点: {to_node}")

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
            llm_client_cypher = LLMClient()
            async for chunk in llm_client_cypher.async_stream_chat(
                    prompt=prompt,
                    model=model_name,
                    max_tokens=8000,
                    temperature=0.0,
                    system_prompt=BATCH_CYPHER_GENERATION_SYSTEM_PROMPT,
            ):
                raw += chunk
                if stream_callback:
                    await stream_callback(chunk)
            print("批量Cypher生成", raw)
            # 解析JSON结果
            intent_cypher_list = JsonExtractor().extract(raw)
            if not intent_cypher_list:
                print(f"[批量Cypher生成] 未解析到结果，原始输出: {raw[:500]}")
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
                            # 清理cypher（去除可能的markdown代码块标记）
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
                    print(f"[Cypher生成] 意图: {intent_item}")
                    print(f"[Cypher生成] Cypher: {cypher}")

            return result
        except Exception as e:
            print(f"[批量Cypher生成] 生成失败: {e}")
            return []

    async def generate_answer_async(self, content, history_msgs=None):
        """
        新流程：
        1. 生成n个意图
        2. n个意图去ES匹配n个示例
        3. 将n个示例调用大模型，重新校验生成cypher
        4. 执行查询
        5. 生成摘要
        """
        if history_msgs is None:
            history_msgs = []

        # ①. 意图识别阶段 - 只生成意图，不生成cypher
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
                intent_result = await self.parse_intent_only_with_stream(
                    content, history_msgs, stream_callback=intent_callback
                )
            finally:
                intent_done.set()
                await intent_queue.put(None)

        # 启动意图解析任务
        parser_task = asyncio.create_task(intent_parser_task())

        # 输出思考过程开始标记
        think_start_data = {
            "content": "<think>\n",
            "msg_type": 1
        }
        yield f"data:{json.dumps(think_start_data, ensure_ascii=False)}\n\n".encode("utf-8")

        # 实时输出意图识别过程
        while True:
            try:
                chunk = await asyncio.wait_for(intent_queue.get(), timeout=0.1)
                if chunk is None:
                    break
                think_data = {
                    "content": chunk,
                    "msg_type": 1
                }
                yield f"data:{json.dumps(think_data, ensure_ascii=False)}\n\n".encode("utf-8")
            except asyncio.TimeoutError:
                if intent_done.is_set():
                    try:
                        chunk = intent_queue.get_nowait()
                        if chunk is None:
                            break
                        think_data = {
                            "content": chunk,
                            "msg_type": 1
                        }
                        yield f"data:{json.dumps(think_data, ensure_ascii=False)}\n\n".encode("utf-8")
                    except asyncio.QueueEmpty:
                        break
                continue

        # 输出思考过程结束标记
        # think_end_data = {
        #     "content": "\n</think>\n",
        #     "msg_type": 1
        # }
        # yield f"data:{json.dumps(think_end_data, ensure_ascii=False)}\n\n".encode("utf-8")

        # 等待意图解析完成
        await parser_task
        print(f"intent_result={intent_result}")

        if not intent_result or not isinstance(intent_result, list):
            print("[错误] 未获取到有效的意图列表")
            return

        # 2. 对每个意图，从ES匹配示例
        intent_with_examples = []
        for intent_item_dict in intent_result:
            intent_item = intent_item_dict.get("intent_item", "")
            if not intent_item:
                continue

            examples = await self.match_examples_from_es(intent_item, top_k=1)
            intent_with_examples.append({
                "intent_item": intent_item,
                "examples": examples
            })
            print(f"[意图] {intent_item}")
            print(f"[ES匹配] {examples}")

        # 3. 基于意图和示例批量生成cypher（流式输出）
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
                intent_with_cypher_result = await self.generate_cyphers_batch_with_stream(
                    intent_with_examples, content, stream_callback=cypher_stream_callback
                )
            finally:
                cypher_done.set()
                await cypher_queue.put(None)

        # 启动批量Cypher生成任务
        cypher_task = asyncio.create_task(cypher_generation_task())

        # 输出Cypher生成思考过程开始标记
        # cypher_think_start_data = {
        #     "content": "\n<think>\n开始生成Cypher查询语句...\n",
        #     "msg_type": 1
        # }
        # yield f"data:{json.dumps(cypher_think_start_data, ensure_ascii=False)}\n\n".encode("utf-8")

        # 实时输出Cypher生成过程
        while True:
            try:
                chunk = await asyncio.wait_for(cypher_queue.get(), timeout=0.1)
                if chunk is None:
                    break
                cypher_think_data = {
                    "content": chunk,
                    "msg_type": 1
                }
                yield f"data:{json.dumps(cypher_think_data, ensure_ascii=False)}\n\n".encode("utf-8")
            except asyncio.TimeoutError:
                if cypher_done.is_set():
                    try:
                        chunk = cypher_queue.get_nowait()
                        if chunk is None:
                            break
                        cypher_think_data = {
                            "content": chunk,
                            "msg_type": 1
                        }
                        yield f"data:{json.dumps(cypher_think_data, ensure_ascii=False)}\n\n".encode("utf-8")
                    except asyncio.QueueEmpty:
                        break
                continue

        # 输出Cypher生成思考过程结束标记
        cypher_think_end_data = {
            "content": "\nCypher生成完成。\n</think>\n",
            "msg_type": 1
        }
        yield f"data:{json.dumps(cypher_think_end_data, ensure_ascii=False)}\n\n".encode("utf-8")

        # 等待批量Cypher生成完成
        await cypher_task
        intent_with_cypher = intent_with_cypher_result

        # 4. 执行cypher查询
        prompt_result = []
        knowledge_result = []
        for item in intent_with_cypher:
            cypher = item.get("cypher", "")
            if not cypher:
                continue

            try:
                cypher_result = self.conn.query(cypher)
                item["intent_result"] = cypher_result
                prompt_result.append(item)
                knowledge_result += cypher_result
                print(f"[查询执行] 成功，返回 {len(cypher_result)} 条结果")
            except Exception as e:
                print(f"[查询执行] 失败: {e}")
                item["intent_result"] = []
                prompt_result.append(item)

        # 5. 生成摘要
        messages2 = [{
            "role": "system",
            "content": "请关闭思考模式，直接使用业务专员查到的结果对你的领导的问题作出回答，业务专员的结果不需要进行筛选，也不需要逐条分析，微小的错误请忽略，名称不统一也请忽略，回答的方式是先生成100个字的总结摘要，然后再进行详细回答。请参考以下模板回答。\n以下是根据涉密网业务图谱查询到的结果作出的回答："
        }]

        content_with_prompt = f"以下是业务专员查到的结果：\n{prompt_result}"
        messages2.append({"role": "user", "content": content_with_prompt})

        content_with_query = f"以下是你的领导的问题，他是一个简单的人，你的思考过程和输出都会被他看见，千万不要重复思考或者重复输出，回答请关闭思考模式：\n{content}"
        messages2.append({"role": "user", "content": content_with_query})

        # 输出数据开始标记
        data_start_data = {
            "content": "<data>\n",
            "msg_type": 2
        }
        yield f"data:{json.dumps(data_start_data, ensure_ascii=False)}\n\n".encode("utf-8")

        llm_client_summary = LLMClient()
        response2 = llm_client_summary.client.chat.completions.create(
            model=model_name,
            messages=messages2,
            stream=True,
            temperature=0.0,
            max_tokens=8000
        )

        for resp in response2:
            if not resp.choices:
                continue
            if not resp.choices[0].delta.content:
                resp.choices[0].delta.content = ""

            ans = resp.choices[0].delta.content
            if resp.choices[0].finish_reason == "length":
                ans = LENGTH_NOTIFICATION_CN

            data_content = {
                "content": ans,
                "msg_type": 2
            }
            yield f"data:{json.dumps(data_content, ensure_ascii=False)}\n\n".encode("utf-8")

        # 输出数据结束标记
        data_end_data = {
            "content": "\n</data>",
            "msg_type": 2
        }
        yield f"data:{json.dumps(data_end_data, ensure_ascii=False)}\n\n".encode("utf-8")

        # 6. 知识匹配和输出（基于意图cypher查询结果）
        if knowledge_result:
            # 输出知识开始标记
            knowledge_start_data = {
                "content": "\n<knowledge>\n",
                "msg_type": 3
            }
            yield f"data:{json.dumps(knowledge_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
            
            # 输出知识内容
            knowledge_dict = {"title": "网络业务知识图谱", "table_list": knowledge_result}
            knowledge_content = json.dumps(knowledge_dict, ensure_ascii=False, indent=2)
            knowledge_content_data = {
                "content": knowledge_content,
                "msg_type": 3
            }
            yield f"data:{json.dumps(knowledge_content_data, ensure_ascii=False)}\n\n".encode("utf-8")
            
            # 输出知识结束标记
            knowledge_end_data = {
                "content": "\n</knowledge>",
                "msg_type": 3
            }
            yield f"data:{json.dumps(knowledge_end_data, ensure_ascii=False)}\n\n".encode("utf-8")