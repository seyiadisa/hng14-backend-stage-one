import httpx
import secrets
import base64
import hashlib
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, Settings
from app.db.session import get_db
from app.models.user import User
from app.services.auth import generate_tokens, get_github_user_info


router = APIRouter()


@router.get("/github")
async def github_login(settings: Settings = Depends(get_settings)):
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    response = RedirectResponse(
        "https://github.com/login/oauth/authorize?"
        + urlencode(
            {
                "client_id": settings.github_client_id,
                "redirect_uri": settings.github_redirect_uri,
                "scope": "read:user user:email",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
    )

    response.set_cookie(
        "github_oauth_state", state, max_age=300, httponly=True, secure=True
    )
    response.set_cookie(
        "github_code_verifier", code_verifier, max_age=300, httponly=True, secure=True
    )

    return response


@router.get("/github/callback")
async def github_callback(
    code: str,
    state: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    saved_state = request.cookies.get("github_oauth_state")
    code_verifier = request.cookies.get("github_code_verifier")

    if not saved_state or not code_verifier or state != saved_state:
        raise HTTPException(status_code=400, detail="Github OAuth state mismatch")

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "redirect_uri": settings.github_redirect_uri,
                "code": code,
                "code_verifier": code_verifier,
            },
        )

    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="GitHub token exchange failed")

    token_data = token_response.json()
    github_access_token = token_data.get("access_token")

    if not github_access_token:
        raise HTTPException(status_code=400, detail="GitHub authentication failed")

    github_user_info = await get_github_user_info(github_access_token)

    user = await db.execute(
        select(User).where(User.github_id == str(github_user_info["id"]))
    )
    user = user.scalar_one_or_none()

    if not user:
        user = User(
            github_id=str(github_user_info["id"]),
            username=github_user_info["login"],
            email=github_user_info.get("email", ""),
            avatar_url=github_user_info.get("avatar_url", ""),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access_token, refresh_token = await generate_tokens(db, user)
    csrf_token = secrets.token_urlsafe(32)

    response = RedirectResponse(settings.frontend_redirect_uri)
    response.delete_cookie("github_oauth_state")
    response.delete_cookie("github_code_verifier")
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=True,
        max_age=settings.access_token_expire_minutes * 60,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=True,
        max_age=settings.refresh_token_expire_minutes * 60,
    )
    response.set_cookie(
        "csrf_token",
        csrf_token,
        secure=True,
        max_age=settings.access_token_expire_minutes * 60,
    )

    return response


@router.post("/refresh")
async def refresh_token():
    pass


@router.post("/logout")
async def logout():
    pass
