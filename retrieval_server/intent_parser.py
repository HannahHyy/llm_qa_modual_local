"""
法规标准智能意图解析器
1. 意图拆解：判断用户查询可以拆解成几个独立意图
2. 对于每个意图：意图重写+涉及法规标准+关联实体+检索策略+判断原因
输入: origin_query + history_msgs（最多上面两轮）
输出1：json格式的结构化意图列表传给retrieval函数(_format_output)
    intent_nums: 意图个数
    intents: 每个意图都是一个json，包括num/rewritten_query/retrieval_type
                /regulation_standards/source_standard
                /entities(assets_objects & requirement_items & applicability_level)
                /reason
    origin_query
    history_msgs
输出2：stream流式输出直接返回给前端，包装在<think></think>标签中
"""

import os
import json
import csv
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field
import asyncio
# 忽略事件循环关闭的警告
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*Event loop is closed.*")
# 导入LLM客户端
try:
    from LLM_Server.llm_client import LLMClient
except ModuleNotFoundError:
    import sys
    ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)
    from LLM_Server.llm_client import LLMClient

# LLM 配置
DEFAULT_LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_LLM_MODEL_NAME = "deepseek-v3"
DEFAULT_LLM_API_KEY = "sk-f9f3209599454a49ba6fb4f36c3c0434" 
DEFAULT_MAX_INTENT_COUNT = 4

# 获取项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
KNOWLEDGE_DATA_DIR = os.path.join(PROJECT_ROOT, "knowledgedata")

# 全局缓存变量,避免重复加载csv
_requirement_synonyms_cache = None
_requirement_descriptions_cache = None
_asset_synonyms_cache = None

def load_requirement_items_from_csv():
    """从要求项词表.csv加载要求项同义词和详细描述（带缓存）"""
    global _requirement_synonyms_cache, _requirement_descriptions_cache
    
    # 如果已经缓存，直接返回
    if _requirement_synonyms_cache is not None and _requirement_descriptions_cache is not None:
        return _requirement_synonyms_cache, _requirement_descriptions_cache
    
    requirement_synonyms = {}
    requirement_descriptions = {}
    
    csv_path = os.path.join(KNOWLEDGE_DATA_DIR, "要求项词表.csv")
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                requirement_item = row['requirement_item']
                description = row['要求项详细描述']
                aliases = row['要求项别名'].split(',') if row['要求项别名'] else []
                
                # 清理别名中的空白字符
                aliases = [alias.strip() for alias in aliases if alias.strip()]
                
                requirement_synonyms[requirement_item] = aliases
                requirement_descriptions[requirement_item] = description
                
        # 缓存结果
        _requirement_synonyms_cache = requirement_synonyms
        _requirement_descriptions_cache = requirement_descriptions
        # print(_requirement_synonyms_cache)
        # print(_requirement_descriptions_cache)
        print(f"成功加载要求项词表，共 {len(requirement_synonyms)} 项")
        
    except FileNotFoundError:
        print(f"警告：未找到文件 {csv_path}，使用默认配置")
        _requirement_synonyms_cache = {}
        _requirement_descriptions_cache = {}
    except Exception as e:
        print(f"读取要求项词表时出错：{e}，使用默认配置")
        _requirement_synonyms_cache = {}
        _requirement_descriptions_cache = {}
    
    return _requirement_synonyms_cache, _requirement_descriptions_cache

def load_asset_objects_from_csv():
    """从产品项词表.csv加载资产对象同义词（带缓存）"""
    global _asset_synonyms_cache
    # 如果已经缓存，直接返回
    if _asset_synonyms_cache is not None:
        return _asset_synonyms_cache
    asset_synonyms = {}
    
    csv_path = os.path.join(KNOWLEDGE_DATA_DIR, "产品项词表.csv")
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                product = row['product']
                aliases = row['产品别名'].split(',') if row['产品别名'] else []
                # 清理别名中的空白字符
                aliases = [alias.strip() for alias in aliases if alias.strip()]
                asset_synonyms[product] = aliases
        
        # 缓存结果
        _asset_synonyms_cache = asset_synonyms
        # print(asset_synonyms)
        print(f"成功加载产品项词表，共 {len(asset_synonyms)} 项")
                
    except FileNotFoundError:
        print(f"警告：未找到文件 {csv_path}，使用默认配置")
        _asset_synonyms_cache = {}
    except Exception as e:
        print(f"读取产品项词表时出错：{e}，使用默认配置")
        _asset_synonyms_cache = {}
    
    return _asset_synonyms_cache

def clear_cache():
    """清除所有缓存（用于重新加载数据）"""
    global _requirement_synonyms_cache, _requirement_descriptions_cache
    global _asset_synonyms_cache
    
    _requirement_synonyms_cache = None
    _requirement_descriptions_cache = None
    _asset_synonyms_cache = None
    print("已清除所有数据缓存")

