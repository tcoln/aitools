# Author: glt
# Email: guolintan@qq.com
# Created: 2026-07-22

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import settings

os.makedirs(settings.DATA_DIR, exist_ok=True)

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# 获取数据库会话（FastAPI 依赖注入用）
async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


# 初始化数据库：创建所有表
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)