"""
智能意图路由器
基于大模型的意图路由器，判断用户查询应该使用哪个知识库来回答
输入: user_query + history_msgs
输出: 路由决策结果 ("neo4j", "es", "hybrid", "none")

支持的路由类型：
1. neo4j：包含具体的业务数据，为业务图谱库
2. es：包含网络安全相关的法规、标准、规范、条款等权威文档，为法规知识库  
3. hybrid：需要同时使用业务数据和法规标准进行对比分析
4. none：不需要检索任何知识库，可以直接回答的问题（如问候语、闲聊等）
"""

import os
import json
import asyncio
import re
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field, ValidationError
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*Event loop is closed.*")

# 导入LLM客户端
try:
    from LLM_Server.llm_client import LLMClient
    import LLM_Server.llm_client as llm_client_module
except ModuleNotFoundError:
    import sys
    ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)
    from LLM_Server.llm_client import LLMClient
    import LLM_Server.llm_client as llm_client_module

router_llm_client = LLMClient()
LLM_MODEL_NAME = llm_client_module.LlmConfig.model_name

# 路由决策数据模型
class RouteDecision(BaseModel):
    decision: Literal["neo4j", "es", "hybrid", "none"] = Field(..., description="路由决策结果")
    reasoning: str = Field(..., description="决策理由")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="决策置信度")

# 路由上下文
class RouteContext(BaseModel):
    user_query: str = Field(..., description="用户查询")
    history_msgs: List[Dict[str, str]] = Field(default_factory=list, description="历史对话消息")

def filter_content(content: str) -> str:
    """过滤掉标签内容，只保留核心回答"""
    if not content:
        return ""
    
    # 移除<think>标签及其内容
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    
    # 提取<data>标签内的内容
    data_match = re.search(r'<data>(.*?)</data>', content, re.DOTALL)
    if data_match:
        content = data_match.group(1).strip()
    
    return content.strip()

class IntentRouter:
    """
    基于LLM的智能意图路由器
    
    主要功能：
    - 分析用户查询的特点和意图
    - 判断应该使用哪个知识库来回答
    - 支持流式输出思考过程
    - 带重试机制和输出验证
    
    路由类型：
    - neo4j: 业务图谱库查询
    - es: 法规标准知识库查询  
    - hybrid: 混合查询（业务+法规）
    - none: 无需检索，直接回答
    """
    
    def __init__(self):
        # LLM客户端初始化
        self.model_name = LLM_MODEL_NAME
        self.llm_client = router_llm_client
    
    def _build_router_prompt(self, ctx: RouteContext) -> str:
        """构建路由判断的prompt"""
        # 构建历史对话上下文
        history_context = ""
        for msg in ctx.history_msgs[-2:]:  # 只取最近2轮对话
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                history_context += f"用户: {content}\n"
            elif role == "assistant":
                # 过滤掉标签内容，只保留<data>内容
                filtered_content = filter_content(content)
                history_context += f"助手: {filtered_content}\n"
        
        router_prompt = f"""
你是一个智能意图路由器，需要判断用户的查询应该要参考哪个知识库来回答。

知识库数据源说明：
1. neo4j：包含具体的业务数据，为业务图谱库，如某个单位的网络架构、系统配置、安全产品部署等具体信息
2. es：包含网络安全相关的法规、标准、规范、条款等权威文档，为法规知识库
3. hybrid：需要同时使用业务数据和法规标准进行对比分析
4. none：不需要检索任何知识库，可以直接回答的问题（如问候语、闲聊、一般性问题等）

历史对话上下文：
{history_context}

当前用户查询：{ctx.user_query}

请分析这个查询的特点，判断应该使用哪个数据源：
- 如果查询涉及具体的单位、网络、系统、设备等业务实体信息，选择"neo4j"
- 如果查询涉及法规条款、标准要求、规范内容等，选择"es"  
- 如果查询需要将具体业务情况与法规要求进行对比分析，选择"hybrid"
- 如果查询是问候语、闲聊、一般性问题或不涉及专业知识的简单问题，选择"none"

请按照以下JSON格式输出你的决策：
{{
  "decision": "neo4j/es/hybrid/none",
  "reasoning": "详细的决策理由",
  "confidence": 0.9
}}
"""
        return router_prompt
    
    def _safe_json_loads(self, text: str) -> Dict:
        """安全的JSON解析"""
        try:
            # 提取JSON部分
            json_match = re.search(r'\{[^}]*"decision"[^}]*\}', text)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            else:
                raise ValueError("未找到有效的JSON格式响应")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {e}")
    
    async def route(self, ctx: RouteContext, stream: bool = False, 
                   stream_callback: Optional[callable] = None, max_retries: int = 3) -> str:
        """
        执行意图路由判断
        
        Args:
            ctx: 路由上下文
            stream: 是否使用流式输出
            stream_callback: 流式输出回调函数
            max_retries: 最大重试次数
            
        Returns:
            str: 路由决策结果 ("neo4j", "es", "hybrid", "none")
        """
        try:
            prompt = self._build_router_prompt(ctx)
            
            # 带重试机制的LLM路由判断
            for attempt in range(max_retries):
                try:
                    print(f"[意图路由] 第{attempt+1}次尝试开始...")
                    response_parts = []
                    
                    if stream and stream_callback:
                        # 流式调用
                        stream_gen = self.llm_client.async_stream_chat(
                            prompt=prompt,
                            model=self.model_name,
                            max_tokens=500,
                            temperature=0.1,
                            system_prompt="你是一个专业的意图路由分析器，请仔细分析用户查询的特点并按照JSON格式输出路由判断。",
                        )
                        
                        async for chunk in stream_gen:
                            if chunk:
                                response_parts.append(chunk)
                                # 不直接输出原始chunk，等待解析完成后输出reasoning
                    else:
                        # 非流式调用
                        full_response = await self.llm_client.async_nonstream_chat(
                            prompt=prompt,
                            model=self.model_name,
                            max_tokens=500,
                            temperature=0.1,
                            system_prompt="你是一个专业的意图路由分析器，请仔细分析用户查询的特点并按照JSON格式输出路由判断。",
                        )
                        response_parts = [full_response]
                    
                    full_response = "".join(response_parts)
                    
                    # 尝试解析JSON格式的响应
                    try:
                        route_data = self._safe_json_loads(full_response)
                        
                        # 验证响应格式
                        route_decision = RouteDecision(**route_data)
                        decision = route_decision.decision
                        
                        print(f"[意图路由] 决策: {decision}, 理由: {route_decision.reasoning}, 置信度: {route_decision.confidence}")
                        
                        # 输出reasoning到流式回调
                        if stream_callback and route_decision.reasoning:
                            if callable(stream_callback):
                                if asyncio.iscoroutinefunction(stream_callback):
                                    await stream_callback(f"\n{route_decision.reasoning}\n")
                                else:
                                    stream_callback(f"\n{route_decision.reasoning}\n")
                        
                        return decision
                        
                    except (json.JSONDecodeError, ValidationError, ValueError) as e:
                        print(f"[意图路由] 第{attempt+1}次尝试解析失败: {e}")
                        if attempt == max_retries - 1:
                            # 最后一次尝试失败，使用传统方式解析
                            if "neo4j" in full_response.lower():
                                return "neo4j"
                            elif "hybrid" in full_response.lower():
                                return "hybrid"
                            elif "none" in full_response.lower():
                                return "none"
                            else:
                                return "es"
                        continue
                        
                except Exception as e:
                    print(f"[意图路由] 第{attempt+1}次调用失败: {e}")
                    if attempt == max_retries - 1:
                        return "es"  # 默认使用ES
                    await asyncio.sleep(0.5)  # 重试前等待
            
            return "es"  # 兜底返回ES
                
        except Exception as e:
            print(f"[意图路由] 错误: {e}")
            return "es"  # 默认使用ES

