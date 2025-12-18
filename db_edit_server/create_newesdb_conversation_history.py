"""
创建 conversation_history 索引用于存储会话历史记录。

默认配置：
- ES_BASE_URL = http://localhost:9200
- INDEX_NAME  = conversation_history
"""

import time
from typing import Dict, List, Optional
import requests
import json
from datetime import datetime

# --------------------------
# 基本配置（与 es_offline_setup.py 保持一致）
# --------------------------

ES_BASE_URL = "http://localhost:9200"               # ES服务部署地址
ES_USERNAME = "elastic"                              # ES用户名
ES_PASSWORD = "password01"                           # ES密码
REQUEST_TIMEOUT = 30                                 # 每个 HTTP 请求超时时间（秒）
RETRY_TIMES = 3                                      # 简单重试次数（部分请求用）
RETRY_BACKOFF_SEC = 1.5                              # 重试退避间隔（秒）
# 一次写 ES 的文档条数,太大可能导致 HTTP 请求体过大、失败率上升，太小则请求次数增多
BULK_BATCH_SIZE = 512


def _es_index_exists(es_base_url: str, index_name: str) -> bool:
    """
    判断 ES 索引是否存在。
    Args:
        es_base_url: ES 基地址
        index_name: 索引名
    Returns:
        True: 存在；False: 不存在
    """
    url = f"{es_base_url}/{index_name}"
    resp = requests.head(url, auth=(ES_USERNAME, ES_PASSWORD), timeout=REQUEST_TIMEOUT)
    return resp.status_code == 200


