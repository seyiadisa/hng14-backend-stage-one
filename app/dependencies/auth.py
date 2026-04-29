from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession


from app.models.user import User
from app.models.enums import Role
from app.core.security import decode_access_token
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)
cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)


async def get_current_user(
    bearer_token: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    cookie_token: str | None = Depends(cookie_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = None

    if bearer_token:
        token = bearer_token.credentials
    elif cookie_token:
        token = cookie_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    user = await db.get(User, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    return user


def require_roles(*roles: Role):
    def role_checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

    return role_checker


def verify_api_version_header(request: Request):
    version_header = request.headers.get("X-API-Version")

    if not version_header or not version_header == "1":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API version header required",
        )
