"""
对话路由
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from api.schemas import ChatRequest, ChatResponse, StreamChatRequest
from api.dependencies import get_chat_service, get_streaming_service
from application.services import ChatService, StreamingService
from core.logging import logger

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service)
) -> ChatResponse:
    """
    对话接口

    Args:
        request: 对话请求
        chat_service: 对话服务（依赖注入）

    Returns:
        ChatResponse: 对话响应
    """
    try:
        result = await chat_service.chat(
            user_id=request.user_id,
            session_id=request.session_id,
            query=request.query,
            enable_knowledge=request.enable_knowledge,
            top_k=request.top_k,
            metadata=request.metadata
        )

        return ChatResponse(**result)

    except Exception as e:
        logger.error(f"对话接口错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(
    request: Request,
    session_id: str = Query(..., description="会话ID"),
    user_id: str = Query(..., description="用户ID"),
    scene_id: int = Query(1, description="场景ID: 1=混合查询, 2=仅Neo4j, 3=仅ES"),
    streaming_service: StreamingService = Depends(get_streaming_service)
):
    """
    流式对话接口（兼容old版本）

    Args:
        request: 原始请求（包含body）
        session_id: 会话ID（Query参数）
        user_id: 用户ID（Query参数）
        scene_id: 场景ID（Query参数）
        streaming_service: 流式服务（依赖注入）

    Returns:
        StreamingResponse: SSE流式响应
    """
    try:
        # 从body中获取message字段
        body = await request.json()
        query = body.get("message", "").strip()

        if not query:
            raise HTTPException(status_code=400, detail="用户查询不能为空")

        # 根据scene_id决定是否启用知识检索
        # scene_id: 1=混合, 2=仅Neo4j, 3=仅ES
        enable_knowledge = scene_id in [1, 2, 3]  # 都启用知识检索

        stream = streaming_service.chat_stream(
            user_id=user_id,
            session_id=session_id,
            query=query,
            enable_knowledge=enable_knowledge,
            top_k=5
        )

        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"流式对话接口错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate")
async def regenerate_response(
    session_id: str,
    user_id: str = "default_user",
    enable_knowledge: bool = True,
    top_k: int = 5,
    chat_service: ChatService = Depends(get_chat_service)
) -> Dict[str, Any]:
    """
    重新生成回复

    Args:
        session_id: 会话ID
        user_id: 用户ID
        enable_knowledge: 是否启用知识检索
        top_k: 知识检索数量
        chat_service: 对话服务（依赖注入）

    Returns:
        Dict: 对话结果
    """
    try:
        result = await chat_service.regenerate_response(
            user_id=user_id,
            session_id=session_id,
            enable_knowledge=enable_knowledge,
            top_k=top_k
        )

        return result

    except Exception as e:
        logger.error(f"重新生成接口错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