def _es_delete_index(es_base_url: str, index_name: str) -> None:
    """
    删除 ES 索引（若存在）。
    Args:
        es_base_url: ES 基地址
        index_name: 索引名
    Raises:
        requests.RequestException: 网络错误或 ES 返回异常
    """
    if not _es_index_exists(es_base_url, index_name):
        return
    url = f"{es_base_url}/{index_name}"
    resp = requests.delete(url, auth=(ES_USERNAME, ES_PASSWORD), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()


def _es_put_index(es_base_url: str, index_name: str, mappings: Dict) -> None:
    """
    使用提供的 mappings 创建 ES 索引。
    Args:
        es_base_url: ES 基地址
        index_name: 索引名
        mappings: 索引的 JSON 映射定义（包含 "mappings": { ... }）
    Raises:
        requests.RequestException: 网络错误或 ES 返回异常
    """
    url = f"{es_base_url}/{index_name}"
    resp = requests.put(url, json=mappings, auth=(ES_USERNAME, ES_PASSWORD), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()


def _es_post_bulk(es_base_url: str, ndjson_payload: str) -> requests.Response:
    """
    向 Elasticsearch 发送 _bulk 批量写入请求。
    Args:
        es_base_url: ES 基地址，例如 http://host:9200
        ndjson_payload: NDJSON 格式字符串，形如：
            {"index": {"_index": "<index>"}}
            {"field":"value", ...}
            {"index": {"_index": "<index>"}}
            {"field":"value2", ...}
    Returns:
        requests.Response: 响应对象（包含批量写入结果）
    Raises:
        requests.RequestException: 网络错误或 ES 返回 4xx/5xx 异常时触发
    """
    url = f"{es_base_url}/_bulk"
    headers = {"Content-Type": "application/x-ndjson"}
    resp = requests.post(url, data=ndjson_payload.encode("utf-8"), headers=headers, auth=(ES_USERNAME, ES_PASSWORD), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


# --------------------------
# 索引创建：会话历史（conversation_history）
# --------------------------

def create_conversation_history_index(es_base_url: str, index_name: str = "conversation_history", force_recreate: bool = False) -> None:
    """
    创建会话历史索引 conversation_history。
    
    用途：存储会话历史记录，支持多轮对话上下文管理。
    采用Redis缓存优先、ES持久化备用的双层存储架构。
    
    字段说明：
    - user_id: keyword，用户ID，便于按用户过滤
    - session_id: keyword，会话ID，用于标识同一会话
    - message_id: keyword，消息ID，唯一标识每条消息
    - role: keyword，角色（user/assistant/system等）
    - content: text，消息内容
    - timestamp: date，时间戳，便于范围查询与排序
    - message_order: integer，消息在会话中的顺序
    
    Args:
        es_base_url: ES 基地址
        index_name: 索引名（默认 "conversation_history"）
        force_recreate: True 时若索引存在则删除后重建（会清空数据）
    Returns:
        None
    """
    if force_recreate:
        _es_delete_index(es_base_url, index_name)

    if _es_index_exists(es_base_url, index_name):
        print(f"索引 {index_name} 已存在，跳过创建。")
        return

    mappings = {
        "mappings": {
            "properties": {
                "user_id": {"type": "keyword"},
                "session_id": {"type": "keyword"},
                "message_id": {"type": "keyword"},
                "role": {"type": "keyword"},
                "content": {"type": "text"},
                "timestamp": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
                "message_order": {"type": "integer"}
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index": {
                "max_result_window": 50000  # 支持深度分页
            }
        }
    }
    
    _es_put_index(es_base_url, index_name, mappings)
    print(f"成功创建索引: {index_name}")


def insert_sample_conversation_data(es_base_url: str, index_name: str = "conversation_history") -> None:
    """
    插入一些示例会话数据用于测试。
    
    Args:
        es_base_url: ES 基地址
        index_name: 索引名
    """
    sample_data = [
        {
            "user_id": "user_001",
            "session_id": "session_001",
            "message_id": "msg_001",
            "role": "user",
            "content": "你好，我想了解一下网络安全相关的标准要求。",
            "timestamp": datetime.now().isoformat(),
            "message_order": 1
        },
        {
            "user_id": "user_001",
            "session_id": "session_001",
            "message_id": "msg_002",
            "role": "assistant",
            "content": "您好！我可以帮您了解网络安全相关的标准要求。请问您具体想了解哪个方面的内容？比如等级保护、密码应用、安全管理等？",
            "timestamp": datetime.now().isoformat(),
            "message_order": 2
        },
        {
            "user_id": "user_001",
            "session_id": "session_001",
            "message_id": "msg_003",
            "role": "user",
            "content": "我想了解等级保护的基本要求。",
            "timestamp": datetime.now().isoformat(),
            "message_order": 3
        },
        {
            "user_id": "user_002",
            "session_id": "session_002",
            "message_id": "msg_004",
            "role": "user",
            "content": "请介绍一下密码应用的相关标准。",
            "timestamp": datetime.now().isoformat(),
            "message_order": 1
        }
    ]
    
    # 构建 NDJSON 批量插入数据
    ndjson_lines: List[str] = []
    for doc in sample_data:
        ndjson_lines.append(f'{{"index": {{"_index": "{index_name}"}}}}')
        ndjson_lines.append(json.dumps(doc, ensure_ascii=False))
    
    ndjson_payload = "\n".join(ndjson_lines) + "\n"
    
    try:
        resp = _es_post_bulk(es_base_url, ndjson_payload)
        result = resp.json()
        if result.get("errors"):
            print("WARN: Bulk API 返回部分错误，请检查响应明细。")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"成功插入 {len(sample_data)} 条示例会话数据。")
    except Exception as e:
        print(f"插入示例数据时发生错误: {e}")


def query_conversation_by_session(es_base_url: str, index_name: str, session_id: str) -> List[Dict]:
    """
    根据 session_id 查询会话历史记录。
    
    Args:
        es_base_url: ES 基地址
        index_name: 索引名
        session_id: 会话ID
    Returns:
        List[Dict]: 按 message_order 排序的消息列表
    """
    url = f"{es_base_url}/{index_name}/_search"
    query = {
        "query": {
            "term": {
                "session_id": session_id
            }
        },
        "sort": [
            {"message_order": {"order": "asc"}}
        ],
        "size": 1000  # 假设单个会话不超过1000条消息
    }
    
    try:
        resp = requests.post(url, json=query, auth=(ES_USERNAME, ES_PASSWORD), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        result = resp.json()
        
        hits = result.get("hits", {}).get("hits", [])
        messages = [hit["_source"] for hit in hits]
        return messages
    except Exception as e:
        print(f"查询会话历史时发生错误: {e}")
        return []


def query_user_sessions(es_base_url: str, index_name: str, user_id: str) -> List[str]:
    """
    查询用户的所有会话ID。
    
    Args:
        es_base_url: ES 基地址
        index_name: 索引名
        user_id: 用户ID
    Returns:
        List[str]: 会话ID列表
    """
    url = f"{es_base_url}/{index_name}/_search"
    query = {
        "query": {
            "term": {
                "user_id": user_id
            }
        },
        "aggs": {
            "sessions": {
                "terms": {
                    "field": "session_id",
                    "size": 1000
                }
            }
        },
        "size": 0  # 只要聚合结果，不要文档
    }
    
    try:
        resp = requests.post(url, json=query, auth=(ES_USERNAME, ES_PASSWORD), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        result = resp.json()
        
        buckets = result.get("aggregations", {}).get("sessions", {}).get("buckets", [])
        session_ids = [bucket["key"] for bucket in buckets]
        return session_ids
    except Exception as e:
        print(f"查询用户会话时发生错误: {e}")
        return []


def main():
    """
    命令行入口：
    - 创建 conversation_history 索引
    - 可选择插入示例数据
    - 提供基本的查询测试功能
    """
    args = type("Args", (), {
        "es": ES_BASE_URL,
        "index": "conversation_history",
        "force": True,           # 强制重建索引
        "insert_sample": True,   # 插入示例数据
        "test_query": True,      # 测试查询功能
    })()
    
    print(f"[Conversation History Setup] ES地址: {args.es}, 索引: {args.index}")
    
    # 1. 创建索引
    create_conversation_history_index(args.es, args.index, force_recreate=args.force)
    
    # 2. 插入示例数据（可选）
    if args.insert_sample:
        print("\n插入示例会话数据...")
        insert_sample_conversation_data(args.es, args.index)
    
    # 3. 测试查询功能（可选）
    if args.test_query:
        print("\n测试查询功能...")
        
        # 查询用户的所有会话
        user_sessions = query_user_sessions(args.es, args.index, "user_001")
        print(f"用户 user_001 的会话列表: {user_sessions}")
        
        # 查询特定会话的历史记录
        if user_sessions:
            session_id = user_sessions[0]
            messages = query_conversation_by_session(args.es, args.index, session_id)
            print(f"\n会话 {session_id} 的历史记录:")
            for msg in messages:
                print(f"  [{msg['role']}] {msg['content'][:50]}...")
    
    print("\nconversation_history 索引初始化完成。")


if __name__ == "__main__":
    main()