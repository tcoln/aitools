# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-23

from pydantic import BaseModel, Field


class PromptVariable(BaseModel):
    name: str
    value: str


class ChatABCInitSessionRequest(BaseModel):
    prompt_variables: list[PromptVariable] | None = None


class ChatABCInitSessionResponse(BaseModel):
    session_id: str


class ChatABCChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    txt: str = Field(..., min_length=1)
    files: list[dict] | None = None
    stream: bool = True


class ChatABCFileItem(BaseModel):
    file_id: str
    url: str
    content_type: str = "doc"


class ChatABCFetchHistoryRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    jsonpath: str | None = None


class ChatABCFetchHistoryResponse(BaseModel):
    status: str
    data: dict | None = None