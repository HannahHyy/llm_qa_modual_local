"""
测试包

本目录包含项目的全部单元测试和集成测试。

测试文件组织：
- conftest.py: pytest配置和全局fixtures
- test_domain_services.py: Domain层服务测试（~30个测试）
- test_infrastructure.py: Infrastructure层客户端和仓储测试（~35个测试）
- test_application.py: Application层服务测试（~25个测试）
- test_core.py: Core层工具测试（~28个测试）

总计: ~118个测试用例，覆盖4层架构的所有关键功能。

运行测试：
```bash
# 运行所有测试
pytest

# 运行特定层测试
pytest tests/test_domain_services.py -v

# 生成覆盖率报告
pytest --cov=domain --cov=infrastructure --cov=application --cov=core --cov-report=html
```

详细文档请参考: docs/05-测试文档.md
"""
