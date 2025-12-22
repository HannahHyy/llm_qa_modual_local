# COMBINE_LLM - 智能问答系统

基于 Clean Architecture 的 RAG（检索增强生成）对话系统，支持网络业务查询（Neo4j）和法规标准查询（Elasticsearch）。

---

## 项目概述

**COMBINE_LLM** 是一个企业级智能问答系统，提供：
- 网络业务情况查询（基于 Neo4j 知识图谱）
- 法规标准查询（基于 Elasticsearch 向量检索）
- 多轮对话支持（基于 Redis 会话管理）
- 流式响应（SSE）实时反馈

## 核心特性

| 特性 | 说明 |
|-----|------|
| **多知识库检索** | ES 向量检索、Neo4j 图谱检索、混合检索 |
| **流式响应** | SSE 流式输出，实时思考过程展示 |
| **会话管理** | Redis 缓存 + ES 持久化双层存储 |
| **Clean Architecture** | 高内聚低耦合，易于测试和维护 |
| **生产就绪** | 完善的日志、监控、错误处理 |

---

## 快速开始

### 系统要求

- **Python**: 3.9+
- **Redis**: 5.0+
- **MySQL**: 8.0+
- **Elasticsearch**: 8.0+
- **Neo4j**: 5.0+ (可选)

### 安装步骤

1. **克隆项目并安装依赖**
```bash
git clone <repository_url>
cd llm_qa_modual_local
pip install -r requirements.txt
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，配置数据库连接信息
```

3. **启动必要服务**
```bash
# Redis
docker run -d -p 6379:6379 redis:7

# MySQL
docker run -d -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=chatdb \
  mysql:8

# Elasticsearch
docker run -d -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  elasticsearch:8.0.0
```

4. **启动应用**
```bash
# 开发模式
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

5. **访问服务**
- 根路径: http://localhost:8000/
- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/api/health/

---

## 架构设计

### 分层架构

采用 Clean Architecture 四层架构 + 横切关注点：

```
API层 (FastAPI路由)
    ↓
应用服务层 (业务流程编排)
    ↓
领域逻辑层 (核心业务逻辑)
    ↓
基础设施层 (数据库、外部服务)
    ↓
横切关注点 (日志、异常、配置)
```

### 目录结构

```
llm_qa_modual_local/
├── api/                    # API层：HTTP接口
│   ├── routers/           # 路由定义
│   ├── schemas/           # 请求/响应模型
│   ├── middleware/        # 中间件
│   └── dependencies/      # 依赖注入
├── application/           # 应用服务层
│   └── services/          # 业务编排服务
├── domain/                # 领域逻辑层
│   ├── models/            # 领域模型
│   ├── parsers/           # 意图解析器
│   ├── retrievers/        # 知识检索器
│   ├── services/          # 领域服务
│   └── strategies/        # 策略模式
├── infrastructure/        # 基础设施层
│   ├── clients/           # 外部客户端
│   └── repositories/      # 数据访问层
├── core/                  # 核心基础设施
│   ├── config/            # 配置管理
│   ├── logging/           # 日志管理
│   └── exceptions/        # 异常定义
├── tests/                 # 测试
├── docs/                  # 文档
├── old/                   # 旧版本代码（参考）
├── main.py                # 主程序
├── .env.example           # 配置示例
├── pytest.ini             # 测试配置
└── requirements.txt       # 依赖列表
```

---

## 技术栈

### 核心框架
- **FastAPI**: 现代 Web 框架，异步支持
- **Pydantic**: 数据验证，类型安全
- **Uvicorn**: ASGI 服务器

### 数据存储
- **Redis**: 缓存、会话存储
- **MySQL**: 持久化存储
- **Elasticsearch**: 全文检索、向量检索
- **Neo4j**: 知识图谱

### AI 相关
- **LLM**: 支持 OpenAI、阿里云通义千问等
- **Embedding**: 向量化服务

### 工具库
- **Loguru**: 日志管理
- **HTTPX**: 异步 HTTP 客户端
- **Pytest**: 测试框架

---

## API 接口

### 会话管理

- `POST /api/sessions/` - 创建会话
- `GET /api/sessions/` - 获取会话列表
- `GET /api/sessions/{session_id}` - 获取会话详情
- `DELETE /api/sessions/{session_id}` - 删除会话
- `PATCH /api/sessions/{session_id}/rename` - 重命名会话

### 对话接口

- `POST /api/chat/` - 标准对话
- `POST /api/chat/stream` - 流式对话
- `POST /api/chat/regenerate` - 重新生成回答

### 健康检查

- `GET /api/health/` - 基础健康检查
- `GET /api/health/detailed` - 详细健康检查
- `GET /api/health/redis` - Redis 检查
- `GET /api/health/mysql` - MySQL 检查
- `GET /api/health/elasticsearch` - ES 检查

---

## 使用示例

### 创建会话并对话

```python
import requests

# 1. 创建会话
response = requests.post(
    "http://localhost:8000/api/sessions/",
    json={"user_id": "user_001", "name": "等保咨询"}
)
session_id = response.json()["session_id"]

# 2. 发起对话
response = requests.post(
    "http://localhost:8000/api/chat/",
    json={
        "session_id": session_id,
        "user_id": "user_001",
        "query": "什么是等保三级？",
        "enable_knowledge": True,
        "top_k": 5
    }
)
print(response.json()["response"])
```

### 流式对话

```python
response = requests.post(
    "http://localhost:8000/api/chat/stream",
    json={
        "session_id": session_id,
        "user_id": "user_001",
        "query": "等保三级有哪些要求？",
        "enable_knowledge": True
    },
    stream=True
)

for line in response.iter_lines():
    if line:
        print(line.decode('utf-8'))
```

---

## 开发指南

### 运行测试

项目使用 pytest 进行测试。测试配置在 `pytest.ini` 中定义。

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit -v

# 运行集成测试
pytest tests/integration -v

# 生成覆盖率报告
pytest --cov=core --cov=infrastructure --cov-report=html
```

**测试标记**:
- `@pytest.mark.unit` - 单元测试
- `@pytest.mark.integration` - 集成测试
- `@pytest.mark.functional` - 功能测试
- `@pytest.mark.slow` - 慢速测试
- `@pytest.mark.skip_ci` - CI 环境跳过

### 代码规范

项目遵循以下规范：
- 使用 Black 进行代码格式化
- 使用 isort 排序导入
- 使用 mypy 进行类型检查
- 使用 pylint/flake8 进行代码质量检查

---

## 配置说明

主要配置项（`.env` 文件）：

```env
# ============= Redis配置 =============
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# ============= MySQL配置 =============
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=chatuser
MYSQL_PASSWORD=ChangeMe123!
MYSQL_DATABASE=chatdb

# ============= Elasticsearch配置 =============
ES_HOST=localhost
ES_PORT=9200
ES_USERNAME=elastic
ES_PASSWORD=password01
ES_KNOWLEDGE_INDEX=kb_vector_store
ES_CONVERSATION_INDEX=conversation_history

# ============= Neo4j配置 =============
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=ChangeMe123!

# ============= LLM配置 =============
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your-api-key-here
LLM_MODEL_NAME=qwen-plus
LLM_TIMEOUT=120
LLM_MAX_RETRIES=3

# ============= 日志配置 =============
LOG_LEVEL=INFO
LOG_FILE_PATH=logs/app.log
LOG_ROTATION=500 MB
LOG_RETENTION=10 days

# ============= 功能开关 =============
REDIS_ENABLED=true
NEO4J_ENABLED=true
KNOWLEDGE_MATCHING_ENABLED=true
INTENT_PARSER_ENABLED=true
KNOWLEDGE_RETRIEVAL_ENABLED=true
```

---

## 实现完成总结

### 第一阶段：基础设施搭建 ✅

**完成内容**:
- 项目结构调整（core、infrastructure 移至根目录）
- 配置管理（基于 Pydantic Settings）
- 日志管理（基于 loguru）
- 异常定义体系
- 数据库客户端（Redis、MySQL、ES、LLM）
- 仓储层（SessionRepository、MessageRepository）
- 测试框架（pytest，30+ 测试用例）

**代码统计**: 21 个文件，约 2,820 行代码

### 第二阶段：领域逻辑层 ✅

**完成内容**:
- 数据模型（Message、Session、Intent、Knowledge）
- 意图解析器（ES、Neo4j）
- 检索器（ES、Neo4j、Hybrid）
- 领域服务（PromptBuilder、KnowledgeMatcher、MemoryService）
- 路由策略（IntentRoutingStrategy）

**代码统计**: 15 个文件，约 2,750 行代码

### 第三阶段：应用服务层 ✅

**完成内容**:
- ChatService（对话流程编排）
- SessionService（会话管理）
- StreamingService（SSE 流式输出）

**代码统计**: 3 个文件，约 790 行代码

### 第四阶段：API层 ✅

**完成内容**:
- Schemas（请求/响应模型）
- Routers（15 个 API 端点）
- Middleware（日志、错误处理、限流）
- Dependencies（依赖注入系统）
- Main（主程序）

**代码统计**: 11 个文件，约 1,660 行代码

**总计**: 50 个文件，约 8,020 行代码，15 个 API 端点

---

## 架构优势

1. **高内聚低耦合**: 各层职责清晰，依赖规则严格遵守
2. **易于测试**: 领域逻辑独立于框架，可独立单元测试
3. **便于扩展**: 新增检索器或解析器不影响现有代码
4. **生产就绪**: 完善的日志、监控、异常处理、限流机制
5. **类型安全**: 完整的类型注解，使用 Pydantic 验证

---

## 常见问题

### Q1: 如何启动应用？

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 3. 启动服务
python main.py
```

### Q2: 如何切换 LLM 模型？

修改 `.env` 文件中的 LLM 配置:
```env
LLM_MODEL_NAME=gpt-4
LLM_API_KEY=your_api_key
```

### Q3: 如何禁用知识检索？

在 API 请求中设置:
```json
{
  "enable_knowledge": false
}
```

### Q4: 如何查看详细日志？

日志文件位置: `logs/app.log`

调整日志级别（`.env`）:
```env
LOG_LEVEL=DEBUG
```

### Q5: Redis 连接失败怎么办？

1. 确认 Redis 服务已启动: `redis-cli ping`
2. 检查 `.env` 中的 Redis 配置
3. 检查防火墙设置

---

## 文档

详细文档位于 `docs/` 目录：

- [架构设计文档](docs/01-架构设计文档.md) - 系统架构和设计原则
- [详细设计文档](docs/02-详细设计文档.md) - 类定义和方法实现
- [数据库设计文档](docs/03-数据库设计文档.md) - 数据库模式设计
- [快速开始指南](docs/快速开始指南.md) - 安装和使用指南
- [测试文档](tests/README.md) - 测试框架说明

---

## 贡献

欢迎贡献代码！请遵循以下步骤：

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 联系方式

如遇问题，请：
1. 查看日志文件 `logs/app.log`
2. 检查配置文件 `.env`
3. 查阅文档 `docs/`
4. 提交 Issue

---

**版本**: 1.0.0
**最后更新**: 2025-12-22