# RegulationStandard 标准别名映射表
REGULATION_STANDARDS = {
    "GB/T 22239-2019": {
        "identifier": "GB/T 22239-2019",
        "source_standard": "信息安全技术网络安全等级保护基本要求",
        "short_name": "37.1",
        "aliases": [
            "GB/T 22239-2019",
            "信息安全技术网络安全等级保护基本要求",
            "网络安全等级保护基本要求",
            "等级保护基本要求",
            "等保基本要求",
            "等保通用基本要求",
            "37.1",
            "22239",
            "2019版基本要求",
        ],
    },
    "GB/T 28448-2019": {
        "identifier": "GB/T 28448-2019",
        "source_standard": "信息安全技术网络安全等级保护测评要求",
        "short_name": "47.1",
        "aliases": [
            "GB/T 28448-2019",
            "信息安全技术网络安全等级保护测评要求",
            "网络安全等级保护测评要求",
            "等级保护测评要求",
            "等保测评要求",
            "等保通用测评要求",
            "47.1",
            "28448",
            "2019版测评要求",
        ],
    },
    "信息安全等级保护管理办法": {
        "identifier": "信息安全等级保护管理办法",
        "source_standard": "信息安全等级保护管理办法",
        "short_name": "等保管理办法",
        "aliases": [
            "信息安全等级保护管理办法",
            "等级保护管理办法",
            "等保管理办法",
            "等保管理规定",
            "信息安全等级保护管理规定",
            "网络安全等级保护管理办法",
            "等级保护办法",
            "等保办法",
        ],
    },
    "公信安[2018]765号": {
        "identifier": "公信安[2018]765号",
        "source_standard": "网络安全等级保护测评机构管理办法",
        "short_name": "测评机构管理办法",
        "aliases": [
            "公信安[2018]765号",
            "网络安全等级保护测评机构管理办法",
            "等级保护测评机构管理办法",
            "测评管理办法",
            "测评管理规定",
            "测评机构管理办法",
            "等保测评机构 methodologies",
            "测评机构管理规定",
            "等保测评机构管理规定",
            "765号文",
            "2018年765号",
        ],
    },
}

# 等级保护级别同义词表
APPLICATION_LEVEL_KEYWORDS = {
    "第一级": ["一级", "第1级", "1级"],
    "第二级": ["二级", "第2级", "2级"],
    "第三级": ["三级", "第3级", "3级"],
    "第四级": ["四级", "第4级", "4级"]
}

# 命中宏观类问题的关键词（用于后置过滤）
MACRO_KEYWORDS = [
    "构建", "总体设计", "规划", "架构", "管理", "流程", "职责", "备案", "定级", "复测", "整改"
]

# 命中宏观测评管理办法词（后置过滤）
MACRO_CP_KEYWORDS = [
    "测评机构", "测评机构管理办法","测评机构要求"
]

# 命中细则/测评/实现方法/产品推荐等关键词（后置过滤）
EVAL_DETAIL_KEYWORDS = [
    "具体要求", "细则",  "测评方法", "测评要求", "评估", "检查", "验证", "核查",
    "实现方法", "产品推荐", "选型", "配置", "部署"
]



# 在模块加载时一次性加载数据
REQUIREMENT_ITEM_SYNONYMS, REQUIREMENT_ITEM_DESCRIPTIONS = load_requirement_items_from_csv()
ASSET_OBJECT_SYNONYMS = load_asset_objects_from_csv()

# print(REQUIREMENT_ITEM_DESCRIPTIONS)

