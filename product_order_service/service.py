import httpx
from fastapi import Header, HTTPException, Depends

USER_SERVICE_URL = "http://localhost:8000"

async def get_current_user(authorization: str = Header()):
    try:
        async with httpx.AsyncClient(timeout=0.5) as client:
            resp = await client.get(f"{USER_SERVICE_URL}/auth/token/verify", headers={"Authorization": authorization})
    except httpx.RequestError:
        raise HTTPException(503, "User service unavailable")
    if resp.status_code != 200:
        raise HTTPException(401, "Invalid or expired token")
    return resp.json()