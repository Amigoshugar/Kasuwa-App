import hmac

from fastapi import Header, HTTPException

from app.config import settings


def require_admin(x_admin_token: str = Header(default="")) -> None:
    """Admin endpoints need the X-Admin-Token header to match ADMIN_TOKEN."""
    expected = settings.admin_token
    if not expected or expected == "change-me" or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Admin password missing or wrong")