# 系统提示词-意图识别，先流式输出，再生成json给retreival
INTENT_SYSTEM_PROMPT = (
    "你是法规标准问答系统的'智能意图解析器'。\n"
    "请根据输入的上下文，完成问题的意图拆解，并对每个意图进行详细分析。\n"
    "你需要进行流式输出，其中分析思路需要展示到前端页面。\n"
    "请先详细说明你的分析思路，分析思路请完全以流利的中文自然语言进行描述，然后输出最终严格的JSON结果。\n"
    "最后的JSON结果，必须严格按照以下格式输出标识符（不要有任何变化）：'\n"
    "'3.以下是json格式的解析结果：'\n"
    "{\"intents\": [{\"rewritten_query\": string, \"retrieval_type\": string, \"regulation_standards\": [string...], \"source_standard\": [string...], \"entities\": {\"asset_objects\":[string...], \"requirement_items\":[string...], \"applicability_level\":[string...]}, \"reason\": string},\n\"origin_query\": string, \"history_msgs\":[string...], \"no_standard_query\": boolean}\n"
    "说明：\n"
    "- rewritten_query：将原始问题进行同义词扩展和语序优化，便于检索，不可遗漏原始内容。\n"
    "- retrieval_type：检索类型，从 {keyword_search, semantic_search, hybrid_search} 中选择。\n"
    "  * keyword_search: 更偏向于精确条款查询（如\"6.1.1.1物理访问控制的要求\"）\n"
    "  * semantic_search: 更偏向于概念性问题（如\"什么是访问控制\"）\n"
    "  * hybrid_search: 更偏向于综合性/总结性查询（如\"第一级的所有基本要求\"、\"总结某个标准的要求\"）\n"
    "- regulation_standards：目标法规标准，从以下四个标准中选择：\n"
    "  * GB/T 22239-2019: 《信息安全技术网络安全等级保护基本要求》\n"
    "    - 适用场景：查询某个要求项的基本规定或总体规范\n"
    "    - 内容范围：第一级到第四级等级保护网络中，对每一个要求项的基本规定，不涉及对资产对象/产品的描述\n"
    "  * GB/T 28448-2019: 《信息安全技术网络安全等级保护测评要求》\n"
    "    - 适用场景：当用户询问\"具体要求\"、\"细则\"，或涉及资产对象/产品（如防火墙、服务器等）时，必须包含此标准\n"
    "    - 内容范围：第一级到第四级等级保护网络中，检测每个要求项的具体测评方法，以及各资产对象/产品的具体细则要求\n"
    "  * 信息安全等级保护管理办法: 《信息安全等级保护管理办法》\n"
    "    - 适用场景：宏观管理、网络架构设计/规划/构建等保网络等整体问题；当问题涉及具体要求项或资产对象时不选择\n"
    "    - 内容范围：开展等保工作的宏观管理办法，不涉及具体要求项，不涉及具体资产对象\n"
    "  * 公信安[2018]765号: 《网络安全等级保护测评机构管理办法》\n"
    "    - 适用场景：与测评机构相关的宏观管理问题；当问题涉及具体要求项或资产对象时不选择\n"
    "    - 内容范围：等保测评机构的宏观管理办法，不涉及具体要求项，不涉及具体资产对象\n"
    "- 选择规则：\n"
    "  1) 意图合并：仅当问题拆分为两个完全不同子问题时才拆分；当同时询问某要求项的实现与资产对象/产品推荐时，应合并为一个意图。\n"
    "  2) 具体要求项/产品推荐：仅选择 GB/T 22239-2019 与 GB/T 28448-2019；不要选择管理办法或公信安[2018]765号。\n"
    "  3) 宏观构建/设计网络：选择 \"信息安全等级保护管理办法\" 与 GB/T 22239-2019；除非同时出现资产对象或明确的具体要求词，否则不选择 GB/T 28448-2019。\n"
    "  4) 出现资产对象（如\"防火墙\"等）或明确询问\"具体要求/细则/测评方法/测评要求\"：必须同时包含 GB/T 28448-2019 和 GB/T 22239-2019。\n"
    "  5) 一致性校验：\n"
    "     - regulation_standards 与 source_standard 的数量必须一致，并一一对应；中文名称必须与标准字典 REGULATION_STANDARDS 中的 \"source_standard\" 完全一致。\n"
    "     - 若 \"reason\" 或问题文本中出现 \"测评方法\"、\"评估\"、\"检查\"、、\"核查\" 等词，必须包含 GB/T 28448-2019。\n"
    "     - 若出现 \"构建/总体设计/规划/架构/管理/流程/职责/备案/定级/复测/整改\" 等宏观关键词，必须包含 \"信息安全等级保护管理办法\" 与 GB/T 22239-2019。\n"
    "  6) 标准数量尽量精简：仅包含与问题强相关的标准，不要遗漏或多出。\n"
    "- source_standard：目标法规标准对应的中文名称。\n"
    "- entities：识别的实体，仅包含 asset_objects, requirement_items, applicability_level 三类。\n"
    "  * requirement_items识别规则：请仔细分析用户问题中的关键词和语义，结合以下要求项详细描述进行精准匹配：\n"
    f"    {REQUIREMENT_ITEM_DESCRIPTIONS}\n"
    "    \n"
    "    **强制识别规则**：\n"
    "    1. 直接匹配：问题中明确提到要求项名称时，必须识别（如\"物理访问控制\"、\"身份鉴别\"、\"访问控制\"等）\n"
    "    2. 关键词匹配：识别问题中的关键词和语义进行匹配：\n"
    "    3. 语义场景匹配：根据问题描述的安全风险、业务场景或技术措施，推断相关要求项\n"
    "    4. 多要求项识别：一个问题可能涉及多个要求项，必须全面识别，不能遗漏\n"
    "    5. **重要提醒**：requirement_items字段一般绝对不能为空，除非问题完全不涉及任何具体的安全要求项\n"
    "- reason：意图分析的原因说明。\n"
    "- origin_query：用户的原始提问。\n"
    "- history_msgs：用户的历史上下文。\n"
    "- no_standard_query：布尔值，当origin_query不涉及任何法规标准查询需求时为true，否则为false。判断标准：\n"
    "  * True：问题是纯粹的问候语、闲聊、与法规标准无关的一般性问题\n"
    "  * False：问题涉及任何法规标准、等级保护、安全要求项、资产对象等相关内容\n"
    f"- 最多给出 {DEFAULT_MAX_INTENT_COUNT} 个意图；若用户问题非常明确，则仅输出 1 个意图，能不拆分的尽量不拆分（例如同时问具体要求与产品推荐时合并为一个意图）。\n"
    "- 特别注意：当用户询问\"总结\"、\"所有\"、\"整体\"、\"概述\"等词汇时，通常是总结性查询，应使用hybrid_search类型。\n"
     "\n在流式输出时，请按以下格式组织你的回答：\n"
    "1. 首先分析用户问题可以拆分成哪几个意图\n"
    "2. 以流利的中文输出每个意图的具体含义，**特别要明确指出识别到的要求项及其识别依据**\n"
    "3. 最后输出完整的JSON结果。（在JSON之前必须输出标识符）。\n"
)

