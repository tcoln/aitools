# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import json
import uuid
import re
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, async_session
from schemas.chat import ChatRequest
from models.user import User
from models.chat_history import ChatHistory
from models.mcp_service import MCPService
from services.llm_service import llm_service
from services.mcp_client import mcp_client_manager


# 去除消息中的文件内容，保留文件名标记
def _strip_file_content(content: str) -> str:
    if not content:
        return content
    file_pattern = re.compile(r'\n\n\[文件:\s*[^\]]+\][\s\S]*?(?=\n\n\[|\Z)')
    attach_pattern = re.compile(r'\n\n\[附件:\s*[^\]]+\]')
    file_names = []
    for m in file_pattern.finditer(content):
        name_match = re.search(r'\[文件:\s*([^\]]+)\]', m.group())
        if name_match:
            file_names.append('📎 ' + name_match.group(1).strip())
    for m in attach_pattern.finditer(content):
        name_match = re.search(r'\[附件:\s*([^\]]+)\]', m.group())
        if name_match:
            file_names.append('📎 ' + name_match.group(1).strip())
    cleaned = file_pattern.sub('', content)
    cleaned = attach_pattern.sub('', cleaned)
    cleaned = cleaned.strip()
    if file_names:
        cleaned = (cleaned + '\n' if cleaned else '') + '\n'.join(file_names)
    return cleaned or content
from services.builtin_tools import BUILTIN_TOOLS, BUILTIN_SERVICE_NAME, execute_builtin_tool
from services.file_parser import parse_file
from routers.auth import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


# 获取当前可用的LLM模型列表
@router.get("/models")
async def list_models(current_user: User = Depends(get_current_user)):
    return await llm_service.fetch_models()


# 上传并解析文件，支持xlsx、docx、txt等格式
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    try:
        content = await file.read()
        parsed = parse_file(file.filename, content)
        if parsed.startswith("["):
            if "解析失败" in parsed or "未安装" in parsed or "不支持" in parsed or "无法解码" in parsed:
                raise HTTPException(status_code=400, detail=parsed.strip("[]"))
        return {"filename": file.filename, "content": parsed}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件解析失败: {e}")


# 发送聊天消息（SSE流式响应），支持工具调用和多轮对话
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

    for tool in BUILTIN_TOOLS:
        all_tools.append(tool)
        tool_to_service_map[tool["name"]] = BUILTIN_SERVICE_NAME

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
        content=_strip_file_content(req.message),
    )
    db.add(user_msg)
    await db.commit()

    # SSE流式生成器：处理LLM对话、工具调用和结果回传
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
                mcp_tool_calls = []
                for tc in tool_calls_collected:
                    func_name = tc["function"]["name"]
                    service_name = tool_to_service_map.get(func_name, "")
                    if service_name == BUILTIN_SERVICE_NAME:
                        try:
                            func_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            func_args = {}
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': func_name, 'arguments': func_args})}\n\n"
                        result = await execute_builtin_tool(func_name, func_args)
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': func_name, 'result': result})}\n\n"
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                    else:
                        mcp_tool_calls.append(tc)

                if mcp_tool_calls:
                    mcp_service_configs = [
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
                    ]
                    async for event in llm_service.execute_tool_calls(
                        mcp_tool_calls, mcp_service_configs, tool_to_service_map,
                    ):
                        if event["type"] == "tool_start":
                            yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': event['tool_name'], 'arguments': event['arguments']})}\n\n"
                        elif event["type"] == "tool_result":
                            yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': event['tool_name'], 'result': event['result']})}\n\n"
                        elif event["type"] == "tool_results_complete":
                            tool_results.extend(event["results"])

                for tr in tool_results:
                    messages.append(tr)

                final_content = ""
                async for chunk in llm_service.chat_with_tool_results(messages, all_tools, req.model):
                    final_content += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                async with async_session() as gen_db:
                    assistant_msg = ChatHistory(
                        user_id=current_user.id,
                        conversation_id=conversation_id,
                        role="assistant",
                        content=final_content,
                        tool_calls=json.dumps(tool_calls_collected, ensure_ascii=False),
                    )
                    gen_db.add(assistant_msg)
                    await gen_db.commit()
            else:
                async with async_session() as gen_db:
                    assistant_msg = ChatHistory(
                        user_id=current_user.id,
                        conversation_id=conversation_id,
                        role="assistant",
                        content=full_content,
                    )
                    gen_db.add(assistant_msg)
                    await gen_db.commit()

            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conversation_id})}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
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


# 获取聊天页面可用的工具列表（内置工具 + MCP工具）
@router.get("/tools")
async def list_chat_tools(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tools = []

    for tool in BUILTIN_TOOLS:
        icon = "📅" if "date" in tool["name"] else "🌤️"
        tools.append({
            "name": tool["name"],
            "description": tool["description"],
            "type": "builtin",
            "icon": icon,
        })

    result = await db.execute(
        select(MCPService).where(MCPService.is_active == True).order_by(MCPService.created_at.desc())
    )
    services = result.scalars().all()
    for svc in services:
        tools.append({
            "name": svc.name,
            "description": svc.description or "",
            "type": "mcp",
            "icon": "🔌",
        })

    return tools


# 获取当前用户的对话列表，按时间倒序
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


# 获取指定对话的所有消息记录
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


# 删除指定对话及其所有消息
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