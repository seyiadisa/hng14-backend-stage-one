from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import Base, engine

app = FastAPI()


@asynccontextmanager
async def lifespan():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield
