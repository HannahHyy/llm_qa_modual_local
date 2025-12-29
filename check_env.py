"""
环境依赖检查工具

检查项目所需的所有Python依赖是否正确安装。
"""

import sys
import importlib.metadata
from typing import Dict, List, Tuple


# ============= 必需依赖列表 =============

REQUIRED_PACKAGES = {
    # Web框架和服务器
    "fastapi": "0.114.2",
    "uvicorn": "0.30.6",

    # 数据库和存储
    "redis": "5.0.8",
    "pymysql": "1.0.0",
    "elasticsearch": "8.0.0",
    "neo4j": "5.0.0",

    # 数据验证和模型
    "pydantic": "2.9.2",
    "pydantic-settings": "2.0.0",

    # LLM和AI相关
    "openai": "1.40.0",
    "httpx": "0.27.0",

    # 中文处理和搜索
    "jieba": "0.42.1",
    "rank-bm25": "0.2.2",

    # 数据处理
    "numpy": "1.21.0",

    # 日志管理
    "loguru": "0.7.0",

    # HTTP客户端
    "requests": "2.32.3",

    # 测试框架
    "pytest": "8.3.0",
    "pytest-asyncio": "0.23.0",
    "pytest-cov": "5.0.0",
}


def check_python_version() -> Tuple[bool, str]:
    """
    检查Python版本

    Returns:
        (是否通过, 消息)
    """
    required_version = (3, 8)
    current_version = sys.version_info[:2]

    if current_version >= required_version:
        return True, f"✓ Python版本: {sys.version.split()[0]} (符合要求 >= 3.8)"
    else:
        return False, f"✗ Python版本: {sys.version.split()[0]} (需要 >= 3.8)"


def check_package(package_name: str, min_version: str) -> Tuple[bool, str]:
    """
    检查单个包是否安装及版本

    Args:
        package_name: 包名
        min_version: 最低版本要求

    Returns:
        (是否通过, 消息)
    """
    try:
        # 获取已安装的版本
        installed_version = importlib.metadata.version(package_name)

        # 简单的版本比较（只比较主版本号和次版本号）
        def parse_version(v: str) -> Tuple[int, ...]:
            return tuple(map(int, v.split('.')[:2]))

        installed = parse_version(installed_version)
        required = parse_version(min_version)

        if installed >= required:
            return True, f"✓ {package_name:20s} {installed_version:15s} (>= {min_version})"
        else:
            return False, f"✗ {package_name:20s} {installed_version:15s} (需要 >= {min_version})"

    except importlib.metadata.PackageNotFoundError:
        return False, f"✗ {package_name:20s} 未安装 (需要 >= {min_version})"
    except Exception as e:
        return False, f"✗ {package_name:20s} 检查失败: {str(e)}"


def check_all_packages() -> Tuple[List[str], List[str]]:
    """
    检查所有依赖包

    Returns:
        (成功列表, 失败列表)
    """
    passed = []
    failed = []

    for package, version in REQUIRED_PACKAGES.items():
        success, message = check_package(package, version)
        if success:
            passed.append(message)
        else:
            failed.append(message)

    return passed, failed


def print_results(passed: List[str], failed: List[str]) -> None:
    """打印检查结果"""
    print("\n" + "=" * 80)
    print("环境依赖检查结果")
    print("=" * 80 + "\n")

    # 打印成功的包
    if passed:
        print("[OK] 已安装的依赖:")
        print("-" * 80)
        for msg in passed:
            print(f"  {msg}")
        print()

    # 打印失败的包
    if failed:
        print("[ERROR] 缺失或版本不符的依赖:")
        print("-" * 80)
        for msg in failed:
            print(f"  {msg}")
        print()

    # 打印统计信息
    total = len(passed) + len(failed)
    print("=" * 80)
    print(f"总计: {total} 个依赖")
    print(f"✓ 通过: {len(passed)}")
    print(f"✗ 失败: {len(failed)}")
    print("=" * 80 + "\n")


def print_installation_guide(failed: List[str]) -> None:
    """打印安装指南"""
    if not failed:
        return

    print("[提示] 安装缺失的依赖:")
    print("-" * 80)
    print("\n方法1: 安装所有依赖")
    print("  pip install -r requirements.txt")
    print("\n方法2: 单独安装缺失的包")

    # 提取缺失的包名
    missing_packages = []
    for msg in failed:
        # 从消息中提取包名（去除符号和空格）
        package_name = msg.split()[1]
        missing_packages.append(package_name)

    if missing_packages:
        print(f"  pip install {' '.join(missing_packages)}")

    print("\n" + "=" * 80 + "\n")


def main():
    """主函数"""
    print("\n[检查] 开始检查环境依赖...\n")

    # 1. 检查Python版本
    py_success, py_message = check_python_version()
    print(py_message)

    if not py_success:
        print("\n[ERROR] Python版本不符合要求，请升级Python到3.8或更高版本")
        sys.exit(1)

    print()

    # 2. 检查所有依赖包
    passed, failed = check_all_packages()

    # 3. 打印结果
    print_results(passed, failed)

    # 4. 如果有失败的包，打印安装指南
    if failed:
        print_installation_guide(failed)
        print("[WARNING] 请先安装缺失的依赖，然后再运行项目\n")
        sys.exit(1)
    else:
        print("[OK] 所有依赖检查通过！环境配置正常\n")
        print("下一步: 运行 python check_project.py 检查项目配置和数据库连接\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
