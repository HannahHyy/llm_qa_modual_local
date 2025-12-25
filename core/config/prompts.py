"""
提示词配置管理

集中管理所有LLM提示词，支持从环境变量或配置文件加载
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class PromptSettings(BaseSettings):
    """提示词配置"""

    # ==================== 系统提示词 ====================

    system_prompt: str = Field(
        default="""你是一个专业的AI助手，致力于为用户提供准确、有用的回答。

请遵循以下原则：
1. 基于提供的参考知识进行回答，确保准确性
2. 如果参考知识不足以回答问题，请诚实地说明
3. 保持回答简洁明了，避免冗余
4. 使用友好、专业的语气
5. 如果涉及专业术语，请适当解释

回答时请：
- 优先使用参考知识中的信息
- 如需引用，请标注来源
- 对不确定的内容，明确表达不确定性""",
        description="系统级提示词"
    )

    # ==================== 意图识别提示词 ====================

    intent_recognition_prompt: str = Field(
        default="""你是一个意图识别专家。请分析用户的查询，判断其意图类型。

可能的意图类型：
1. es_query - 通用知识查询（法规、标准、概念等）
2. neo4j_query - 图数据库查询（关系、路径、层级、网络拓扑等）
3. hybrid_query - 混合查询

用户查询: {query}

请判断意图类型，并给出置信度（0-1）。
只输出JSON格式: {{"intent_type": "xxx", "confidence": 0.xx}}""",
        description="意图识别提示词"
    )

    # ==================== Neo4j Cypher生成提示词 ====================

    neo4j_cypher_generation_prompt: str = Field(
        default="""你是一个Neo4j Cypher查询生成专家。

数据库包含以下节点类型:
- Netname: 网络节点 (属性: name, netSecretLevel, networkType)
- Unit: 单位节点 (属性: name, unitType)
- SYSTEM: 系统节点 (属性: name, systemSecretLevel)
- Safeproduct: 安全产品 (属性: name, safeProductCount)
- Totalintegrations: 集成商 (属性: name, totalIntegrationLevel)

关系类型:
- UNIT_NET, OPERATIONUNIT_NET, OVERUNIT_NET
- SOFTWAREUNIT_SYSTEM, SYSTEM_NET, SECURITY_NET

参考以下示例:
{examples}

用户问题: {query}

请生成一个Cypher查询来回答这个问题。
要求:
1. 只输出Cypher查询,不要有任何解释
2. Cypher必须是可执行的
3. 参考示例的格式和模式
4. 确保返回有意义的结果

Cypher查询:""",
        description="Neo4j Cypher生成提示词"
    )

    # ==================== 知识检索增强提示词 ====================

    knowledge_enhanced_prompt_template: str = Field(
        default="""{system_prompt}

以下是历史对话，请基于上下文回答用户的新问题。

--- 历史对话开始 ---
{history}
--- 历史对话结束 ---

--- 相关知识 ---
{knowledge}
--- 知识结束 ---

用户: {query}

助手:""",
        description="知识增强提示词模板"
    )

    # ==================== 摘要生成提示词 ====================

    summary_generation_prompt: str = Field(
        default="""请为以下对话生成简洁的摘要（不超过50字）：

{conversation}

摘要:""",
        description="对话摘要生成提示词"
    )

    # ==================== 知识匹配提示词 ====================

    knowledge_matching_prompt: str = Field(
        default="""请分析LLM的回答，找出其中引用的知识点，并与提供的知识库进行匹配。

LLM回答:
{llm_output}

知识库:
{knowledge_base}

