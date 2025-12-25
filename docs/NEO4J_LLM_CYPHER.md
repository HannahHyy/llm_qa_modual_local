# Neo4j LLM生成Cypher功能实现文档

## 概述

本文档说明如何实现了与old版本完全一致的Neo4j查询功能:通过LLM生成Cypher查询。

## 工作流程

### 完整流程图

```
用户提问: "河北单位建设了哪些网络?"
    ↓
[1] 意图识别
    → Neo4jIntentParser识别为neo4j_query
    ↓
[2] ES检索Cypher示例
    → 从kb_vector_store索引检索相似问题的Cypher
    → 示例格式: {"question": "...", "answer": "MATCH (u:Unit)..."}
    ↓
[3] LLM生成Cypher
    → 基于示例和问题,生成可执行的Cypher查询
    → 例如: MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS '河北' RETURN n.name
    ↓
[4] Neo4j执行Cypher
    → Neo4jRetriever接收generated_cypher参数
    → 直接执行LLM生成的Cypher
    ↓
[5] 返回结果
    → 转换为Knowledge对象返回
```

## 关键组件

### 1. Neo4jIntentParser (domain/parsers/neo4j_intent_parser.py)

**作用**: 解析意图并生成Cypher

**关键方法**:
```python
async def parse(query: str) -> Intent:
    # 1. 从ES检索Cypher示例
    examples = await self._retrieve_cypher_examples(query, top_k=3)

    # 2. LLM生成Cypher
    generated_cypher = await self._generate_cypher_with_llm(query, examples)

    # 3. 保存到Intent metadata
    return Intent(
        intent_type=NEO4J_QUERY,
        metadata={"generated_cypher": generated_cypher}
    )
```

**依赖注入**:
- `es_client`: 用于检索Cypher示例
- `llm_client`: 用于生成Cypher
- `cypher_index`: Cypher示例索引名(kb_vector_store)

### 2. Neo4jRetriever (domain/retrievers/neo4j_retriever.py)

**作用**: 执行Cypher查询

**关键修改**:
```python
async def retrieve(
    query: str,
    generated_cypher: Optional[str] = None  # 新增参数
) -> List[Knowledge]:
    # 优先使用LLM生成的Cypher
    if generated_cypher:
        cypher_query = generated_cypher
        params = {}
    else:
        # 回退到简单查询
        cypher_query, params = self._build_cypher_query(...)

    # 执行查询
    results = self.neo4j_client.execute_query(cypher_query, params)
```

### 3. IntentRoutingStrategy (domain/strategies/intent_routing_strategy.py)

**作用**: 传递Cypher到检索器

**关键修改**:
```python
# 检查是否是Neo4j查询
if intent.intent_type == NEO4J_QUERY:
    generated_cypher = intent.metadata.get("generated_cypher")
    knowledge = await retriever.retrieve(
        query=query,
        generated_cypher=generated_cypher  # 传递Cypher
    )
```

**禁用fallback**:
```python
# Neo4j查询不需要fallback
if intent.intent_type == "neo4j_query":
    return intent, knowledge  # 直接返回,不触发ES fallback
```

### 4. 依赖注入配置 (api/dependencies/app_dependencies.py)

**关键修改**:
```python
def get_neo4j_parser() -> Neo4jIntentParser:
    settings = get_cached_settings()
    es_client = get_es_client()
    llm_client = get_llm_client()

    return Neo4jIntentParser(
        es_client=es_client,
        llm_client=llm_client,
        cypher_index=settings.es.knowledge_index  # kb_vector_store
    )
```

## ES Cypher示例索引要求

### 索引名称
`qa_system` (old版本使用的索引名)

### 文档结构
```json
{
    "question": "哪些单位建设了网络?",
    "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) RETURN u.name, n.name",
    "embedding_question": [0.123, 0.456, ...] // 1024维向量
}
```

**字段说明**:
- `question`: 示例问题(text类型,用于文本匹配)
- `answer`: 对应的Cypher查询(text类型,用于LLM参考)
- `embedding_question`: 问题的向量表示(dense_vector类型,1024维,用于相似度搜索)

### 检查索引是否存在
```bash
curl -X GET "localhost:9200/qa_system/_search?size=1&pretty"
```

