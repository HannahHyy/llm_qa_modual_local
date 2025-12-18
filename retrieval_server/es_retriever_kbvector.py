# -*- coding: utf-8 -*-
"""
ES专用检索器
基于intent_parser.py的结构化输出进行检索
分两个部分:
1. 硬标签过滤:将标准名称/级别/要求项名称定义为硬标签,如果用户的问题里明确提出某个级别,那不应该搜索其它级别.
2. 软标签+文本匹配: 混合bm25 和 向量相似度检索,可根据不同的查询问题赋权重,例如摘要类的更偏向量相似都比对/具体条款查询更偏bm25比对.
"""

import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
import os
import json
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor


# --------------------------
# 可配置参数
# --------------------------
ES_BASE_URL = "http://localhost:9200"
INDEX_KB = "kb_vector_store"
REQUEST_TIMEOUT = 30.0
EMBED_SERVICE_URL = "http://localhost:8000/embed"

# ES认证配置
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "password01")  # 根据你的ES配置调整

# 默认检索参数
DEFAULT_BM25_WEIGHT = 0.6
DEFAULT_VECTOR_WEIGHT = 0.4
DEFAULT_BM25_THRESHOLD = 0.7
DEFAULT_VECTOR_THRESHOLD = 0.7
DEFAULT_MAX_RESULTS = 500  # 支持大量结果检索

# 检索类型特定的参数配置
# 修改默认配置，降低向量阈值
RETRIEVAL_TYPE_CONFIG = {
    # 关键词搜索：主要依赖BM25
    "keyword_search": {
        "bm25_weight": 0.8,
        "vector_weight": 0.2,
        "bm25_threshold": 0.7,
        "vector_threshold": 0.3  # 降低阈值
    },
    # 语义搜索：主要依赖向量
    "semantic_search": {
        "bm25_weight": 0.2,
        "vector_weight": 0.8,
        "bm25_threshold": 0.7,
        "vector_threshold": 0.3  # 降低阈值
    },
    # 混合搜索：平衡两者
    "hybrid_search": {
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "bm25_threshold": 0.7,
        "vector_threshold": 0.3  # 降低阈值
    }
}


def _norm(v: Optional[str]) -> str:
    """标准化字符串"""
    if v is None:
        return ""
    s = v.strip()
    if s == "" or s.lower() == "null":
        return ""
    s = s.replace("—", "-")
    return s


def _post_embed(embed_url: str, texts: List[str]) -> List[List[float]]:
    """调用embedding服务"""
    try:
        # 绕过代理访问本地服务
        proxies = {
            'http': None,
            'https': None
        }
        resp = requests.post(embed_url, json=texts, timeout=REQUEST_TIMEOUT, proxies=proxies)
        resp.raise_for_status()
        data = resp.json()
        vectors = data.get("embeddings")
        if not isinstance(vectors, list):
            raise ValueError("Embedding 服务响应不包含 'embeddings' 列表")
        return vectors
    except Exception as e:
        print(f"Embedding服务调用失败: {e}")
        raise


# 数据结构定义
@dataclass
class RetrievalResult:
    """检索结果统一数据结构 """
    clause_key_en: str  # 条款标识符
    content: str  # 条款内容
    source_standard: str  # 来源标准
    identifier: str  # 标准标识符
    section_levels: Dict[str, str]  # level1-level5 章节层级
    intent_num: int  # 相关意图的intent num
    score: float = 0.0  # 分数
    retrieval_path: str = ""  # 检索路径
    applicability_level: str = ""  # 适用级别
    embedding_content: str = "" # 拼接的字段

@dataclass
class ESRetrievalParams:
    """ES检索参数"""
    origin_query: str
    rewritten_query: str
    retrieval_type: str  # keyword_search, semantic_search, hybrid_search
    standards: List[str]
    entities: Dict[str, List[str]]
    intent_num: int  # 添加意图编号
    bm25_weight: float = DEFAULT_BM25_WEIGHT
    vector_weight: float = DEFAULT_VECTOR_WEIGHT
    bm25_threshold: float = DEFAULT_BM25_THRESHOLD
    vector_threshold: float = DEFAULT_VECTOR_THRESHOLD
    max_results: int = DEFAULT_MAX_RESULTS
    standards_names: List[str] = None


