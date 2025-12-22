# 代码迁移注意事项

## 新旧代码对比分析

### API路由对比

#### 会话管理API

| 功能 | 旧代码 (server2.py) | 新代码 (main.py) | 状态 |
|-----|-------------------|----------------|------|
| 创建会话 | `POST /api/sessions` | `POST /api/sessions/` | ✅ 兼容 |
| 会话列表 | `GET /api/sessions` | `GET /api/sessions/` | ✅ 兼容 |
| 获取消息 | `GET /api/sessions/{id}/messages` | `GET /api/sessions/{id}?include_messages=true` | ⚠️ 参数不同 |
| 删除会话 | `DELETE /api/sessions/{id}` | `DELETE /api/sessions/{id}` | ✅ 兼容 |
| 重命名会话 | ❌ 不存在 | `PATCH /api/sessions/{id}/rename` | ✨ 新增功能 |
| 清空消息 | ❌ 不存在 | `DELETE /api/sessions/{id}/messages` | ✨ 新增功能 |

#### 对话API

| 功能 | 旧代码 | 新代码 | 状态 |
|-----|-------|-------|------|
| 流式对话 | `POST /api/chat/stream?session_id=xxx&user_id=xxx&scene_id=1` | `POST /api/chat/stream` (body) | ⚠️ **不兼容** |
| 标准对话 | ❌ 不存在 | `POST /api/chat/` | ✨ 新增功能 |
| 重新生成 | ❌ 不存在 | `POST /api/chat/regenerate` | ✨ 新增功能 |

### 核心功能差异

#### 1. **Scene ID 功能缺失** (❌ 重要)

**旧代码的scene_id**:
- `scene_id=1`: 混合查询 (Neo4j + ES)
- `scene_id=2`: 仅Neo4j查询
- `scene_id=3`: 仅ES查询

**新代码**:
- ❌ 不支持scene_id参数
- ✅ 但有意图路由策略 (IntentRoutingStrategy) 可以自动判断

**解决方案**: 需要在新代码中添加scene_id支持,或者使用意图路由策略

#### 2. **流式输出格式差异**

**旧代码**:
```json
data:{"content": "...", "message_type": 1}  // 1=think, 2=data, 3=knowledge, 4=error
```

**新代码**:
```
event: start
data: {...}

event: content
data: {"text": "..."}

event: done
data: {...}
```

**解决方案**: 需要统一流式输出格式

#### 3. **三层数据存储**

**旧代码**:
- Redis缓存 (优先)
- ES持久化 (备份)
- MySQL元数据

**新代码**:
- ✅ Redis缓存
- ✅ ES持久化
- ✅ MySQL元数据
- ✅ 支持缓存未命中时自动回填

**状态**: ✅ 功能完整

### 缺失的功能模块

#### 1. Neo4j集成

**旧代码**:
```python
from neo4j_code.apps.views_intent.views_new import LLM as Neo4jLLM
neo4j_llm_instance = Neo4jLLM()
```

**新代码**:
- ❌ Neo4j检索器 (Neo4jRetriever) 已定义但未完全集成
- ❌ neo4j_code模块未导入

**状态**: ⚠️ 需要补充

#### 2. 知识匹配模块

**旧代码**:
```python
from knowledge_matcher import match_and_format_knowledge
```

**新代码**:
- ✅ KnowledgeMatcher服务已实现
- ⚠️ 但功能可能不完全一致

**状态**: ⚠️ 需要验证

#### 3. 意图路由器

**旧代码**:
```python
from intent_router import llm_based_intent_router
routing_decision = await llm_based_intent_router(question, history_msgs)
```

**新代码**:
- ✅ IntentRoutingStrategy 已实现
- ⚠️ 但可能不包含LLM-based路由

**状态**: ⚠️ 需要验证

### 配置差异

| 配置项 | 旧代码 | 新代码 | 状态 |
|-------|-------|-------|------|
| Redis | ✅ 支持 | ✅ 支持 | ✅ 兼容 |
| MySQL | ✅ 支持 | ✅ 支持 | ✅ 兼容 |
| ES | ✅ 支持 | ✅ 支持 | ✅ 兼容 |
| Neo4j | ✅ 支持 | ⚠️ 部分支持 | ⚠️ 需要补充 |
| LLM | ✅ 阿里云通义千问 | ✅ 可配置 | ✅ 兼容 |
| Embedding | ✅ 本地服务 | ✅ 可配置 | ✅ 兼容 |

