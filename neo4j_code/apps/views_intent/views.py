# -*-coding: UTF-8 -*-
"""
    Author: haoxiaolin
    CreateTime: 2025/10/14 10:33
    Description: 整合了意图识别功能的LLM服务器
"""
import uuid
import json
import asyncio
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from fastapi import Request, APIRouter
from langchain_core.documents import Document
import os
from typing import List, Dict, Optional
from fastapi.responses import StreamingResponse

from documents.cypher_example import cypher_example
from db.neo_conn import Neo4jConnection
from settings.config import Neo4jConfig, EmbeddingConfig, LlmConfig
from apps.views_intent.neo4j_intent_parser import Neo4jIntentParser, Neo4jIntentParseContext
# 使用统一的LLMClient
import sys
import os

model_name = LlmConfig.model_name

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from LLM_Server.llm_client import LLMClient

LENGTH_NOTIFICATION_CN = "······\n由于模型支持的上下文长度的原因，回答被截断了"

os.environ["TOKENIZERS_PARALLELISM"] = "false"

router = APIRouter()


from langchain.embeddings.base import Embeddings
import requests
import json
from typing import List


class RemoteEmbeddings(Embeddings):
    """远程 embedding 服务客户端"""

    def __init__(self, server_ip: str, port: str, timeout: int = 30):
        self.server_ip = server_ip
        self.port = port
        self.url = f"http://{server_ip}:{port}/embed"
        self.health_url = f"http://{server_ip}:{port}/health"
        self.timeout = timeout

        # 检查服务健康状态
        self._check_service_health()

    def _check_service_health(self):
        """检查远程服务健康状态"""
        try:
            # 绕过代理访问本地服务
            proxies = {'http': None, 'https': None}
            response = requests.get(self.health_url, timeout=5, proxies=proxies)
            if response.status_code == 200:
                print(f"✅ 远程 embedding 服务连接正常 ({self.server_ip}:{self.port})")
            else:
                print(f"⚠️ 远程 embedding 服务响应异常，状态码: {response.status_code}")
        except Exception as e:
            print(f"❌ 远程 embedding 服务连接失败: {e}")
            raise ConnectionError(f"无法连接到远程 embedding 服务: {e}")

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """从远程服务获取 embeddings"""
        try:
            headers = {"Content-Type": "application/json"}
            # 绕过代理访问本地服务
            proxies = {'http': None, 'https': None}
            response = requests.post(
                self.url,
                json=texts,
                headers=headers,
                timeout=self.timeout,
                proxies=proxies
            )

            if response.status_code == 200:
                result = response.json()
                embeddings = result.get("embeddings", [])
                if not embeddings:
                    raise ValueError("远程服务返回空的 embeddings")
                return embeddings
            else:
                raise Exception(f"远程服务请求失败，状态码: {response.status_code}, 错误: {response.text}")

        except requests.exceptions.Timeout:
            raise Exception(f"远程服务请求超时 (>{self.timeout}s)")
        except Exception as e:
            raise Exception(f"获取 embeddings 失败: {e}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表"""
        return self._get_embeddings(texts)

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询文本"""
        embeddings = self._get_embeddings([text])
        return embeddings[0] if embeddings else []


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

        # 初始化Neo4j意图识别器
        # elf.intent_parser = Neo4jIntentParser(vector_stores) if Neo4jIntentParser else None
        self.intent_parser = Neo4jIntentParser() if Neo4jIntentParser else None

    async def parse_intent_with_stream(self, user_query: str, history_msgs: List[Dict[str, str]],
                                     stream_callback: Optional[callable] = None) -> Optional[Dict]:
        """
        流式意图识别，支持实时输出思考过程
        """
        if not self.intent_parser:
            return None

        try:
            context = Neo4jIntentParseContext(
                user_query=user_query,
                history_msgs=history_msgs
            )

            # 使用流式解析，传入回调函数
            # print(f"130 {stream_callback}")
            result = await self.intent_parser.parse(context, stream=True, stream_callback=stream_callback)
            # print(result)
            print(f"[意图识别] 流式解析成功: {len(result)}个意图")
            return result

        except Exception as e:
            print(f"[意图识别] 流式解析失败: {e}")
            return None

    async def generate_answer_async(self, content, history_msgs=None):
        """
        异步版本的generate_answer方法，集成了意图识别功能
        """
        # 如果没有提供历史消息，使用空列表
        if history_msgs is None:
            history_msgs = []

        # 1. 意图识别阶段 - 使用流式输出
        intent_result = None
        intent_queue = asyncio.Queue()
        intent_done = asyncio.Event()
        full_stream_content: List[str] = []

        async def intent_callback(chunk: str):
            """意图识别流式回调"""
            if chunk:
                await intent_queue.put(chunk)
                full_stream_content.append(chunk)  # 收集思考过程

        async def intent_parser_task():
            """意图解析任务"""
            nonlocal intent_result
            try:
                intent_result = await self.parse_intent_with_stream(
                    content, history_msgs, stream_callback=intent_callback
                )
            finally:
                intent_done.set()
                await intent_queue.put(None)  # 结束标记

        # 启动意图解析任务
        parser_task = asyncio.create_task(intent_parser_task())
        
        # 输出思考过程开始标记
        think_start_data = {
            "content": "<think>\n",
            "msg_type": 1
        }
        yield f"data:{json.dumps(think_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
        full_stream_content.append("<think>\n")

        # 实时输出意图识别过程
        while True:
            try:
                chunk = await asyncio.wait_for(intent_queue.get(), timeout=0.1)
                
                # 新增
                #if chunk == "</think>":
                #    continue 
                
                if chunk is None:  # 解析完成
                    break
                #print(chunk)
                # 输出思考过程内容
                think_data = {
                    "content": chunk,
                    "msg_type": 1
                }
                yield f"data:{json.dumps(think_data, ensure_ascii=False)}\n\n".encode("utf-8")
                full_stream_content.append(chunk)  # 收集完整内容（包含思考过程）

            except asyncio.TimeoutError:
                if intent_done.is_set():
                    # 检查队列是否还有数据
                    try:
                        chunk = intent_queue.get_nowait()
                        if chunk is None:
                            break
                        think_data = {
                            "content": chunk,
                            "msg_type": 1
                        }
                        yield f"data:{json.dumps(think_data, ensure_ascii=False)}\n\n".encode("utf-8")
                        full_stream_content.append(chunk)
                    except asyncio.QueueEmpty:
                        break
                continue

        # 输出思考过程结束标记
        think_end_data = {
            "content": "\n</think>\n",
            "msg_type": 1
        }
        yield f"data:{json.dumps(think_end_data, ensure_ascii=False)}\n\n".encode("utf-8")
        full_stream_content.append("\n</think>\n")

        # 等待意图解析完成
        await parser_task
        print(f"intent_result={intent_result}")

        # 2. 使用意图识别结果中的Cypher并执行
        #final_cypher = ""
        #if intent_result and isinstance(intent_result, dict):
        #    final_cypher = str(intent_result.get('cypher') or "").strip()
        #    # 如果没有提供cypher，尝试从首个intent的提示中兜底
        #    if not final_cypher:
        #        intents = intent_result.get('intents', [])
        #        if intents:
        #            intent = intents[0]
        #            final_cypher = str(intent.get('cypher_hint') or "").strip()
        #try:
        #    result = self.conn.query(final_cypher)
        #except:
        #    result = []
        #print(final_cypher, result)

        result = []
        # 2. 使用意图识别结果中的Cypher并执行
        try:
            if intent_result and isinstance(intent_result, list):
                for intent_result_item in intent_result:
                    intent_cypher = intent_result_item.get("cypher")
                    cypher_result = self.conn.query(intent_cypher)
                    intent_result_item["intent_result"] = cypher_result
                    result.append(cypher_result)
        except Exception as e:
            print(e)

        # 准备系统消息和用户消息
        messages2 = [{"role": "system", "content": f"请关闭思考模式，直接使用业务专员查到的结果对你的领导的问题作出回答，业务专员的结果不需要进行筛选，也不需要逐条分析，微小的错误请忽略，名称不统一也请忽略，回答的方式是先生成100个字的总结摘要，然后再进行详细回答。请参考以下模板回答。\n以下是根据涉密网业务图谱查询到的结果作出的回答： "}]

        # 添加查询结果提示
        content_with_prompt = f"""
        以下是业务专员查到的结果：
        {result}
        """
        messages2.append({"role": "user", "content": content_with_prompt})

        # 添加用户查询
        content_with_query = f"""
        以下是你的领导的问题，他是一个简单的人，你的思考过程和输出都会被他看见，千万不要重复思考或者重复输出，回答请关闭思考模式：
        {content}
        """
        messages2.append({"role": "user", "content": content_with_query })
        
        # 输出数据开始标记
        data_start_data = {
            "content": "<data>\n",
            "msg_type": 2
        }
        yield f"data:{json.dumps(data_start_data, ensure_ascii=False)}\n\n".encode("utf-8")

        llm_connect = LLMClient()
        response2 = llm_connect.client.chat.completions.create(
            model=model_name,
            messages=messages2,
            stream=True, temperature=0.0)

        for resp in response2:
            if not resp.choices:
                continue
            if not resp.choices[0].delta.content:
                resp.choices[0].delta.content = ""

            ans = resp.choices[0].delta.content
            if resp.choices[0].finish_reason == "length":
                ans = LENGTH_NOTIFICATION_CN
            
            # 输出数据内容
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

        # 3. 知识匹配和输出（基于意图识别结果）
        if intent_result and isinstance(intent_result, dict):
            # 输出知识开始标记
            knowledge_start_data = {
                "content": "\n<knowledge>\n",
                "msg_type": 3
            }
            yield f"data:{json.dumps(knowledge_start_data, ensure_ascii=False)}\n\n".encode("utf-8")
            
            # 输出知识内容
            knowledge_dict = {"title": "网络业务知识图谱", "table_list": result}
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


class LoadVector():
    def __init__(self, path=None):
        vector_list = ["documentation", "ddl", "query"]
        model_kwargs = {'device': 'cpu'}
        # # 使用正确的相对路径指向本地模型
        # import os
        # # 从当前文件位置计算到项目根目录的路径
        # current_file_dir = os.path.dirname(os.path.abspath(__file__))  # apps/views_intent/
        # project_root = os.path.dirname(os.path.dirname(current_file_dir))  # neo4j_code/
        #
        # # 使用绝对路径指向chroma_db目录
        # if path is None:
        #     path = os.path.join(project_root, "chroma_db")
        #
        # embedding_model_name = os.path.join(project_root, "embedding-models", "paraphrase-multilingual-MiniLM-L12-v2")
        # embedding_model = HuggingFaceEmbeddings(model_name=embedding_model_name, model_kwargs=model_kwargs)

        # 使用远程 embedding
        embedding_model = RemoteEmbeddings(
            server_ip=EmbeddingConfig.SERVER_IP,  # 改为你的远程服务器IP
            port=EmbeddingConfig.BGE_PORT,
            timeout=EmbeddingConfig.REQUEST_TIMEOUT
        )

        self.vector_stores = dict()
        for i in vector_list:
            vector_store = Chroma(collection_name=i,
                                  embedding_function=embedding_model,
                                  persist_directory=path,
                                  collection_metadata={"hnsw:space": "cosine"})
            self.vector_stores[i] = vector_store

    def load_vector(self):
        for cypher_item in cypher_example:
            cypher_question = cypher_item.get("question")
            cypher_query = cypher_item.get("cypher_query")
            source = cypher_question + "\n" + cypher_query
            ids = str(uuid.uuid3(namespace=uuid.NAMESPACE_DNS, name=cypher_question)) + '-sql'
            document = Document(
                page_content=cypher_question,
                metadata={"source": source})
            self.vector_stores["query"].add_documents(documents=[document], ids=[ids])


#vector_obj = LoadVector()
#vector_obj.load_vector()
#vector_stores = vector_obj.vector_stores


@router.post("/chat/stream")
async def stream_response(request: Request):
    """流式响应API端点"""
    # 从请求中获取JSON数据
    data = await request.json()
    question = data.get("question", "")
    history_msgs = data.get("history_msgs", [])

    if not question:
        return {"error": "问题不能为空"}

    # 返回流式响应
    return StreamingResponse(LLM(vector_stores).generate_answer_async(question, history_msgs), media_type="text/event-stream")
    # return EventSourceResponse(LLM(vector_stores).generate_answer_async(question, history_msgs), media_type="text/event-stream")


# 添加一个简单的HTML页面用于测试
@router.get("/")
async def get_root():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Enhanced LLM Streaming Demo with Neo4j Intent Recognition</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            #response { white-space: pre-wrap; border: 1px solid #ddd; padding: 10px; min-height: 200px; margin-top: 10px; }
            button, input { margin: 5px 0; padding: 8px; }
            input { width: 100%; }
            .intent-section { background-color: #f0f0f0; padding: 10px; margin: 10px 0; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>Enhanced LLM Streaming Demo with Neo4j Intent Recognition</h1>
        <input type="text" id="question" placeholder="输入您的问题" />
        <button onclick="sendRequest()">发送</button>
        <div id="response"></div>

        <script>
            async function sendRequest() {
                const question = document.getElementById('question').value;
                const responseDiv = document.getElementById('response');

                if (!question) {
                    alert('请输入问题');
                    return;
                }

                responseDiv.textContent = "等待响应...";

                try {
                    const response = await fetch('/chat/stream', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ 
                            question: question,
                            history_msgs: [] // 可以在这里添加历史消息
                        }),
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    responseDiv.textContent = "";

                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;

                        const chunk = decoder.decode(value);
                        responseDiv.textContent += chunk;
                    }
                } catch (error) {
                    console.error('Error:', error);
                    responseDiv.textContent = `错误: ${error.message}`;
                }
            }
        </script>
    </body>
    </html>
    """
    return StreamingResponse(iter([html_content]), media_type="text/html")


# # 如果作为独立应用运行
# if __name__ == "__main__":
#     import uvicorn
#     print("program already started")
#     vector_obj = LoadVector()
#     vector_obj.load_vector()
#     vector_stores = vector_obj.vector_stores
#     print("向量:", vector_stores)
#     uvicorn.run(app, host="0.0.0.0", port=8001)
