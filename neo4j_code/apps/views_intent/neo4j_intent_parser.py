# -*-coding: UTF-8 -*-
"""
Neo4j图数据库意图识别器
基于intent_parser.py重写，专门针对Neo4j图数据库的节点和关系进行意图识别
"""
import os
import json
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field
# 使用统一的LLMClient
import sys
import os
# 添加项目根目录到路径
from neo4j_code.documents.es_embedding import QASearchEngine

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from LLM_Server.llm_client import LLMClient
from settings.config import LlmConfig
from apps.views_intent.json_extractor import JsonExtractor

# LLM 配置
DEFAULT_LLM_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# DEFAULT_LLM_MODEL_NAME = "QwQ-32B"
DEFAULT_LLM_MODEL_NAME = "deepseek-v3"
DEFAULT_LLM_API_KEY = "sk-f9f3209599454a49ba6fb4f36c3c0434" 
DEFAULT_MAX_INTENT_COUNT = 4

# Neo4j图数据库节点和关系定义
NEO4J_NODES = {
    "Netname": {
        "properties": ["name", "netSecretLevel", "networkType"],
        "description": "网络名称节点，包含网络标识、安全等级、网络类型等信息",
        "aliases": ["网络", "网络名称", "网络标识", "net", "network"]
    },
    "Totalintegrations": {
        "properties": ["name", "totalIntegrationLevel", "validatedateend"],
        "description": "集成商/运维商，包含名称、集级、验证结束日期等信息",
        "aliases": ["集成单位", "integration", "total_integration"]
    },
    "SYSTEM": {
        "properties": ["name", "systemSecretLevel"],
        "description": "系统节点，包含系统名称、系统安全等级等信息",
        "aliases": ["应用系统", "system", "系统名称"]
    },
    "Unit": {
        "properties": ["name", "unitType"],
        "description": "单元节点，包含单元名称、单元类型等信息",
        "aliases": ["机关单位", "unit"]
    },
    "Safeproduct": {
        "properties": ["name", "safeProductCount"],
        "description": "安全产品节点，包含产品名称、产品数量",
        "aliases": ["安全产品", "产品", "安全设备", "safe_product", "security_product"]
    },
    "question": {
        "properties": ["questionContent"],
        "description": "问题内容",
        "aliases": ["question", "网络问题"]
    },
}

NEO4J_RELATIONSHIPS = {
    "UNIT_NET": {
        "from": "Unit",
        "to": "Netname",
        "description": "单元与网络的关联关系",
        "aliases": ["单元网络", "单元关联网络", "unit_network"]
    },
    "OPERATIONUNIT_NET": {
        "from": "Totalintegrations",
        "to": "Netname",
        "description": "操作单元与网络的关联关系",
        "aliases": ["操作单元网络", "操作关联网络", "operation_unit_network"]
    },
    "OVERUNIT_NET": {
        "from": "Totalintegrations",
        "to": "Netname",
        "description": "覆盖单元与网络的关联关系",
        "aliases": ["覆盖单元网络", "覆盖关联网络", "over_unit_network"]
    },
    "SOFTWAREUNIT_SYSTEM": {
        "from": "Totalintegrations",
        "to": "SYSTEM",
        "description": "软件单元与系统的关联关系",
        "aliases": ["软件单元系统", "软件关联系统", "software_unit_system"]
    },
    "SYSTEM_NET": {
        "from": "Netname",
        "to": "SYSTEM",
        "description": "系统与网络的关联关系",
        "aliases": ["系统网络", "系统关联网络", "system_network"]
    },
    "SECURITY_NET": {
        "from": "Netname",
        "to": "SafeProduct",
        "description": "安全产品与网络的关联关系",
        "aliases": ["安全网络", "安全关联网络", "security_network"]
    },
    "QUESTIONNET": {
        "from": "Question",
        "to": "Netname",
        "description": "网络和问题的关系",
        "aliases": ["网络中的问题", "QuestionNet"]
    }
}

