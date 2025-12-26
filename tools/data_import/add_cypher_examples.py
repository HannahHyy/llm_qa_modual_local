"""
添加Cypher示例到ES索引

这个脚本向qa_system索引添加示例Cypher查询，用于Neo4j意图解析时的示例匹配
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.clients.es_client import ESClient
from core.config import get_settings
from core.logging import logger


def add_cypher_examples():
    """添加Cypher示例到ES的qa_system索引"""

    settings = get_settings()
    es_client = ESClient(settings.es)

    # Cypher示例数据（用于Neo4j意图解析）
    # 注意：使用实际数据库中的英文标签和关系名称
    examples = [
        {
            "intent": "查询单位建设的网络",
            "example": "河北单位建设了哪些网络?",
            "cypher": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS '河北' RETURN u.name, n.name",
            "description": "查询特定单位拥有的网络资源"
        },
        {
            "intent": "查询所有单位网络关系",
            "example": "哪些单位建设了网络?",
            "cypher": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) RETURN u.name, n.name",
            "description": "查询所有单位与网络的关系"
        },
        {
            "intent": "查询单位的系统",
            "example": "北京单位有哪些系统?",
            "cypher": "MATCH (s:SYSTEM)<-[:SYSTEM_NET]-(n:Netname)<-[:UNIT_NET]-(u:Unit) WHERE u.name CONTAINS '北京' RETURN u.name, s.name",
            "description": "查询特定单位拥有的系统"
        },
        {
            "intent": "查询网络部署的安全产品",
            "example": "网络的安全产品有哪些?",
            "cypher": "MATCH (s:Safeproduct)-[:SECURITY_NET]->(n:Netname) RETURN n.name, s.name",
            "description": "查询网络上部署的安全产品"
        },
        {
            "intent": "查询单位网络关系详情",
            "example": "查询单位和网络的关系",
            "cypher": "MATCH (u:Unit)-[r:UNIT_NET]->(n:Netname) RETURN u.name, type(r), n.name LIMIT 10",
            "description": "查询单位与网络之间的关系类型"
        },
        {
            "intent": "查询系统部署的网络",
            "example": "系统部署在哪些网络上?",
            "cypher": "MATCH (s:SYSTEM)-[:SYSTEM_NET]->(n:Netname) RETURN s.name, n.name",
            "description": "查询系统所在的网络"
        },
        {
            "intent": "按地区查询单位",
            "example": "河北省有哪些单位?",
            "cypher": "MATCH (u:Unit) WHERE u.unitArea CONTAINS '河北' OR u.name CONTAINS '河北' RETURN u.name, u.unitType",
            "description": "按地区筛选单位"
        },
        {
            "intent": "查询集成商信息",
            "example": "查询集成商信息",
            "cypher": "MATCH (t:Totalintegrations) RETURN t.name LIMIT 10",
            "description": "查询集成商基本信息"
        },
        {
            "intent": "查询网络属性",
            "example": "网络的类型是什么?",
            "cypher": "MATCH (n:Netname) RETURN n.name, n.networkType LIMIT 10",
            "description": "查询网络的类型属性"
        },
        {
            "intent": "查询单位系统关系",
            "example": "单位和系统的关系",
            "cypher": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname)<-[:SYSTEM_NET]-(s:SYSTEM) RETURN u.name, s.name LIMIT 10",
            "description": "查询单位与系统的关系"
        },
        {
            "intent": "查询终端类型信息",
            "example": "有哪些终端类型?",
            "cypher": "MATCH (t:Terminaltype) RETURN t.name, t.terminalSum LIMIT 10",
            "description": "查询终端类型信息"
        },
        {
            "intent": "查询集成商服务的网络",
            "example": "哪些集成商为网络提供服务?",
            "cypher": "MATCH (t:Totalintegrations)-[:OVERUNIT_NET]->(n:Netname) RETURN t.name, n.name",
            "description": "查询集成商与网络的服务关系"
        }
    ]

    # ✅ 正确的索引名称：qa_system（Cypher示例库）
    index = settings.es.cypher_index  # qa_system

    logger.info(f"开始向索引 {index} 添加 {len(examples)} 个Cypher示例")

    # 检查索引是否存在，不存在则创建
    try:
        es_client.client.indices.get(index=index)
        logger.info(f"索引 {index} 已存在")
    except Exception:
        logger.warning(f"索引 {index} 不存在，正在创建...")
        try:
            es_client.client.indices.create(
                index=index,
                body={
                    "mappings": {
                        "properties": {
                            "intent": {"type": "text"},
                            "example": {"type": "text"},
                            "cypher": {"type": "text"},
                            "description": {"type": "text"}
                        }
                    }
                }
            )
            logger.info(f"索引 {index} 创建成功")
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            return

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
            logger.info(f"✅ 添加示例 {i}/{len(examples)}: {example['example'][:40]}...")
            success_count += 1
        except Exception as e:
            logger.error(f"❌ 添加示例 {i} 失败: {e}")

    logger.info(f"✅ 完成! 成功添加 {success_count}/{len(examples)} 个Cypher示例")

    # 验证
    try:
        result = es_client.search(
            index=index,
            query={"match_all": {}},
            size=1
        )
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        logger.info(f"📊 索引 {index} 当前总文档数: {total}")
    except Exception as e:
        logger.warning(f"⚠️ 验证索引失败: {e}")


if __name__ == "__main__":
    try:
        add_cypher_examples()
    except Exception as e:
        logger.error(f"脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
