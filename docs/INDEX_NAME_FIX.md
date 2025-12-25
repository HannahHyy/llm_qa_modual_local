# ES索引名称修正文档

## 问题发现

用户反馈指出ES索引名称应该是 **`qa_system`**，而不是之前代码中使用的 `kb_vector_store`。

## 索引信息

### 正确的索引名称
**`qa_system`** - old版本使用的Cypher示例索引

### 配置方式
- **环境变量**: `ES_CYPHER_INDEX=qa_system` (在 `.env` 文件中配置)
- **默认值**: `qa_system`
- **代码位置**: [core/config/settings.py](../core/config/settings.py:64) 中的 `ESSettings.cypher_index` 字段

### 索引结构

根据 `old/neo4j_code/documents/es_embedding.py` 的实现:

```json
{
  "question": "河北单位建设了哪些网络?",
  "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS '河北' RETURN u.name, n.name",
  "embedding_question": [0.123, 0.456, ..., 0.789]  // 1024维向量
}
```

### 字段说明

| 字段 | 类型 | 用途 |
|------|------|------|
| `question` | text | 问题文本,支持文本搜索 |
| `answer` | text | Cypher查询语句,LLM参考用 |
| `embedding_question` | dense_vector | 问题向量(1024维),用于相似度搜索 |

### 索引映射配置

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "question": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "answer": {
        "type": "text"
      },
      "embedding_question": {
        "type": "dense_vector",
        "dims": 1024,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
```

## 修复的文件

### 1. domain/parsers/neo4j_intent_parser.py

**修改**: 默认索引名从 `kb_vector_store` 改为 `qa_system`

```python
# 修改前
def __init__(self, es_client=None, llm_client=None, cypher_index="kb_vector_store"):

# 修改后
def __init__(self, es_client=None, llm_client=None, cypher_index="qa_system"):
```

### 2. api/dependencies/app_dependencies.py

**修改**: 硬编码使用 `qa_system` 索引

```python
# 修改前
_neo4j_parser = Neo4jIntentParser(
    es_client=es_client,
    llm_client=llm_client,
    cypher_index=settings.es.knowledge_index  # kb_vector_store
)

# 修改后
_neo4j_parser = Neo4jIntentParser(
    es_client=es_client,
    llm_client=llm_client,
    cypher_index="qa_system"  # old版本使用的索引名
)
```

### 3. docs/NEO4J_LLM_CYPHER.md

**修改**: 更新文档说明索引名称和字段

## 生成索引的方法

### 方法1: 运行old版本脚本 (推荐)

```bash
cd old/neo4j_code/documents
python es_embedding.py
```

这个脚本会:
1. 从 `cypher_example.py` 读取Cypher示例
2. 调用embedding服务生成向量
3. 创建 `qa_system` 索引
4. 批量写入数据

### 方法2: 手动创建 (不推荐,需要embedding服务)

需要自己调用BGE embedding服务生成1024维向量:

```bash
curl -X POST "http://localhost:9200/qa_system/_doc" \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "河北单位建设了哪些网络?",
    "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS \"河北\" RETURN u.name, n.name",
    "embedding_question": [/* 1024维向量 */]
  }'
```

## 验证索引

### 检查索引是否存在

```bash
curl -X GET "http://localhost:9200/_cat/indices/qa*?v"
```

预期输出:
```
health status index     uuid                   pri rep docs.count docs.deleted store.size pri.store.size
green  open   qa_system xxxxxxxxxxxxxxxxxxx    1   1         10            0      50kb          25kb
```

### 查看索引映射

```bash
curl -X GET "http://localhost:9200/qa_system/_mapping?pretty"
```

应该看到 `embedding_question` 是 `dense_vector` 类型，维度为1024。

### 查询示例数据

```bash
curl -X GET "http://localhost:9200/qa_system/_search?size=1&pretty"
```

预期响应:
```json
{
  "hits": {
    "total": {"value": 10},
    "max_score": 1.0,
    "hits": [
      {
        "_index": "qa_system",
        "_id": "1",
        "_score": 1.0,
        "_source": {
          "question": "河北单位建设了哪些网络?",
          "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS '河北' RETURN u.name, n.name",
          "embedding_question": [0.0123, 0.0456, ...]
        }
      }
    ]
  }
}
```

## 检索逻辑

### 当前实现

`Neo4jIntentParser._retrieve_cypher_examples()` 方法:

```python
# 使用文本匹配
results = self.es_client.search(
    index=self.cypher_index,  # "qa_system"
    query={"match": {"question": query}},
    size=top_k
)
```

### 未来优化 (可选)

可以改用向量相似度搜索以提高准确性:

```python
# 1. 先获取query的embedding
query_embedding = get_embedding(query)  # 调用embedding服务

