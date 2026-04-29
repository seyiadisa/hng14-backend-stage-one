import base64
import hashlib
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import clear_auth_cookies, hash_token, set_auth_cookies
from app.db.session import get_db
from app.dependencies.auth import verify_csrf_token
from app.models.user import RefreshToken, User
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
    set_auth_cookies(response, access_token, refresh_token, csrf_token, settings)

    return response


@router.post("/refresh", dependencies=[Depends(verify_csrf_token)])
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    token_hash = hash_token(refresh_token)
    token_result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored_token = token_result.scalar_one_or_none()

    if not stored_token:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    expires_at = stored_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= datetime.now(timezone.utc):
        await db.delete(stored_token)
        await db.commit()
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user = await db.get(User, stored_token.user_id)
    if not user or not user.is_active:
        await db.delete(stored_token)
        await db.commit()
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    await db.delete(stored_token)
    access_token, new_refresh_token = await generate_tokens(db, user)
    csrf_token = secrets.token_urlsafe(32)
    set_auth_cookies(response, access_token, new_refresh_token, csrf_token, settings)

    return {"status": "success", "message": "Token refreshed"}


@router.post("/logout", dependencies=[Depends(verify_csrf_token)])
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get("refresh_token")

    if refresh_token:
        token_result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(refresh_token)
            )
        )
        stored_token = token_result.scalar_one_or_none()
        if stored_token:
            await db.delete(stored_token)
            await db.commit()

    clear_auth_cookies(response)
    return {"status": "success", "message": "Logged out successfully"}
