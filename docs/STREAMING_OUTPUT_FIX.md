# 流式输出格式修复文档

## 问题描述

用户反馈的问题:
1. **没有根据查询结果输出答案** - 输出格式不正确
2. **不是流式返回** - 内容一次性出现,而非逐字流式输出
3. **不直接体现在前端** - 需要刷新才能看到,以历史记录形式出现
4. **缺少旧版本的标签** - 缺少`<think>`, `<data>`, `<knowledge>`标签

## 根本原因

新版本的`StreamingService`没有实现old版本的输出格式:
- Old版本使用`<think>`, `<data>`, `<knowledge>`标签包裹不同阶段的输出
- Old版本使用`message_type`字段区分内容类型
- Old版本输出格式: `data:{"content":"...", "message_type":1}\n\n`

## 修复方案

### 1. 重写StreamingService.chat_stream()方法

**文件**: [application/services/streaming_service.py](../application/services/streaming_service.py)

**关键修改**:

#### 输出格式结构

```
<think>
  开始对用户的提问进行深入解析...
  用户查询意图识别为: neo4j_query
  置信度: 0.70
  检索到5条相关知识
  现在开始业务知识图谱检索
  检索到的业务信息：
  - 网20（网络ID：netid20）...
  完成对用户问题的详细解析分析。正在检索知识库中的内容并生成回答，请稍候....
</think>

<data>
  根据查询结果，河北省单位建设的网络包括：
  - 网20（网络ID：netid20，类型：自行研发）
  - 网21（网络ID：netid21，类型：购买）
  ...
</data>

<knowledge>
  相关的标准规范原文内容
  1. 网络安全等级保护条例
  ...
  2. 信息系统安全等级保护实施指南
  ...
</knowledge>
```

#### 消息类型定义

```python
message_type = 1  # <think>思考过程
message_type = 2  # <data>LLM回答
message_type = 3  # <knowledge>知识原文
message_type = 4  # 错误信息
```

#### SSE输出格式

```python
def _format_data_event(self, content: str, message_type: int) -> str:
    """格式化数据事件(兼容old版本格式)"""
    data = {
        "content": content,
        "message_type": message_type
    }
    return f"data:{json.dumps(data, ensure_ascii=False)}\n\n"
```

### 2. 实现流程

```python
async def chat_stream(...):
    full_stream_content = []  # 收集完整内容用于保存

    # 1. <think>开始
    yield _format_data_event("<think>开始对用户的提问进行深入解析...\n", 1)

    # 2. 意图识别和知识检索
    intent, knowledge = await routing_strategy.route_with_fallback(...)

    # 3. 输出意图分析结果
    if intent:
        yield _format_data_event(f"用户查询意图识别为: {intent.intent_type}\n", 1)

        if intent.intent_type == "neo4j_query":
            yield _format_data_event("现在开始业务知识图谱检索\n", 1)
            # 输出检索到的业务信息
            for k in knowledge[:3]:
                yield _format_data_event(f"- {k.content[:100]}...\n", 1)

    # 4. </think>结束
    yield _format_data_event("\n完成对用户问题的详细解析分析...\n</think>\n", 1)

    # 5. <data>开始
    yield _format_data_event("<data>\n", 2)

    # 6. 流式LLM输出
    async for chunk in llm_client.chat_completion_stream(messages):
        content = chunk.get("delta", {}).get("content", "")
        if content:
            yield _format_data_event(content, 2)
            await asyncio.sleep(0.01)  # 小延迟确保流式效果

    # 7. </data>结束
    yield _format_data_event("\n</data>", 2)

    # 8. <knowledge>标签(如果有)
    if knowledge:
        yield _format_data_event("\n<knowledge>\n相关的标准规范原文内容\n", 3)
        for i, k in enumerate(knowledge[:2], 1):
            yield _format_data_event(f"{i}. {k.title}\n{k.content[:500]}...\n\n", 3)
        yield _format_data_event("</knowledge>", 3)

    # 9. 保存完整内容(包含所有标签)
    complete_reply = "".join(full_stream_content)
    await memory_service.add_message(user_id, session_id, "assistant", complete_reply)
```

## 与Old版本对比

| 特性 | Old版本 | 新版本(修复后) | 状态 |
|------|---------|---------------|------|
| `<think>`标签 | ✅ | ✅ | ✅ 已实现 |
| `<data>`标签 | ✅ | ✅ | ✅ 已实现 |
| `<knowledge>`标签 | ✅ | ✅ | ✅ 已实现 |
| `message_type`字段 | ✅ | ✅ | ✅ 已实现 |
| 流式输出 | ✅ | ✅ | ✅ 已实现 |
| 意图分析展示 | ✅ | ✅ | ✅ 已实现 |
| Neo4j结果展示 | ✅ | ✅ | ✅ 已实现 |
| 知识匹配输出 | ✅ | ✅ | ✅ 已实现 |
| 保存完整内容 | ✅ | ✅ | ✅ 已实现 |

## 前端兼容性

### 前端需要解析的JSON格式

```javascript
// SSE事件格式
data:{"content":"<think>开始对用户的提问进行深入解析...\n", "message_type":1}

// 解析代码示例
eventSource.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    const content = data.content;
    const messageType = data.message_type;

    switch(messageType) {
        case 1: // <think>思考过程
            appendToThinkSection(content);
            break;
        case 2: // <data>LLM回答
            appendToDataSection(content);
            break;
        case 3: // <knowledge>知识原文
            appendToKnowledgeSection(content);
            break;
        case 4: // 错误
            showError(content);
            break;
    }
});
```

