"""
LLM客户端

提供LLM API调用的封装（保留原有llm_client.py的实现）。
注意：这是一个简单的导入包装器，实际实现使用原有的llm_client.py
"""

import sys
import os

# 导入原有的LLMClient
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from llm_client import LLMClient as OriginalLLMClient, LlmConfig

from core.logging import get_logger

logger = get_logger("LLMClient")


# 直接使用原有的LLMClient实现
LLMClient = OriginalLLMClient

__all__ = ["LLMClient", "LlmConfig"]
