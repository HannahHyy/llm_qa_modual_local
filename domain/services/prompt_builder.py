"""
Prompt构建器

负责构建发送给LLM的提示词
"""

from typing import List, Optional, Dict, Any
from domain.models import Message, Knowledge


class PromptBuilder:
    """
    Prompt构建器

    根据对话历史、检索到的知识和系统设置构建提示词
    """

    def __init__(
        self,
        system_prompt: Optional[str] = None,
        max_history_length: int = 10,
        max_knowledge_items: int = 5
    ):
        """
        初始化Prompt构建器

        Args:
            system_prompt: 系统提示词
            max_history_length: 最大历史消息数量
            max_knowledge_items: 最大知识条目数量
        """
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.max_history_length = max_history_length
        self.max_knowledge_items = max_knowledge_items

    def build_prompt(
        self,
        current_query: str,
        history: Optional[List[Message]] = None,
        knowledge: Optional[List[Knowledge]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """
        构建完整的提示词

        Args:
            current_query: 当前用户查询
            history: 对话历史
            knowledge: 检索到的知识
            metadata: 额外元数据

        Returns:
            List[Dict]: OpenAI格式的消息列表
        """
        messages = []

        # 1. 系统提示词
        system_content = self._build_system_message(knowledge, metadata)
        messages.append({
            "role": "system",
            "content": system_content
        })

        # 2. 历史对话
        if history:
            history_messages = self._build_history_messages(history)
            messages.extend(history_messages)

        # 3. 当前查询
        messages.append({
            "role": "user",
            "content": current_query
        })

        return messages

    def _build_system_message(
        self,
        knowledge: Optional[List[Knowledge]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建系统消息

        Args:
            knowledge: 检索到的知识
            metadata: 元数据

        Returns:
            str: 系统消息内容
        """
        parts = [self.system_prompt]

        # 添加检索到的知识
        if knowledge:
            knowledge_section = self._format_knowledge(knowledge)
            parts.append(knowledge_section)

        # 添加额外指令
        if metadata:
            extra_instructions = metadata.get("extra_instructions")
            if extra_instructions:
                parts.append(f"\n额外指令：\n{extra_instructions}")

        return "\n\n".join(parts)

    def _build_history_messages(self, history: List[Message]) -> List[Dict[str, str]]:
        """
        构建历史消息

        Args:
            history: 历史消息列表

        Returns:
            List[Dict]: 格式化的历史消息
        """
        # 限制历史长度
        recent_history = history[-self.max_history_length:] if len(history) > self.max_history_length else history

        messages = []
        for msg in recent_history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        return messages

    def _format_knowledge(self, knowledge: List[Knowledge]) -> str:
        """
        格式化知识为文本

        Args:
            knowledge: 知识列表

        Returns:
            str: 格式化的知识文本
        """
        if not knowledge:
            return ""

        # 限制知识数量
        limited_knowledge = knowledge[:self.max_knowledge_items]

        lines = ["参考知识："]
        for i, k in enumerate(limited_knowledge, 1):
            title = k.title or "知识条目"
            source_indicator = "📚" if k.is_from_es() else "🔗"
            lines.append(f"\n{i}. {source_indicator} {title}")
            lines.append(f"   {k.content}")
            if k.score > 0:
                lines.append(f"   (相关性: {k.score:.2f})")

        return "\n".join(lines)

    def _default_system_prompt(self) -> str:
        """
        默认系统提示词

        Returns:
            str: 默认提示词
        """
        return """你是一个专业的AI助手，致力于为用户提供准确、有用的回答。

请遵循以下原则：
1. 基于提供的参考知识进行回答，确保准确性
2. 如果参考知识不足以回答问题，请诚实地说明
3. 保持回答简洁明了，避免冗余
4. 使用友好、专业的语气
5. 如果涉及专业术语，请适当解释

回答时请：
- 优先使用参考知识中的信息
- 如需引用，请标注来源
- 对不确定的内容，明确表达不确定性"""

    def build_streaming_prompt(
        self,
        current_query: str,
        history: Optional[List[Message]] = None,
        knowledge: Optional[List[Knowledge]] = None
    ) -> List[Dict[str, str]]:
        """
        构建流式输出的提示词

        Args:
            current_query: 当前查询
            history: 历史消息
            knowledge: 检索知识

        Returns:
            List[Dict]: 消息列表
        """
        # 流式输出使用相同的提示词构建逻辑
        return self.build_prompt(current_query, history, knowledge)

    def update_system_prompt(self, new_prompt: str) -> None:
        """
        更新系统提示词

        Args:
            new_prompt: 新的系统提示词
        """
        self.system_prompt = new_prompt

    def estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        估算token数量（简单估算）

        Args:
            messages: 消息列表

        Returns:
            int: 估算的token数
        """
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        # 简单估算：中文约1.5字符/token，英文约4字符/token
        # 这里使用保守估计：2字符/token
        return total_chars // 2
