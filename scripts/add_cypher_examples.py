"""
添加Cypher示例到ES索引

这个脚本向kb_vector_store索引添加示例Cypher查询,用于LLM生成Cypher时的参考
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.clients.es_client import ESClient
from core.config import get_settings
from core.logging import logger


def add_cypher_examples():
    """添加Cypher示例到ES"""

    settings = get_settings()
    es_client = ESClient(settings.es)

    # Cypher示例数据
    examples = [
        {
            "question": "河北单位建设了哪些网络?",
            "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS '河北' RETURN u.name, n.name"
        },
        {
            "question": "哪些单位建设了网络?",
            "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) RETURN u.name, n.name"
        },
        {
            "question": "北京单位有哪些系统?",
            "answer": "MATCH (u:Unit)-[:SOFTWAREUNIT_SYSTEM]->(s:SYSTEM) WHERE u.name CONTAINS '北京' RETURN u.name, s.name"
        },
        {
            "question": "网络的安全产品有哪些?",
            "answer": "MATCH (n:Netname)-[:SECURITY_NET]->(s:Safeproduct) RETURN n.name, s.name"
        },
        {
            "question": "查询单位和网络的关系",
            "answer": "MATCH (u:Unit)-[r:UNIT_NET]->(n:Netname) RETURN u.name, type(r), n.name LIMIT 10"
        },
        {
            "question": "系统部署在哪些网络上?",
            "answer": "MATCH (s:SYSTEM)-[:SYSTEM_NET]->(n:Netname) RETURN s.name, n.name"
        },
        {
            "question": "河北省有哪些单位?",
            "answer": "MATCH (u:Unit) WHERE u.name CONTAINS '河北' RETURN u.name, u.unitType"
        },
        {
            "question": "查询集成商信息",
            "answer": "MATCH (t:Totalintegrations) RETURN t.name, t.totalIntegrationLevel LIMIT 10"
        },
        {
            "question": "网络的密级是什么?",
            "answer": "MATCH (n:Netname) RETURN n.name, n.netSecretLevel LIMIT 10"
        },
        {
            "question": "单位和系统的关系",
            "answer": "MATCH (u:Unit)-[:SOFTWAREUNIT_SYSTEM]->(s:SYSTEM) RETURN u.name, s.name LIMIT 10"
        }
    ]

    # 索引名称
    index = settings.es.knowledge_index  # kb_vector_store

    logger.info(f"开始向索引 {index} 添加 {len(examples)} 个Cypher示例")

    # 检查索引是否存在
    try:
        es_client.client.indices.get(index=index)
        logger.info(f"索引 {index} 已存在")
    except Exception:
        logger.warning(f"索引 {index} 不存在，将在插入文档时自动创建")

    # 添加示例
    success_count = 0
    for i, example in enumerate(examples, 1):
        try:
            doc_id = f"cypher_example_{i}"
            es_client.index_document(
                index=index,
                document=example,
                doc_id=doc_id
            )
            logger.info(f"添加示例 {i}/{len(examples)}: {example['question'][:30]}...")
            success_count += 1
        except Exception as e:
            logger.error(f"添加示例 {i} 失败: {e}")

    logger.info(f"完成! 成功添加 {success_count}/{len(examples)} 个Cypher示例")

    # 验证
    try:
        result = es_client.search(
            index=index,
            query={"match_all": {}},
            size=1
        )
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        logger.info(f"索引 {index} 当前总文档数: {total}")
    except Exception as e:
        logger.warning(f"验证索引失败: {e}")


if __name__ == "__main__":
    try:
        add_cypher_examples()
    except Exception as e:
        logger.error(f"脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
