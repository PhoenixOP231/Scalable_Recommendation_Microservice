from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.settings import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if settings.DEMO_MODE:
        return "demo_user"
        
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_API_KEY not configured in production mode."
        )
        
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header"
        )
        
    expected = settings.ADMIN_API_KEY.strip()
    provided = api_key.strip()
    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid API Key (expected length {len(expected)}, got length {len(provided)})"
        )
        
    return "admin"

from fastapi import Header

async def verify_cron_secret(authorization: str = Header(None)) -> str:
    """Verify the request comes from Vercel Cron."""
    if not settings.CRON_SECRET:
        raise HTTPException(status_code=500, detail="CRON_SECRET not configured")
        
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        
    token = authorization.split(" ")[1]
    if token != settings.CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid CRON_SECRET")
        
    return "cron"
