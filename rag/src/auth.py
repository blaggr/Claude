from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from .config import settings


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    if not settings.api_bearer_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_BEARER_TOKEN not configured on server.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(token, settings.api_bearer_token):
        raise HTTPException(status_code=401, detail="Invalid bearer token.")
