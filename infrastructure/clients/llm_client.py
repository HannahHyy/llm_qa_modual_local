"""
LLM客户端

提供LLM API调用的封装
"""

from typing import Optional, AsyncGenerator, List, Dict, Any
from openai import OpenAI, AsyncOpenAI
from core.config import LLMSettings
from core.exceptions import LLMClientError
from core.logging import logger
from core.retry import retry_sync, retry_async


class LlmConfig:
    """LLM配置类（兼容old版本）"""
    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.base_url = base_url
        self.key = api_key
        self.model_name = model_name


class LLMClient:
    """
    LLM客户端

    提供同步/异步、流式/非流式的LLM调用
    """

    def __init__(self, settings: LLMSettings):
        """
        初始化LLM客户端

        Args:
            settings: LLM配置
        """
        self.settings = settings
        self.base_url = settings.base_url
        self.api_key = settings.api_key
        self.model_name = settings.model_name

        # 初始化同步客户端
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=float(settings.timeout),
            max_retries=settings.max_retries,
        )

        # 初始化异步客户端
        self.async_client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=float(settings.timeout),
            max_retries=settings.max_retries,
        )

        logger.info(f"LLM客户端初始化成功: {self.base_url}, model={self.model_name}")

    @retry_sync(max_attempts=3, delay=1.0, backoff=2.0)
    def sync_nonstream_chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 40000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        同步非流式对话

        Args:
            prompt: 用户输入
            model: 模型名称（可选，默认使用配置中的模型）
            max_tokens: 最大token数
            temperature: 温度参数
            system_prompt: 系统提示词

        Returns:
            str: LLM响应内容
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=model or self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"LLM同步非流式调用错误: {str(e)}")
            raise LLMClientError(f"LLM调用失败: {str(e)}")

    def sync_stream_chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 40000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ):
        """
        同步流式对话

        Args:
            prompt: 用户输入
            model: 模型名称（可选，默认使用配置中的模型）
            max_tokens: 最大token数
            temperature: 温度参数
            system_prompt: 系统提示词

        Yields:
            str: LLM响应内容片段
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=model or self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as e:
            logger.error(f"LLM同步流式调用错误: {str(e)}")
            raise LLMClientError(f"LLM流式调用失败: {str(e)}")

    @retry_async(max_attempts=3, delay=1.0, backoff=2.0)
    async def async_nonstream_chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 40000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        异步非流式对话

        Args:
            prompt: 用户输入
            model: 模型名称（可选，默认使用配置中的模型）
            max_tokens: 最大token数
            temperature: 温度参数
            system_prompt: 系统提示词

        Returns:
            str: LLM响应内容
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await self.async_client.chat.completions.create(
                model=model or self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"LLM异步非流式调用错误: {str(e)}")
            raise LLMClientError(f"LLM调用失败: {str(e)}")

    async def async_stream_chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 40000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        异步流式对话

        Args:
            prompt: 用户输入
            model: 模型名称（可选，默认使用配置中的模型）
            max_tokens: 最大token数
            temperature: 温度参数
            system_prompt: 系统提示词

        Yields:
            str: LLM响应内容片段
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await self.async_client.chat.completions.create(
                model=model or self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as e:
            logger.error(f"LLM异步流式调用错误: {str(e)}")
            raise LLMClientError(f"LLM流式调用失败: {str(e)}")

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        异步流式对话(兼容StreamingService接口)

        Args:
            messages: 消息列表,格式: [{"role": "user", "content": "..."}]
            model: 模型名称
            max_tokens: 最大token数
            temperature: 温度参数

        Yields:
            Dict: 包含delta的响应,格式: {"delta": {"content": "..."}}
        """
        try:
            response = await self.async_client.chat.completions.create(
                model=model or self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    # 返回兼容的格式
                    yield {"delta": {"content": content}}

        except Exception as e:
            logger.error(f"LLM流式对话错误: {str(e)}")
            raise LLMClientError(f"LLM流式对话失败: {str(e)}")


__all__ = ["LLMClient", "LlmConfig"]
