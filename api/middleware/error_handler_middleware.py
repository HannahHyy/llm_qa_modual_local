"""
错误处理中间件
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from core.exceptions import BaseAppException
from core.logging import logger


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    错误处理中间件

    统一处理应用程序异常
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
        try:
            response = await call_next(request)
            return response

        except BaseAppException as e:
            # 处理业务异常
            error_code = e.error_code
            error_message = e.message
            logger.warning(
                f"业务异常: {error_code} - {error_message}",
                extra={"details": e.details}
            )

            return JSONResponse(
                status_code=400,
                content={
                    "error": e.error_code,
                    "message": e.message,
                    "details": e.details
                }
            )

        except ValueError as e:
            # 处理值错误
            logger.warning(f"参数错误: {str(e)}")

            return JSONResponse(
                status_code=400,
                content={
                    "error": "ValueError",
                    "message": str(e),
                    "details": None
                }
            )

        except Exception as e:
            # 处理未知异常
            logger.error(
                f"未知异常: {type(e).__name__} - {str(e)}",
                exc_info=True
            )

            return JSONResponse(
                status_code=500,
                content={
                    "error": "InternalServerError",
                    "message": "服务器内部错误，请稍后重试",
                    "details": None
                }
            )


# 创建中间件实例
error_handler_middleware = ErrorHandlerMiddleware
