# 测试文档

## 测试结构

```
tests/
├── conftest.py              # pytest全局配置和fixtures
├── unit/                    # 单元测试
│   ├── test_config.py       # 配置管理测试
│   ├── test_redis_client.py # Redis客户端测试
│   └── test_mysql_client.py # MySQL客户端测试
├── integration/             # 集成测试
│   ├── test_session_flow.py # 会话流程测试
│   └── test_message_flow.py # 消息流程测试
└── functional/              # 功能测试（待实现）
```

## 运行测试

### 安装依赖

```bash
pip install pytest pytest-asyncio pytest-cov
```

### 运行所有测试

```bash
pytest
```

### 运行单元测试

```bash
pytest tests/unit
```

### 运行集成测试

```bash
pytest tests/integration
```

### 运行指定文件

```bash
pytest tests/unit/test_config.py
```

### 运行指定测试函数

```bash
pytest tests/unit/test_config.py::TestSettings::test_redis_settings
```

### 查看详细输出

```bash
pytest -v
```

### 生成覆盖率报告

```bash
pytest --cov=core --cov=infrastructure --cov-report=html --cov-report=term
```

然后打开 `htmlcov/index.html` 查看详细报告。

## 测试前准备

### 1. 创建.env文件

复制`.env.example`为`.env`并配置：

```bash
cp .env.example .env
```

### 2. 启动必要的服务

- **Redis**: `redis-server`
- **MySQL**: 确保服务运行，数据库`chatdb`已创建
- **Elasticsearch**: 确保服务运行

### 3. 初始化数据库

运行MySQL初始化脚本创建users和sessions表。

## 测试说明

### conftest.py

包含全局fixtures：

- `settings`: 全局配置实例
- `redis_client`: Redis客户端（每个测试函数独立）
- `mysql_client`: MySQL客户端（每个测试函数独立）
- `es_client`: ES客户端（每个测试函数独立）
- `session_repository`: 会话仓储
- `message_repository`: 消息仓储
- `test_user_id`: 测试用户ID
- `cleanup_test_data`: 自动清理测试数据

### 单元测试

测试单个模块的功能：

- **test_config.py**: 配置管理功能
- **test_redis_client.py**: Redis基本操作（SET/GET/Hash/List）
- **test_mysql_client.py**: MySQL基本操作（查询/插入/更新/删除/事务）

### 集成测试

测试多个模块协作：

- **test_session_flow.py**: 会话的完整生命周期
  - 创建会话（MySQL → Redis → ES）
  - 获取会话列表（Redis优先，MySQL备用）
  - 删除会话
  - 缓存机制验证

- **test_message_flow.py**: 消息的完整生命周期
  - 追加消息（Redis + ES并行）
  - 获取消息（Redis优先，ES备用）
  - 缓存未命中和回填
  - 多条消息流程
  - 清空消息

## 注意事项

1. **测试隔离**: 每个测试函数使用独立的客户端实例
2. **自动清理**: `cleanup_test_data` fixture会自动清理测试数据
3. **异步测试**: 使用`@pytest.mark.asyncio`标记异步测试
4. **跳过测试**: 如果Redis/MySQL/ES未启动，相关测试会自动跳过
5. **测试用户**: 所有测试使用`test_user_pytest_001`作为测试用户ID

## 持续集成

在CI/CD中运行测试：

```yaml
# .github/workflows/test.yml 示例
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:7
        ports:
          - 6379:6379

      mysql:
        image: mysql:8
        env:
          MYSQL_ROOT_PASSWORD: root
          MYSQL_DATABASE: chatdb
        ports:
          - 3306:3306

    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install -r requirements.txt pytest pytest-asyncio pytest-cov

      - name: Run tests
        run: pytest --cov=core --cov=infrastructure --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## 最佳实践

1. **命名规范**: 测试文件以`test_`开头，测试函数以`test_`开头
2. **AAA模式**: Arrange（准备）、Act（执行）、Assert（断言）
3. **单一职责**: 每个测试函数只测试一个功能点
4. **可重复性**: 测试应该是幂等的，可以重复运行
5. **独立性**: 测试之间不应该有依赖关系
6. **清晰的断言**: 使用明确的断言消息

## 待完成

- [ ] 添加更多单元测试（ES客户端、异常类等）
- [ ] 添加功能测试（端到端测试）
- [ ] 添加性能测试
- [ ] 集成测试覆盖率提升到80%以上
- [ ] 添加Mock测试（隔离外部依赖）
- [ ] 添加压力测试