## LLM Prompt模板

```python
prompt = f"""你是一个Neo4j Cypher查询生成专家。

数据库包含以下节点类型:
- Netname: 网络节点 (属性: name, netSecretLevel, networkType)
- Unit: 单位节点 (属性: name, unitType)
- SYSTEM: 系统节点 (属性: name, systemSecretLevel)
- Safeproduct: 安全产品 (属性: name, safeProductCount)
- Totalintegrations: 集成商 (属性: name, totalIntegrationLevel)

关系类型:
- UNIT_NET, OPERATIONUNIT_NET, OVERUNIT_NET
- SOFTWAREUNIT_SYSTEM, SYSTEM_NET, SECURITY_NET

参考以下示例:
{examples_text}

用户问题: {query}

请生成一个Cypher查询来回答这个问题。
要求:
1. 只输出Cypher查询,不要有任何解释
2. Cypher必须是可执行的
3. 参考示例的格式和模式
4. 确保返回有意义的结果

Cypher查询:"""
```

## 调试日志关键点

成功的查询日志应该显示:

```
INFO | 意图路由: query='河北单位建设了哪些网络?', intent_type=neo4j_query, confidence=0.70
INFO | 检索到3个Cypher示例
INFO | LLM生成Cypher: MATCH (u:Unit)-[:UNIT_NET]->...
INFO | 检测到Neo4j查询,generated_cypher=True
INFO | 使用LLM生成的Cypher: MATCH (u:Unit)-[:UNIT_NET]->...
INFO | Neo4j检索完成: query='...', 结果数=5
INFO | Neo4j查询不启用fallback，直接返回结果: 5条
```

如果看到以下日志说明有问题:
- `未找到Cypher示例` → ES索引为空或配置错误
- `LLM生成Cypher失败` → LLM API调用失败
- `使用简单匹配查询` → 没有传递generated_cypher
- `检索结果不足，尝试混合检索` → fallback被错误触发

## 与old版本对比

| 特性 | Old版本 | 新版本 | 状态 |
|------|---------|--------|------|
| ES检索Cypher示例 | ✅ qa_system索引 | ✅ kb_vector_store索引 | ✅ 兼容 |
| LLM生成Cypher | ✅ | ✅ | ✅ 实现 |
| Neo4j执行Cypher | ✅ | ✅ | ✅ 实现 |
| 结果返回格式 | 字典记录 | Knowledge对象 | ✅ 已适配 |
| Fallback机制 | 无 | 禁用Neo4j fallback | ✅ 一致 |

## 常见问题

### Q: 为什么Neo4j返回0结果?
**A**: 可能原因:
1. ES索引`kb_vector_store`中没有Cypher示例
2. LLM生成的Cypher语法错误或逻辑错误
3. Neo4j数据库中确实没有匹配数据

**调试步骤**:
1. 检查日志中的`generated_cypher`
2. 手动在Neo4j中执行该Cypher验证是否正确
3. 检查ES示例索引是否包含相关问题

### Q: 如何添加更多Cypher示例?
**A**: 运行old版本的脚本生成索引:
```bash
cd old/neo4j_code/documents
python es_embedding.py
```

或者手动向ES的`qa_system`索引添加文档(需要包含embedding):
```bash
curl -X POST "localhost:9200/qa_system/_doc" -H 'Content-Type: application/json' -d'
{
  "question": "北京单位有哪些网络?",
  "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS \"北京\" RETURN u.name, n.name",
  "embedding_question": [/* 需要调用embedding服务生成1024维向量 */]
}
'
```

### Q: LLM生成的Cypher不准确怎么办?
**A**:
1. 增加更多高质量的Cypher示例
2. 调整LLM temperature(当前0.3)
3. 优化prompt模板增加更多约束
4. 考虑使用更强大的模型

## 后续优化建议

1. **Cypher验证**: 在执行前验证Cypher语法
2. **缓存机制**: 缓存相同问题的Cypher避免重复生成
3. **示例质量**: 定期清理和优化ES中的Cypher示例
4. **错误处理**: 更详细的错误提示和降级策略
5. **性能监控**: 记录LLM生成耗时和成功率

## 最后更新
2025-12-25 20:15
