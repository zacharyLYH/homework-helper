from fastapi import APIRouter, HTTPException

from app.auth import create_access_token
from app.db import create_verification_code, get_user_by_email, verify_code
from app.email import send_verification_email
from app.logging import get_logger
from app.schemas import (
    AuthRequestCodeRequest,
    AuthRequestCodeResponse,
    AuthVerifyRequest,
    AuthVerifyResponse,
)

log = get_logger(__name__)
router = APIRouter()


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
async def verify(req: AuthVerifyRequest):
    if not verify_code(req.email, req.code):
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    user = get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_access_token(user)
    return AuthVerifyResponse(access_token=token, user=user)
