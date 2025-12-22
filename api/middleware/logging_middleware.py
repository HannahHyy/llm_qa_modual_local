"""
日志中间件
"""

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from core.logging import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件

    记录每个请求的详细信息
    """

    async def dispatch(self, request: Request, call_next):
        """
        处理请求

        Args:
            request: 请求对象
            call_next: 下一个中间件

        Returns:
            Response: 响应对象
        """
        # 记录请求开始
        start_time = time.time()
        request_id = f"{int(start_time * 1000)}"

        logger.info(
            f"请求开始: [{request_id}] {request.method} {request.url.path} "
            f"client={request.client.host if request.client else 'unknown'}"
        )

        # 添加请求ID到请求状态
        request.state.request_id = request_id

        # 调用下一个中间件/路由
        try:
            response = await call_next(request)

            # 计算处理时间
            process_time = (time.time() - start_time) * 1000

            # 记录响应
            logger.info(
                f"请求完成: [{request_id}] {request.method} {request.url.path} "
                f"status={response.status_code} time={process_time:.2f}ms"
            )

            # 添加响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

            return response

        except Exception as e:
            # 计算处理时间
            process_time = (time.time() - start_time) * 1000

            # 记录错误
            logger.error(
                f"请求失败: [{request_id}] {request.method} {request.url.path} "
                f"error={str(e)} time={process_time:.2f}ms"
            )

            raise


# 创建中间件实例
logging_middleware = LoggingMiddleware
