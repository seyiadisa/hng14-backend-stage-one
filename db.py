from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from config import get_settings

engine = create_async_engine(get_settings().db_url, echo=True)
AsyncSessionLocal = async_sessionmaker(
    bind=engine, expire_on_commit=False, autoflush=False
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
