from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.db import get_user_by_email
from app.logging import get_logger
from app.schemas import User

log = get_logger(__name__)


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


async def get_current_user(request: Request) -> User:
    token = request.cookies.get("jwt_token")

    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        email = payload.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