# 查询类型定义
QUERY_TYPES = {
    "node_query": "节点查询 - 查询特定节点的属性和信息",
    "relationship_query": "关系查询 - 查询节点之间的关系",
    "path_query": "路径查询 - 查询节点间的路径",
    "aggregation_query": "聚合查询 - 统计和聚合数据",
    "filter_query": "过滤查询 - 基于条件过滤数据",
    "traversal_query": "遍历查询 - 遍历图结构"
}

# 安全等级关键词
SECURITY_LEVEL_KEYWORDS = {
#    "高": ["高", "高级", "high", "high_level"],
#    "中": ["中", "中级", "medium", "medium_level"],
#    "低": ["低", "低级", "low", "low_level"],
#    "内部": ["内部", "internal", "private"],
#    "公开": ["公开", "public", "open"]
}

# 网络类型关键词
NETWORK_TYPE_KEYWORDS = {
#    "内网": ["内网", "内部网络", "internal_network", "intranet"],
#    "外网": ["外网", "外部网络", "external_network", "internet"],
#    "混合": ["混合", "混合网络", "hybrid_network", "mixed_network"]
}


class Neo4jNodeInfo(BaseModel):
    """Neo4j节点信息"""
    node_type: str = Field(description="节点类型")
    properties: List[str] = Field(description="节点属性列表")
    description: str = Field(description="节点描述")
    confidence: float = Field(default=1.0, description="识别置信度")


class Neo4jRelationshipInfo(BaseModel):
    """Neo4j关系信息"""
    relationship_type: str = Field(description="关系类型")
    from_node: str = Field(description="起始节点类型")
    to_node: str = Field(description="目标节点类型")
    description: str = Field(description="关系描述")
    confidence: float = Field(default=1.0, description="识别置信度")


class Neo4jEntityInfo(BaseModel):
    """Neo4j实体信息"""
    nodes: List[str] = Field(default_factory=list, description="识别的节点类型")
    relationships: List[str] = Field(default_factory=list, description="识别的关系类型")
    properties: List[str] = Field(default_factory=list, description="识别的属性")
    security_levels: List[str] = Field(default_factory=list, description="识别的安全等级")
    network_types: List[str] = Field(default_factory=list, description="识别的网络类型")


class Neo4jIntent(BaseModel):
    """Neo4j意图数据结构"""
    rewritten_query: str = Field(..., description="改写后的Cypher查询友好问题")
    query_type: Literal[
        "node_query", "relationship_query", "path_query", 
        "aggregation_query", "filter_query", "traversal_query"
    ] = Field(..., description="查询类型")
    target_nodes: List[Neo4jNodeInfo] = Field(
        default_factory=list, description="目标节点类型"
    )
    target_relationships: List[Neo4jRelationshipInfo] = Field(
        default_factory=list, description="目标关系类型"
    )
    entities: Neo4jEntityInfo = Field(default_factory=Neo4jEntityInfo, description="识别的实体信息")
    cypher_hint: Optional[str] = Field(None, description="Cypher查询提示")
    reason: Optional[str] = Field(None, description="意图分析的原因说明")
    origin_query: str = Field(..., description="用户原始提问")
    history_msgs: List[Dict[str, str]] = Field(default_factory=list, description="历史对话消息列表")


class Neo4jIntentParseResult(BaseModel):
    """Neo4j意图解析结果容器"""
    intents: List[Neo4jIntent] = Field(default_factory=list)


class Neo4jIntentParseContext(BaseModel):
    """Neo4j意图解析上下文"""
    user_query: str  # 当前用户查询
    history_msgs: List[Dict[str, str]] = Field(default_factory=list, description="历史对话消息列表")


