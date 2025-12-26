"""
重试机制

提供装饰器和工具函数实现自动重试功能
"""

import asyncio
import time
from functools import wraps
from typing import Callable, Type, Tuple, Optional
from core.logging import logger


def retry_sync(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    同步函数重试装饰器

    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟倍数（指数退避）
        exceptions: 需要重试的异常类型
        on_retry: 重试时的回调函数

    Example:
        @retry_sync(max_attempts=3, delay=1.0, backoff=2.0)
        def api_call():
            response = requests.get("https://api.example.com")
            return response.json()
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            f"[重试] {func.__name__} 失败，已达最大尝试次数 {max_attempts}",
                            exc_info=True
                        )
                        raise

                    logger.warning(
                        f"[重试] {func.__name__} 第{attempt}次失败: {str(e)}, "
                        f"{current_delay:.1f}秒后重试..."
                    )

                    if on_retry:
                        on_retry(attempt, e)

                    time.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        return wrapper
    return decorator


def retry_async(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    异步函数重试装饰器

    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟倍数（指数退避）
        exceptions: 需要重试的异常类型
        on_retry: 重试时的回调函数（可以是async函数）

    Example:
        @retry_async(max_attempts=3, delay=1.0, backoff=2.0)
        async def api_call():
            async with httpx.AsyncClient() as client:
                response = await client.get("https://api.example.com")
                return response.json()
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            f"[重试] {func.__name__} 失败，已达最大尝试次数 {max_attempts}",
                            exc_info=True
                        )
                        raise

                    logger.warning(
                        f"[重试] {func.__name__} 第{attempt}次失败: {str(e)}, "
                        f"{current_delay:.1f}秒后重试..."
                    )

                    if on_retry:
                        if asyncio.iscoroutinefunction(on_retry):
                            await on_retry(attempt, e)
                        else:
                            on_retry(attempt, e)

                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        return wrapper
    return decorator


# 常用异常组合
class RetryExceptions:
    """常用的重试异常组合"""

    # 网络相关异常
    NETWORK = (
        ConnectionError,
        TimeoutError,
        OSError,
    )

    # HTTP相关异常（需要安装对应库后取消注释）
    # HTTP = (
    #     httpx.HTTPError,
    #     httpx.TimeoutException,
    # )

    # 数据库相关异常
    # DATABASE = (
    #     pymysql.err.OperationalError,
    #     redis.exceptions.ConnectionError,
    # )
