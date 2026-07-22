# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

BEIJING_TZ = timezone(timedelta(hours=8))


# 返回当前北京时间（带时区信息）
def _beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=True)
    email: Mapped[str] = mapped_column(String(200), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_beijing_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_beijing_now, onupdate=_beijing_now)