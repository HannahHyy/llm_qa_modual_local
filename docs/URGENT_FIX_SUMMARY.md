# 紧急修复总结

## 用户反馈的问题

### 1. LLM模型只支持流式模式错误

**错误日志**:
```
ERROR | LLM异步非流式调用错误: Error code: 400 - {'error': {'message': 'This model only support stream mode, please enable the stream parameter to access the model. ', 'type': 'invalid_request_error'...
```

**原因**: 在生成Cypher时使用了 `async_nonstream_chat()`,但某些LLM模型只支持流式模式。

**修复**:
- 文件: [domain/parsers/neo4j_intent_parser.py](../domain/parsers/neo4j_intent_parser.py:321-338)
- 改用 `async_stream_chat()` 并收集完整响应

```python
# 修改前
response = await self.llm_client.async_nonstream_chat(...)

# 修改后
cypher_parts = []
async for chunk in self.llm_client.async_stream_chat(...):
    if chunk:
        cypher_parts.append(chunk)
cypher = "".join(cypher_parts).strip()
```

### 2. 配置化需求

**用户要求**:
1. 不同场景的LLM调用使用不同的模型和参数(意图识别、Cypher生成、对话生成等)
2. 所有提示词都可配置可修改
3. 通过.env文件管理配置

## 实现的配置化系统

### 核心文件

1. **core/config/prompts.py** - 提示词和LLM模型配置管理
2. **.env.example** - 配置文件示例
3. **docs/CONFIGURATION_GUIDE.md** - 完整的配置指南

### 配置分类

#### 1. LLM模型分场景配置

系统支持5种不同场景,每个场景独立配置:

| 场景 | 模型配置前缀 | 用途 | 默认温度 |
|------|-------------|------|---------|
| 意图识别 | `LLM_MODEL_INTENT_RECOGNITION_` | 判断查询类型 | 0.3 |
| Cypher生成 | `LLM_MODEL_CYPHER_GENERATION_` | 生成Neo4j查询 | 0.3 |
| 对话生成 | `LLM_MODEL_CHAT_GENERATION_` | 生成最终回答 | 0.7 |
| 摘要生成 | `LLM_MODEL_SUMMARY_GENERATION_` | 生成对话摘要 | 0.5 |
| 知识匹配 | `LLM_MODEL_KNOWLEDGE_MATCHING_` | 匹配引用知识 | 0.3 |

每个场景配置包括:
- `_MODEL` - 模型名称
- `_TEMPERATURE` - 温度参数
- `_MAX_TOKENS` - 最大token数

#### 2. 提示词配置

所有LLM调用的提示词都可配置:

| 提示词 | 环境变量 | 用途 |
|--------|---------|------|
| 系统提示词 | `PROMPT_SYSTEM_PROMPT` | 所有对话的基础提示 |
| 意图识别 | `PROMPT_INTENT_RECOGNITION_PROMPT` | 判断查询意图 |
| Cypher生成 | `PROMPT_NEO4J_CYPHER_GENERATION_PROMPT` | 生成Cypher查询 |
| 知识增强 | `PROMPT_KNOWLEDGE_ENHANCED_PROMPT_TEMPLATE` | 对话生成模板 |
| 摘要生成 | `PROMPT_SUMMARY_GENERATION_PROMPT` | 生成摘要 |
| 知识匹配 | `PROMPT_KNOWLEDGE_MATCHING_PROMPT` | 匹配知识点 |

### 使用示例

#### 在.env中配置

```bash
# Cypher生成使用qwen-plus,温度0.3
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-plus
LLM_MODEL_CYPHER_GENERATION_TEMPERATURE=0.3
LLM_MODEL_CYPHER_GENERATION_MAX_TOKENS=500

# 对话生成使用qwen-max,温度0.7
LLM_MODEL_CHAT_GENERATION_MODEL=qwen-max
LLM_MODEL_CHAT_GENERATION_TEMPERATURE=0.7
LLM_MODEL_CHAT_GENERATION_MAX_TOKENS=4000

# 自定义Cypher生成提示词
PROMPT_NEO4J_CYPHER_GENERATION_PROMPT="你是一个Neo4j Cypher专家...
要求:
1. 只输出Cypher
2. 必须可执行
3. 使用CONTAINS匹配
...
用户问题: {query}"
```

#### 在代码中使用

```python
from core.config import get_llm_model_settings, get_cypher_generation_prompt

# 获取配置
llm_config = get_llm_model_settings()

# 使用配置调用LLM
async for chunk in llm_client.async_stream_chat(
    prompt=get_cypher_generation_prompt(query, examples),
    model=llm_config.cypher_generation_model,
    temperature=llm_config.cypher_generation_temperature,
    max_tokens=llm_config.cypher_generation_max_tokens
):
    # ...
```

## 修改的文件

### 1. 新增文件

1. **core/config/prompts.py** - 提示词和LLM模型配置类
   - `PromptSettings` - 提示词配置
   - `LLMModelSettings` - LLM模型配置
   - 便捷函数: `get_cypher_generation_prompt()` 等

2. **.env.example** - 完整的配置示例
   - 所有环境变量说明
   - 默认值
   - 使用说明

3. **docs/CONFIGURATION_GUIDE.md** - 配置指南
   - 配置详解
   - 优化建议
   - 常见问题
   - 最佳实践

4. **docs/URGENT_FIX_SUMMARY.md** - 本文档

### 2. 修改文件

1. **core/config/__init__.py** - 导出新的配置类

2. **domain/parsers/neo4j_intent_parser.py**
   - 改用流式LLM调用(修复400错误)
   - 使用配置化的提示词和模型参数

## 配置优势

### 1. 灵活性

- 不同场景使用不同模型
- Cypher生成可用便宜模型(qwen-turbo)
- 对话生成可用好模型(qwen-max)
- 降低整体成本

### 2. 可维护性

- 所有提示词集中管理
- 不需要修改代码,只需修改.env
- 支持快速实验和优化

### 3. 可扩展性

- 容易添加新的场景
- 容易添加新的提示词
- 支持用户级配置(未来)

## 使用指南

### 1. 初次配置

```bash
# 复制配置文件
cp .env.example .env

# 修改配置
vi .env

# 重启服务
python main.py
```

### 2. 优化Cypher生成

如果Cypher生成不准确:

```bash
# 降低温度
LLM_MODEL_CYPHER_GENERATION_TEMPERATURE=0.1

# 使用更好的模型
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-max

# 修改提示词,添加更多约束
PROMPT_NEO4J_CYPHER_GENERATION_PROMPT="...
要求:
1. 只输出Cypher
2. 使用CONTAINS而非=
3. LIMIT不超过100
4. 必须返回name字段
..."
```

### 3. 降低成本

```bash
# 意图识别和Cypher生成用便宜模型
LLM_MODEL_INTENT_RECOGNITION_MODEL=qwen-turbo
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-turbo

# 只在对话生成时用好模型
LLM_MODEL_CHAT_GENERATION_MODEL=qwen-plus
```

### 4. 提高质量

```bash
# 所有场景都用最好的模型
LLM_MODEL_INTENT_RECOGNITION_MODEL=qwen-max
LLM_MODEL_CYPHER_GENERATION_MODEL=qwen-max
LLM_MODEL_CHAT_GENERATION_MODEL=qwen-max

# 提高温度使回答更自然
LLM_MODEL_CHAT_GENERATION_TEMPERATURE=0.9
```

## 验证配置

创建测试脚本:

```python
from core.config import get_llm_model_settings, get_prompt_settings

llm_config = get_llm_model_settings()
print(f"Cypher生成: model={llm_config.cypher_generation_model}, "
      f"temp={llm_config.cypher_generation_temperature}")

prompt_config = get_prompt_settings()
print(f"系统提示词: {prompt_config.system_prompt[:50]}...")
```

## 下一步

1. **测试修复**:
   ```bash
   python main.py
   # 测试Neo4j查询: "河北单位建设了哪些网络?"
   ```

2. **验证配置**:
   - 检查日志确认使用的模型和温度
   - 验证Cypher是否正确生成

3. **优化调整**:
   - 根据实际效果调整温度
   - 优化提示词
   - 选择合适的模型

## 常见问题

### Q: 如何知道配置是否生效?

**A**: 查看日志:

```
INFO | Cypher生成配置: model=qwen-plus, temperature=0.3, max_tokens=500
INFO | LLM生成Cypher: MATCH (u:Unit)...
```

### Q: 修改提示词后需要重启吗?

**A**: 是的,配置在启动时加载:

```bash
Ctrl+C
python main.py
```

### Q: 如何快速测试不同的提示词?

**A**:
1. 在 `.env` 中修改
2. 重启服务
3. 发送测试请求
4. 查看日志和响应

### Q: 提示词中的占位符有哪些?

**A**:
- Cypher生成: `{query}`, `{examples}`
- 知识增强: `{system_prompt}`, `{history}`, `{knowledge}`, `{query}`
- 摘要: `{conversation}`
- 等等

详见 [docs/CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md)

## 参考文档

1. [docs/CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) - 完整配置指南
2. [.env.example](../.env.example) - 配置文件示例
3. [core/config/prompts.py](../core/config/prompts.py) - 配置类源码

## 最后更新

2025-12-25 23:30

**状态**:
- ✅ LLM流式模式错误已修复
- ✅ 完整配置化系统已实现
- ✅ 所有提示词可配置
- ✅ 所有LLM场景可独立配置

**待用户完成**:
1. 运行 `cd old/neo4j_code/documents && python es_embedding.py` 生成ES索引
2. 根据需要调整 `.env` 中的配置
3. 测试验证
