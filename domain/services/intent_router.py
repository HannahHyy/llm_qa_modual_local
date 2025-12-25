"""
智能意图路由器 (基于old版本重构)

基于大模型的意图路由器,判断用户查询应该使用哪个知识库来回答
输入: user_query + history_msgs
输出: 路由决策结果 ("neo4j", "es", "hybrid", "none")

支持的路由类型:
1. neo4j: 包含具体的业务数据,为业务图谱库
2. es: 包含网络安全相关的法规、标准、规范、条款等权威文档,为法规知识库
3. hybrid: 需要同时使用业务数据和法规标准进行对比分析
4. none: 不需要检索任何知识库,可以直接回答的问题(如问候语、闲聊等)
"""

import json
import re
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field
from core.logging import logger


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
    """过滤掉标签内容,只保留核心回答"""
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

    主要功能:
    - 分析用户查询的特点和意图
    - 判断应该使用哪个知识库来回答
    - 支持流式输出思考过程
    - 带重试机制和输出验证

    路由类型:
    - neo4j: 业务图谱库查询
    - es: 法规标准知识库查询
    - hybrid: 混合查询(业务+法规)
    - none: 无需检索,直接回答
    """

    def __init__(self, llm_client):
        """
        初始化路由器

        Args:
            llm_client: LLM客户端
        """
        self.llm_client = llm_client

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
                # 过滤掉标签内容,只保留<data>内容
                filtered_content = filter_content(content)
                history_context += f"助手: {filtered_content}\n"

        router_prompt = f"""
你是一个智能意图路由器,需要判断用户的查询应该要参考哪个知识库来回答。

知识库数据源说明:
1. neo4j: 包含具体的业务数据,为业务图谱库,如某个单位的网络架构、系统配置、安全产品部署等具体信息
2. es: 包含网络安全相关的法规、标准、规范、条款等权威文档,为法规知识库
3. hybrid: 需要同时使用业务数据和法规标准进行对比分析
4. none: 不需要检索任何知识库,可以直接回答的问题(如问候语、闲聊、一般性问题等)

历史对话上下文:
{history_context}

当前用户查询: {ctx.user_query}

请分析这个查询的特点,判断应该使用哪个数据源:
- 如果查询涉及具体的单位、网络、系统、设备等业务实体信息,选择"neo4j"
- 如果查询涉及法规条款、标准要求、规范内容等,选择"es"
- 如果查询需要将具体业务情况与法规要求进行对比分析,或者同时包含业务实体和法规标准两部分内容,选择"hybrid"
- 如果查询是问候语、闲聊、一般性问题或不涉及专业知识的简单问题,选择"none"

请按照以下JSON格式输出你的决策:
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

    async def route(
        self,
        ctx: RouteContext,
        stream: bool = False,
        stream_callback: Optional[callable] = None,
        max_retries: int = 3
    ) -> str:
        """
        执行意图路由判断

        Args:
            ctx: 路由上下文
            stream: 是否使用流式输出
            stream_callback: 流式输出回调函数
            max_retries: 最大重试次数

        Returns:
            str: 路由决策 ("neo4j", "es", "hybrid", "none")
        """
        router_prompt = self._build_router_prompt(ctx)

        for attempt in range(max_retries):
            try:
                if stream and stream_callback:
                    # 流式输出模式
                    llm_response = ""
                    async for chunk in self.llm_client.async_stream_chat(
                        prompt=router_prompt,
                        temperature=0.1,
                        max_tokens=500
                    ):
                        if chunk:
                            llm_response += chunk
                            await stream_callback(chunk)
                else:
                    # 非流式模式
                    llm_response = await self.llm_client.async_nonstream_chat(
                        prompt=router_prompt,
                        temperature=0.1,
                        max_tokens=500
                    )

                # 解析JSON响应
                decision_dict = self._safe_json_loads(llm_response)
                decision = RouteDecision(**decision_dict)

                logger.info(
                    f"意图路由成功: decision={decision.decision}, "
                    f"confidence={decision.confidence:.2f}, reasoning={decision.reasoning}"
                )

                return decision.decision

            except Exception as e:
                logger.warning(f"意图路由失败 (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"意图路由最终失败,使用默认路由: hybrid")
                    return "hybrid"  # 失败时默认使用混合查询
                continue

        return "hybrid"

    async def route_with_context(
        self,
        user_query: str,
        history_msgs: Optional[List[Dict[str, str]]] = None,
        stream_callback: Optional[callable] = None
    ) -> str:
        """
        便捷方法: 直接传入查询和历史进行路由

        Args:
            user_query: 用户查询
            history_msgs: 历史消息
            stream_callback: 流式输出回调

        Returns:
            str: 路由决策
        """
        ctx = RouteContext(
            user_query=user_query,
            history_msgs=history_msgs or []
        )

        return await self.route(
            ctx=ctx,
            stream=bool(stream_callback),
            stream_callback=stream_callback
        )