class ExpertExpander:
    """同义词扩写实体识别"""
    def __init__(self):
        self.standards = REGULATION_STANDARDS
        self.asset_map = ASSET_OBJECT_SYNONYMS
        self.req_map = REQUIREMENT_ITEM_SYNONYMS
        self.level_map = APPLICATION_LEVEL_KEYWORDS
    # query子串匹配标准名
    def identify_standards(self, text):
        """识别用户query中是否明确提到法规标准"""
        t = text.lower()
        found = [] # 返回的找到的标准列表
        # 子串匹配用户query中是否存在法规标准别名aliases
        for info in self.standards.values():
            for alias in info.get("aliases", []):
                if alias.lower() in t:
                    found.append(info["identifier"])
                    break
        # 没匹配上别名，但是query中包含等保 或 等级保护
        if not found and ("等保" in text or "等级保护" in text):
            # 明确提到测评 或 评估
            if ("测评" in text or "评估" in text):
                found.append("GB/T 28448-2019")
            else:
                found.append("GB/T 22239-2019")
        # 去重
        return list(dict.fromkeys(found))

    # query子串匹配实体信息
    def extract_entities(self, text, history_msgs=None):
        """提取用户query + 最近上下文中的信息系统资产、要求项、适用等级 实体信息"""
        assets, reqs, applicability_level = [], [], []
        # 构建上下文文本（当前查询 + 最近的历史对话）
        full_text = text
        if history_msgs:
            # 只取最近的1轮对话，避免历史过长引起混乱
            recent_msgs = history_msgs[-2:]  # 用户输入的最近2条消息（2轮对话）
            recent_content = []
            for msg in recent_msgs:
                if msg.get("role") == "user":
                    recent_content.append(msg.get("content", ""))
            if recent_content:
                full_text = " ".join(recent_content) + " " + text
        full_text_lower = full_text.lower()
        
        # 从完整上下文中提取三类实体
        # 1. 资产对象匹配
        for k, syns in self.asset_map.items():
            if k in full_text or any(s.lower() in full_text_lower for s in syns):
                assets.append(k)
        # 2. 要求项匹配
        for k, syns in self.req_map.items():
            if k in full_text or any(s.lower() in full_text_lower for s in syns):
                reqs.append(k)
        # 3. 等级匹配
        for k, syns in self.level_map.items():
            if k in full_text or any(s.lower() in full_text_lower for s in syns):
                applicability_level.append(k)
        return assets, reqs, applicability_level
    
    # 去除空白字符
    def expand_query(self, text):
        return text.strip()

    def build_expert_context(self, text):
        """构建专家上下文"""
        stds = self.identify_standards(text) # 实体识别
        assets, reqs, applicability_level = self.extract_entities(text) # 实体识别
        lines = []
        if stds:
            lines.append(f"用户提到的法规标准(仅供参考): {', '.join(stds)}")
        if assets:
            lines.append(f"资产对象: {', '.join(assets)}")
        if reqs:
            lines.append(f"要求项: {', '.join(reqs)}")
        if applicability_level:
            lines.append(f"等级: {', '.join(applicability_level)}")
        return "\n".join(lines)

class RegulationStandardInfo(BaseModel):
    """法规标准信息"""
    identifier: str = Field(description="标准标识符，如GB/T 22239-2019")
    source_standard: str = Field(description="标准全称")
    short_name: str = Field(description="简称")
    confidence: float = Field(default=1.0, description="识别置信度")
class EntityInfo(BaseModel):
    """实体信息"""
    asset_objects: List[str] = Field(default_factory=list, description="识别的资产对象")
    requirement_items: List[str] = Field(default_factory=list, description="识别的要求项")
    applicability_level: List[str] = Field(default_factory=list, description="识别的等级")

# 意图返回数据模型
class Intent(BaseModel):
    """增强的意图数据结构"""
    rewritten_query: str = Field(..., description="改写后的检索友好问题")
    regulation_standards: List[RegulationStandardInfo] = Field(
        default_factory=list, description="目标法规标准"
    )
    retrieval_type: Literal[
        "keyword_search", "semantic_search", "hybrid_search"
    ] = Field(..., description="检索路径类型")
    entities: EntityInfo = Field(default_factory=EntityInfo, description="识别的实体信息")
    reason: Optional[str] = Field(None, description="意图分析和策略选择的说明")
    origin_query: str = Field(..., description="用户原始提问")
    history_msgs: List[Dict[str, str]] = Field(default_factory=list, description="历史对话消息列表")

class IntentParseResult(BaseModel):
    """意图解析结果容器"""
    intents: List[Intent] = Field(default_factory=list)

# 与 server.py 的输入格式一致
class IntentParseContext(BaseModel):
    """输入上下文 - 与 server.py 保持一致的输入格式"""
    user_query: str  # 当前用户查询
    history_msgs: List[Dict[str, str]] = Field(default_factory=list, description="历史对话消息列表")

