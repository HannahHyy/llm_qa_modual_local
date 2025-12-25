# qa_system索引配置说明

## 更新时间
2025-12-25 (最新)

## 问题背景

用户反馈: **"neo4j的示例问题es库 qa_system我没有在.env.example里看到"**

## 解决方案

### 1. 已添加到 `.env.example`

在 [.env.example](../.env.example) 的 Elasticsearch配置部分:

```bash
# Elasticsearch配置
ES_HOST=localhost
ES_PORT=9200
ES_USERNAME=elastic
ES_PASSWORD=password01
ES_KNOWLEDGE_INDEX=kb_vector_store        # 通用知识库索引(用于ESRetriever)
ES_CONVERSATION_INDEX=conversation_history # 对话历史索引
ES_CYPHER_INDEX=qa_system                 # Neo4j Cypher示例索引(用于Neo4jIntentParser生成Cypher查询)
# 注意: qa_system索引包含字段 question(问题), answer(Cypher查询), embedding_question(1024维向量)
# 运行 old/neo4j_code/documents/es_embedding.py 生成该索引
```

### 2. 已添加到配置类

在 [core/config/settings.py](../core/config/settings.py:64):

```python
class ESSettings(BaseSettings):
    """Elasticsearch配置"""

    host: str = Field(default="localhost", description="ES主机地址")
    port: int = Field(default=9200, description="ES端口")
    username: str = Field(default="elastic", description="ES用户名")
    password: str = Field(default="password01", description="ES密码")
    knowledge_index: str = Field(default="kb_vector_store", description="知识库索引名")
    conversation_index: str = Field(default="conversation_history", description="会话历史索引名")
    cypher_index: str = Field(default="qa_system", description="Neo4j Cypher示例索引名")  # 新增
    timeout: int = Field(default=30, description="请求超时时间（秒）")
```

### 3. 已更新依赖注入

在 [api/dependencies/app_dependencies.py](../api/dependencies/app_dependencies.py:154-159):

```python
def get_neo4j_parser() -> Neo4jIntentParser:
    """获取Neo4j意图解析器（单例）"""
    global _neo4j_parser
    if _neo4j_parser is None:
        settings = get_cached_settings()
        es_client = get_es_client()
        llm_client = get_llm_client()
        # 使用配置的Cypher示例索引(默认qa_system,可通过ES_CYPHER_INDEX配置)
        _neo4j_parser = Neo4jIntentParser(
            es_client=es_client,
            llm_client=llm_client,
            cypher_index=settings.es.cypher_index  # 从配置读取
        )
    return _neo4j_parser
```

**变更**: 从硬编码 `cypher_index="qa_system"` 改为从配置读取 `cypher_index=settings.es.cypher_index`

## qa_system索引详细说明

### 索引用途

`qa_system` 索引存储了 **Neo4j Cypher查询的示例问答对**,用于:
1. 通过向量相似度检索相关的Cypher示例
2. 作为few-shot examples提供给LLM
3. 帮助LLM生成准确的Cypher查询语句

### 索引结构

```json
{
  "question": "河北单位建设了哪些网络?",
  "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS '河北' RETURN u.name, n.name",
  "embedding_question": [0.123, 0.456, ..., 0.789]
}
```

### 字段说明

| 字段 | 类型 | 维度 | 说明 |
|------|------|------|------|
| `question` | text | - | 示例问题文本 |
| `answer` | text | - | 对应的Cypher查询语句 |
| `embedding_question` | dense_vector | 1024 | 问题的向量表示,用于相似度搜索 |

### 如何生成索引

运行以下命令生成 `qa_system` 索引:

```bash
cd old/neo4j_code/documents
python es_embedding.py
```

**注意**: 必须先生成此索引,否则Neo4j查询功能无法正常工作!

### 工作流程

1. **用户查询**: "河北单位建设了哪些网络?"
2. **向量检索**: 系统将查询向量化,在 `qa_system` 索引中检索相似问题
3. **示例检索**: 找到top-3最相似的问答对
4. **LLM生成**: 将示例提供给LLM,生成新的Cypher查询
5. **执行查询**: 在Neo4j中执行生成的Cypher

## 配置灵活性

现在用户可以通过 `.env` 文件修改索引名称:

```bash
# 使用默认名称
ES_CYPHER_INDEX=qa_system

# 或使用自定义名称
ES_CYPHER_INDEX=my_custom_cypher_examples
```

## 相关文档

- [完整配置总结](./COMPLETE_CONFIGURATION_SUMMARY.md) - 查看所有配置项
- [索引名称修正](./INDEX_NAME_FIX.md) - qa_system索引的发现过程
- [紧急修复总结](./URGENT_FIX_SUMMARY.md) - LLM和配置化系统修复

## 检查清单

启动前请确认:

- [ ] `.env` 文件中已配置 `ES_CYPHER_INDEX=qa_system` (或保持默认)
- [ ] 已运行 `python es_embedding.py` 生成 `qa_system` 索引
- [ ] ES服务正常运行
- [ ] 可以通过 `curl http://localhost:9200/qa_system/_count` 验证索引存在

## 验证方法

### 1. 检查索引是否存在

```bash
curl -u elastic:password01 http://localhost:9200/qa_system/_count
```

应该看到:
```json
{"count":15,"_shards":{"total":1,"successful":1,"skipped":0,"failed":0}}
```

### 2. 查看示例数据

```bash
curl -u elastic:password01 http://localhost:9200/qa_system/_search?size=1
```

应该看到包含 `question`, `answer`, `embedding_question` 字段的文档

### 3. 检查配置是否生效

启动服务后查看日志:
```
INFO | ES索引配置: knowledge=kb_vector_store, conversation=conversation_history, cypher=qa_system
```

## 故障排除

### 问题1: 索引不存在
**错误**: `index_not_found_exception`
**解决**: 运行 `python es_embedding.py` 生成索引

### 问题2: Neo4j查询生成失败
**原因**: 没有检索到Cypher示例
**检查**:
1. `qa_system` 索引是否存在
2. 索引中是否有数据
3. embedding服务是否正常运行

### 问题3: 配置不生效
**原因**: 配置未重新加载
**解决**: 重启服务 `Ctrl+C` 然后 `python main.py`

## 最后更新

**日期**: 2025-12-25
**状态**: ✅ qa_system索引配置已完善
**变更**: 从硬编码改为配置化,用户可自定义索引名称
