"""
调试脚本：查看ES索引实际字段结构和值
"""
import requests
import json
import os

# 禁用代理
proxies = {'http': None, 'https': None}
old_proxies = {}
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    old_proxies[key] = os.environ.pop(key, None)

# ES连接信息
url = "http://localhost:9200"
auth = ("elastic", "password01")

# 检查连接
try:
    response = requests.get(f"{url}/_cluster/health", auth=auth, proxies=proxies, timeout=10)
    response.raise_for_status()
    print("✓ ES连接成功\n")
except Exception as e:
    print(f"无法连接到ES: {e}")
    exit(1)

# 获取索引mapping
index_name = "kb_vector_store"
try:
    response = requests.get(f"{url}/{index_name}/_mapping", auth=auth, proxies=proxies, timeout=10)
    response.raise_for_status()
    mapping = response.json()
    print(f"=== {index_name} 索引Mapping ===")
    properties = mapping[index_name]['mappings'].get('properties', {})
    # 只显示关键字段
    key_fields = ['identifier', 'source_standard', 'requirement_item', 'applicability_level', 'embedding_content', 'content']
    for field in key_fields:
        if field in properties:
            print(f"{field}: {json.dumps(properties[field], ensure_ascii=False)}")
    print("\n")
except Exception as e:
    print(f"获取mapping失败: {e}\n")

# 查询样本数据
print(f"=== {index_name} 样本数据 ===")
try:
    # 查询包含"等保"或"三级"的文档
    search_body = {
        "query": {
            "bool": {
                "should": [
                    {"match": {"content": "等保"}},
                    {"match": {"applicability_level": "三级"}},
                    {"match": {"identifier": "GB/T 22239-2019"}}
                ],
                "minimum_should_match": 1
            }
        },
        "size": 3
    }

    response = requests.post(
        f"{url}/{index_name}/_search",
        json=search_body,
        auth=auth,
        proxies=proxies,
        timeout=10
    )
    response.raise_for_status()
    result = response.json()

    hits = result.get('hits', {}).get('hits', [])
    print(f"找到 {len(hits)} 条文档\n")

    for i, hit in enumerate(hits, 1):
        source = hit['_source']
        print(f"--- 文档 {i} (score: {hit['_score']}) ---")
        print(f"identifier: {source.get('identifier', 'N/A')}")
        print(f"source_standard: {source.get('source_standard', 'N/A')}")
        print(f"requirement_item: {source.get('requirement_item', 'N/A')}")
        print(f"applicability_level: {source.get('applicability_level', 'N/A')}")
        print(f"embedding_content: {source.get('embedding_content', 'N/A')[:100]}..." if source.get('embedding_content') else "embedding_content: N/A")
        print(f"content: {source.get('content', 'N/A')[:100]}..." if source.get('content') else "content: N/A")
        print()

except Exception as e:
    print(f"查询失败: {e}")
    import traceback
    traceback.print_exc()

# 测试当前查询逻辑
print("\n=== 测试当前查询逻辑 ===")
try:
    # 模拟当前的查询
    query_text = "等保 三级 网络建设要求"
    identifiers = ["GB/T 22239-2019", "网络安全等级保护条例"]
    standard_names = ["信息安全技术 网络安全等级保护基本要求"]
    appl_levels = ["三级"]
    req_items = ["物理安全", "访问控制", "安全审计", "入侵防范"]

    filter_clauses = []

    # 标准过滤
    if identifiers or standard_names:
        standard_should = []
        if identifiers:
            standard_should.append({"terms": {"identifier": identifiers}})
        if standard_names:
            standard_should.append({"terms": {"source_standard": standard_names}})
        filter_clauses.append({
            "bool": {
                "should": standard_should,
                "minimum_should_match": 1
            }
        })

    # requirement_items 过滤
    if req_items:
        filter_clauses.append({
            "bool": {
                "should": [
                    {"terms": {"requirement_item": req_items}},
                    {"term": {"requirement_item": ""}}
                ],
                "minimum_should_match": 1
            }
        })

    # applicability_level 过滤
    if appl_levels:
        filter_clauses.append({"terms": {"applicability_level": appl_levels}})

    es_query = {
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query_text,
                            "fields": [
                                "requirement_item^20.0",
                                "embedding_content^5.0",
                                "applicability_level^5.0"
                            ],
                            "type": "best_fields",
                            "fuzziness": "AUTO"
                        }
                    }
                ],
                "filter": filter_clauses if filter_clauses else []
            }
        },
        "size": 10
    }

    print(f"查询文本: {query_text}")
    print(f"Filters: {len(filter_clauses)} 个")
    print(f"查询DSL: {json.dumps(es_query, indent=2, ensure_ascii=False)}")

    response = requests.post(
        f"{url}/{index_name}/_search",
        json=es_query,
        auth=auth,
        proxies=proxies,
        timeout=10
    )
    response.raise_for_status()
    result = response.json()
    hits = result.get('hits', {}).get('hits', [])
    print(f"\n结果: {len(hits)} 条")

    if hits:
        for i, hit in enumerate(hits[:3], 1):
            source = hit['_source']
            print(f"\n--- 结果 {i} (score: {hit['_score']}) ---")
            print(f"identifier: {source.get('identifier')}")
            print(f"requirement_item: {source.get('requirement_item')}")
            print(f"applicability_level: {source.get('applicability_level')}")
    else:
        print("\n❌ 没有结果！")

        # 尝试逐步放宽条件
        print("\n=== 尝试不带filter的查询 ===")
        simple_query = {
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": [
                        "requirement_item^20.0",
                        "embedding_content^5.0",
                        "applicability_level^5.0"
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            },
            "size": 5
        }
        response = requests.post(
            f"{url}/{index_name}/_search",
            json=simple_query,
            auth=auth,
            proxies=proxies,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        hits = result.get('hits', {}).get('hits', [])
        print(f"不带filter结果: {len(hits)} 条")

        if hits:
            for i, hit in enumerate(hits[:2], 1):
                source = hit['_source']
                print(f"\n--- 结果 {i} (score: {hit['_score']}) ---")
                print(f"identifier: {source.get('identifier')}")
                print(f"source_standard: {source.get('source_standard')}")
                print(f"requirement_item: {source.get('requirement_item')}")
                print(f"applicability_level: {source.get('applicability_level')}")

except Exception as e:
    print(f"测试查询失败: {e}")
    import traceback
    traceback.print_exc()
