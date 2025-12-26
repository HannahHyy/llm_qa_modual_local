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
cd combine_llm_new
pip install -r requirements.txt
```

2. **检查环境**
```bash
# 检查所有依赖是否已安装
python check_env.py

# 检查项目模块是否正常
python check_project.py
```

3. **配置环境变量**
```bash
# .env 文件已经存在，根据需要修改配置
# 编辑 .env 文件，配置数据库连接信息
```

4. **启动必要服务**
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

5. **启动应用**
```bash
# 开发模式
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

6. **访问服务**
- 根路径: http://localhost:8000/
- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/api/health/

