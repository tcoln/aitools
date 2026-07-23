# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-23

import json
import uuid
import time
import asyncio
import logging
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="Mock ChatABC Service", version="1.0.0")

_sessions: dict[str, dict] = {}
_chat_histories: dict[str, list[dict]] = {}
_uploaded_files: dict[str, dict[str, bytes]] = {}


class InitSessionBody(BaseModel):
    appId: str = ""
    trCode: str = ""
    trVersion: str = ""
    timestamp: int = 0
    requestId: str = ""
    data: dict = {}


class ChatBody(BaseModel):
    appId: str = ""
    trCode: str = ""
    trVersion: str = ""
    timestamp: int = 0
    requestId: str = ""
    data: dict = {}


class FetchHistoryBody(BaseModel):
    appId: str = ""
    trCode: str = ""
    trVersion: str = ""
    timestamp: int = 0
    requestId: str = ""
    data: dict = {}


@app.post("/chatabc/init_session")
async def init_session(body: InitSessionBody):
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "session_id": session_id,
        "prompt_variables": body.data.get("prompt_variables", []),
        "created_at": time.time(),
    }
    _chat_histories[session_id] = []
    _uploaded_files[session_id] = {}
    logger.info(f"init_session: {session_id}")
    return {"session_id": session_id}


@app.post("/chatabc/upload_file")
async def upload_file(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    content = await file.read()
    if session_id not in _uploaded_files:
        _uploaded_files[session_id] = {}
    file_path = f"/tmp/chatabc/{session_id}/{file.filename}"
    _uploaded_files[session_id][file.filename] = content
    logger.info(f"upload_file: session={session_id}, filename={file.filename}, size={len(content)}")
    return {"status": "SUCCESS", "file_path": file_path}


@app.post("/chatabc/chat")
async def chat(body: ChatBody):
    session_id = body.data.get("session_id", "")
    txt = body.data.get("txt", "")
    stream = body.data.get("stream", True)

    chat_id = f"{session_id}#{len(_chat_histories.get(session_id, [])) + 1}"

    async def generate():
        yield f"event:chat_started\ndata:{json.dumps({'chat_id': chat_id})}\n\n"

        mock_response = f"收到您的消息：「{txt}」。这是一个模拟的ChatABC回复。"
        if stream:
            for char in mock_response:
                chunk_data = {
                    "content": char,
                    "additional_kwargs": {},
                    "response_metadata": {},
                    "type": "ai",
                    "name": None,
                    "id": None,
                    "tool_calls": [],
                    "invalid_tool_calls": [],
                    "usage_metadata": None,
                }
                yield f"event:chunk\ndata:{json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)

        message_data = {
            "content": mock_response,
            "additional_kwargs": {},
            "response_metadata": {},
            "type": "AIMessageChunk",
            "name": None,
            "id": f"lc_run-{uuid.uuid4()}",
            "tool_calls": [],
            "invalid_tool_calls": [],
            "usage_metadata": None,
            "tool_call_chunks": [],
            "chunk_position": None,
        }
        yield f"event:message\ndata:{json.dumps(message_data, ensure_ascii=False)}\n\n"

        if session_id not in _chat_histories:
            _chat_histories[session_id] = []
        _chat_histories[session_id].append({
            "chat_id": chat_id,
            "question": txt,
            "answer": mock_response,
            "timestamp": time.time(),
        })

        yield f"event:done\ndata:{json.dumps({'status': 'success', 'rescode': 'FAIAG0000'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/chatabc/download_file")
async def download_file(session_id: str, filename: str):
    files = _uploaded_files.get(session_id, {})
    content = files.get(filename)
    if content is None:
        return {"status": "FAILED", "error": f"File {filename} not found for session {session_id}"}
    logger.info(f"download_file: session={session_id}, filename={filename}")
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/chatabc/fetch_history")
async def fetch_history(body: FetchHistoryBody):
    session_id = body.data.get("session_id", "")
    jsonpath = body.data.get("jsonpath")

    history = _chat_histories.get(session_id, [])
    logger.info(f"fetch_history: session={session_id}, jsonpath={jsonpath}, records={len(history)}")

    status = "idle"
    if history and time.time() - history[-1].get("timestamp", 0) < 5:
        status = "running"

    return {
        "data": {
            "status": status,
            "history": history,
        }
    }


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(_sessions)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mock_chatabc:app", host="0.0.0.0", port=9000, reload=True)