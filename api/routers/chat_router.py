"""
对话路由
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from api.schemas import ChatRequest, ChatResponse, StreamChatRequest
from api.dependencies import get_chat_service, get_streaming_service, get_legacy_streaming_service
from application.services import ChatService, StreamingService
from application.services.legacy_streaming_service import LegacyStreamingService
from fastapi import BackgroundTasks
from core.logging import logger

# router初始化定义
router = APIRouter(prefix="/api/chat", tags=["Chat"])

# 完整路径: /api/chat + / = /api/chat/
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

# 完整路径: /api/chat + /stream = /api/chat/stream
@router.post("/stream")
async def chat_stream(
    request: Request,
    background_tasks: BackgroundTasks,
    session_id: str = Query(..., description="会话ID"),
    user_id: str = Query(..., description="用户ID"),
    scene_id: int = Query(1, description="场景ID: 1=混合查询, 2=仅Neo4j, 3=仅ES"),
    legacy_streaming_service: LegacyStreamingService = Depends(get_legacy_streaming_service)
):
    """
    流式对话接口（完全兼容server2.py）

    使用Legacy流式服务,输出格式为:
    data:{"content": "...", "message_type": 1}

    message_type说明:
    - 1: think (思考过程)
    - 2: data (LLM回答)
    - 3: knowledge (知识匹配结果)
    - 4: error (错误信息)

    Args:
        request: 原始请求（包含body）
        background_tasks: 后台任务
        session_id: 会话ID（Query参数）
        user_id: 用户ID（Query参数）
        scene_id: 场景ID（1=混合, 2=Neo4j, 3=ES）
        legacy_streaming_service: Legacy流式服务（依赖注入）

    Returns:
        StreamingResponse: 流式响应
    """
    try:
        # 从body中获取message字段
        body = await request.json()
        query = body.get("message", "").strip()

        if not query:
            raise HTTPException(status_code=400, detail="用户查询不能为空")

        # 使用Legacy流式服务
        stream = legacy_streaming_service.chat_stream_by_scene(
            user_id=user_id,
            session_id=session_id,
            query=query,
            scene_id=scene_id,
            background_tasks=background_tasks
        )

        return StreamingResponse(
            stream,
            media_type="text/plain; charset=utf-8",  # 与server2.py保持一致
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

# 完整路径: /api/chat + /regenerate = /api/chat/regenerate
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