请返回匹配的知识ID列表（JSON格式）。
格式: {{"matched_ids": ["id1", "id2", ...]}}""",
        description="知识匹配提示词"
    )

    class Config:
        env_prefix = "PROMPT_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略不认识的字段


class LLMModelSettings(BaseSettings):
    """LLM模型配置 - 不同场景使用不同的模型配置"""

    # ==================== 意图识别LLM ====================

    intent_recognition_model: str = Field(
        default="qwen-plus",
        description="意图识别使用的模型"
    )

    intent_recognition_temperature: float = Field(
        default=0.3,
        description="意图识别温度"
    )

    intent_recognition_max_tokens: int = Field(
        default=500,
        description="意图识别最大token数"
    )

    # ==================== Cypher生成LLM ====================

    cypher_generation_model: str = Field(
        default="qwen-plus",
        description="Cypher生成使用的模型"
    )

    cypher_generation_temperature: float = Field(
        default=0.3,
        description="Cypher生成温度（低温度确保准确性）"
    )

    cypher_generation_max_tokens: int = Field(
        default=500,
        description="Cypher生成最大token数"
    )

    # ==================== 对话生成LLM ====================

    chat_generation_model: str = Field(
        default="qwen-plus",
        description="对话生成使用的模型"
    )

    chat_generation_temperature: float = Field(
        default=0.7,
        description="对话生成温度"
    )

    chat_generation_max_tokens: int = Field(
        default=4000,
        description="对话生成最大token数"
    )

    # ==================== 摘要生成LLM ====================

    summary_generation_model: str = Field(
        default="qwen-plus",
        description="摘要生成使用的模型"
    )

    summary_generation_temperature: float = Field(
        default=0.5,
        description="摘要生成温度"
    )

    summary_generation_max_tokens: int = Field(
        default=200,
        description="摘要生成最大token数"
    )

    # ==================== 知识匹配LLM ====================

    knowledge_matching_model: str = Field(
        default="qwen-plus",
        description="知识匹配使用的模型"
    )

    knowledge_matching_temperature: float = Field(
        default=0.3,
        description="知识匹配温度"
    )

    knowledge_matching_max_tokens: int = Field(
        default=1000,
        description="知识匹配最大token数"
    )

    class Config:
        env_prefix = "LLM_MODEL_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略不认识的字段


# 全局配置实例
_prompt_settings: Optional[PromptSettings] = None
_llm_model_settings: Optional[LLMModelSettings] = None


def get_prompt_settings() -> PromptSettings:
    """获取提示词配置（单例）"""
    global _prompt_settings
    if _prompt_settings is None:
        _prompt_settings = PromptSettings()
    return _prompt_settings


def get_llm_model_settings() -> LLMModelSettings:
    """获取LLM模型配置（单例）"""
    global _llm_model_settings
    if _llm_model_settings is None:
        _llm_model_settings = LLMModelSettings()
    return _llm_model_settings


# 便捷函数

def get_system_prompt() -> str:
    """获取系统提示词"""
    return get_prompt_settings().system_prompt


def get_intent_recognition_prompt(query: str) -> str:
    """获取意图识别提示词"""
    template = get_prompt_settings().intent_recognition_prompt
    return template.format(query=query)


def get_cypher_generation_prompt(query: str, examples: str) -> str:
    """获取Cypher生成提示词"""
    template = get_prompt_settings().neo4j_cypher_generation_prompt
    return template.format(query=query, examples=examples)


def get_knowledge_enhanced_prompt(
    system_prompt: str,
    history: str,
    knowledge: str,
    query: str
) -> str:
    """获取知识增强提示词"""
    template = get_prompt_settings().knowledge_enhanced_prompt_template
    return template.format(
        system_prompt=system_prompt,
        history=history,
        knowledge=knowledge,
        query=query
    )


def get_summary_prompt(conversation: str) -> str:
    """获取摘要生成提示词"""
    template = get_prompt_settings().summary_generation_prompt
    return template.format(conversation=conversation)


def get_knowledge_matching_prompt(llm_output: str, knowledge_base: str) -> str:
    """获取知识匹配提示词"""
    template = get_prompt_settings().knowledge_matching_prompt
    return template.format(llm_output=llm_output, knowledge_base=knowledge_base)


__all__ = [
    "PromptSettings",
    "LLMModelSettings",
    "get_prompt_settings",
    "get_llm_model_settings",
    "get_system_prompt",
    "get_intent_recognition_prompt",
    "get_cypher_generation_prompt",
    "get_knowledge_enhanced_prompt",
    "get_summary_prompt",
    "get_knowledge_matching_prompt",
]
