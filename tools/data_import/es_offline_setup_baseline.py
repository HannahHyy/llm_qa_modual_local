"""
1. 创建es索引：
（1）`kb_vector_store` (法规知识向量库)
（2）`user_memory` (用户长期记忆库) # 暂时没用到
2. 从 CSV 离线导入数据到 Elasticsearch，包括knowledgedata/测评要求.csv, knowledgedata/基本要求.csv
3. 调用 embedding 模型生成 content_embedding。
默认配置：
- ES_BASE_URL = http://localhost:9200
- EMBED_URL   = http://localhost:8000/embed
- INDEX_NAME  = kb_vector_store, user_memory
- EMBEDDING_DIM = 1024
"""

import csv
import time
from typing import Dict, List, Iterable
import requests
import json
import hashlib

# --------------------------
# 基本配置（不依赖环境变量）
# --------------------------

ES_BASE_URL = "http://localhost:9200"               # ES服务部署地址
ES_USERNAME = "elastic"                              # ES用户名
ES_PASSWORD = "password01"                           # ES密码
EMBED_SERVICE_URL = "http://localhost:8000/embed"  # Embedding服务接口地址
EMBEDDING_DIM = 1024                             # 向量维度，需与 embedding 模型输出一致
REQUEST_TIMEOUT = 30                             # 每个 HTTP 请求超时时间（秒）
RETRY_TIMES = 3                                  # 简单重试次数（部分请求用）
RETRY_BACKOFF_SEC = 1.5                          # 重试退避间隔（秒）
# 一次请求 embedding 的文本条数, 太大可能影响服务稳定性，太小则请求次数增多
EMBED_BATCH_SIZE = 4
# 一次写 ES 的文档条数,太大可能导致 HTTP 请求体过大、失败率上升，太小则请求次数增多
BULK_BATCH_SIZE = 512


def _batch(iterable: Iterable, size: int) -> Iterable[List]:
    """
    Args:
        iterable: 任意可迭代对象
        size: 每批大小（正整数）
    Returns:
        逐批返回列表，每个列表最多 size 个元素
    """
    batch_buf = []
    for item in iterable:
        batch_buf.append(item)
        if len(batch_buf) >= size:
            yield batch_buf
            batch_buf = []
    if batch_buf:
        yield batch_buf


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
# 索引创建：知识库（kb_vector_store）
# --------------------------

def create_kb_index(es_base_url: str, index_name: str = "kb_vector_store", force_recreate: bool = False) -> None:
    """
    创建知识库向量索引 kb_vector_store。
    Args:
        es_base_url: ES 基地址
        index_name: 索引名（默认 "kb_vector_store"）
        force_recreate: True 时若索引存在则删除后重建（会清空数据）
    Returns:
        None
    """
    if force_recreate:
        _es_delete_index(es_base_url, index_name)

    if _es_index_exists(es_base_url, index_name):
        return

    mappings = {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "content": {"type": "text"},
                "source_standard": {"type": "keyword"},
                "identifier": {"type": "keyword"},
                "requirement_item": {"type": "keyword"},
                "section_level1": {"type": "keyword"},
                "section_level2": {"type": "keyword"},
                "section_level3": {"type": "keyword"},
                "section_level4": {"type": "keyword"},
                "section_level5": {"type": "keyword"},
                "applicability_level": {"type": "keyword"},
                # 新增：用于 ES/Neo4j 对齐的英文（ASCII）标识符
                "clause_key_en": {"type": "keyword"},
                "requirement_item_en": {"type": "keyword"},
                "applicability_level_en": {"type": "keyword"},
                # 用于向量生成的拼接文本
                "embedding_content": {"type": "text"},
                # 向量字段：内容的 embedding，1024 维，余弦相似度
                "content_embedding": {
                    "type": "dense_vector",
                    "dims": EMBEDDING_DIM,
                    "index": True,
                    "similarity": "cosine"
                }
            }
        }
    }
    _es_put_index(es_base_url, index_name, mappings)


# --------------------------
# 索引创建：用户长期记忆库（user_memory）
# --------------------------

def create_user_memory_index(es_base_url: str, index_name: str = "user_memory", force_recreate: bool = False) -> None:
    """
    创建用户长期记忆库索引 user_memory。

    字段建议：
    - memory_id: keyword，记忆条目 ID（可选，若不提供则 ES 自动生成）
    - user_id: keyword，用户 ID，便于按用户过滤
    - content: text，记忆正文文本
    - content_embedding: dense_vector，维度与模型一致（1024），用于语义检索
    - source: keyword，来源（人工/系统/会话等），便于过滤
    - created_at / updated_at: date，时间戳，便于范围查询与排序

    Args:
        es_base_url: ES 基地址
        index_name: 索引名（默认 "user_memory"）
        force_recreate: True 时若索引存在则删除后重建（会清空数据）

    Returns:
        None
    """
    if force_recreate:
        _es_delete_index(es_base_url, index_name)

    if _es_index_exists(es_base_url, index_name):
        return

    mappings = {
        "mappings": {
            "properties": {
                "memory_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "content": {"type": "text"},
                "content_embedding": {
                    "type": "dense_vector",
                    "dims": EMBEDDING_DIM,
                    "index": True,
                    "similarity": "cosine"
                },
                "source": {"type": "keyword"},
                "created_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
                "updated_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"}
            }
        }
    }
    _es_put_index(es_base_url, index_name, mappings)


# --------------------------
# Embedding 请求
# --------------------------

def _post_embed(embed_url: str, texts: List[str]) -> List[List[float]]:
    """
    调用 Embedding 服务生成向量。
    - POST {embed_url}
    - 请求体: 直接为字符串数组 ["text1", "text2", ...]（不是 {"texts": [...]}）
    - 响应体: {"embeddings": [[...], [...], ...]} —— 与输入文本顺序一一对应

    Args:
        embed_url: Embedding 服务 /embed 的完整地址
        texts: 待编码的文本列表

    Returns:
        List[List[float]]: 每个文本对应的向量列表

    """
    # 绕过代理访问本地服务
    proxies = {'http': None, 'https': None}
    resp = requests.post(embed_url, json=texts, timeout=REQUEST_TIMEOUT, proxies=proxies)
    resp.raise_for_status()
    data = resp.json()
    vectors = data.get("embeddings")
    if not isinstance(vectors, list):
        raise ValueError("Embedding 服务响应不包含 'embeddings' 列表")
    return vectors


def embed_texts(embed_url: str, texts: List[str], batch_size: int = EMBED_BATCH_SIZE) -> List[List[float]]:
    """
    分批请求 Embedding，返回与 texts 顺序对应的向量列表。
    Args:
        embed_url: Embedding 服务地址
        texts: 待编码文本列表
        batch_size: 每批请求条数
    Returns:
        List[List[float]]: 全量向量列表，顺序与 texts 一致
    """
    all_vectors: List[List[float]] = []
    for batch in _batch(texts, batch_size):
        vectors = _post_embed(embed_url, batch)
        if len(vectors) != len(batch):
            raise ValueError("Embedding 服务返回的向量数量与请求文本数量不匹配")
        all_vectors.extend(vectors)
        # 适当放松速率，减轻服务压力
        time.sleep(0.05)
    return all_vectors


# --------------------------
# KB 数据导入（CSV -> ES）
# --------------------------

KB_DEFAULT_CSVS = [
    "knowledgedata/测评要求.csv",
    "knowledgedata/基本要求.csv",
]


def _get_field(row: Dict[str, str], candidates: List[str]) -> str:
    """
    在 CSV 行中按候选名查找字段，返回第一个存在且非空的值（否则返回空字符串）。
    现在仅支持英文列名的精确匹配，不做模糊/归一化。
    - 额外规则：将 'null'（大小写不敏感）视为空，不参与拼接。
    """
    for name in candidates:
        val = row.get(name)
        if val is not None:
            s = str(val).strip()
            if s == "":
                continue
            if s.lower() == "null":
                continue
            return s
    return ""