class EnhancedIntentParser:
    """
    基于LLM的意图分析解析器，主要功能包括：
    - 意图拆解：将复杂查询分解为多个独立的意图
    - 标准识别：LLM识别查询中涉及的法规标准（如GB/T 22239-2019等）
    - 实体提取：提取资产对象、要求项、等级等关键实体
    - 查询重写：基于上下文和专家知识重写查询以提高检索效果
    - 检索策略：为每个意图选择最适合的检索类型（关键词/语义/混合）
    
    异步流式处理：
    - 支持流式输出思考过程，提供实时反馈
    - 智能截断，避免向前端发送JSON结果
    
    输入格式：
    - user_query: 用户当前查询
    - history_msgs: 历史对话消息（用于上下文理解）
    
    输出格式：
    - 结构化JSON，包含意图列表、原始查询、历史消息等
    - 每个意图包含：重写查询、检索类型、法规标准、实体信息、分析原因
    
    注意事项：
    - 依赖LLM服务，需要配置正确的API密钥和端点
    - 流式输出需要提供回调函数处理实时数据
    - 支持历史对话上下文，但需控制历史消息数量以避免token超限
    """

    def __init__(self):
        # LLM客户端初始化（一次性调用）
        self.base_url = DEFAULT_LLM_BASE_URL
        self.model_name = DEFAULT_LLM_MODEL_NAME
        self.api_key = DEFAULT_LLM_API_KEY
        
        # 设置LLM_Server.llm_client模块的全局配置
        import LLM_Server.llm_client as llm_client_module
        llm_client_module.base_url = self.base_url
        llm_client_module.api_key = self.api_key
        
        # 使用统一的LLMClient，不传递参数，使用全局配置
        self.llm_client = LLMClient()
        self.max_intent_count = DEFAULT_MAX_INTENT_COUNT
        # 同义词扩写进行实体识别
        self.expert_expander = ExpertExpander()
        # 添加流式截断状态
        self._stream_stopped = False
        self._accumulated_content = ""

    # 同义词扩写进行标准识别
    def identify_regulation_standards(self, query):
        """
        使用 ExpertExpander 识别查询中涉及的 RegulationStandard。
        """
        standard_ids = self.expert_expander.identify_standards(query)
        identified = []
        
        for std_id in standard_ids:
            if std_id in REGULATION_STANDARDS:
                info = REGULATION_STANDARDS[std_id]
                identified.append(
                    RegulationStandardInfo(
                        identifier=info["identifier"],
                        source_standard=info["source_standard"],
                        short_name=info["short_name"],
                        confidence=1.0,
                    )
                )
        
        # 如果没有识别到任何标准，返回默认标准
        if not identified:
            for info in REGULATION_STANDARDS.values():
                identified.append(
                    RegulationStandardInfo(
                        identifier=info["identifier"],
                        source_standard=info["source_standard"],
                        short_name=info["short_name"],
                        confidence=0.3,
                    )
                )
        
        return identified

    def _filter_content(self, content: str) -> str:
        """过滤掉包含think和knowledge标签的内容"""
        import re
        if not content:
            return content
        
        # 移除 <think> </think> 标签及其内容
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        # 移除 <knowledge> </knowledge> 标签及其内容
        content = re.sub(r'<knowledge>.*?</knowledge>', '', content, flags=re.DOTALL)
        
        # 清理多余的空白字符
        content = re.sub(r'\n\s*\n', '\n', content.strip())
        
        return content

    def _build_llm_prompt(self, ctx: IntentParseContext) -> str:
        """构建LLM提示词"""
        # 构建历史上下文（参考 server.py 的逻辑）
        history_context = ""
        if ctx.history_msgs:
            history_parts = ["以下是历史对话："]
            for msg in ctx.history_msgs[-2:]:  # 意图识别的历史对话只带最近2轮
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")
                # 过滤掉think和knowledge标签内容
                filtered_content = self._filter_content(content)
                if filtered_content.strip():  # 只有在过滤后还有内容时才添加
                    history_parts.append(f"{role}: {filtered_content}")
            history_context = "\n".join(history_parts) + "\n\n"
        
        # 获取专家上下文（标准识别 + 实体识别）
        expert_note = self.expert_expander.build_expert_context(ctx.user_query)
        suggested = self.expert_expander.expand_query(ctx.user_query)
        
        # 使用INTENT_PROMPT_HEADER
        prompt = (
            f"{INTENT_SYSTEM_PROMPT}\n\n"
            f"[用户问题]\n{ctx.user_query}\n\n"
            f"[专家扩写](模型必须优先参考)\n{expert_note}\n\n"
            f"[当前上下文对话历史](模型也需要参考)\n{history_context}\n\n"
            f"[建议改写](供 rewritten_query 参考)\n请根据{suggested}和上面的[专家扩写]来进行改写，不需要体现标准全名"
        )

        return prompt

    @staticmethod
    def _safe_json_loads(txt: str) -> Optional[dict]:
        """安全的JSON解析"""
        print("\n_safe_json_loads 开始解析JSON")
        
        # 去除可能的markdown包裹
        s = txt.strip()
        if s.startswith("```"):
            s = s.strip("`\n ")
            if s.lower().startswith("json"):
                s = s[4:].lstrip()
        
        try:
            result = json.loads(s)
            return result
        except Exception as e:
            try:
                start = s.find("{")
                end = s.rfind("}")
                if start != -1 and end != -1 and end > start:
                    extracted = s[start : end + 1]
                    result = json.loads(extracted)
                    return result
                else:
                    return None
            except Exception as e2:
                return None

    @staticmethod
    def _normalize_standard(std_text: str) -> List[RegulationStandardInfo]:
        """标准化法规标准文本"""
        t = std_text.strip()
        out: List[RegulationStandardInfo] = []
        # 先按identifier精确匹配
        for info in REGULATION_STANDARDS.values():
            if t == info["identifier"]:
                out.append(
                    RegulationStandardInfo(
                        identifier=info["identifier"],
                        source_standard=info["source_standard"],
                        short_name=info["short_name"],
                        confidence=1.0,
                    )
                )
                return out
        # 再按别名包含匹配
        tl = t.lower()
        for info in REGULATION_STANDARDS.values():
            for alias in info.get("aliases", []):
                if alias.lower() in tl or tl in alias.lower():
                    out.append(
                        RegulationStandardInfo(
                            identifier=info["identifier"],
                            source_standard=info["source_standard"],
                            short_name=info["short_name"],
                            confidence=0.8,
                        )
                    )
                    return out
        # 未知时返回多个标准（低置信度）
        for info in REGULATION_STANDARDS.values():
            out.append(
                RegulationStandardInfo(
                    identifier=info["identifier"],
                    source_standard=info["source_standard"],
                    short_name=info["short_name"],
                    confidence=0.3,
                )
            )
        return out

    def _format_output(self, intents: List[Intent], origin_query: str, history_msgs: List[Dict[str, str]], no_standard_query: bool = False) -> Dict:
        """将内部 Intent 模型转换为终端所需的 JSON 格式"""
        items: List[Dict] = []
        for i, it in enumerate(intents, start=1):
            reg_ids = [rs.identifier for rs in it.regulation_standards] if it.regulation_standards else []
            src_names = [rs.source_standard for rs in it.regulation_standards if rs.source_standard] if it.regulation_standards else []
            # 去重，保持顺序
            src_names = list(dict.fromkeys(src_names))
            items.append({
                "num": i,  # 第几个intent
                "rewritten_query": it.rewritten_query,
                "retrieval_type": it.retrieval_type,
                "regulation_standards": reg_ids,      # 标识符列表
                "source_standard": src_names,          # 标准全称列表，与上并列
                "entities": {
                    "asset_objects": it.entities.asset_objects,
                    "requirement_items": it.entities.requirement_items,
                    "applicability_level": it.entities.applicability_level,
                },
                "reason": it.reason,
            })
        
        # 过滤history_msgs中的think和knowledge标签内容
        filtered_history_msgs = []
        for msg in history_msgs:
            filtered_msg = msg.copy()  # 创建消息副本
            if "content" in filtered_msg:
                filtered_msg["content"] = self._filter_content(filtered_msg["content"])
            filtered_history_msgs.append(filtered_msg)
        
        return {
            "intent_nums": len(items),
            "intents": items,
            "origin_query": origin_query,
            "history_msgs": filtered_history_msgs,
            "no_standard_query": no_standard_query, 
        }
    def _post_filter_regulation_standards(self, intents: List[Intent]) -> List[Intent]:
        """
        解析后进行一次标准过滤：
        - 当entities.requirement_items、entities.asset_objects、applicability都为空且命中宏观关键词（在 origin_query/reason/rewritten_query 中命中），去除"GB/T 28448-2019"
        - 当出现要求项/资产对象类问题（asset_objects 非空并且 requirement_items 非空，并且已经包含GB/T 22239-2019时，才强制仅保留并补齐"GB/T 28448-2019"
        """
        for intent in intents:
            has_requirements = bool(intent.entities.requirement_items)
            has_assets = bool(intent.entities.asset_objects)
            has_applicability = bool(intent.entities.applicability_level)
            has_entities = has_requirements or has_assets or has_applicability

            text_for_macro = f"{intent.origin_query} {intent.reason or ''} {intent.rewritten_query}"
            macro_hit = any(k in text_for_macro for k in MACRO_KEYWORDS)
            cp_macro_hit = any(k in text_for_macro for k in MACRO_CP_KEYWORDS)

            # 1. 当entities都为空且命中宏观关键词，去除"GB/T 28448-2019"
            if not has_entities and macro_hit:
                intent.regulation_standards = [
                    rs for rs in intent.regulation_standards
                    if rs.identifier != "GB/T 28448-2019"
                ]

            # 2. 当出现要求项/资产对象类问题且包含GB/T 22239-2019时，强制再添加"GB/T 28448-2019"
            if has_requirements and (has_assets or has_applicability):
                has_gb22239 = any(rs.identifier == "GB/T 22239-2019" for rs in intent.regulation_standards)
                if has_gb22239:
                    # 检查是否已存在GB/T 28448-2019，如果不存在则添加
                    if not any(rs.identifier == "GB/T 28448-2019" for rs in intent.regulation_standards):
                        info = REGULATION_STANDARDS["GB/T 28448-2019"]
                        intent.regulation_standards.append(
                            RegulationStandardInfo(
                                identifier=info["identifier"],
                                source_standard=info["source_standard"],
                                short_name=info["short_name"],
                                confidence=0.95,
                            )
                        )

            # 3. 当出现要求项/资产对象类问题且包含GB/T 28448-2019时，强制再添加"GB/T 22239-2019"
            if has_requirements and (has_assets or has_applicability):
                has_gb28448 = any(rs.identifier == "GB/T 28448-2019" for rs in intent.regulation_standards)
                if has_gb28448:
                    # 检查是否已存在GB/T 22239-2019，如果不存在则添加
                    if not any(rs.identifier == "GB/T 22239-2019" for rs in intent.regulation_standards):
                        info = REGULATION_STANDARDS["GB/T 22239-2019"]
                        intent.regulation_standards.append(
                            RegulationStandardInfo(
                                identifier=info["identifier"],
                                source_standard=info["source_standard"],
                                short_name=info["short_name"],
                                confidence=0.95,
                            )
                        )

            # 4. 当命中宏观关键词且没有资产对象和要求项时，强制添加等保管理办法
            if macro_hit and not has_assets and not has_requirements:
                # 检查是否已存在信息安全等级保护管理办法，如果不存在则添加
                if not any(rs.identifier == "信息安全等级保护管理办法" for rs in intent.regulation_standards):
                    info = REGULATION_STANDARDS["信息安全等级保护管理办法"]
                    intent.regulation_standards.append(
                        RegulationStandardInfo(
                            identifier=info["identifier"],
                            source_standard=info["source_standard"],
                            short_name=info["short_name"],
                            confidence=0.95,
                        )
                    )

            # 5. 当命中测评机构相关关键词且没有资产对象和要求项时，强制添加等保测评管理办法
            if cp_macro_hit and not has_assets and not has_requirements:
                # 检查是否已存在公信安[2018]765号，如果不存在则添加
                if not any(rs.identifier == "公信安[2018]765号" for rs in intent.regulation_standards):
                    info = REGULATION_STANDARDS["公信安[2018]765号"]
                    intent.regulation_standards.append(
                        RegulationStandardInfo(
                            identifier=info["identifier"],
                            source_standard=info["source_standard"],
                            short_name=info["short_name"],
                            confidence=0.95,
                        )
                    )
        return intents

    def _format_thinking_chunk(self, chunk: str) -> str:
        """
        处理流式输出的chunk，实现智能截断
        当遇到JSON结果标识符时停止向前端发送内容
        """
        # 如果已经停止流式输出，直接返回空字符串
        if self._stream_stopped:
            return ""
        
        # 累积内容用于检测截断标识符
        self._accumulated_content += chunk
        
        # 检查多个可能的截断标识符（因为LLM可能不严格按照指示输出）
        truncate_markers = [
            "3.以下是json格式的解析结果：",
            "3.以下是",
            "3.以下是json格式",
            "3. 以下是json格式",
            "3.以下是JSON格式",
            "3. 以下是JSON格式"
            "3. 最后"
        ]
        
        for truncate_marker in truncate_markers:
            if truncate_marker in self._accumulated_content:
                # 找到标识符的位置
                marker_pos = self._accumulated_content.find(truncate_marker)
                
                # 计算当前chunk中应该返回的部分
                content_before_marker = self._accumulated_content[:marker_pos]
                already_sent_length = len(self._accumulated_content) - len(chunk)
                
                if already_sent_length < marker_pos:
                    # 当前chunk中有部分内容在标识符之前，需要返回这部分
                    chunk_before_marker = content_before_marker[already_sent_length:]
                    self._stream_stopped = True
                    return chunk_before_marker
                else:
                    # 当前chunk完全在标识符之后，停止输出
                    self._stream_stopped = True
                    return ""
        
        # 没有遇到截断标识符，正常返回chunk
        return chunk

    async def parse(self, ctx: IntentParseContext, stream: bool = False, 
                stream_callback: Optional[callable] = None) -> Dict:
        """
        主流程（LLM一次性完成）：
        - 单次调用LLM，完成意图拆解、以及每个意图具体解析；
        - 输出固定JSON结构传给retrieval；
        
        Args:
            ctx: 意图解析上下文
            stream: 是否使用流式输出，默认False
            stream_callback: 流式输出回调函数，传给前端作为<think></think>内容
        """
        # 重置流式状态
        self._stream_stopped = False
        self._accumulated_content = ""
        
        prompt = self._build_llm_prompt(ctx)
        
        try:
            # 根据stream参数选择调用方式
            if stream and stream_callback:
            # if stream:
                # 流式调用 - 发送思考过程
                raw = ""
                # if stream_callback:
                #     await stream_callback("<think>开始对用户的提问进行深入解析...\n\n")
                
                async for chunk in self.llm_client.async_stream_chat(
                    prompt=prompt,
                    model=self.model_name,
                    max_tokens=10000,
                    temperature=0,
                    system_prompt=INTENT_SYSTEM_PROMPT,
                ):
                    raw += chunk
                    # 将LLM的原始输出转换为可读的思考过程，并实现智能截断
                    if stream_callback:
                        readable_chunk = self._format_thinking_chunk(chunk)
                        if readable_chunk:
                            await stream_callback(readable_chunk)
                    
                # if stream_callback:
                #     await stream_callback("\n意图分析完成。</think>\n")
            else:
                # 非流式调用
                raw = await self.llm_client.async_nonstream_chat(
                    prompt=prompt,
                    model=self.model_name,
                    max_tokens=4000,
                    temperature=0.1,
                    system_prompt=INTENT_SYSTEM_PROMPT,
                )
                print(f"非流式：{raw}")
            print("LLM调用成功")
            data = self._safe_json_loads(raw)
            
            if not data or "intents" not in data or not isinstance(data["intents"], list):
                # print("LLM返回数据验证失败")
                # print(f"数据类型: {type(data)}")
                # if data:
                #     print(f"数据键: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                raise ValueError("LLM未返回有效intents数组")
            
            # print("LLM返回数据验证通过")
            # print(f"针对用户原始提问：\"{ctx.user_query}\"，总共解析到{len(data['intents'])}个意图")
            # 提取no_standard_query字段
            no_standard_query = data.get("no_standard_query", False)
            intents: List[Intent] = []
            for idx, it in enumerate(data["intents"][: self.max_intent_count]):
                # print(f"\n处理第 {idx + 1} 个意图:")
                # 添加origin_query到意图数据中
                it_with_origin = dict(it)
                it_with_origin["origin_query"] = ctx.user_query
                # print(f"原始意图数据: {it_with_origin}")
                
                rq = str(it.get("rewritten_query") or ctx.user_query).strip()
                
                # standards 归一化
                raw_standards = it.get("standards", []) or []
                
                stds: List[RegulationStandardInfo] = []
                for s in raw_standards:
                    normalized = self._normalize_standard(str(s))
                    stds.extend(normalized)
                
                if not stds:
                    stds = self.identify_regulation_standards(rq)
                
                # print(f"匹配标准列表: {[std.identifier for std in stds]}")
                
                # retrieval_type 校验
                raw_rtype = it.get("retrieval_type")
                rtype = str(raw_rtype or "hybrid_search").strip()
                if rtype not in {"keyword_search", "semantic_search", "hybrid_search"}:
                    rtype = "hybrid_search"
                
                # print(f"匹配检索类型: {rtype}")
                
                # entities
                ent = it.get("entities") or {}        
                asset_objects = [str(x) for x in ent.get("asset_objects") or []]
                requirement_items = [str(x) for x in ent.get("requirement_items") or []]
                applicability_level = [str(x) for x in ent.get("applicability_level") or []]
                
                # 使用 ExpertExpander 进行实体识别，传入最近的历史消息上下文
                asset_objects, requirement_items, applicability_level = self.expert_expander.extract_entities(rq, ctx.history_msgs)
                
                entities = EntityInfo(
                    asset_objects=asset_objects,
                    requirement_items=requirement_items,
                    applicability_level=applicability_level,
                )
                
                reason = str(it.get("reason") or "LLM解析结果")
                
                # 创建Intent对象，手动设置 history_msgs
                intent = Intent(
                    origin_query=ctx.user_query,
                    history_msgs=ctx.history_msgs,  # 设置历史消息
                    rewritten_query=rq,
                    regulation_standards=stds,
                    retrieval_type=rtype,
                    entities=entities,
                    reason=reason,
                )
                
                intents.append(intent)

            intents = self._post_filter_regulation_standards(intents)
            # 使用_format_output方法格式化返回结果
            formatted_result = self._format_output(intents, ctx.user_query, ctx.history_msgs,no_standard_query)
            print(f"返回的结果：\n{json.dumps(formatted_result, ensure_ascii=False, indent=2)}")
            return formatted_result
                
        except Exception as e:
            # print(f"\nLLM解析过程发生异常: {e}")
            return e