# 2. 使用向量搜索
results = self.es_client.search(
    index="qa_system",
    knn={
        "field": "embedding_question",
        "query_vector": query_embedding,
        "k": top_k,
        "num_candidates": 100
    }
)
```

但这需要:
1. 集成embedding服务调用
2. 额外的网络请求
3. 当前的文本匹配已经足够好用

## 与其他索引的区别

### qa_system vs kb_vector_store

| 特性 | qa_system | kb_vector_store |
|------|-----------|-----------------|
| 用途 | Cypher示例(Neo4j查询) | 通用知识库 |
| 字段 | question, answer, embedding_question | content, title, metadata等 |
| answer字段 | 存储Cypher查询 | 不存在 |
| 向量维度 | 1024 | 可能不同 |
| 数据来源 | cypher_example.py | 各种知识文档 |
| 使用者 | Neo4jIntentParser | ESRetriever |

## 配置文件

### .env配置

**注意**: `ES_KNOWLEDGE_INDEX` 配置的是通用知识库索引，**不影响**Neo4j的Cypher示例索引。

```bash
# 通用知识库索引(用于ESRetriever)
ES_KNOWLEDGE_INDEX=kb_vector_store

# Neo4j Cypher示例索引(硬编码为qa_system,不需要配置)
# 已在代码中固定使用 "qa_system"
```

### 为什么不用配置?

因为 `qa_system` 是old版本的固定索引名，为了保持兼容性，直接硬编码在代码中更清晰。

## 常见问题

### Q: 为什么检索到0个Cypher示例?

**A**: 索引不存在或为空，运行:
```bash
cd old/neo4j_code/documents
python es_embedding.py
```

### Q: 日志显示 "generated_cypher=False" ?

**A**: 因为没有检索到Cypher示例，LLM无法生成。确保:
1. ES服务运行正常
2. `qa_system` 索引存在且有数据
3. 检查日志中的 "检索到X个Cypher示例"

### Q: 能用kb_vector_store吗?

**A**: 不能。`kb_vector_store` 是通用知识库，不包含Cypher示例。必须使用 `qa_system`。

### Q: 如何添加更多示例?

**A**: 修改 `old/neo4j_code/documents/cypher_example.py`，然后重新运行:
```bash
cd old/neo4j_code/documents
python es_embedding.py
```

## 测试验证

### 1. 测试Neo4j查询

```bash
curl -N -X POST "http://localhost:8011/api/chat/stream?session_id=test&user_id=test" \
  -H "Content-Type: application/json" \
  -d '{"content":"河北单位建设了哪些网络?"}'
```

### 2. 检查日志

应该看到:
```
INFO | 检索到3个Cypher示例
INFO | LLM生成Cypher: MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS '河北' RETURN u.name, n.name
INFO | 检测到Neo4j查询,generated_cypher=True
INFO | 使用LLM生成的Cypher: MATCH (u:Unit)...
```

### 3. 前端验证

在前端输入Neo4j相关问题，应该在 `<think>` 部分看到:
```
现在开始业务知识图谱检索
检索到的业务信息：
- session_id: xxx, user_id: xxx, name: 网20...
```

## 最后更新

2025-12-25 23:00

**状态**: ✅ 索引名称已修正为 `qa_system`

**关键修改**:
1. Neo4jIntentParser默认使用 `qa_system`
2. 依赖注入硬编码 `qa_system`
3. 文档已更新
4. 需要运行old版本脚本生成索引