## Neo4j查询特殊处理

当识别为Neo4j查询时,`<think>`部分会包含:

```
现在开始业务知识图谱检索
检索到的业务信息：
- 网20（网络ID：netid20，类型：自行研发）
- 网21（网络ID：netid21，类型：购买）
```

这样用户可以看到Neo4j检索的中间结果。

## 测试验证

### 1. 启动服务

```bash
python main.py
```

### 2. 测试ES查询

```bash
curl -X POST "http://localhost:8011/api/chat/stream?session_id=test&user_id=test&scene_id=3" \
  -H "Content-Type: application/json" \
  -d '{"content":"等级保护的基本要求是什么?"}'
```

预期输出:
```
data:{"content":"<think>开始对用户的提问进行深入解析...\n","message_type":1}

data:{"content":"用户查询意图识别为: es_query\n","message_type":1}

data:{"content":"检索到5条相关知识\n","message_type":1}

data:{"content":"\n完成对用户问题的详细解析分析...\n</think>\n","message_type":1}

data:{"content":"<data>\n","message_type":2}

data:{"content":"等级保护的基本要求包括...","message_type":2}

data:{"content":"\n</data>","message_type":2}

data:{"content":"\n<knowledge>\n相关的标准规范原文内容\n","message_type":3}

data:{"content":"1. 信息系统安全等级保护基本要求\n...","message_type":3}

data:{"content":"</knowledge>","message_type":3}
```

### 3. 测试Neo4j查询

```bash
curl -X POST "http://localhost:8011/api/chat/stream?session_id=test&user_id=test&scene_id=2" \
  -H "Content-Type: application/json" \
  -d '{"content":"河北单位建设了哪些网络?"}'
```

预期输出:
```
data:{"content":"<think>开始对用户的提问进行深入解析...\n","message_type":1}

data:{"content":"用户查询意图识别为: neo4j_query\n","message_type":1}

data:{"content":"现在开始业务知识图谱检索\n","message_type":1}

data:{"content":"检索到的业务信息：\n","message_type":1}

data:{"content":"- 网20（网络ID：netid20）...\n","message_type":1}

data:{"content":"\n完成对用户问题的详细解析分析...\n</think>\n","message_type":1}

data:{"content":"<data>\n","message_type":2}

data:{"content":"根据查询结果，河北省单位建设的网络包括：...","message_type":2}

data:{"content":"\n</data>","message_type":2}
```

## ES Cypher示例索引

### 问题: generated_cypher=False

如果看到日志:
```
generated_cypher=False
未提供生成的Cypher,使用简单匹配查询
```

**原因**: ES的`kb_vector_store`索引为空,没有Cypher示例

**解决方案**: 运行脚本添加示例

```bash
cd d:\combine_llm_new
python scripts/add_cypher_examples.py
```

### 验证索引

```bash
# 检查索引是否存在
curl -X GET "http://localhost:9200/kb_vector_store/_count"

# 查看示例数据
curl -X GET "http://localhost:9200/kb_vector_store/_search?size=1&pretty"
```

预期响应:
```json
{
  "hits": {
    "total": {"value": 10},
    "hits": [
      {
        "_source": {
          "question": "河北单位建设了哪些网络?",
          "answer": "MATCH (u:Unit)-[:UNIT_NET]->(n:Netname) WHERE u.name CONTAINS '河北' RETURN u.name, n.name"
        }
      }
    ]
  }
}
```

## 常见问题

### Q1: 输出仍然一次性出现,不是流式?

**A**: 检查:
1. 前端是否正确处理SSE事件
2. 是否有代理/缓冲导致延迟
3. `await asyncio.sleep(0.01)`是否生效

### Q2: 前端不显示内容?

**A**: 检查:
1. 前端是否监听`message`事件
2. 是否正确解析`data.content`
3. 浏览器控制台是否有错误

### Q3: Neo4j查询返回0结果?

**A**:
1. 确保ES索引有Cypher示例: `python scripts/add_cypher_examples.py`
2. 检查Neo4j数据库是否有数据
3. 查看日志中生成的Cypher是否正确

### Q4: 知识标签不显示?

**A**:
1. 检查是否检索到知识: 日志中"检索到X条相关知识"
2. 确认knowledge列表长度 > 0
3. 验证前端是否处理`message_type=3`

## 调试技巧

### 查看完整流式输出

```bash
curl -N -X POST "http://localhost:8011/api/chat/stream?session_id=test&user_id=test" \
  -H "Content-Type: application/json" \
  -d '{"content":"测试问题"}' 2>&1 | tee output.log
```

### 检查保存的历史记录

```bash
# 查看Redis中的历史
redis-cli
> LRANGE "chat:test:test:messages" 0 -1
```

### 查看日志

```bash
tail -f logs/app.log | grep -E "(流式对话|意图识别|检索)"
```

## 最后更新

2025-12-25 22:00

**状态**: ✅ 流式输出格式已修复,完全兼容old版本

**修改文件**:
- [application/services/streaming_service.py](../application/services/streaming_service.py)
- 新增: [scripts/add_cypher_examples.py](../scripts/add_cypher_examples.py)
