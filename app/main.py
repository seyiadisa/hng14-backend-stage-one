from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import router
from app.core.config import get_settings
from app.core.errors import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.db.base import Base
from app.db.session import engine
from app.core.limiter import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter

app.include_router(router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[get_settings().frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore
