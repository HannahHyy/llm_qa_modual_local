# 完整配置总结

## 更新时间
2025-12-25 (最新更新)

## 概述

本文档总结了系统的完整配置能力，包括所有可配置的参数和环境变量。

## 配置文件位置

- **配置模板**: [.env.example](../.env.example) - 包含所有配置项的示例文件
- **实际配置**: `.env` - 从 `.env.example` 复制并修改(此文件不提交到Git)
- **配置类**: [core/config/settings.py](../core/config/settings.py) 和 [core/config/prompts.py](../core/config/prompts.py)

## 配置分类

### 1. 数据库配置

#### Redis
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

#### MySQL
```bash
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=chatuser
MYSQL_PASSWORD=ChangeMe123!
MYSQL_DATABASE=chatdb
```

#### Elasticsearch
```bash
ES_HOST=localhost
ES_PORT=9200
ES_USERNAME=elastic
ES_PASSWORD=password01
ES_KNOWLEDGE_INDEX=kb_vector_store        # 通用知识库索引(用于ESRetriever)
ES_CONVERSATION_INDEX=conversation_history # 对话历史索引
ES_CYPHER_INDEX=qa_system                 # Neo4j Cypher示例索引(用于生成Cypher查询)
```

**重要**: `qa_system` 索引包含:
- `question` (text) - 示例问题
- `answer` (text) - 对应的Cypher查询语句
- `embedding_question` (dense_vector, 1024维) - 问题向量

运行 `cd old/neo4j_code/documents && python es_embedding.py` 生成此索引。

#### Neo4j
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### 2. LLM基础配置

```bash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-f9f3209599454a49ba6fb4f36c3c0434
LLM_MODEL_NAME=deepseek-v3  # 默认模型
```

### 3. LLM分场景配置

系统在5个不同场景调用LLM,每个场景可独立配置模型、温度和token数:

#### 场景1: 意图识别
```bash
LLM_MODEL_INTENT_RECOGNITION_MODEL=deepseek-v3
LLM_MODEL_INTENT_RECOGNITION_TEMPERATURE=0      # 低温度确保准确性
LLM_MODEL_INTENT_RECOGNITION_MAX_TOKENS=500
```
**用途**: 判断用户查询是ES查询、Neo4j查询还是混合查询

#### 场景2: Cypher生成
```bash
LLM_MODEL_CYPHER_GENERATION_MODEL=deepseek-v3
LLM_MODEL_CYPHER_GENERATION_TEMPERATURE=0       # 低温度确保语法正确
LLM_MODEL_CYPHER_GENERATION_MAX_TOKENS=500
```
**用途**: 根据用户问题生成Neo4j Cypher查询语句
**重要**: 这个配置直接影响Neo4j查询的准确性!

#### 场景3: 对话生成
```bash
LLM_MODEL_CHAT_GENERATION_MODEL=qwq-32b
LLM_MODEL_CHAT_GENERATION_TEMPERATURE=0         # 可适当提高使回答更自然
LLM_MODEL_CHAT_GENERATION_MAX_TOKENS=4000
```
**用途**: 生成最终的对话回答

#### 场景4: 摘要生成
```bash
LLM_MODEL_SUMMARY_GENERATION_MODEL=deepseek-v3
LLM_MODEL_SUMMARY_GENERATION_TEMPERATURE=0
LLM_MODEL_SUMMARY_GENERATION_MAX_TOKENS=200
```
**用途**: 为对话生成摘要

#### 场景5: 知识匹配
```bash
LLM_MODEL_KNOWLEDGE_MATCHING_MODEL=deepseek-v3
LLM_MODEL_KNOWLEDGE_MATCHING_TEMPERATURE=0
LLM_MODEL_KNOWLEDGE_MATCHING_MAX_TOKENS=1000
```
**用途**: 匹配LLM回答中引用的知识点

### 4. 提示词配置

所有LLM调用的提示词都可自定义:

#### 系统提示词
```bash
PROMPT_SYSTEM_PROMPT="你是一个专业的AI助手，致力于为用户提供准确、有用的回答。
请遵循以下原则：
1. 基于提供的参考知识进行回答，确保准确性
..."
```