async def demo_intent_parsing_with_history(parser):
    """演示带历史上下文的意图解析"""
    print("=== 带历史上下文的意图解析测试 ===")
    
    # 模拟历史对话
    history_msgs = [
        {"role": "user", "content": "我想了解网络安全等级保护的基本要求"},
        {"role": "assistant", "content": "网络安全等级保护基本要求主要包括技术要求和管理要求两大类..."}
    ]
    
    # 测试用例
    test_queries = [
        "请列出一级,二级等级保护系统对于边界防护的具体要求各是什么样的?在第一级等保系统中，我能否通过使用防火墙来实现边界防护？对防火墙的规定是什么样的？给出一个300字的概述。除此之外,我要构建一个第一级的等保网络,给我一些简介.",
        # "我的一级等保系统有哪些和FW相关的规定？",
        # "37.1中对于边界防护是怎么规定的？",
        # "在一级等级保护系统中怎么实现边界隔离的？可以给我推荐一些相关产品吗？",
        # "765号文对测评机构和测评人员是怎么要求的？"
        # "请查询网络安全等级保护基本要求的第6.1.8条",
        # "在等保一级系统中，对于防止用户越权访问敏感数据有哪些规定",
        # "在等保一级系统中，对于存在未防护的影子系统有哪些规定？",
        # "你好你好你好"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n--- 测试查询 {i}: {query} ---")
        # 创建解析上下文
        ctx = IntentParseContext(
            user_query=query,
            history_msgs=history_msgs
        )
        
        print(f"用户查询: {query}")
        print(f"历史上下文: {len(history_msgs)} 条消息")
        
        # 测试非流式输出
        # print("\n【非流式输出】:")
        # await parser.parse(ctx, stream=False)

        # 只保留流式输出
        print("\n【流式输出】:")
    
        async def stream_callback(chunk: str):
            """流式输出回调函数"""
            if chunk:
                print(chunk, end='', flush=True)
        
        await parser.parse(ctx, stream=True, stream_callback=stream_callback)

if __name__ == "__main__":
    async def main():
        parser = EnhancedIntentParser()
        
        # 带历史上下文的测试
        await demo_intent_parsing_with_history(parser)
        
        # 简单测试查询（无历史上下文）
        # print("\n=== 简单测试查询（无历史上下文） ===")
        # q1 = "第三级防火墙在等保基本要求中的访问控制要求有哪些？"
        # ctx = IntentParseContext(user_query=q1)
        # print("\n【流式模式】:")
        # await parser.parse(ctx, stream=True,stream_callback=True)
        # print("\n【非流式模式】:")
        # await parser.parse(ctx, stream=False)
    
    import asyncio
    import sys
    import warnings
    # Windows 事件循环策略，避免 Event loop is closed 警告
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
