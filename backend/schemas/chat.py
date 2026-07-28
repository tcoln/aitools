# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    model: str | None = None
    files: list[dict] | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    tool_calls: list[dict] | None = None


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    created_at: datetime
    messages: list[dict]