#### 意图识别提示词
```bash
PROMPT_INTENT_RECOGNITION_PROMPT="你是一个意图识别专家。请分析用户的查询，判断其意图类型。
可能的意图类型：
1. es_query - 通用知识查询
2. neo4j_query - 图数据库查询
3. hybrid_query - 混合查询
用户查询: {query}
请判断意图类型，并给出置信度（0-1）。
只输出JSON格式: {\"intent_type\": \"xxx\", \"confidence\": 0.xx}"
```
**占位符**: `{query}` - 用户查询

#### Neo4j Cypher生成提示词
```bash
PROMPT_NEO4J_CYPHER_GENERATION_PROMPT="你是一个Neo4j Cypher查询生成专家。
数据库包含以下节点类型:
- Netname: 网络节点
- Unit: 单位节点
- SYSTEM: 系统节点
...
参考以下示例:
{examples}

用户问题: {query}

请生成一个Cypher查询来回答这个问题。
要求:
1. 只输出Cypher查询,不要有任何解释
2. Cypher必须是可执行的
..."
```
**占位符**:
- `{query}` - 用户查询
- `{examples}` - 从ES检索的Cypher示例

**调整建议**: 如果生成的Cypher不准确,可以在提示词中添加更多约束

#### 知识增强提示词模板
```bash
PROMPT_KNOWLEDGE_ENHANCED_PROMPT_TEMPLATE="{system_prompt}

以下是历史对话，请基于上下文回答用户的新问题。

--- 历史对话开始 ---
{history}
--- 历史对话结束 ---

--- 相关知识 ---
{knowledge}
--- 知识结束 ---

用户: {query}

助手:"
```
**占位符**:
- `{system_prompt}` - 系统提示词
- `{history}` - 对话历史
- `{knowledge}` - 检索到的知识
- `{query}` - 当前查询

#### 摘要生成提示词
```bash
PROMPT_SUMMARY_GENERATION_PROMPT="请为以下对话生成简洁的摘要（不超过50字）：
{conversation}
摘要:"
```
**占位符**: `{conversation}` - 对话内容

#### 知识匹配提示词
```bash
PROMPT_KNOWLEDGE_MATCHING_PROMPT="请分析LLM的回答，找出其中引用的知识点，并与提供的知识库进行匹配。
LLM回答:
{llm_output}

知识库:
{knowledge_base}

请返回匹配的知识ID列表（JSON格式）。
格式: {\"matched_ids\": [\"id1\", \"id2\", ...]}"
```
**占位符**:
- `{llm_output}` - LLM生成的回答
- `{knowledge_base}` - 知识库内容

### 5. Embedding配置

```bash
EMBEDDING_API_URL=http://localhost:8012/embeddings
EMBEDDING_MODEL_NAME=bge-large-zh-v1.5
EMBEDDING_DIMENSION=1024
```

### 6. 应用配置

```bash
APP_HOST=0.0.0.0
APP_PORT=8011
APP_DEBUG=False

LOG_LEVEL=INFO
LOG_FILE=logs/app.log
```

## 配置索引总览

| 索引名称 | 环境变量 | 默认值 | 用途 |
|---------|---------|--------|------|
| 通用知识库索引 | `ES_KNOWLEDGE_INDEX` | `kb_vector_store` | ESRetriever检索标准规范等知识 |
| 对话历史索引 | `ES_CONVERSATION_INDEX` | `conversation_history` | 存储对话历史 |
| Cypher示例索引 | `ES_CYPHER_INDEX` | `qa_system` | Neo4jIntentParser生成Cypher查询 |

## 配置使用流程

### 1. 初次配置
```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
vi .env

# 修改必要的配置:
# - LLM_API_KEY (必须)
# - 数据库连接信息
# - 根据需要调整模型和温度参数
```

### 2. 生成ES索引
```bash
# 生成qa_system索引(Cypher示例)
cd old/neo4j_code/documents
python es_embedding.py
```

