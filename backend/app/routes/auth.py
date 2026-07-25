from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth import create_access_token, create_refresh_token, get_current_user
from app.config import settings
from app.db import (
    create_verification_code,
    get_user_by_email,
    get_user_refresh_expiry,
    set_user_refresh_expiry,
    verify_code,
)
from app.email import send_verification_email
from app.logging import get_logger
from app.schemas import (
    AuthRequestCodeRequest,
    AuthRequestCodeResponse,
    AuthVerifyRequest,
    AuthVerifyResponse,
    User,
)

log = get_logger(__name__)
router = APIRouter()


def _set_token_cookies(response: Response, access_token: str, refresh_token: str | None = None):
    response.set_cookie(
        "jwt_token",
        access_token,
        max_age=180,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    if refresh_token:
        response.set_cookie(
            "refresh_token",
            refresh_token,
            max_age=15552000,
            httponly=True,
            secure=False,
            samesite="lax",
            path="/",
        )


@router.post("/api/auth/request-code", response_model=AuthRequestCodeResponse)
async def request_code(req: AuthRequestCodeRequest):
    user = get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=404, detail="Not registered")

    code = create_verification_code(req.email)
    log.info("Verification code for %s: %s (DEV ONLY)", req.email, code)
    send_verification_email(req.email, code)

    return AuthRequestCodeResponse(message="Code sent")


@router.post("/api/auth/verify", response_model=AuthVerifyResponse)
async def verify(req: AuthVerifyRequest, response: Response):
    if not verify_code(req.email, req.code):
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    user = get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    refresh_expires_at = (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
    set_user_refresh_expiry(user.id, refresh_expires_at)
    _set_token_cookies(response, access_token, refresh_token)
    return AuthVerifyResponse(access_token=access_token, user=user)


@router.post("/api/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        email = payload.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    db_expiry = get_user_refresh_expiry(email)
    if not db_expiry or datetime.fromisoformat(db_expiry) < datetime.now(timezone.utc):
        response.delete_cookie("refresh_token", path="/")
        response.delete_cookie("jwt_token", path="/")
        raise HTTPException(status_code=401, detail="Refresh token revoked, please login again")

    access_token = create_access_token(user)
    _set_token_cookies(response, access_token)
    return {"access_token": access_token}


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = jwt.decode(refresh_token, settings.jwt_secret_key, algorithms=["HS256"])
            user = get_user_by_email(payload.get("email", ""))
            if user:
                set_user_refresh_expiry(user.id, None)
        except Exception:
            pass
    response.delete_cookie("jwt_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}


@router.get("/api/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
