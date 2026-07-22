# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    display_name: str | None = None
    email: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    password: str | None = Field(None, min_length=6, max_length=100)
    is_admin: bool | None = None
    is_active: bool | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str | None
    email: str | None
    is_admin: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse