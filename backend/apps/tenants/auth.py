from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from django.conf import settings
from ninja.security import HttpBearer


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def create_operator_token(operator) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(operator.id),
        "type": "operator",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=ALGORITHM)


def verify_operator_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SIGNING_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "operator":
            return None
        return payload
    except JWTError:
        return None


class OperatorAuth(HttpBearer):
    def authenticate(self, request, token: str):
        payload = verify_operator_token(token)
        if not payload:
            return None
        from apps.tenants.models import Operator
        try:
            return Operator.objects.get(id=payload["sub"])
        except Operator.DoesNotExist:
            return None


class TenantKeyAuth(HttpBearer):
    def authenticate(self, request, token: str):
        from apps.tenants.models import Tenant
        tenant = Tenant.verify_key(token)
        if not tenant:
            return None
        return tenant


def create_tenant_agent_token(agent) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(agent.id),
        "tenant_id": str(agent.tenant_id),
        "type": "tenant_agent",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=ALGORITHM)


def verify_tenant_agent_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SIGNING_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "tenant_agent":
            return None
        return payload
    except JWTError:
        return None


class TenantAgentAuth(HttpBearer):
    def authenticate(self, request, token: str):
        payload = verify_tenant_agent_token(token)
        if not payload:
            return None
        from apps.tenants.models import TenantAgent
        try:
            return TenantAgent.objects.select_related("tenant").get(
                id=payload["sub"], is_active=True
            )
        except TenantAgent.DoesNotExist:
            return None


operator_auth = OperatorAuth()
tenant_key_auth = TenantKeyAuth()
tenant_agent_auth = TenantAgentAuth()
