# 重构修复计划

## 问题分析

根据用户反馈和old版本代码分析,新版本存在以下核心问题:

### 1. 意图路由逻辑缺失
- **问题**: 新版本只选择单一意图(Neo4j OR ES),缺少hybrid混合查询支持
- **old版本**: 使用IntentRouter基于LLM判断使用neo4j/es/hybrid/none
- **修复**: 新增IntentRouter层,在StreamingService调用前先判断路由

### 2. Neo4j意图识别流式输出缺失
- **问题**: 新版本的<think>标签内容太简单,缺少LLM流式思考过程
- **old版本**: Neo4jIntentParser使用流式输出,实时显示分析过程
- **修复**: 恢复Neo4jIntentParser的流式输出,通过callback传递给StreamingService

### 3. Cypher查询执行缺失
- **问题**: 新版本识别出neo4j_query后没有真正执行Cypher,直接说"无法提供数据"
- **old版本**: 执行intent_result中的cypher字段,调用conn.query()获取结果
- **修复**: 在Neo4jRetriever中正确执行generated_cypher

### 4. LLM调用参数不正确
- **问题**: 新版本temperature和max_tokens参数可能不符合old版本
- **old版本**:
  - Neo4j意图识别: temperature=0, max_tokens=8000, stream=True
  - 回答生成: temperature=0, stream=True
- **修复**: 更新配置文件和调用逻辑

### 5. ES检索逻辑简化
- **问题**: 新版本的ES检索缺少混合检索策略(BM25+向量)
- **old版本**: ESRetriever支持keyword_search/semantic_search/hybrid_search三种模式
- **修复**: 恢复完整的混合检索逻辑

### 6. 混合查询(hybrid)缺失
- **问题**: 用户查询"河北单位+等保三级"时,应该同时查Neo4j和ES
- **old版本**: IntentRouter识别为hybrid,同时调用两个知识库
- **修复**: 实现真正的混合查询逻辑

## 修复方案

### 阶段1: 恢复IntentRouter层 ✅

1. 创建 `domain/services/intent_router.py` (基于old版本)
2. 在StreamingService中先调用IntentRouter判断路由
3. 根据路由结果(neo4j/es/hybrid)选择不同的处理流程

### 阶段2: 修复Neo4j意图识别流式输出

1. 修改 `domain/parsers/neo4j_intent_parser.py`
   - 恢复流式LLM调用
   - 添加stream_callback参数
   - 实时输出思考过程

2. 修改 `application/services/streaming_service.py`
   - 在<think>标签中实时显示Neo4j意图识别过程
   - 收集完整的思考过程

### 阶段3: 修复Cypher执行逻辑

1. 确保Neo4jIntentParser正确提取cypher字段
2. 确保Neo4jRetriever正确执行generated_cypher
3. 确保结果正确返回

### 阶段4: 恢复ES检索混合策略

1. 修改 `domain/retrievers/es_retriever.py`
   - 添加_bm25_search()和_vector_search()方法
   - 实现权重配置和结果合并
   - 支持keyword_search/semantic_search/hybrid_search

### 阶段5: 实现混合查询(hybrid)

1. 修改 `application/services/streaming_service.py`
   - 检测hybrid路由
   - 同时调用Neo4jRetriever和ESRetriever
   - 合并结果并生成回答

### 阶段6: 更新LLM调用参数

1. 更新 `.env` 和 `.env.example`
2. 确保所有LLM调用使用正确的temperature和max_tokens

## 实施顺序

1. ✅ 创建IntentRouter (最关键)
2. 修复Neo4j流式输出
3. 修复Cypher执行
4. 实现hybrid混合查询
5. 恢复ES混合检索
6. 验证和测试

## 测试用例

### 用例1: 纯Neo4j查询
**输入**: "河北单位建设了哪些网络?"
**预期**:
- IntentRouter返回"neo4j"
- Neo4j意图识别流式输出思考过程
- 执行Cypher查询
- 返回网络列表

### 用例2: 混合查询
**输入**: "河北单位建设了哪些网络?等保三级网络建设要求是什么？"
**预期**:
- IntentRouter返回"hybrid"
- 同时执行Neo4j和ES检索
- <think>标签显示两部分分析
- <data>标签包含两部分回答

### 用例3: 纯ES查询
**输入**: "等保三级网络建设要求是什么？"
**预期**:
- IntentRouter返回"es"
- ES意图识别
- ES混合检索
- 返回法规标准

## 关键代码位置

- **IntentRouter**: `d:\combine_llm_new\old\retrieval_server\intent_router.py` (参考)
- **Neo4jIntentParser**: `d:\combine_llm_new\old\neo4j_code\apps\views_intent\neo4j_intent_parser.py` (参考)
- **ESRetriever**: `d:\combine_llm_new\old\retrieval_server\es_retriever_kbvector.py` (参考)
- **StreamingService**: `d:\combine_llm_new\application\services\streaming_service.py` (需要修改)

## 预期效果

修复后的输出应该完全匹配old版本:
- <think>标签包含详细的流式思考过程
- <data>标签包含基于查询结果的回答
- <knowledge>标签包含结构化的知识结果
- 混合查询同时返回Neo4j和ES结果
