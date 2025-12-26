import csv
import time
import json
import hashlib
import argparse
from typing import Dict, List, Iterable
import requests

# --------------------------
# 基本配置（与离线脚本保持一致）
# --------------------------
ES_BASE_URL = "http://localhost:9200"
ES_USERNAME = "elastic"
ES_PASSWORD = "password01"
EMBED_SERVICE_URL = "http://localhost:8000/embed"
EMBEDDING_DIM = 1024
REQUEST_TIMEOUT = 30
EMBED_BATCH_SIZE = 4
BULK_BATCH_SIZE = 512

# 默认追加导入的两个新 CSV 文件
DEFAULT_CSVS = [
    r"d:\\es-llm\\knowledgedata\\等保测评管理办法.csv",
    r"d:\\es-llm\\knowledgedata\\等保管理办法.csv",
]


def _batch(iterable: Iterable, size: int) -> Iterable[List]:
    buf = []
    for item in iterable:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def _get_field(row: Dict[str, str], candidates: List[str]) -> str:
    for name in candidates:
        val = row.get(name)
        if val is not None:
            s = str(val).strip()
            if s == "" or s.lower() == "null":
                continue
            return s
    return ""


def _build_embedding_content(row: Dict[str, str]) -> str:
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
    rows: List[Dict[str, str]] = []
    for path in csv_paths:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows


def _post_embed(embed_url: str, texts: List[str]) -> List[List[float]]:
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
    all_vectors: List[List[float]] = []
    for batch in _batch(texts, batch_size):
        vectors = _post_embed(embed_url, batch)
        if len(vectors) != len(batch):
            raise ValueError("Embedding 服务返回的向量数量与请求文本数量不匹配")
        all_vectors.extend(vectors)
        time.sleep(0.05)
    return all_vectors


def _build_doc(row: Dict[str, str], emb_text: str, vec: List[float]) -> Dict:
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
    md5hex = hashlib.md5(clause_basis.encode("utf-8")).hexdigest()

    clause_key_en = "ck_" + md5hex[:12]
    requirement_item_en = "ri_" + hashlib.md5(requirement_item.encode("utf-8")).hexdigest()[:12] if requirement_item else ""
    applicability_level_en = "al_" + hashlib.md5(applicability_level.encode("utf-8")).hexdigest()[:12] if applicability_level else ""

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
        "clause_key_en": clause_key_en,
        "requirement_item_en": requirement_item_en,
        "applicability_level_en": applicability_level_en,
        "embedding_content": emb_text,
        "content_embedding": vec,
    }
    es_id = clause_key_en  # 使用稳定 md5 前缀作为 _id，避免重复
    return {"_id": es_id, "_source": doc}


def _es_post_bulk_upsert(es_base_url: str, index_name: str, docs: List[Dict]) -> Dict:
    lines: List[str] = []
    for item in docs:
        es_id = item["_id"]
        doc = item["_source"]
        lines.append(json.dumps({"update": {"_index": index_name, "_id": es_id}}, ensure_ascii=False))
        lines.append(json.dumps({"doc": doc, "doc_as_upsert": True}, ensure_ascii=False))
    payload = "\n".join(lines) + "\n"
    url = f"{es_base_url}/_bulk"
    headers = {"Content-Type": "application/x-ndjson"}
    resp = requests.post(url, data=payload.encode("utf-8"), headers=headers, auth=(ES_USERNAME, ES_PASSWORD), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def add_csvs_to_index(
    es_base_url: str,
    index_name: str,
    embed_url: str,
    csv_paths: List[str],
    embed_batch_size: int = EMBED_BATCH_SIZE,
    bulk_batch_size: int = BULK_BATCH_SIZE,
) -> None:
    rows = _read_csv_rows(csv_paths)
    texts = [_build_embedding_content(r) for r in rows]
    vectors = embed_texts(embed_url, texts, batch_size=embed_batch_size)
    if len(vectors) != len(rows):
        raise ValueError("生成的向量数量与输入行数不匹配")

    docs: List[Dict] = []
    for r, t, v in zip(rows, texts, vectors):
        docs.append(_build_doc(r, t, v))

    for chunk in _batch(docs, bulk_batch_size):
        result = _es_post_bulk_upsert(es_base_url, index_name, chunk)
        if result.get("errors"):
            print("WARN: Bulk Upsert 返回部分错误，请检查明细。")


def main():
    parser = argparse.ArgumentParser(description="向已存在的 ES 索引追加导入 CSV 数据（自动向量化、去重 upsert）")
    parser.add_argument("--es", default=ES_BASE_URL, help="ES 基地址，如 http://host:9200")
    parser.add_argument("--index", default="kb_vector_store", help="目标索引名")
    parser.add_argument("--embed", default=EMBED_SERVICE_URL, help="Embedding 服务地址，如 http://host:8000/embed")
    parser.add_argument("--csv", nargs="+", default=DEFAULT_CSVS, help="一个或多个 CSV 文件路径")
    parser.add_argument("--embed-batch", type=int, default=EMBED_BATCH_SIZE, help="每批请求 Embedding 的数量")
    parser.add_argument("--bulk-batch", type=int, default=BULK_BATCH_SIZE, help="每批写入 ES 的文档数量")
    args = parser.parse_args()

    print(f"[Add-Data] es={args.es}, index={args.index}, embed={args.embed}")
    print(f"[Add-Data] csv={args.csv}")

    add_csvs_to_index(
        es_base_url=args.es,
        index_name=args.index,
        embed_url=args.embed,
        csv_paths=args.csv,
        embed_batch_size=args.embed_batch,
        bulk_batch_size=args.bulk_batch,
    )
    print("增量导入完成。")


if __name__ == "__main__":
    main()