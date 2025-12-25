# 配置指南

## 概述

本系统支持完整的配置化管理,包括:
- **数据库配置** - Redis, MySQL, ES, Neo4j
- **LLM模型配置** - 不同场景使用不同模型和参数
- **提示词配置** - 所有LLM调用的提示词都可自定义
- **应用配置** - 端口、日志等

所有配置通过 `.env` 文件管理,支持热重载(部分配置)。

## 快速开始

### 1. 复制示例配置文件

```bash
cp .env.example .env
```

### 2. 修改配置

编辑 `.env` 文件,根据您的环境修改配置。

### 3. 重启服务

```bash
python main.py
```

## 配置详解

### 数据库配置

#### Redis

```bash
REDIS_HOST=localhost      # Redis主机地址
REDIS_PORT=6379          # Redis端口
REDIS_DB=0               # Redis数据库编号
REDIS_PASSWORD=          # Redis密码(如果有)
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
ES_KNOWLEDGE_INDEX=kb_vector_store  # 通用知识库索引
ES_CONVERSATION_INDEX=conversation_history  # 对话历史索引
```

**注意**: `qa_system` 索引(Neo4j Cypher示例)是硬编码的,不在此配置。

#### Neo4j

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### LLM配置

#### 基础配置

```bash
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your-api-key-here
LLM_MODEL_NAME=qwen-plus  # 默认模型
```

#### 分场景LLM配置

系统在不同场景会调用LLM,每个场景可以配置不同的模型和参数:

##### 1. 意图识别

```bash
LLM_MODEL_INTENT_RECOGNITION_MODEL=qwen-plus
LLM_MODEL_INTENT_RECOGNITION_TEMPERATURE=0.3  # 低温度,确保准确性
LLM_MODEL_INTENT_RECOGNITION_MAX_TOKENS=500
```

**使用场景**: 判断用户查询是ES查询、Neo4j查询还是混合查询

##### 2. Cypher生成

```bash
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-plus
LLM_MODEL_CYPHER_GENERATION_TEMPERATURE=0.3  # 低温度,确保语法正确
LLM_MODEL_CYPHER_GENERATION_MAX_TOKENS=500
```

**使用场景**: 根据用户问题生成Neo4j Cypher查询语句

**重要**: 这个配置直接影响Neo4j查询的准确性!

##### 3. 对话生成

```bash
LLM_MODEL_CHAT_GENERATION_MODEL=qwen-plus
LLM_MODEL_CHAT_GENERATION_TEMPERATURE=0.7  # 较高温度,回答更自然
LLM_MODEL_CHAT_GENERATION_MAX_TOKENS=4000
```

**使用场景**: 生成最终的对话回答

##### 4. 摘要生成

```bash
LLM_MODEL_SUMMARY_GENERATION_MODEL=qwen-plus
LLM_MODEL_SUMMARY_GENERATION_TEMPERATURE=0.5
LLM_MODEL_SUMMARY_GENERATION_MAX_TOKENS=200
```

**使用场景**: 为对话生成摘要

##### 5. 知识匹配

```bash
LLM_MODEL_KNOWLEDGE_MATCHING_MODEL=qwen-plus
LLM_MODEL_KNOWLEDGE_MATCHING_TEMPERATURE=0.3
LLM_MODEL_KNOWLEDGE_MATCHING_MAX_TOKENS=1000
```

**使用场景**: 匹配LLM回答中引用的知识点

### 提示词配置

所有LLM调用的提示词都可以自定义。

#### 系统提示词

```bash
PROMPT_SYSTEM_PROMPT="你是一个专业的AI助手..."
```

这是所有对话的基础提示词。

#### 意图识别提示词

```bash
PROMPT_INTENT_RECOGNITION_PROMPT="你是一个意图识别专家...
用户查询: {query}
..."
```

**占位符**:
- `{query}` - 用户查询

#### Neo4j Cypher生成提示词

```bash
PROMPT_NEO4J_CYPHER_GENERATION_PROMPT="你是一个Neo4j Cypher查询生成专家...
参考以下示例:
{examples}

用户问题: {query}
..."
```

**占位符**:
- `{query}` - 用户查询
- `{examples}` - 从ES检索的Cypher示例

**调整建议**:
- 如果生成的Cypher不准确,可以在提示词中添加更多约束
- 可以添加更多的节点类型和关系类型说明
- 可以添加常见错误的避免说明

#### 知识增强提示词

```bash
PROMPT_KNOWLEDGE_ENHANCED_PROMPT_TEMPLATE="{system_prompt}

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
PROMPT_SUMMARY_GENERATION_PROMPT="请为以下对话生成简洁的摘要...
{conversation}
摘要:"
```

**占位符**:
- `{conversation}` - 对话内容

#### 知识匹配提示词

```bash
PROMPT_KNOWLEDGE_MATCHING_PROMPT="请分析LLM的回答...
LLM回答:
{llm_output}

知识库:
{knowledge_base}
..."
```

**占位符**:
- `{llm_output}` - LLM生成的回答
- `{knowledge_base}` - 知识库内容

## 配置优化建议

### 场景1: 提高Neo4j查询准确性

**问题**: Cypher生成不准确

**解决方案**:

1. **降低温度**:
```bash
LLM_MODEL_CYPHER_GENERATION_TEMPERATURE=0.1
```

2. **增加max_tokens**:
```bash
LLM_MODEL_CYPHER_GENERATION_MAX_TOKENS=800
```

