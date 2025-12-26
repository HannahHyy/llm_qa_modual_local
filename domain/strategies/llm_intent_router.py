"""
LLM-based意图路由策略

使用大模型判断用户查询应该使用哪个知识库:
- neo4j: 业务图谱库（具体业务数据）
- es: 法规标准库（权威文档）
- hybrid: 混合查询（业务+法规对比）
- none: 无需检索（问候语、闲聊）
"""

import re
import json
import asyncio
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field, ValidationError

from infrastructure.clients.llm_client import LLMClient
from core.logging import logger
from core.config import (
    get_llm_router_prompt,
    get_llm_router_system_prompt,
    get_llm_model_settings
)


class RouteDecision(BaseModel):
    """路由决策模型"""
    decision: Literal["neo4j", "es", "hybrid", "none"] = Field(..., description="路由决策")
    reasoning: str = Field(..., description="决策理由")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="置信度")


class LLMIntentRouter:
    """
    基于LLM的智能意图路由器

    职责：
    - 分析用户查询的特点和意图
    - 判断应该使用哪个知识库
    - 支持流式输出思考过程
    """

    def __init__(self, llm_client: LLMClient):
        """
        初始化路由器

        Args:
            llm_client: LLM客户端实例
        """
        self.llm_client = llm_client
        self.model_settings = get_llm_model_settings()

    def _filter_content(self, content: str) -> str:
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

    def _build_router_prompt(self, user_query: str, history_msgs: List[Dict[str, str]]) -> str:
        """构建路由判断的prompt（使用配置化提示词）"""
        # 构建历史对话上下文
        history_context = ""
        for msg in history_msgs[-2:]:  # 只取最近2轮对话
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                history_context += f"用户: {content}\n"
            elif role == "assistant":
                filtered_content = self._filter_content(content)
                history_context += f"助手: {filtered_content}\n"

        if not history_context:
            history_context = "无历史对话"

        # 使用配置化的提示词模板
        return get_llm_router_prompt(user_query=user_query, history_context=history_context)

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
        user_query: str,
        history_msgs: List[Dict[str, str]],
        stream_callback: Optional[callable] = None,
        max_retries: int = 3
    ) -> str:
        """
        执行意图路由判断

        Args:
            user_query: 用户查询
            history_msgs: 历史对话消息
            stream_callback: 流式输出回调函数
            max_retries: 最大重试次数

        Returns:
            str: 路由决策结果 ("neo4j", "es", "hybrid", "none")
        """
        try:
            prompt = self._build_router_prompt(user_query, history_msgs)

            # 带重试机制的LLM路由判断
            for attempt in range(max_retries):
                try:
                    logger.info(f"[LLM路由] 第{attempt+1}次尝试...")
                    response_parts = []

                    if stream_callback:
                        # 流式调用（使用配置化参数）
                        async for chunk in self.llm_client.async_stream_chat(
                            prompt=prompt,
                            model=self.model_settings.router_model,
                            max_tokens=self.model_settings.router_max_tokens,
                            temperature=self.model_settings.router_temperature,
                            system_prompt=get_llm_router_system_prompt(),
                        ):
                            if chunk:
                                response_parts.append(chunk)
                    else:
                        # 非流式调用（使用配置化参数）
                        full_response = await self.llm_client.async_nonstream_chat(
                            prompt=prompt,
                            model=self.model_settings.router_model,
                            max_tokens=self.model_settings.router_max_tokens,
                            temperature=self.model_settings.router_temperature,
                            system_prompt=get_llm_router_system_prompt(),
                        )
                        response_parts = [full_response]

                    full_response = "".join(response_parts)

                    # 尝试解析JSON格式的响应
                    try:
                        route_data = self._safe_json_loads(full_response)
                        route_decision = RouteDecision(**route_data)
                        decision = route_decision.decision

                        logger.info(f"[LLM路由] 决策: {decision}, 理由: {route_decision.reasoning}")

                        # 输出reasoning到流式回调
                        if stream_callback and route_decision.reasoning:
                            if asyncio.iscoroutinefunction(stream_callback):
                                await stream_callback(f"\n{route_decision.reasoning}\n")
                            else:
                                stream_callback(f"\n{route_decision.reasoning}\n")

                        return decision

                    except (json.JSONDecodeError, ValidationError, ValueError) as e:
                        logger.warning(f"[LLM路由] 第{attempt+1}次解析失败: {e}")
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
                    logger.error(f"[LLM路由] 第{attempt+1}次调用失败: {e}")
                    if attempt == max_retries - 1:
                        return "es"  # 默认使用ES
                    await asyncio.sleep(0.5)

            return "es"

        except Exception as e:
            logger.error(f"[LLM路由] 错误: {e}")
            return "es"