### 3. 启动服务
```bash
# 返回项目根目录
cd ../../..

# 启动服务
python main.py
```

### 4. 验证配置
查看启动日志,确认配置已正确加载:
```
INFO | 加载配置...
INFO | LLM基础配置: model=deepseek-v3, base_url=https://...
INFO | Cypher生成配置: model=deepseek-v3, temperature=0.0
INFO | ES索引配置: knowledge=kb_vector_store, conversation=conversation_history, cypher=qa_system
```

## 优化建议

### 场景1: 降低成本
```bash
# 意图识别和Cypher生成用便宜模型
LLM_MODEL_INTENT_RECOGNITION_MODEL=qwen-turbo
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-turbo

# 只在对话生成时用好模型
LLM_MODEL_CHAT_GENERATION_MODEL=qwen-plus
```

### 场景2: 提高Cypher生成准确性
```bash
# 使用更好的模型
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-max

# 降低温度
LLM_MODEL_CYPHER_GENERATION_TEMPERATURE=0.1

# 增加max_tokens
LLM_MODEL_CYPHER_GENERATION_MAX_TOKENS=800

# 优化提示词(在.env中添加更多约束)
```

### 场景3: 提高对话质量
```bash
# 使用最好的模型
LLM_MODEL_CHAT_GENERATION_MODEL=qwen-max

# 提高温度使回答更自然
LLM_MODEL_CHAT_GENERATION_TEMPERATURE=0.7

# 增加max_tokens
LLM_MODEL_CHAT_GENERATION_MAX_TOKENS=6000
```

## 常见问题

### Q: 修改配置后不生效?
**A**: 配置在应用启动时加载,修改后需要重启服务:
```bash
Ctrl+C
python main.py
```

### Q: 如何知道配置是否生效?
**A**: 查看启动日志,会显示加载的配置信息

### Q: qa_system索引不存在怎么办?
**A**: 运行以下命令生成:
```bash
cd old/neo4j_code/documents
python es_embedding.py
```

### Q: 如何修改提示词?
**A**:
1. 在 `.env` 中找到对应的 `PROMPT_*` 变量
2. 修改提示词内容(保留占位符如 `{query}`)
3. 重启服务

### Q: 不同场景的LLM配置有什么区别?
**A**:
- **意图识别/Cypher生成**: 低温度(0-0.3),确保准确性,可用便宜模型
- **对话生成**: 较高温度(0.5-0.9),回答更自然,建议用好模型
- **摘要生成/知识匹配**: 中等温度(0.3-0.5),平衡准确性和灵活性

## 参考文档

- [配置指南](CONFIGURATION_GUIDE.md) - 详细配置说明
- [紧急修复总结](URGENT_FIX_SUMMARY.md) - LLM流式模式和配置化系统实现
- [索引名称修正](INDEX_NAME_FIX.md) - qa_system索引详细说明
- [流式输出修复](STREAMING_OUTPUT_FIX.md) - 流式输出格式说明

## 配置检查清单

启动前请确认:

- [ ] 已复制 `.env.example` 到 `.env`
- [ ] 已配置 `LLM_API_KEY`
- [ ] 已配置数据库连接信息(Redis/MySQL/ES/Neo4j)
- [ ] 已运行 `es_embedding.py` 生成 `qa_system` 索引
- [ ] 已根据需求调整模型和温度参数
- [ ] 已根据需求自定义提示词(可选)

## 最后更新

**日期**: 2025-12-25
**状态**: ✅ 完整配置系统已实现
**版本**: v2.0 (配置完全可控版本)

## 变更历史

### v2.0 (2025-12-25)
- ✅ 添加 `ES_CYPHER_INDEX` 配置项
- ✅ 支持从 `.env` 配置所有索引名称
- ✅ 移除硬编码的索引名称
- ✅ 完善配置文档

### v1.0 (2025-12-25)
- ✅ 实现完整的LLM分场景配置
- ✅ 实现所有提示词可配置
- ✅ 修复LLM流式模式错误
- ✅ 修复Pydantic验证错误