# 便捷函数
async def llm_based_intent_router(user_query: str, history_msgs: List[Dict[str, str]], 
                                 stream_callback: Optional[callable] = None, max_retries: int = 3) -> str:
    """
    基于大模型的意图路由器便捷函数
    
    Args:
        user_query: 用户查询
        history_msgs: 历史对话消息
        stream_callback: 流式输出回调函数
        max_retries: 最大重试次数
        
    Returns:
        str: 路由决策结果 ("neo4j", "es", "hybrid", "none")
    """
    router = IntentRouter()
    ctx = RouteContext(user_query=user_query, history_msgs=history_msgs)
    return await router.route(ctx, stream=bool(stream_callback), stream_callback=stream_callback, max_retries=max_retries)

# 测试案例
async def test_intent_router():
    """测试意图路由器的各种场景"""
    
    test_cases = [
        {
            "query": "你好",
            "history": [],
            "expected": "none"
        },
        {
            "query": "今天天气怎么样？",
            "history": [],
            "expected": "none"
        },
        {
            "query": "等保三级的身份鉴别要求是什么？",
            "history": [],
            "expected": "es"
        },
        {
            "query": "A单位的集成商是谁？",
            "history": [],
            "expected": "neo4j"
        },
        {
            "query": "A单位的防火墙配置是什么样的？是否符合等保三级要求？",
            "history": [],
            "expected": "hybrid"
        },
        {
            "query": "查询办公网的安全产品部署情况",
            "history": [],
            "expected": "neo4j"
        },
        {
            "query": "等保三级要求中关于访问控制的具体要求",
            "history": [],
            "expected": "es"
        }
    ]
    
    router = IntentRouter()
    
    print("开始测试意图路由器...")
    print("=" * 60)
    
    for i, case in enumerate(test_cases, 1):
        print(f"查询: {case['query']}")
        print(f"期望结果: {case['expected']}")
        
        try:
            ctx = RouteContext(user_query=case['query'], history_msgs=case['history'])
            result = await router.route(ctx)
            
            print(f"实际结果: {result}")
            
            if result == case['expected']:
                print("✅ 测试通过")
            else:
                print("❌ 测试失败")
                
        except Exception as e:
            print(f"❌ 测试异常: {e}")
        
        print("-" * 40)
    
    print("\n测试完成!")

# 主函数
if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_intent_router())