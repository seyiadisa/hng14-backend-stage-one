from fastapi import APIRouter

from app.api.routes import profile

router = APIRouter()

router.include_router(profile.router, prefix="/api/profiles", tags=["Profiles"])
