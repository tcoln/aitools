# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

from datetime import datetime
from pydantic import BaseModel, Field


class MCPServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    transport_type: str = "stdio"
    command: str | None = None
    args: str | None = None
    env_vars: str | None = None
    url: str | None = None
    headers: str | None = None


class MCPServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    transport_type: str | None = None
    command: str | None = None
    args: str | None = None
    env_vars: str | None = None
    url: str | None = None
    headers: str | None = None
    is_active: bool | None = None


class MCPServiceResponse(BaseModel):
    id: str
    name: str
    description: str | None
    transport_type: str
    command: str | None
    args: str | None
    env_vars: str | None
    url: str | None
    headers: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True