class Neo4jExpertExpander:
    """Neo4j专家扩展器 - 进行实体识别和同义词扩展"""
    
    def __init__(self):
        self.nodes = NEO4J_NODES
        self.relationships = NEO4J_RELATIONSHIPS
        self.security_levels = SECURITY_LEVEL_KEYWORDS
        self.network_types = NETWORK_TYPE_KEYWORDS

    def identify_nodes(self, text: str) -> List[str]:
        """识别用户query中提到的节点类型"""
        t = text.lower()
        found = []
        
        for node_type, info in self.nodes.items():
            # 检查节点类型名称
            if node_type.lower() in t:
                found.append(node_type)
                continue
            # 检查别名
            for alias in info.get("aliases", []):
                if alias.lower() in t:
                    found.append(node_type)
                    break
        
        return list(dict.fromkeys(found))  # 去重


    def identify_relationships(self, text: str) -> List[str]:
        """识别用户query中提到的关系类型"""
        t = text.lower()
        found = []
        
        for rel_type, info in self.relationships.items():
            # 检查关系类型名称
            if rel_type.lower() in t:
                found.append(rel_type)
                continue
            # 检查别名
            for alias in info.get("aliases", []):
                if alias.lower() in t:
                    found.append(rel_type)
                    break
        
        return list(dict.fromkeys(found))  # 去重

    def identify_security_levels(self, text: str) -> List[str]:
        """识别安全等级"""
        t = text.lower()
        found = []
        
        for level, keywords in self.security_levels.items():
            for keyword in keywords:
                if keyword.lower() in t:
                    found.append(level)
                    break
        
        return list(dict.fromkeys(found))

    def identify_network_types(self, text: str) -> List[str]:
        """识别网络类型"""
        t = text.lower()
        found = []
        
        for net_type, keywords in self.network_types.items():
            for keyword in keywords:
                if keyword.lower() in t:
                    found.append(net_type)
                    break
        
        return list(dict.fromkeys(found))

    def extract_entities(self, text: str, history_msgs=None) -> Neo4jEntityInfo:
        """提取Neo4j实体信息"""
        # 构建上下文文本
        full_text = text
        if history_msgs:
            recent_msgs = history_msgs[-2:]  # 最近2轮对话
            recent_content = []
            for msg in recent_msgs:
                if msg.get("role") == "user":
                    recent_content.append(msg.get("content", ""))
            if recent_content:
                full_text = " ".join(recent_content) + " " + text

        # 识别各类实体
        nodes = self.identify_nodes(full_text)
        relationships = self.identify_relationships(full_text)
        security_levels = self.identify_security_levels(full_text)
        network_types = self.identify_network_types(full_text)
        
        # 提取属性（从节点信息中提取）
        properties = []
        for node_type in nodes:
            if node_type in self.nodes:
                properties.extend(self.nodes[node_type]["properties"])

        return Neo4jEntityInfo(
            nodes=nodes,
            relationships=relationships,
            properties=properties,
            security_levels=security_levels,
            network_types=network_types
        )

    def build_expert_context(self, text: str) -> str:
        """构建专家上下文"""
        entities = self.extract_entities(text)
        lines = []
        
        if entities.nodes:
            lines.append(f"识别的节点类型: {', '.join(entities.nodes)}")
        if entities.relationships:
            lines.append(f"识别的关系类型: {', '.join(entities.relationships)}")
        if entities.security_levels:
            lines.append(f"识别的安全等级: {', '.join(entities.security_levels)}")
        if entities.network_types:
            lines.append(f"识别的网络类型: {', '.join(entities.network_types)}")
        if entities.properties:
            lines.append(f"相关属性: {', '.join(entities.properties[:5])}...")  # 只显示前5个属性
        
        return "\n".join(lines) if lines else "未识别到特定实体"