3. **优化提示词**,添加更多约束:
```bash
PROMPT_NEO4J_CYPHER_GENERATION_PROMPT="...
要求:
1. 只输出Cypher查询,不要有任何解释
2. Cypher必须是可执行的
3. 必须使用CONTAINS而非等号匹配
4. 必须返回至少name字段
5. LIMIT不超过100
..."
```

4. **使用更强的模型**:
```bash
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-max
```

### 场景2: 提高对话质量

**问题**: 回答太机械、不自然

**解决方案**:

1. **提高温度**:
```bash
LLM_MODEL_CHAT_GENERATION_TEMPERATURE=0.9
```

2. **增加max_tokens**:
```bash
LLM_MODEL_CHAT_GENERATION_MAX_TOKENS=6000
```

3. **优化系统提示词**:
```bash
PROMPT_SYSTEM_PROMPT="你是一个富有同理心、专业且友好的AI助手...
请用通俗易懂的语言解释专业术语..."
```

### 场景3: 降低成本

**问题**: LLM调用成本太高

**解决方案**:

1. **意图识别和Cypher生成使用便宜的模型**:
```bash
LLM_MODEL_INTENT_RECOGNITION_MODEL=qwen-turbo
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-turbo
```

2. **只在对话生成时使用好模型**:
```bash
LLM_MODEL_CHAT_GENERATION_MODEL=qwen-plus
```

3. **减少max_tokens**:
```bash
LLM_MODEL_INTENT_RECOGNITION_MAX_TOKENS=200
LLM_MODEL_CYPHER_GENERATION_MAX_TOKENS=300
```

### 场景4: 提高响应速度

**问题**: 响应太慢

**解决方案**:

1. **使用更快的模型**:
```bash
LLM_MODEL_CHAT_GENERATION_MODEL=qwen-turbo
```

2. **减少max_tokens**:
```bash
LLM_MODEL_CHAT_GENERATION_MAX_TOKENS=2000
```

3. **降低检索数量** (在代码中配置):
```python
top_k=3  # 默认是5
```

## 配置验证

### 检查配置是否生效

创建测试脚本 `test_config.py`:

```python
from core.config import (
    get_prompt_settings,
    get_llm_model_settings,
    get_cypher_generation_prompt,
)

# 检查提示词配置
prompt_settings = get_prompt_settings()
print("系统提示词:", prompt_settings.system_prompt[:50], "...")

# 检查LLM模型配置
llm_settings = get_llm_model_settings()
print(f"Cypher生成模型: {llm_settings.cypher_generation_model}")
print(f"Cypher生成温度: {llm_settings.cypher_generation_temperature}")
print(f"Cypher生成max_tokens: {llm_settings.cypher_generation_max_tokens}")

# 检查提示词生成
cypher_prompt = get_cypher_generation_prompt(
    query="测试查询",
    examples="示例1: ..."
)
print("\nCypher生成提示词:", cypher_prompt[:100], "...")
```

运行:
```bash
python test_config.py
```

## 配置文件管理

### 开发环境 vs 生产环境

**方案1**: 使用不同的 `.env` 文件

```bash
# 开发环境
.env.development

# 生产环境
.env.production

# 使用符号链接切换
ln -s .env.development .env
```

**方案2**: 使用环境变量覆盖

```bash
export LLM_MODEL_CHAT_GENERATION_MODEL=qwen-max
python main.py
```

### 敏感信息管理

**不要**将包含敏感信息的 `.env` 文件提交到Git:

```.gitignore
.env
.env.local
.env.*.local
```

**应该**提交 `.env.example`:
- 包含所有配置项
- 不包含真实密码/API密钥
- 包含配置说明

## 常见问题

### Q: 修改配置后不生效?

**A**: 配置在应用启动时加载,修改后需要重启:

```bash
# 停止服务
Ctrl+C

# 重启服务
python main.py
```

### Q: 如何验证配置是否正确?

**A**: 查看启动日志:

```bash
python main.py
```

应该看到:
```
INFO | 加载配置...
INFO | LLM基础配置: model=qwen-plus, base_url=https://...
INFO | Cypher生成配置: model=qwen-plus, temperature=0.3
...
```

### Q: 提示词太长,在.env中不好编辑?

**A**: 两种方案:

1. **使用续行符**:
```bash
PROMPT_SYSTEM_PROMPT="第一行\
第二行\
第三行"
```

2. **改用配置文件**:
在 `core/config/prompts.py` 中直接修改默认值,不走 `.env`。

### Q: 不同用户能使用不同的提示词吗?

**A**: 当前不支持。如需实现:
1. 在数据库中存储用户级提示词
2. 修改 `PromptBuilder` 支持动态加载
3. 在调用时传入用户ID

### Q: 如何动态切换模型?

**A**: 修改 `.env` 中的配置并重启服务。

如需运行时切换,需要:
1. 实现配置热重载
2. 清除缓存的配置实例
3. 重新初始化LLM客户端

## 最佳实践

1. **版本控制**:
   - 提交 `.env.example`
   - 不提交 `.env`
   - 在README中说明如何配置

2. **文档化**:
   - 为每个配置项添加注释
   - 说明默认值的含义
   - 提供示例值

3. **分层配置**:
   - 通用配置在 `.env`
   - 敏感配置用环境变量
   - 用户配置在数据库

4. **配置验证**:
   - 启动时验证必需配置
   - 提供友好的错误提示
   - 记录配置加载日志

5. **配置迁移**:
   - 新增配置项时,提供默认值
   - 在 `.env.example` 中添加说明
   - 更新文档

## 参考

- [Pydantic Settings文档](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [python-dotenv文档](https://pypi.org/project/python-dotenv/)

## 最后更新

2025-12-25 23:30

**状态**: ✅ 完整的配置化系统已实现
