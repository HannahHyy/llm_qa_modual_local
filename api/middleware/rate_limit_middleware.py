"""
限流中间件
"""

import time
from collections import defaultdict
from typing import Dict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from core.logging import logger


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    限流中间件

    基于IP的简单限流实现
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000
    ):
        """
        初始化限流中间件

        Args:
            app: FastAPI应用
            requests_per_minute: 每分钟请求限制
            requests_per_hour: 每小时请求限制
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

        # 存储请求记录 {ip: [timestamp1, timestamp2, ...]}
        self.request_records: Dict[str, list] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        """
        处理请求

        Args:
            request: 请求对象
            call_next: 下一个中间件

        Returns:
            Response: 响应对象
        """
        # 获取客户端IP
        client_ip = request.client.host if request.client else "unknown"

        # 跳过健康检查接口
        if request.url.path.startswith("/api/health"):
            return await call_next(request)

        # 当前时间
        current_time = time.time()

        # 清理过期记录（超过1小时）
        self._cleanup_old_records(client_ip, current_time)

        # 检查限流
        if self._is_rate_limited(client_ip, current_time):
            logger.warning(f"限流触发: IP={client_ip}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RateLimitExceeded",
                    "message": "请求过于频繁，请稍后再试",
                    "details": {
                        "limit_per_minute": self.requests_per_minute,
                        "limit_per_hour": self.requests_per_hour
                    }
                }
            )

        # 记录请求
        self.request_records[client_ip].append(current_time)

        # 继续处理
        response = await call_next(request)

        # 添加限流信息到响应头
        minute_count = self._count_requests(client_ip, current_time, 60)
        hour_count = self._count_requests(client_ip, current_time, 3600)

        response.headers["X-RateLimit-Minute-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Minute-Remaining"] = str(
            max(0, self.requests_per_minute - minute_count)
        )
        response.headers["X-RateLimit-Hour-Limit"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Hour-Remaining"] = str(
            max(0, self.requests_per_hour - hour_count)
        )

        return response

    def _is_rate_limited(self, client_ip: str, current_time: float) -> bool:
        """
        检查是否触发限流

        Args:
            client_ip: 客户端IP
            current_time: 当前时间

        Returns:
            bool: 是否限流
        """
        # 检查每分钟限制
        minute_count = self._count_requests(client_ip, current_time, 60)
        if minute_count >= self.requests_per_minute:
            return True

        # 检查每小时限制
        hour_count = self._count_requests(client_ip, current_time, 3600)
        if hour_count >= self.requests_per_hour:
            return True

        return False

    def _count_requests(
        self,
        client_ip: str,
        current_time: float,
        time_window: int
    ) -> int:
        """
        统计时间窗口内的请求数

        Args:
            client_ip: 客户端IP
            current_time: 当前时间
            time_window: 时间窗口（秒）

        Returns:
            int: 请求数
        """
        if client_ip not in self.request_records:
            return 0

        cutoff_time = current_time - time_window
        return sum(1 for t in self.request_records[client_ip] if t > cutoff_time)

    def _cleanup_old_records(self, client_ip: str, current_time: float):
        """
        清理过期记录

        Args:
            client_ip: 客户端IP
            current_time: 当前时间
        """
        if client_ip in self.request_records:
            cutoff_time = current_time - 3600  # 保留1小时内的记录
            self.request_records[client_ip] = [
                t for t in self.request_records[client_ip]
                if t > cutoff_time
            ]


# 创建中间件工厂函数
def rate_limit_middleware(
    requests_per_minute: int = 60,
    requests_per_hour: int = 1000
):
    """
    创建限流中间件

    Args:
        requests_per_minute: 每分钟请求限制
        requests_per_hour: 每小时请求限制

    Returns:
        RateLimitMiddleware: 限流中间件类
    """
    def factory(app):
        return RateLimitMiddleware(
            app,
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour
        )
    return factory
