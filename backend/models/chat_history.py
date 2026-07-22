# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

BEIJING_TZ = timezone(timedelta(hours=8))


# 返回当前北京时间（带时区信息）
def _beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_beijing_now)