## 迁移建议

### 立即需要修复的问题

1. **添加scene_id支持到新代码的流式对话接口**
   - 修改 `api/routers/chat_router.py`
   - 添加scene_id参数
   - 根据scene_id选择不同的检索策略

2. **统一流式输出格式**
   - 决定使用旧格式还是新格式
   - 如果保持旧格式,修改 `application/services/streaming_service.py`

3. **集成Neo4j模块**
   - 将 `old/neo4j_code` 集成到新架构
   - 或者完善新代码中的 `domain/retrievers/neo4j_retriever.py`

4. **集成意图路由器**
   - 将 `old/LLM_Server/retrieval_server/intent_router.py` 集成到新架构
   - 或者扩展 `domain/strategies/intent_routing_strategy.py`

### 推荐的迁移步骤

#### 方案A: 渐进式迁移 (推荐)

1. **保留旧代码**,将其移到 `old/LLM_Server/` 继续运行
2. **新代码作为独立服务**,运行在不同端口 (如8000)
3. **逐步迁移功能**:
   - 第一步: 实现scene_id支持
   - 第二步: 集成Neo4j
   - 第三步: 统一流式输出格式
   - 第四步: 端到端测试
4. **完全切换**到新代码

#### 方案B: 快速修复旧代码兼容性

1. **修改新代码的chat_router.py**,添加scene_id参数
2. **修改streaming_service.py**,输出旧格式的SSE
3. **测试验证**
4. **直接替换**

## 需要补充的文件

### 1. Neo4j相关

```
infrastructure/clients/neo4j_client.py  ✅ 已存在
domain/retrievers/neo4j_retriever.py   ✅ 已存在 (但可能不完整)
```

### 2. 意图路由

```
domain/strategies/intent_routing_strategy.py  ✅ 已存在
需要添加: LLM-based意图路由功能
```

### 3. 知识匹配

```
domain/services/knowledge_matcher.py  ✅ 已存在
需要验证: 是否与旧代码功能一致
```

## 关键代码片段对比

### 旧代码的核心流程

```python
# 1. 根据scene_id选择检索方式
if scene_id == 1:  # 混合
    routing_decision = await llm_based_intent_router(question, history)
    if routing_decision == "neo4j":
        # Neo4j查询
    elif routing_decision == "es":
        # ES查询
    else:  # hybrid
        # 先Neo4j再ES

elif scene_id == 2:  # 仅Neo4j
    neo4j_llm_instance.generate_answer_async(question, history)

else:  # scene_id == 3, 仅ES
    # ES查询流程
    intent_result = await parse_intent(question, history)
    knowledge = retrieve_knowledge(intent_result)
    # LLM生成
```

### 新代码的核心流程

```python
# 1. 意图路由
strategy = IntentRoutingStrategy(parsers, retrievers)
intent = await strategy.route(query, history)

# 2. 知识检索
retriever = strategy.select_retriever(intent)
knowledge = await retriever.retrieve(query, intent)

# 3. LLM生成
prompt = prompt_builder.build(history, query, knowledge)
response = await llm_client.stream_chat(prompt)
```

**主要差异**: 新代码没有显式的scene_id选择,而是通过意图路由自动判断

## 测试清单

- [ ] Redis连接测试
- [ ] MySQL连接测试
- [ ] ES连接测试
- [ ] Neo4j连接测试
- [ ] 创建会话测试
- [ ] 获取会话列表测试
- [ ] 流式对话测试 (ES)
- [ ] 流式对话测试 (Neo4j)
- [ ] 流式对话测试 (混合)
- [ ] 知识匹配测试
- [ ] 意图解析测试
- [ ] 历史消息持久化测试
- [ ] 缓存回填测试

## 结论

新代码架构更清晰、更易维护,但需要补充以下功能才能完全替代旧代码:

1. ❌ **scene_id参数支持** (重要)
2. ⚠️ **Neo4j完整集成** (重要)
3. ⚠️ **流式输出格式统一** (重要)
4. ⚠️ **LLM-based意图路由** (可选,已有自动路由)

**建议**: 优先完成前3项,然后进行完整的端到端测试。
