import httpx
from fastapi import Header, HTTPException
from config import USER_SERVICE_URL

def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    try:
        resp = httpx.get(
            f"{USER_SERVICE_URL}/auth/token/verify",
            headers={"Authorization": authorization},
            timeout=5.0,
        )
    except httpx.RequestError:
        raise HTTPException(503, "User service unavailable")
    if resp.status_code != 200:
        raise HTTPException(401, "Invalid or expired token")
    user = resp.json()
    user["token"] = authorization      # keep it to forward to the order service
    return user