# Neo4j意图识别系统提示词
old_NEO4J_INTENT_SYSTEM_PROMPT = (
    "你是Neo4j业务图数据库的'智能意图解析器'。think的时候不要返回cypher语句\n"
    "请根据输入的上下文，完成Neo4j查询的意图拆解，并对每个意图进行详细分析。\n"
    "你需要进行流式输出，其中分析思路需要展示到前端页面。\n"
    "请先详细说明你的分析思路，分析思路请完全以流利的中文自然语言进行描述，然后输出最终严格的JSON结果。\n"
    "最后的JSON结果，必须严格按照以下格式输出标识符（不要有任何变化）：\n"
    "'3.以下是json格式的解析结果：'\n"
    "{\"intents\": [{\"rewritten_query\": string, \"query_type\": string, \"target_nodes\": [string...], \"target_relationships\": [string...], \"entities\": {\"nodes\":[string...], \"relationships\":[string...], \"properties\":[string...], \"security_levels\":[string...], \"network_types\":[string...]}, \"cypher_hint\": string, \"reason\": string},\n\"origin_query\": string, \"history_msgs\":[string...], \"cypher\": string}\n"
    "说明：\n"
    "- rewritten_query：将原始问题进行同义词扩展和语序优化，便于Cypher查询生成，如果原始问题中有你不了解的节点和关系信息，请删除。（尤其是法规标准查询，请删除这部分）\n"
    "- query_type：查询类型，从 {node_query, relationship_query, path_query, aggregation_query, filter_query, traversal_query} 中选择。\n"
    "  * node_query: 查询特定节点的属性和信息（如\"查询所有网络的基本信息\"）\n"
    "  * relationship_query: 查询节点之间的关系（如\"查询网络与系统的关联关系\"）\n"
    "  * path_query: 查询节点间的路径（如\"查找从网络到安全产品的路径\"）\n"
    "  * aggregation_query: 统计和聚合数据（如\"统计各安全等级的网络数量\"）\n"
    "  * filter_query: 基于条件过滤数据（如\"查询高安全等级的网络\"）\n"
    "  * traversal_query: 遍历图结构（如\"遍历所有相关的网络节点\"）\n"
    "- target_nodes：目标节点类型，从以下节点中选择：\n"
    f"  {list(NEO4J_NODES.keys())}\n"
    "- target_relationships：目标关系类型，从以下关系中选择：\n"
    f"  {list(NEO4J_RELATIONSHIPS.keys())}\n"
    "- entities：识别的实体信息，包含nodes, relationships, properties, security_levels, network_types\n"
    "- cypher_hint：Cypher查询提示，提供查询构建的建议\n"
    "- reason：意图分析的原因说明\n"
    "- origin_query：用户的原始提问\n"
    "- history_msgs：用户的历史上下文\n"
    "- cypher：基于用户问题生成的一条完整可执行Cypher查询语句\n"
    f"- 最多给出 {DEFAULT_MAX_INTENT_COUNT} 个意图；若用户问题非常明确，则仅输出 1 个意图，能不拆分的尽量不拆分。\n"
    "\n在流式输出时，请按以下格式组织你的回答：\n"
    "1. 首先分析用户问题可以拆分成哪几个意图\n"
    "2. 以流利的中文输出每个意图的具体含义，**特别要明确指出识别到的节点类型、关系类型及其识别依据**\n"
    "3. 最后输出完整的JSON结果。（在JSON之前必须输出标识符）。\n"
)

NEO4J_INTENT_SYSTEM_PROMPT = (
    "你是Neo4j图数据库的'智能意图解析器'。\n"
    "请根据输入的上下文，完成Neo4j查询的意图拆解，并对每个意图进行详细分析。\n"
    "你需要进行流式输出，其中分析思路需要展示到前端页面。\n"
    "请先详细说明你的分析思路，分析思路请完全以流利的中文自然语言进行描述，然后输出最终严格的JSON结果。\n"
    "最后的JSON结果，必须严格按照以下格式输出标识符（不要有任何变化）：\n"
    "'3.以下是json格式的解析结果：'\n"
    "[{intent_item: string, cypher: string}, {intent_item: string, cypher: string}, ...] \n"
    "说明:\n"
    "- intent_item: Neo4j查询的意图拆解的意图"
    "- cypher：基于用户问题生成的完整可执行Cypher查询语句\n "
    f"- 最多给出 {DEFAULT_MAX_INTENT_COUNT} 个意图；若用户问题非常明确，则仅输出 1 个意图，能不拆分的尽量不拆分。\n"
    "\n在流式输出时，请按以下格式组织你的回答：\n"
    "1. 首先分析用户问题可以拆分成哪几个意图\n"
    "2. 以流利的中文输出每个意图的具体含义，**特别要明确指出识别到的节点类型、关系类型及其识别依据**\n"
    "3. 最后输出完整的JSON结果。（在JSON之前必须输出标识符）。\n"
)


