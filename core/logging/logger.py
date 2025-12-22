"""
日志管理模块

使用loguru进行日志管理，支持：
- 控制台和文件输出
- 自动轮转和压缩
- 结构化日志
- 不同级别的日志分离
"""

import sys
from pathlib import Path
from typing import Optional
from loguru import logger


class LoggerManager:
    """日志管理器"""

    _initialized: bool = False

    @classmethod
    def setup_logging(
        cls,
        log_level: str = "INFO",
        log_file_path: str = "logs/app.log",
        rotation: str = "500 MB",
        retention: str = "10 days",
        enable_console: bool = True,
    ) -> None:
        """
        配置日志系统

        Args:
            log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file_path: 日志文件路径
            rotation: 日志轮转策略 (如 "500 MB", "1 day")
            retention: 日志保留时间 (如 "10 days")
            enable_console: 是否启用控制台输出
        """
        if cls._initialized:
            return

        # 移除默认handler
        logger.remove()

        # 控制台输出 - 使用彩色格式
        if enable_console:
            logger.add(
                sys.stdout,
                level=log_level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>",
                colorize=True,
            )

        # 确保日志目录存在
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 文件输出 - 普通日志（INFO及以上）
        logger.add(
            log_file_path,
            level=log_level,
            rotation=rotation,
            retention=retention,
            compression="zip",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        )

        # 文件输出 - 错误日志（ERROR及以上）
        error_log_path = log_path.parent / f"{log_path.stem}_error{log_path.suffix}"
        logger.add(
            str(error_log_path),
            level="ERROR",
            rotation=rotation,
            retention=retention,
            compression="zip",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}\n{exception}",
            backtrace=True,
            diagnose=True,
        )

        cls._initialized = True
        logger.info(f"日志系统初始化完成: level={log_level}, file={log_file_path}")

    @classmethod
    def get_logger(cls, name: Optional[str] = None):
        """
        获取logger实例

        Args:
            name: logger名称（可选）

        Returns:
            logger实例
        """
        if not cls._initialized:
            cls.setup_logging()

        if name:
            return logger.bind(name=name)
        return logger


# 便捷函数
def get_logger(name: Optional[str] = None):
    """
    获取logger实例的便捷函数

    Args:
        name: logger名称（可选）

    Returns:
        logger实例

    Examples:
        >>> logger = get_logger("my_module")
        >>> logger.info("这是一条日志")
    """
    return LoggerManager.get_logger(name)
