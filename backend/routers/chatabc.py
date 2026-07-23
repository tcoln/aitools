# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-23

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, Response

from schemas.chatabc import (
    ChatABCInitSessionRequest,
    ChatABCChatRequest,
    ChatABCFetchHistoryRequest,
)
from services.chatabc_service import chatabc_service
from routers.auth import get_current_user
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chatabc", tags=["chatabc"])


@router.post("/init_session")
async def init_session(
    req: ChatABCInitSessionRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        prompt_vars = None
        if req.prompt_variables:
            prompt_vars = [pv.model_dump() for pv in req.prompt_variables]
        result = await chatabc_service.init_session(prompt_vars)
        return result
    except Exception as e:
        logger.error(f"init_session error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload_file")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    try:
        content = await file.read()
        result = await chatabc_service.upload_file(
            session_id=session_id,
            filename=file.filename,
            file_content=content,
            content_type=file.content_type or "application/octet-stream",
        )
        return result
    except Exception as e:
        logger.error(f"upload_file error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def chat(
    req: ChatABCChatRequest,
    current_user: User = Depends(get_current_user),
):
    async def generate():
        try:
            async for event in chatabc_service.chat(
                session_id=req.session_id,
                txt=req.txt,
                files=req.files,
                stream=req.stream,
            ):
                evt_type = event["event"]
                evt_data = event["data"]

                if evt_type == "chat_started":
                    yield f"event: chat_started\ndata: {json.dumps(evt_data, ensure_ascii=False)}\n\n"
                elif evt_type == "chunk":
                    content = evt_data.get("content", "")
                    yield f"event: chunk\ndata: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                elif evt_type == "message":
                    content = evt_data.get("content", "")
                    tool_calls = evt_data.get("tool_calls", [])
                    msg = {"content": content}
                    if tool_calls:
                        msg["tool_calls"] = tool_calls
                    yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                elif evt_type == "failed":
                    yield f"event: failed\ndata: {json.dumps(evt_data, ensure_ascii=False)}\n\n"
                elif evt_type == "done":
                    yield f"event: done\ndata: {json.dumps(evt_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"chat stream error: {e}")
            yield f"event: failed\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/download_file")
async def download_file(
    session_id: str,
    filename: str,
    current_user: User = Depends(get_current_user),
):
    try:
        content = await chatabc_service.download_file(session_id, filename)
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"download_file error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fetch_history")
async def fetch_history(
    req: ChatABCFetchHistoryRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = await chatabc_service.fetch_history(
            session_id=req.session_id,
            jsonpath=req.jsonpath,
        )
        return result
    except Exception as e:
        logger.error(f"fetch_history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))