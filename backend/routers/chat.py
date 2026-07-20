import json
import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.chat import ChatRequest
from models.user import User
from models.chat_history import ChatHistory
from models.mcp_service import MCPService
from services.llm_service import llm_service
from services.mcp_client import mcp_client_manager
from routers.auth import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/models")
async def list_models(current_user: User = Depends(get_current_user)):
    return await llm_service.fetch_models()


@router.post("/send")
async def send_message(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation_id = req.conversation_id or str(uuid.uuid4())

    history_result = await db.execute(
        select(ChatHistory)
        .where(
            ChatHistory.user_id == current_user.id,
            ChatHistory.conversation_id == conversation_id,
        )
        .order_by(ChatHistory.created_at.asc())
    )
    history_records = history_result.scalars().all()
    history = [
        {"role": h.role, "content": h.content}
        for h in history_records
    ]

    services_result = await db.execute(
        select(MCPService).where(MCPService.is_active == True)
    )
    active_services = services_result.scalars().all()

    all_tools = []
    tool_to_service_map = {}
    for svc in active_services:
        config = {
            "name": svc.name,
            "transport_type": svc.transport_type,
            "command": svc.command,
            "args": svc.args,
            "env_vars": svc.env_vars,
            "url": svc.url,
            "headers": svc.headers,
        }
        try:
            tools = await mcp_client_manager.get_tools(config)
            for tool in tools:
                tool_to_service_map[tool["name"]] = svc.name
            all_tools.extend(tools)
        except Exception as e:
            all_tools.append({
                "name": f"error_{svc.name}",
                "description": f"MCP服务 {svc.name} 连接失败: {str(e)}",
                "inputSchema": {"type": "object", "properties": {}},
            })

    user_msg = ChatHistory(
        user_id=current_user.id,
        conversation_id=conversation_id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    await db.commit()

    async def generate():
        messages = history + [{"role": "user", "content": req.message}]
        full_content = ""
        tool_calls_collected = []

        try:
            async for event in llm_service.chat(req.message, history, all_tools, req.model):
                if event["type"] == "content":
                    full_content += event["content"]
                    yield f"data: {json.dumps({'type': 'content', 'content': event['content']})}\n\n"
                elif event["type"] == "tool_calls":
                    tool_calls_collected = event["tool_calls"]
                    yield f"data: {json.dumps({'type': 'tool_calls', 'tool_calls': [{'function': tc['function']} for tc in tool_calls_collected]})}\n\n"

            if tool_calls_collected:
                messages.append({
                    "role": "assistant",
                    "content": full_content or None,
                    "tool_calls": tool_calls_collected,
                })

                tool_results = []
                async for event in llm_service.execute_tool_calls(
                    tool_calls_collected,
                    [
                        {
                            "name": s.name,
                            "transport_type": s.transport_type,
                            "command": s.command,
                            "args": s.args,
                            "env_vars": s.env_vars,
                            "url": s.url,
                            "headers": s.headers,
                        }
                        for s in active_services
                    ],
                    tool_to_service_map,
                ):
                    if event["type"] == "tool_start":
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': event['tool_name'], 'arguments': event['arguments']})}\n\n"
                    elif event["type"] == "tool_result":
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': event['tool_name'], 'result': event['result']})}\n\n"
                    elif event["type"] == "tool_results_complete":
                        tool_results = event["results"]

                for tr in tool_results:
                    messages.append(tr)

                final_content = ""
                async for chunk in llm_service.chat_with_tool_results(messages, all_tools, req.model):
                    final_content += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                assistant_msg = ChatHistory(
                    user_id=current_user.id,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=final_content,
                    tool_calls=json.dumps(tool_calls_collected, ensure_ascii=False),
                )
                db.add(assistant_msg)
                await db.commit()
            else:
                assistant_msg = ChatHistory(
                    user_id=current_user.id,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_content,
                )
                db.add(assistant_msg)
                await db.commit()

            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conversation_id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations")
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatHistory.conversation_id)
        .where(ChatHistory.user_id == current_user.id)
        .distinct()
        .order_by(ChatHistory.conversation_id)
    )
    conv_ids = [row[0] for row in result.all()]

    conversations = []
    for cid in conv_ids:
        msg_result = await db.execute(
            select(ChatHistory)
            .where(
                ChatHistory.user_id == current_user.id,
                ChatHistory.conversation_id == cid,
            )
            .order_by(ChatHistory.created_at.asc())
            .limit(1)
        )
        first_msg = msg_result.scalar_one_or_none()
        conversations.append({
            "id": cid,
            "first_message": first_msg.content[:100] if first_msg else "",
            "created_at": first_msg.created_at.isoformat() if first_msg else "",
        })

    conversations.sort(key=lambda x: x["created_at"], reverse=True)
    return conversations


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatHistory)
        .where(
            ChatHistory.user_id == current_user.id,
            ChatHistory.conversation_id == conversation_id,
        )
        .order_by(ChatHistory.created_at.asc())
    )
    messages = result.scalars().all()

    return {
        "id": conversation_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "tool_calls": json.loads(m.tool_calls) if m.tool_calls else None,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatHistory).where(
            ChatHistory.user_id == current_user.id,
            ChatHistory.conversation_id == conversation_id,
        )
    )
    messages = result.scalars().all()
    for msg in messages:
        await db.delete(msg)
    await db.commit()
    return {"ok": True}