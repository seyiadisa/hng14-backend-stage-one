from fastapi import APIRouter, Depends

from app.api.routes import profile, auth
from app.dependencies.auth import verify_api_version_header

router = APIRouter()

router.include_router(
    profile.router,
    prefix="/api/profiles",
    tags=["Profiles"],
    dependencies=[Depends(verify_api_version_header)],
)
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])


@router.get("/")
async def root():
    return {"message": "Welcome to the HNG 14 Backend API!"}