def _build_embedding_content(row: Dict[str, str]) -> str:
    """
    按规则构造 embedding_content：
    标准 + source_standard + identifier + 的章节部分 + level1.+.level5（有值才拼接） + 的具体内容如下： + content
    """
    source_standard = _get_field(row, ["source_standard"])
    identifier = _get_field(row, ["identifier"])
    level1 = _get_field(row, ["section_level1"])
    level2 = _get_field(row, ["section_level2"])
    level3 = _get_field(row, ["section_level3"])
    level4 = _get_field(row, ["section_level4"])
    level5 = _get_field(row, ["section_level5"])
    content = _get_field(row, ["content"])

    prefix_parts = [p for p in ["标准：", source_standard, identifier] if p]
    prefix = "".join(prefix_parts)

    chapter_parts = [p for p in [level2, level3, level4, level5] if p]
    chapter = "-".join(chapter_parts)

    header_segments = []
    if prefix:
        header_segments.append(prefix)
    if chapter:
        header_segments.append(f"的章节部分 {chapter}")
    header = " ".join(header_segments)

    if header and content:
        return f"{header} 的具体内容如下：{content}"
    if content:
        return content
    return header


def _read_csv_rows(csv_paths: List[str]) -> List[Dict[str, str]]:
    """
    读取多个 CSV 文件，返回合并后的行列表。
    Args:
        csv_paths: CSV 文件路径列表
    Returns:
        List[Dict[str, str]]: 每个元素是“字段名 -> 值”的字典（按文件顺序合并）
    """
    rows: List[Dict[str, str]] = []
    for path in csv_paths:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows


def ingest_kb_csvs(
    es_base_url: str,
    index_name: str,
    embed_url: str,
    csv_paths: List[str] = KB_DEFAULT_CSVS,
    embed_batch_size: int = EMBED_BATCH_SIZE,
    bulk_batch_size: int = BULK_BATCH_SIZE
) -> None:
    """
    将 CSV 数据导入到 kb_vector_store：
    - 构造 embedding_content
    - 请求 embedding 服务生成 content_embedding
    - 与原始字段一起批量写入 ES

    Args:
        es_base_url: ES 基地址
        index_name: 目标索引表名"kb_vector_store"）
        embed_url: Embedding 服务地址
        csv_paths: CSV 文件列表，默认 ["knowledgedata/测评要求.csv", "knowledgedata/基本要求.csv"]
        embed_batch_size: 每批请求 embedding 的数量
        bulk_batch_size: 每批写 ES 的文档数量
    Raises:
        requests.RequestException: 网络错误或服务异常
        ValueError: 响应体格式异常或数据不匹配
    """
    rows = _read_csv_rows(csv_paths)

    # 构造 embedding_content 列表
    embedding_texts = [_build_embedding_content(row) for row in rows]
    # 批量请求向量
    vectors = embed_texts(embed_url, embedding_texts, batch_size=embed_batch_size)

    if len(vectors) != len(rows):
        raise ValueError("生成的向量数量与输入行数不匹配")

    # 组装 ES 文档（英文字段名）
    docs: List[Dict] = []
    for row, emb_text, vec in zip(rows, embedding_texts, vectors):
        # 取原始字段
        row_id = _get_field(row, ["cp_id", "basic_id"])
        content = _get_field(row, ["content"])
        source_standard = _get_field(row, ["source_standard"])
        identifier = _get_field(row, ["identifier"])
        requirement_item = _get_field(row, ["requirement_item"])
        level1 = _get_field(row, ["section_level1"])
        level2 = _get_field(row, ["section_level2"])
        level3 = _get_field(row, ["section_level3"])
        level4 = _get_field(row, ["section_level4"])
        level5 = _get_field(row, ["section_level5"])
        applicability_level = _get_field(row, ["applicability_level"])

        # 生成统一英文（ASCII）标识符（使用稳定 md5 前缀，避免额外依赖）
        # 修改为：source_standard + identifier + 最小标题（取 level1..level5 中最深层非空者，且将 CSV 中的 "null" 视为缺失）
        def _norm(v: str) -> str:
            if not v:
                return ""
            s = v.strip()
            return "" if s.lower() == "null" else s

        levels = [_norm(level1), _norm(level2), _norm(level3), _norm(level4), _norm(level5)]
        smallest_title = ""
        for lv in reversed(levels):
            if lv:
                smallest_title = lv
                break

        id_part = _norm(identifier).replace(" ", "")
        title_part = smallest_title.replace(" ", "") if smallest_title else ""
        clause_basis = f"{source_standard}|{id_part}|{title_part}"
        clause_key_en = "ck_" + hashlib.md5(clause_basis.encode("utf-8")).hexdigest()[:12]

        # 2) requirement_item_en: 基于 requirement_item 文本
        requirement_item_en = ""
        if requirement_item:
            requirement_item_en = "ri_" + hashlib.md5(requirement_item.encode("utf-8")).hexdigest()[:12]

        # 3) applicability_level_en: 基于 applicability_level 文本
        applicability_level_en = ""
        if applicability_level:
            applicability_level_en = "al_" + hashlib.md5(applicability_level.encode("utf-8")).hexdigest()[:12]

        doc = {
            "id": row_id,
            "content": content,
            "source_standard": source_standard,
            "identifier": identifier,
            "requirement_item": requirement_item,
            "section_level1": level1,
            "section_level2": level2,
            "section_level3": level3,
            "section_level4": level4,
            "section_level5": level5,
            "applicability_level": applicability_level,

            # 新增对齐字段（英文/ASCII）
            "clause_key_en": clause_key_en,
            "requirement_item_en": requirement_item_en,
            "applicability_level_en": applicability_level_en,

            # 拼接文本与向量
            "embedding_content": emb_text,
            "content_embedding": vec,
        }
        docs.append(doc)

    # NDJSON 批量写入
    for chunk in _batch(docs, bulk_batch_size):
        ndjson_lines: List[str] = []
        for doc in chunk:
            ndjson_lines.append(f'{{"index": {{"_index": "{index_name}"}}}}')
            ndjson_lines.append(json.dumps(doc, ensure_ascii=False))
        ndjson_payload = "\n".join(ndjson_lines) + "\n"
        resp = _es_post_bulk(es_base_url, ndjson_payload)
        result = resp.json()
        if result.get("errors"):
            print("WARN: Bulk API 返回部分错误，请检查响应明细。")


def main():
    """
    命令行入口：
    - 默认：创建 kb_vector_store 与 user_memory 两个索引，并导入 KB CSV 数据
    - 可通过参数指定 ES 地址、Embedding 服务地址、是否强制重建索引等
    """
    args = type("Args", (), {
        "es": ES_BASE_URL,
        "embed": EMBED_SERVICE_URL,
        "kb_index": "kb_vector_store",
        "user_index": "user_memory",
        "force_kb": True,      # 强制重建 KB 索引
        "force_user": True,    # 强制重建 user_memory 索引
        "skip_ingest": False,
        "csv": KB_DEFAULT_CSVS,       # ["knowledgedata/测评要求.csv", "knowledgedata/基本要求.csv"]
        "embed_batch": EMBEDDING_DIM if False else EMBED_BATCH_SIZE,  # 保持原默认
        "bulk_batch": BULK_BATCH_SIZE,
    })()
    print(f"[One-Click] es={args.es}, embed={args.embed}, csv={args.csv}")

    create_kb_index(args.es, args.kb_index, force_recreate=args.force_kb)
    create_user_memory_index(args.es, args.user_index, force_recreate=args.force_user)

    if not args.skip_ingest:
        ingest_kb_csvs(
            es_base_url=args.es,
            index_name=args.kb_index,
            embed_url=args.embed,
            csv_paths=args.csv,
            embed_batch_size=args.embed_batch,
            bulk_batch_size=args.bulk_batch,
        )
        print("KB 数据导入完成。")
    else:
        print("已跳过 KB 数据导入。")

    print("离线初始化脚本执行完成。")


if __name__ == "__main__":
    main()