class Neo4jIntentParser:
    """
    基于LLM的Neo4j意图分析解析器，主要功能包括：
    - 节点识别：识别查询中涉及的Neo4j节点类型
    - 关系识别：识别查询中涉及的Neo4j关系类型
    - 实体提取：提取节点、关系、属性、安全等级、网络类型等关键实体
    - 查询重写：基于上下文和专家知识重写查询以提高Cypher生成效果
    - 查询策略：为每个意图选择最适合的查询类型
    
    异步流式处理：
    - 支持流式输出思考过程，提供实时反馈
    - 智能截断，避免向前端发送JSON结果
    
    输入格式：
    - user_query: 用户当前查询
    - history_msgs: 历史对话消息（用于上下文理解）
    
    输出格式：
    - 结构化JSON，包含意图列表、原始查询、历史消息等
    - 每个意图包含：重写查询、查询类型、目标节点、目标关系、实体信息、Cypher提示、分析原因
    
    注意事项：
    - 依赖LLM服务，需要配置正确的API密钥和端点
    - 流式输出需要提供回调函数处理实时数据
    - 支持历史对话上下文，但需控制历史消息数量以避免token超限
    """

    def __init__(self, vector_stores=None):
        # LLM客户端初始化
        self.model_name = DEFAULT_LLM_MODEL_NAME
        # self.llm_client = LLMClient()
        self.max_intent_count = DEFAULT_MAX_INTENT_COUNT
        # Neo4j专家扩展器
        self.expert_expander = Neo4jExpertExpander()
        # 向量存储
        self.vector_stores = vector_stores
        self.n_result = 1
        # 添加流式截断状态
        self._stream_stopped = False
        self._accumulated_content = ""

    def retrieve_related_documentation(self, content: str):
        """检索相关文档"""
        if not self.vector_stores:
            return ""

        prompt_list = []
        collections = list(self.vector_stores.keys())
        for i in collections:
            vector_store = self.vector_stores[i]
            related_list = vector_store.similarity_search(query=content, k=self.n_result)
            for i in related_list:
                print(f"i={i.metadata['source']}")
                prompt_list.append(i.metadata['source'])
        return self.integrate_prompt(prompt_list)

    def integrate_prompt(self, prompt_list: list[str]) -> str:
        """整合提示词"""
        prompt = ""
        for i in prompt_list:
            prompt += i + "\n\n"
        return prompt

    def identify_target_nodes(self, query: str) -> List[Neo4jNodeInfo]:
        """识别目标节点类型"""
        node_types = self.expert_expander.identify_nodes(query)
        identified = []
        
        for node_type in node_types:
            if node_type in NEO4J_NODES:
                info = NEO4J_NODES[node_type]
                identified.append(
                    Neo4jNodeInfo(
                        node_type=node_type,
                        properties=info["properties"],
                        description=info["description"],
                        confidence=1.0,
                    )
                )
        
        # 如果没有识别到任何节点，返回所有节点类型（低置信度）
        if not identified:
            for node_type, info in NEO4J_NODES.items():
                identified.append(
                    Neo4jNodeInfo(
                        node_type=node_type,
                        properties=info["properties"],
                        description=info["description"],
                        confidence=0.3,
                    )
                )
        
        return identified

    def get_related_documentation(self, question):
        search_engine = QASearchEngine()

        # 执行向量搜索
        results = search_engine.vector_similarity_search(question, top_k=1)
        documentation_list = []
        for i, result in enumerate(results['results'], 1):
            question = result['question']
            answer = result['answer']
            print(f"\n{i}. [相似度: {result['score']:.4f}]")
            print(f"   问题: {question}")
            # print(f"   答案: {result['answer'][:100]}..." if len(result['answer']) > 100 else f"   答案: {result['answer']}")
            print(f"答案: {answer}")
            documentation_list.append(dict(question=question, answer=answer))
        return documentation_list

    def identify_target_relationships(self, query: str) -> List[Neo4jRelationshipInfo]:
        """识别目标关系类型"""
        rel_types = self.expert_expander.identify_relationships(query)
        identified = []
        
        for rel_type in rel_types:
            if rel_type in NEO4J_RELATIONSHIPS:
                info = NEO4J_RELATIONSHIPS[rel_type]
                identified.append(
                    Neo4jRelationshipInfo(
                        relationship_type=rel_type,
                        from_node=info["from"],
                        to_node=info["to"],
                        description=info["description"],
                        confidence=1.0,
                    )
                )
        
        return identified

    def _build_llm_prompt(self, ctx: Neo4jIntentParseContext) -> str:
        """构建LLM提示词"""
        # 构建历史上下文
        history_context = ""
        if ctx.history_msgs:
            history_parts = ["以下是历史对话："]
            for msg in ctx.history_msgs[-2:]:  # 意图识别的历史对话只带最近2轮
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")
                history_parts.append(f"{role}: {content}")
            history_context = "\n".join(history_parts) + "\n\n"
        
        # 获取专家上下文（节点识别 + 关系识别 + 实体识别）
        expert_note = self.expert_expander.build_expert_context(ctx.user_query)

        # 检索相关文档
        # related_docs = self.retrieve_related_documentation(ctx.user_query)
        related_docs = self.get_related_documentation(ctx.user_query)
        print("相关文档", related_docs)

        # 构建合并的提示词 - 同时完成意图识别和Cypher生成
        prompt = (
            f"{NEO4J_INTENT_SYSTEM_PROMPT}\n\n"
            f"[用户问题]\n{ctx.user_query}\n\n"
            f"[专家分析](模型必须优先参考)\n{expert_note}\n\n"
            f"[相关文档](模型参考)\n{related_docs}\n\n"
            f"[Neo4j图数据库结构]\n"
            f"节点类型: {list(NEO4J_NODES.keys())}\n"
            f"关系类型: {list(NEO4J_RELATIONSHIPS.keys())}\n"
            f"查询类型: {list(QUERY_TYPES.keys())}\n"
            f"[任务要求]\n"
            f"请基于以上上下文完成以下两个任务：\n"
            f"1. 完成Neo4j查询的意图拆解，并给出JSON结果\n"
            f"2. 基于上述上下文直接生成一个可以执行的Cypher语句用于回答该问题\n"
            f"注意：无需重复描述Neo4j的节点或关系定义。\n"
            f"请在JSON结果中额外添加一个字段 'cypher' 来包含生成的Cypher语句。\n"
        )

        return prompt

    @staticmethod
    def _safe_json_loads(txt: str):
        """安全的JSON解析"""
        cypher_list = JsonExtractor().extract(txt)
        return cypher_list

    def _format_thinking_chunk(self, chunk: str) -> str:
        """处理流式输出的chunk，实现智能截断"""
        if self._stream_stopped:
            return ""
        
        self._accumulated_content += chunk
        
        # 检查多个可能的截断标识符
        truncate_markers = [
            "3.以下是json格式的解析结果：",
            "3.以下是",
            "3.以下是json格式",
            "3. 以下是json格式",
            "3.以下是JSON格式",
            "3. 以下是JSON格式",
            "3. 最后"
        ]
        
        for truncate_marker in truncate_markers:
            if truncate_marker in self._accumulated_content:
                marker_pos = self._accumulated_content.find(truncate_marker)
                content_before_marker = self._accumulated_content[:marker_pos]
                already_sent_length = len(self._accumulated_content) - len(chunk)

                if already_sent_length < marker_pos:
                    chunk_before_marker = content_before_marker[already_sent_length:]
                    self._stream_stopped = True
                    return chunk_before_marker
                else:
                    self._stream_stopped = True
                    return ""
        
        return chunk

    def _format_output(self, intents: List[Neo4jIntent], origin_query: str, history_msgs: List[Dict[str, str]]) -> Dict:
        """将内部 Neo4jIntent 模型转换为终端所需的 JSON 格式"""
        items: List[Dict] = []
        for i, it in enumerate(intents, start=1):
            target_nodes = [node.node_type for node in it.target_nodes] if it.target_nodes else []
            target_relationships = [rel.relationship_type for rel in it.target_relationships] if it.target_relationships else []
            
            items.append({
                "num": i,
                "rewritten_query": it.rewritten_query,
                "query_type": it.query_type,
                "target_nodes": target_nodes,
                "target_relationships": target_relationships,
                "entities": {
                    "nodes": it.entities.nodes,
                    "relationships": it.entities.relationships,
                    "properties": it.entities.properties,
                    "security_levels": it.entities.security_levels,
                    "network_types": it.entities.network_types,
                },
                "cypher_hint": it.cypher_hint,
                "reason": it.reason,
            })
        return {
            "intent_nums": len(items),
            "intents": items,
            "origin_query": origin_query,
            "history_msgs": history_msgs,
        }

    async def parse(self, ctx: Neo4jIntentParseContext, stream: bool = False,
                stream_callback: Optional[callable] = None) -> Dict:
        """
        主流程（LLM一次性完成）：
        - 单次调用LLM，完成意图拆解、以及每个意图具体解析；
        - 输出固定JSON结构传给Cypher查询生成；
        
        Args:
            ctx: Neo4j意图解析上下文
            stream: 是否使用流式输出，默认False
            stream_callback: 流式输出回调函数，传给前端作为<think></think>内容
        """
        # 重置流式状态
        self._stream_stopped = False
        self._accumulated_content = ""
        
        prompt = self._build_llm_prompt(ctx)
        # print(f"{573}---{stream}---{stream_callback}")
        try:
            # 根据stream参数选择调用方式
            if stream and stream_callback:
                # 流式调用 - 发送思考过程
                raw = ""
                llm_client2 = LLMClient()                
                async for chunk in llm_client2.async_stream_chat(
                    prompt=prompt,
                    model=self.model_name,
                    max_tokens=8000,
                    temperature=0,
                    system_prompt=NEO4J_INTENT_SYSTEM_PROMPT,
                ):
                    raw += chunk
                    # 将LLM的原始输出转换为可读的思考过程，并实现智能截断
                    if stream_callback:
                        # readable_chunk = self._format_thinking_chunk(chunk)
                        readable_chunk = chunk
                        if readable_chunk:
                            await stream_callback(readable_chunk)
            else:
                # 非流式调用
                raw = await self.llm_client2.async_nonstream_chat(
                    prompt=prompt,
                    model=self.model_name,
                    max_tokens=8000,
                    temperature=0.1,
                    system_prompt=NEO4J_INTENT_SYSTEM_PROMPT,
                )
                print(f"非流式：{raw}")
            
            print("LLM调用成功")
            intent_cypher_list = self._safe_json_loads(raw)
            # print(intent_cypher_list, type(intent_cypher_list))

            if not intent_cypher_list:
                raise ValueError("LLM未返回intent_cypher_list")

            return intent_cypher_list
                
        except Exception as e:
            print(f"\nLLM解析过程发生异常: {e}")
            return {"error": str(e)}


async def demo_neo4j_intent_parsing():
    """演示Neo4j意图解析"""
    print("=== Neo4j意图解析测试 ===")
    
    # 测试用例
    test_queries = [
        "查询河北单位建设了哪些网络, 以及这些网络的基本信息.",
    ]
    
    parser = Neo4jIntentParser()
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n--- 测试查询 {i}: {query} ---")
        
        # 创建解析上下文
        ctx = Neo4jIntentParseContext(
            user_query=query,
            history_msgs=[]
        )
        
        print(f"用户查询: {query}")
        
        # 测试流式输出
        print("\n【流式输出】:")
    
        async def stream_callback(chunk: str):
            """流式输出回调函数"""
            if chunk:
                print(chunk, end='', flush=True)
        
        try:
            result = await parser.parse(ctx, stream=True, stream_callback=stream_callback)
            print(f"\n解析结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        except Exception as e:
            print(f"解析失败: {e}")

if __name__ == "__main__":
    async def main():
        await demo_neo4j_intent_parsing()
    
    import asyncio
    import sys
    # Windows 事件循环策略，避免 Event loop is closed 警告
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
