from fastapi import APIRouter

from app.api.routes import profile, auth

router = APIRouter()

router.include_router(profile.router, prefix="/api/profiles", tags=["Profiles"])
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])


@router.get("/")
async def root():
    return {"message": "Welcome to the HNG 14 Backend API!"}
