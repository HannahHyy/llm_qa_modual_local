1. 技术栈：
后端框架：FastAPI
图数据库:Neo4j
缓存数据库：Redis
向量数据库：Chroma - chroma_db存储本地向量数据
嵌入模型：HuggingFace paraphrase-multilingual-MiniLM-L12-v2


2. 执行入口：main.py
- 作用 : 项目启动入口，配置FastAPI应用
- 功能 :
    2.1 初始化Redis和Neo4j连接
    2.2 配置CORS中间件
    2.3 注册路由（聊天API和意图识别API）
- 运行 : uvicorn main:app --host 0.0.0.0 --port 8000

3. 配置模块-settings：
- `config.py` : 核心配置（数据库连接、LLM配置等）
- `sence_question.py` : 场景问题配置（ 可删除 ，内容过于简单）

4. 数据库连接模块-db：
- `neo_conn.py` : Neo4j连接和查询封装
- `redis_conn.py` : Redis连接依赖注入
- `utils_llm.py` : LLM模型实例化

5. 应用逻辑模块 - apps：
5.1 views_chat.py: - 功能 : 传统聊天对话功能
    - API端点 :
    - POST /api/sessions - 创建会话
    - GET /api/sessions - 获取会话列表
    - GET /api/sessions/messages - 获取会话消息
    - DELETE /api/sessions - 删除会话
    - GET /api/session/scene - 获取场景问题
    - 特点 : 使用Redis存储对话历史，支持流式响应
5.2 views_intent:
    - `views.py` : 核心功能模块
    - `neo4j_intent_parser.py` : Neo4j意图解析器
    功能 :
    - 智能意图识别
    - 自动生成Cypher查询
    - 执行Neo4j查询
    - 流式返回结果
    - API端点 : POST /api/chat/stream - 流式智能问答

6. 工具 utils：
    - `utils_embedding.py` : 嵌入向量服务（ 可能不需要 ，项目中未使用）
    - `utils_log.py` : 日志配置
    - `utils_question_answer_embedding.py` : 问答嵌入（ 需要检查是否使用 ）

embedding：
- 1.删除 utils_embedding.py - 没有被使用
- 2.删除 EmbeddingConfig - 没有被使用
- 3.保留 embedding-models 目录 - 被views_intent使用
- 4.保留 chroma_db - 存储向量数据