class ESRetriever:
    """ES专用检索器"""
    
    def __init__(self, es_url: str = ES_BASE_URL, embed_url: str = EMBED_SERVICE_URL, 
                 username: str = ES_USERNAME, password: str = ES_PASSWORD):
        self.es_url = es_url
        self.embed_url = embed_url
        self.index_name = INDEX_KB
        self.auth = (username, password) if username and password else None
        
        # 测试ES连接
        try:
            # 绕过代理访问本地服务
            proxies = {'http': None, 'https': None}
            resp = requests.get(f"{self.es_url}/_cluster/health", timeout=5, auth=self.auth, proxies=proxies)
            if resp.status_code == 200:
                print("ES连接成功")
            else:
                print(f"ES连接异常: {resp.status_code}")
        except Exception as e:
            print(f"ES连接失败: {e}")
    
    def _build_base_filters(self, params: ESRetrievalParams) -> List[Dict]:
        """根据 regulation_standards 和 entities 构建基础过滤条件"""
        filters: List[Dict] = []

        # 标准过滤：identifier 或 source_standard 命中其一即可
        idents = params.standards or []
        names = params.standards_names or []
        if idents or names:
            if idents and names:
                filters.append({
                    "bool": {
                        "should": [
                            {"terms": {"identifier": idents}},
                            {"terms": {"source_standard": names}}
                        ],
                        "minimum_should_match": 1
                    }
                })
            elif idents:
                filters.append({"terms": {"identifier": idents}})
            elif names:
                filters.append({"terms": {"source_standard": names}})

        entities = params.entities or {}

        """
        如果 intent 中有 requirement_items，文档的 requirement_item 字段要么在指定的 req_items 列表中，要么为空字符串;
        如果 intent 中 requirement_items 是空，则不加过滤（匹配所有）
        """
        req_items = entities.get("requirement_items") or []
        if req_items:
            should_clauses = []
            should_clauses.append({"terms": {"requirement_item": req_items}})
            # 允许 ES 的 requirement_item 为空字符串也匹配
            should_clauses.append({"term": {"requirement_item": ""}})
            filters.append({
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1
                }
            })

        # applicability_level 过滤：第一级/第二级/第三级 -> 并集 + 通用 + 空值
        appl_levels = entities.get("applicability_level") or []
        if appl_levels:
            allowed = set()
            for lvl in appl_levels:
                if lvl in ("第一级", "第二级", "第三级"):
                    # allowed.update([lvl, "通用", ""])
                    allowed.update([lvl])
            if allowed:
                filters.append({"terms": {"applicability_level": list(allowed)}})

        return filters

    def _get_retrieval_config(self, retrieval_type: str) -> Dict[str, float]:
        """获取检索类型特定的配置"""
        config = RETRIEVAL_TYPE_CONFIG.get(retrieval_type, RETRIEVAL_TYPE_CONFIG["hybrid_search"])
        return {
            "bm25_weight": config["bm25_weight"],
            "vector_weight": config["vector_weight"],
            "bm25_threshold": config["bm25_threshold"],
            "vector_threshold": config["vector_threshold"]
        }

    def retrieve(self, params: ESRetrievalParams) -> List[RetrievalResult]:
        """主检索入口 - 所有检索类型都混合bm25和向量检索，只是权重和阈值不同"""
        print(f"开始检索意图{params.intent_num}，类型: {params.retrieval_type}")
        
        # 获取检索类型特定的配置
        type_config = self._get_retrieval_config(params.retrieval_type)
        
        # 使用混合检索，但根据检索类型调整参数
        return self._hybrid_search_with_config(params, type_config)

    def _hybrid_search_with_config(self, params: ESRetrievalParams, config: Dict[str, float]) -> List[RetrievalResult]:
        """使用配置参数的混合检索"""
        # 分别进行BM25和向量检索
        bm25_results = self._bm25_search(params, config["bm25_threshold"])
        vector_results = self._vector_search(params, config["vector_threshold"])
        
        # 合并结果并计算加权分数
        result_dict = {}
        
        # 处理BM25结果
        for result in bm25_results:
            key = result.clause_key_en
            result.score = result.score * config["bm25_weight"]
            result.retrieval_path = f"{params.retrieval_type}_bm25"
            result_dict[key] = result
        
        # 处理向量结果
        for result in vector_results:
            key = result.clause_key_en
            weighted_score = result.score * config["vector_weight"]
            
            if key in result_dict:
                # 合并分数
                result_dict[key].score += weighted_score
                result_dict[key].retrieval_path = f"{params.retrieval_type}_combined"
            else:
                result.score = weighted_score
                result.retrieval_path = f"{params.retrieval_type}_vector"
                result_dict[key] = result
        
        # 排序并返回
        final_results = list(result_dict.values())
        final_results.sort(key=lambda x: x.score, reverse=True)
        
        print(f"意图{params.intent_num} {params.retrieval_type}检索到 {len(final_results)} 条结果")
        return final_results

    def _bm25_search(self, params: ESRetrievalParams, threshold: float) -> List[RetrievalResult]:
        """BM25关键词检索 - 只针对embedding_content、applicability_level、requirement_item字段"""
        base_filters = self._build_base_filters(params)
    
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": f"{params.origin_query} {params.rewritten_query}",  # 移除 + 号，直接空格连接
                                "fields": [
                                    "requirement_item^20.0",        # 要求项 - 高权重
                                    "embedding_content^5.0",       # embedding内容 - 中权重
                                    "applicability_level^5.0",     # 适用级别 - 中权重

                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO"
                            }
                        }
                    ],
                    "filter": base_filters
                }
            },
            "size": params.max_results,
            "min_score": threshold
        }
        
        try:
            # 绕过代理访问本地服务
            proxies = {'http': None, 'https': None}
            resp = requests.post(
                f"{self.es_url}/{self.index_name}/_search",
                json=query,
                timeout=REQUEST_TIMEOUT,
                auth=self.auth,
                proxies=proxies
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for hit in data.get("hits", {}).get("hits", []):
                result = self._es_hit_to_result(hit, "bm25_search", params.intent_num)
                if result.score >= threshold:
                    results.append(result)

            print(f"意图{params.intent_num} BM25检索到 {len(results)} 条结果")
            return results

        except Exception as e:
            print(f"意图{params.intent_num} BM25检索失败: {e}")
            # 打印详细错误信息
            try:
                error_detail = resp.json() if 'resp' in locals() else "无响应"
                print(f"ES错误详情: {error_detail}")
            except:
                pass
            return []

    def _vector_search(self, params: ESRetrievalParams, threshold: float) -> List[RetrievalResult]:
        """向量语义检索"""
        try:
            instructed_query = f"请找到和下面问题中中具体意图最相关的法条文本，问题：{params.origin_query},你当前要查的具体意图为：{params.rewritten_query}"
            query_vectors = _post_embed(self.embed_url, [instructed_query])
            query_vector = query_vectors[0]
    
            base_filters = self._build_base_filters(params)
            
            # 使用 bool + must(script_score) + filter(base_filters) 限定评分范围
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "script_score": {
                                    "query": {"match_all": {}},
                                    "script": {
                                        "source": "cosineSimilarity(params.query_vector, 'content_embedding') + 1.0",
                                        "params": {"query_vector": query_vector}
                                    }
                                }
                            }
                        ],
                        "filter": base_filters
                    }
                },
                "size": params.max_results,
                "min_score": threshold + 1.0
            }
            
            # 绕过代理访问本地服务
            proxies = {'http': None, 'https': None}
            resp = requests.post(
                f"{self.es_url}/{self.index_name}/_search",
                json=query,
                timeout=REQUEST_TIMEOUT,
                auth=self.auth,
                proxies=proxies
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for hit in data.get("hits", {}).get("hits", []):
                result = self._es_hit_to_result(hit, "vector_search", params.intent_num)
                result.score = max(0.0, result.score - 1.0)
                if result.score >= threshold:
                    results.append(result)

            print(f"意图{params.intent_num} 向量检索到 {len(results)} 条结果")
            return results

        except Exception as e:
            print(f"意图{params.intent_num} 向量检索失败: {e}")
            # 打印详细错误信息
            try:
                error_detail = resp.json() if 'resp' in locals() else "无响应"
                print(f"ES错误详情: {error_detail}")
            except:
                pass
            return []
    
    def _es_hit_to_result(self, hit: Dict, retrieval_path: str, intent_num: int) -> RetrievalResult:
        """将ES命中结果转换为RetrievalResult"""
        source = hit.get("_source", {})
        
        return RetrievalResult(
            clause_key_en=_norm(source.get("clause_key_en", "")),
            content=_norm(source.get("content", "")),
            source_standard=_norm(source.get("source_standard", "")),
            identifier=_norm(source.get("identifier", "")),
            section_levels={
                "level1": _norm(source.get("section_level1", "")),
                "level2": _norm(source.get("section_level2", "")),
                "level3": _norm(source.get("section_level3", "")),
                "level4": _norm(source.get("section_level4", "")),
                "level5": _norm(source.get("section_level5", ""))
            },
            intent_num=intent_num,
            score=hit.get("_score", 0.0),
            retrieval_path=retrieval_path,
            applicability_level=_norm(source.get("applicability_level", "")),
            embedding_content = _norm(source.get("embedding_content", ""))
        )


def create_retriever() -> ESRetriever:
    """创建检索器实例"""
    return ESRetriever()


def _process_single_intent(retriever: ESRetriever, intent: Dict, origin_query: str = "") -> List[RetrievalResult]:
    """处理单个意图的检索"""
    try:
        # 解析regulation_standards
        rs_list = intent.get("regulation_standards") or []
        standard_identifiers: List[str] = rs_list  # 新格式直接是字符串列表
        standard_names: List[str] = intent.get("source_standard") or []  # 新格式中的source_standard
        
        rp = intent.get("retrieval_params") or {}
        
        # 获取检索类型特定的默认配置
        retrieval_type = _norm(intent.get("retrieval_type")) or "keyword_search"
        type_config = RETRIEVAL_TYPE_CONFIG.get(retrieval_type, RETRIEVAL_TYPE_CONFIG["hybrid_search"])
        
        bm25_weight = rp.get("bm25_weight", type_config["bm25_weight"])
        vector_weight = rp.get("vector_weight", type_config["vector_weight"])
        bm25_threshold = rp.get("bm25_threshold", type_config["bm25_threshold"])
        vector_threshold = rp.get("vector_threshold", type_config["vector_threshold"])
        max_results = rp.get("max_results", DEFAULT_MAX_RESULTS)

        params = ESRetrievalParams(
            origin_query=_norm(origin_query),  # 使用传入的 origin_query
            rewritten_query=_norm(intent.get("rewritten_query")),
            retrieval_type=retrieval_type,
            standards=standard_identifiers,
            standards_names=standard_names,
            entities=intent.get("entities") or {},
            intent_num=intent.get("num", 0),
            bm25_weight=bm25_weight,
            vector_weight=vector_weight,
            bm25_threshold=bm25_threshold,
            vector_threshold=vector_threshold,
            max_results=max_results,
        )
        
        results = retriever.retrieve(params)
        return results
        
    except Exception as e:
        print(f"处理意图{intent.get('num', 'unknown')}失败: {e}")
        return []


def search_clauses(intent_result: Dict) -> List[RetrievalResult]:
    """基于意图解析结果进行检索的便捷函数 - 支持并行处理多个意图"""
    retriever = create_retriever()
    
    intents = intent_result.get("intents", [])
    if not intents:
        return []
    
    # 从根级别获取 origin_query
    origin_query = intent_result.get("origin_query", "")
    
    all_results = []
    
    # 使用线程池并行处理多个意图
    with ThreadPoolExecutor(max_workers=min(len(intents), 5)) as executor:
        # 提交所有意图的检索任务，传递 origin_query
        future_to_intent = {
            executor.submit(_process_single_intent, retriever, intent, origin_query): intent 
            for intent in intents
        }
        
        # 收集结果
        for future in concurrent.futures.as_completed(future_to_intent):
            intent = future_to_intent[future]
            try:
                results = future.result()
                all_results.extend(results)
                print(f"意图{intent.get('num', 'unknown')}处理完成，获得{len(results)}条结果")
            except Exception as e:
                print(f"意图{intent.get('num', 'unknown')}处理异常: {e}")
    
    # 去重：同一个clause_key_en只保留分数最高的
    unique_results = {}
    for result in all_results:
        key = result.clause_key_en
        if key not in unique_results or result.score > unique_results[key].score:
            unique_results[key] = result
    
    final_results = list(unique_results.values())
    final_results.sort(key=lambda x: x.score, reverse=True)
    
    print(f"总计处理{len(intents)}个意图，最终去重后获得{len(final_results)}条结果")
    return final_results


# 辅助函数,测试看结果
def _save_detailed_results(test_case_idx: int, test_case_name: str, results: List[RetrievalResult]):
    """保存详细的检索结果到文件"""
    test_result_dir = os.path.join(os.path.dirname(__file__), "test_result")
    os.makedirs(test_result_dir, exist_ok=True)
    
    filename = os.path.join(test_result_dir, f"test_case_{test_case_idx}_{test_case_name.replace(' ', '_')}.txt")
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"测试用例 {test_case_idx}: {test_case_name}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("检索结果详细信息:\n")
        f.write("-" * 40 + "\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"\n结果 {i}:\n")
            f.write(f"  分数: {result.score:.6f}\n")
            f.write(f"  检索路径: {result.retrieval_path}\n")
            f.write(f"  意图编号: {result.intent_num}\n")
            f.write(f"  条款标识符: {result.clause_key_en}\n")
            f.write(f"  标准标识符: {result.identifier}\n")
            f.write(f"  来源标准: {result.source_standard}\n")
            f.write(f"  章节层级:\n")
            for level, value in result.section_levels.items():
                if value:  # 只显示非空的章节层级
                    f.write(f"    {level}: {value}\n")
            
            # 内容字段（截断显示前200字符）
            content_preview = result.content[:200] + "..." if len(result.content) > 200 else result.content
            f.write(f"  内容预览: {content_preview}\n")
            f.write("-" * 40 + "\n")
        
        f.write(f"\n总计检索到 {len(results)} 条结果\n")


def load_test_case_from_json(json_file_path: str) -> Dict:
    """从JSON文件加载测试用例"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载JSON文件失败 {json_file_path}: {e}")
        return {}


# 测试用例
if __name__ == "__main__":
    print("开始运行ES检索器测试用例...")
    
    # 从JSON文件读取测试用例
    script_dir = os.path.dirname(__file__)
    test_files = [
        # {
        #     "name": "intent_return1测试",
        #     "file_path": os.path.join(script_dir, "intent_return1.json")
        # },
        # {
        #     "name": "intent_return2测试", 
        #     "file_path": os.path.join(script_dir, "intent_return2.json")
        # },
        {
            "name": "intent_return3测试",
            "file_path": os.path.join(script_dir, "intent_return2.json")
        }
    ]
    
    for i, test_file in enumerate(test_files, 1):
        try:
            test_case_name = test_file["name"]
            print(f"\n执行测试用例 {i}: {test_case_name}")
            
            # 从JSON文件加载意图数据
            intent_data = load_test_case_from_json(test_file["file_path"])
            if not intent_data:
                print(f"测试用例 {i}: 无法加载JSON文件，跳过")
                continue
                
            results = search_clauses(intent_data)
            print(f"测试用例 {i}: 检索到 {len(results)} 条结果")
            
            # 保存详细结果到文件
            _save_detailed_results(i, test_case_name, results)
            print(f"详细结果已保存到 test_result 文件夹")
                
        except Exception as e:
            print(f"测试用例 {i} 执行失败: {e}")
    
    print("\n所有测试用例执行完毕, 详细检索结果已保存到 retrieval_server/test_result/ 文件夹中")