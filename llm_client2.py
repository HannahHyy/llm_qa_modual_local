import logging
import asyncio
from typing import Optional, AsyncGenerator
from openai import OpenAI, AsyncOpenAI

"""
同步非流式/同步流式/异步非流式/异步流式：
- sync_nonstream_chat
- sync_stream_chat
- async_nonstream_chat
- async_stream_chat
"""

class LLMClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

        # 初始化同步客户端
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0,
            max_retries=1,
        )
        # 初始化异步客户端
        self.async_client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0,
            max_retries=3,
        )
    def sync_nonstream_chat(self, prompt: str, model: str, max_tokens: int = 40000, temperature: float = 0.7, system_prompt: Optional[str] = None) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.getLogger(__name__).error(f"未知错误: {e}")
            raise

    def sync_stream_chat(self, prompt: str, model: str, max_tokens: int = 40000, temperature: float = 0.7, system_prompt: Optional[str] = None):
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.client.chat.completions.create(
                model=model,
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
            logging.getLogger(__name__).error(f"流式调用错误: {e}")
            raise

    async def async_nonstream_chat(self, prompt: str, model: str, max_tokens: int = 40000, temperature: float = 0.7, system_prompt: Optional[str] = None) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.getLogger(__name__).error(f"未知错误: {e}")
            raise

    async def async_stream_chat(self, prompt: str, model: str, max_tokens: int = 40000, temperature: float = 0.7, system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = await self.async_client.chat.completions.create(
                model=model,
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
            logging.getLogger(__name__).error(f"未知错误: {e}")
            raise