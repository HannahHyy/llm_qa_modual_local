"""
会话路由
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional, Dict, Any
from api.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    SessionListResponse,
    SessionDetailResponse,
    RenameSessionRequest,
    SuccessResponse
)
from api.dependencies import get_session_service
from application.services import SessionService
from core.logging import logger

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.post("/", response_model=CreateSessionResponse)
async def create_session(
    user_id: str = Query(..., description="用户ID"),
    payload: Optional[Dict[str, Any]] = Body(None),
    session_service: SessionService = Depends(get_session_service)
) -> CreateSessionResponse:
    """
    创建新会话（兼容old版本Query参数）

    Args:
        user_id: 用户ID（Query参数，兼容old版本）
        payload: 请求体（可选，包含name字段）
        session_service: 会话服务（依赖注入）

    Returns:
        CreateSessionResponse: 会话信息
    """
    try:
        # 从payload获取name，如果没有则为None
        name = (payload or {}).get("name") if payload else None

        result = await session_service.create_session(
            user_id=user_id,
            name=name
        )

        return CreateSessionResponse(**result)

    except Exception as e:
        logger.error(f"创建会话错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_sessions(
    user_id: str = Query(default="default_user", description="用户ID"),
    limit: Optional[int] = Query(default=None, ge=1, le=100, description="限制数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    session_service: SessionService = Depends(get_session_service)
):
    """
    获取会话列表（兼容old版本，直接返回数组）

    Args:
        user_id: 用户ID
        limit: 限制数量
        offset: 偏移量
        session_service: 会话服务（依赖注入）

    Returns:
        List: 会话列表（直接返回数组，字段使用id而非session_id）
    """
    try:
        result = await session_service.list_sessions(
            user_id=user_id,
            limit=limit,
            offset=offset
        )

        # 兼容old版本：直接返回数组，并将session_id重命名为id
        sessions = result.get("sessions", [])
        return [
            {
                "id": s.get("session_id"),
                "name": s.get("name"),
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
                "message_count": s.get("message_count", 0)
            }
            for s in sessions
        ]

    except Exception as e:
        logger.error(f"获取会话列表错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    user_id: str = Query(default="default_user", description="用户ID"),
    include_messages: bool = Query(default=False, description="是否包含消息"),
    session_service: SessionService = Depends(get_session_service)
) -> SessionDetailResponse:
    """
    获取会话详情

    Args:
        session_id: 会话ID
        user_id: 用户ID
        include_messages: 是否包含消息
        session_service: 会话服务（依赖注入）

    Returns:
        SessionDetailResponse: 会话详情
    """
    try:
        result = await session_service.get_session(
            user_id=user_id,
            session_id=session_id,
            include_messages=include_messages
        )

        return SessionDetailResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取会话详情错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}", response_model=SuccessResponse)
async def delete_session(
    session_id: str,
    user_id: str = Query(default="default_user", description="用户ID"),
    session_service: SessionService = Depends(get_session_service)
) -> SuccessResponse:
    """
    删除会话

    Args:
        session_id: 会话ID
        user_id: 用户ID
        session_service: 会话服务（依赖注入）

    Returns:
        SuccessResponse: 删除结果
    """
    try:
        result = await session_service.delete_session(
            user_id=user_id,
            session_id=session_id
        )

        return SuccessResponse(
            success=True,
            message="会话删除成功",
            data=result
        )

    except Exception as e:
        logger.error(f"删除会话错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{session_id}/rename", response_model=SessionDetailResponse)
async def rename_session(
    session_id: str,
    request: RenameSessionRequest,
    user_id: str = Query(default="default_user", description="用户ID"),
    session_service: SessionService = Depends(get_session_service)
) -> SessionDetailResponse:
    """
    重命名会话

    Args:
        session_id: 会话ID
        request: 重命名请求
        user_id: 用户ID
        session_service: 会话服务（依赖注入）

    Returns:
        SessionDetailResponse: 更新后的会话信息
    """
    try:
        result = await session_service.rename_session(
            user_id=user_id,
            session_id=session_id,
            new_name=request.name
        )

        return SessionDetailResponse(**result)

    except Exception as e:
        logger.error(f"重命名会话错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user_id: str = Query(..., description="用户ID"),
    session_service: SessionService = Depends(get_session_service)
):
    """
    获取会话消息（兼容old版本API）

    Args:
        session_id: 会话ID
        user_id: 用户ID
        session_service: 会话服务（依赖注入）

    Returns:
        List: 消息列表
    """
    try:
        result = await session_service.get_session(
            user_id=user_id,
            session_id=session_id,
            include_messages=True
        )

        # 返回消息列表
        return result.get("messages", [])

    except ValueError as e:
        raise HTTPException(status_code=404, detail="会话不存在")
    except Exception as e:
        logger.error(f"获取会话消息错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}/messages", response_model=SuccessResponse)
async def clear_session_messages(
    session_id: str,
    user_id: str = Query(default="default_user", description="用户ID"),
    session_service: SessionService = Depends(get_session_service)
) -> SuccessResponse:
    """
    清空会话消息

    Args:
        session_id: 会话ID
        user_id: 用户ID
        session_service: 会话服务（依赖注入）

    Returns:
        SuccessResponse: 清空结果
    """
    try:
        result = await session_service.clear_session_messages(
            user_id=user_id,
            session_id=session_id
        )

        return SuccessResponse(
            success=True,
            message="会话消息清空成功",
            data=result
        )

    except Exception as e:
        logger.error(f"清空会话消息错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
