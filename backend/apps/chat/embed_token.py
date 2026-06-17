from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from django.conf import settings

ALGORITHM = "HS256"


def create_embed_token(
    tenant_id: str,
    visitor_id: str,
    visitor_context: dict,
    ttl_seconds: int = None,
) -> str:
    if ttl_seconds is None:
        ttl_seconds = settings.EMBED_TOKEN_TTL_SECONDS
    expire = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    payload = {
        "type": "embed",
        "tenant_id": tenant_id,
        "visitor_id": visitor_id,
        "visitor_context": visitor_context,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=ALGORITHM)


def verify_embed_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SIGNING_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "embed":
            return None
        return payload
    except JWTError:
        return None
