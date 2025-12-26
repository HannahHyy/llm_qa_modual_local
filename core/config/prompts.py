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

    # ==================== LLM路由器提示词 ====================

    llm_router_prompt: str = Field(
        default="""你是一个智能意图路由器，需要判断用户的查询应该要参考哪个知识库来回答。

知识库数据源说明：
1. neo4j：包含具体的业务数据，为业务图谱库，如某个单位的网络架构、系统配置、安全产品部署等具体信息
2. es：包含网络安全相关的法规、标准、规范、条款等权威文档，为法规知识库
3. hybrid：需要同时使用业务数据和法规标准进行对比分析
4. none：不需要检索任何知识库，可以直接回答的问题（如问候语、闲聊、一般性问题等）

历史对话上下文：
{history_context}

当前用户查询：{user_query}

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
}}""",
        description="LLM路由器提示词"
    )

    llm_router_system_prompt: str = Field(
        default="你是一个专业的意图路由分析器，请仔细分析用户查询的特点并按照JSON格式输出路由判断。",
        description="LLM路由器系统提示词"
    )

    # ==================== Neo4j意图解析提示词 ====================

    neo4j_intent_only_prompt: str = Field(
        default="""你是Neo4j图数据库的'智能意图解析器'。
请根据输入的上下文，完成Neo4j查询的意图拆解，并对每个意图进行详细分析。
你需要进行流式输出，其中分析思路需要展示到前端页面。
请先详细说明你的分析思路，分析思路请完全以流利的中文自然语言进行描述，然后输出最终严格的JSON结果。
最后的JSON结果，必须严格按照以下格式输出标识符（不要有任何变化）：
'3.以下是json格式的解析结果：'
[{{intent_item: string}}, {{intent_item: string}}, ...]
说明:
- intent_item: Neo4j查询的意图拆解的意图描述
- 最多给出3个意图；若用户问题非常明确，则仅输出1个意图，能不拆分的尽量不拆分。

在流式输出时，请按以下格式组织你的回答：
1. 首先分析用户问题可以拆分成哪几个意图
2. 以流利的中文输出每个意图的具体含义
3. 最后输出完整的JSON结果。（在JSON之前必须输出标识符）。""",
        description="Neo4j意图解析提示词"
    )

    neo4j_batch_cypher_prompt: str = Field(
        default="""你是Neo4j图数据库的Cypher查询生成专家。
请根据多个用户意图和提供的示例，为每个意图生成一条完整可执行的Cypher查询语句。
要求：
1. 为每个意图生成对应的Cypher语句，必须可以直接执行
2. 参考每个意图对应的示例中的Cypher语法和模式
3. 输出格式必须为严格的JSON格式，标识符为：'3.以下是json格式的解析结果：'
4. JSON格式：[{{"intent_item": "意图描述", "cypher": "Cypher语句"}}, ...]
5. 如果某个意图不明确或无法生成有效的Cypher，该意图的cypher字段返回空字符串
6. 请先简要说明分析思路，然后输出JSON结果（在JSON之前必须输出标识符）""",
        description="Neo4j批量Cypher生成提示词"
    )

    neo4j_summary_prompt: str = Field(
        default="""请关闭思考模式，直接使用业务专员查到的结果对你的领导的问题作出回答，业务专员的结果不需要进行筛选，也不需要逐条分析，微小的错误请忽略，名称不统一也请忽略，回答的方式是先生成100个字的总结摘要，然后再进行详细回答。请参考以下模板回答。
以下是根据涉密网业务图谱查询到的结果作出的回答：""",
        description="Neo4j结果摘要生成提示词"
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

    # ==================== LLM路由器LLM ====================

    router_model: str = Field(
        default="qwen-plus",
        description="LLM路由器使用的模型"
    )

    router_temperature: float = Field(
        default=0.1,
        description="LLM路由器温度（低温度确保判断准确）"
    )

    router_max_tokens: int = Field(
        default=500,
        description="LLM路由器最大token数"
    )

    # ==================== Neo4j相关LLM ====================

    neo4j_intent_model: str = Field(
        default="qwen-plus",
        description="Neo4j意图解析使用的模型"
    )

    neo4j_intent_temperature: float = Field(
        default=0.0,
        description="Neo4j意图解析温度"
    )

    neo4j_intent_max_tokens: int = Field(
        default=8000,
        description="Neo4j意图解析最大token数"
    )

    neo4j_cypher_model: str = Field(
        default="qwen-plus",
        description="Neo4j Cypher生成使用的模型"
    )

    neo4j_cypher_temperature: float = Field(
        default=0.0,
        description="Neo4j Cypher生成温度"
    )

    neo4j_cypher_max_tokens: int = Field(
        default=8000,
        description="Neo4j Cypher生成最大token数"
    )

    neo4j_summary_model: str = Field(
        default="qwen-plus",
        description="Neo4j摘要生成使用的模型"
    )

    neo4j_summary_temperature: float = Field(
        default=0.0,
        description="Neo4j摘要生成温度"
    )

    neo4j_summary_max_tokens: int = Field(
        default=8000,
        description="Neo4j摘要生成最大token数"
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


def get_llm_router_prompt(user_query: str, history_context: str) -> str:
    """获取LLM路由器提示词"""
    template = get_prompt_settings().llm_router_prompt
    return template.format(user_query=user_query, history_context=history_context)


def get_llm_router_system_prompt() -> str:
    """获取LLM路由器系统提示词"""
    return get_prompt_settings().llm_router_system_prompt


def get_neo4j_intent_only_prompt() -> str:
    """获取Neo4j意图解析提示词"""
    return get_prompt_settings().neo4j_intent_only_prompt


def get_neo4j_batch_cypher_prompt() -> str:
    """获取Neo4j批量Cypher生成提示词"""
    return get_prompt_settings().neo4j_batch_cypher_prompt


def get_neo4j_summary_prompt() -> str:
    """获取Neo4j摘要生成提示词"""
    return get_prompt_settings().neo4j_summary_prompt


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
    "get_llm_router_prompt",
    "get_llm_router_system_prompt",
    "get_neo4j_intent_only_prompt",
    "get_neo4j_batch_cypher_prompt",
    "get_neo4j_summary_prompt",
]
