import secrets
from typing import List
from ninja import Router, Schema
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from apps.tenants.auth import (
    create_operator_token, create_tenant_agent_token,
    operator_auth, tenant_key_auth, tenant_agent_auth,
)
from apps.tenants.models import Tenant, TenantConfig, TenantAgent

operator_router = Router(tags=["operator"])
tenant_router = Router(tags=["tenant"], auth=tenant_agent_auth)
agent_router = Router(tags=["tenant-agents"])


class LoginIn(Schema):
    username: str
    password: str


class LoginOut(Schema):
    access_token: str


class TenantIn(Schema):
    name: str


class TenantOut(Schema):
    id: str
    name: str
    is_active: bool


class TenantCreatedOut(Schema):
    id: str
    name: str
    is_active: bool
    tenant_key: str
    agent_username: str
    agent_temp_password: str


class TenantConfigOut(Schema):
    model_id: str
    system_prompt: str
    agent_display_name: str
    webhook_url: str
    webhook_type: str
    welcome_message: str
    brand_name: str
    hitl_enabled: bool
    require_identity_verification: bool


class TenantConfigIn(Schema):
    model_id: str = None
    system_prompt: str = None
    agent_display_name: str = None
    webhook_url: str = None
    webhook_type: str = None
    welcome_message: str = None
    brand_name: str = None
    hitl_enabled: bool = None
    require_identity_verification: bool = None


class SlugIn(Schema):
    slug: str


class ResetKeyOut(Schema):
    new_tenant_key: str


class AgentLoginIn(Schema):
    tenant_name: str
    username: str
    password: str


class AgentLoginOut(Schema):
    access_token: str


class AgentOut(Schema):
    id: str
    username: str
    is_active: bool


class AgentCreateIn(Schema):
    username: str


class AgentCreatedOut(Schema):
    id: str
    username: str
    is_active: bool
    temp_password: str


class ChangePasswordIn(Schema):
    current_password: str
    new_password: str


def _make_agent_auth():
    """Returns auth that accepts EITHER TenantAgentAuth OR TenantKeyAuth."""
    from ninja.security import HttpBearer
    from apps.tenants.auth import verify_tenant_agent_token

    class DualAuth(HttpBearer):
        def authenticate(self, request, token: str):
            payload = verify_tenant_agent_token(token)
            if payload:
                try:
                    return TenantAgent.objects.select_related("tenant").get(
                        id=payload["sub"], is_active=True
                    )
                except TenantAgent.DoesNotExist:
                    pass
            tenant = Tenant.verify_key(token)
            if tenant:
                return tenant
            return None

    return DualAuth()


_dual_auth = _make_agent_auth()


@agent_router.post("/auth/login", response={200: AgentLoginOut, 401: dict}, auth=None)
def agent_login(request, body: AgentLoginIn):
    try:
        agent = TenantAgent.objects.select_related("tenant").get(
            tenant__name=body.tenant_name, username=body.username, is_active=True
        )
    except TenantAgent.DoesNotExist:
        return 401, {"detail": "Invalid credentials"}
    except TenantAgent.MultipleObjectsReturned:
        return 401, {"detail": "Invalid credentials"}
    if not agent.check_password(body.password):
        return 401, {"detail": "Invalid credentials"}
    return 200, {"access_token": create_tenant_agent_token(agent)}


def _get_tenant_from_auth(auth_obj):
    if isinstance(auth_obj, TenantAgent):
        return auth_obj.tenant
    return auth_obj


@agent_router.get("/", response=list[AgentOut], auth=_dual_auth)
def list_agents(request):
    tenant = _get_tenant_from_auth(request.auth)
    return [
        {"id": str(a.id), "username": a.username, "is_active": a.is_active}
        for a in TenantAgent.objects.filter(tenant=tenant)
    ]


@agent_router.post("/", response={201: AgentCreatedOut}, auth=_dual_auth)
def create_agent(request, body: AgentCreateIn):
    tenant = _get_tenant_from_auth(request.auth)
    temp_password = secrets.token_urlsafe(16)
    agent = TenantAgent(tenant=tenant, username=body.username)
    agent.set_password(temp_password)
    agent.save()
    return 201, {
        "id": str(agent.id),
        "username": agent.username,
        "is_active": agent.is_active,
        "temp_password": temp_password,
    }


@agent_router.patch("/{agent_id}/deactivate", response={200: AgentOut}, auth=_dual_auth)
def deactivate_agent(request, agent_id: str):
    from django.shortcuts import get_object_or_404
    tenant = _get_tenant_from_auth(request.auth)
    agent = get_object_or_404(TenantAgent, id=agent_id, tenant=tenant)
    agent.is_active = False
    agent.save()
    return {"id": str(agent.id), "username": agent.username, "is_active": agent.is_active}


@agent_router.post("/me/change-password", response={200: dict, 400: dict}, auth=tenant_agent_auth)
def change_password(request, body: ChangePasswordIn):
    agent = request.auth
    if not agent.check_password(body.current_password):
        return 400, {"detail": "현재 비밀번호가 올바르지 않습니다."}
    agent.set_password(body.new_password)
    agent.save()
    return 200, {"detail": "비밀번호가 변경되었습니다."}


@operator_router.post("/auth/login", response={200: LoginOut, 401: dict}, auth=None)
def login(request, body: LoginIn):
    user = authenticate(username=body.username, password=body.password)
    if not user:
        return 401, {"detail": "Invalid credentials"}
    token = create_operator_token(user)
    return 200, {"access_token": token}


@operator_router.post("/tenants/", response={201: TenantCreatedOut}, auth=operator_auth)
def create_tenant(request, body: TenantIn):
    raw_key = secrets.token_urlsafe(32)
    tenant = Tenant.objects.create_with_key(name=body.name, raw_key=raw_key)
    temp_password = secrets.token_urlsafe(16)
    agent = TenantAgent(tenant=tenant, username="admin")
    agent.set_password(temp_password)
    agent.save()
    return 201, {
        "id": str(tenant.id),
        "name": tenant.name,
        "is_active": tenant.is_active,
        "tenant_key": raw_key,
        "agent_username": "admin",
        "agent_temp_password": temp_password,
    }


@operator_router.get("/tenants/", response=List[TenantOut], auth=operator_auth)
def list_tenants(request):
    return [
        {"id": str(t.id), "name": t.name, "is_active": t.is_active}
        for t in Tenant.objects.all()
    ]


@operator_router.patch("/tenants/{tenant_id}/suspend", response={200: TenantOut}, auth=operator_auth)
def suspend_tenant(request, tenant_id: str):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.is_active = False
    tenant.save()
    return {"id": str(tenant.id), "name": tenant.name, "is_active": tenant.is_active}


@operator_router.delete("/tenants/{tenant_id}", response={204: None}, auth=operator_auth)
def delete_tenant(request, tenant_id: str):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.delete()
    return 204, None


def _config_out(config):
    return {
        "model_id": config.model_id,
        "system_prompt": config.system_prompt,
        "agent_display_name": config.agent_display_name,
        "webhook_url": config.webhook_url,
        "webhook_type": config.webhook_type,
        "welcome_message": config.welcome_message,
        "brand_name": config.brand_name,
        "hitl_enabled": config.hitl_enabled,
        "require_identity_verification": config.require_identity_verification,
    }


@tenant_router.get("/config/", response=TenantConfigOut)
def get_config(request):
    return _config_out(request.auth.tenant.config)


@tenant_router.patch("/config/", response=TenantConfigOut)
def update_config(request, body: TenantConfigIn):
    config = request.auth.tenant.config
    for field in ("model_id", "system_prompt", "agent_display_name", "webhook_url", "webhook_type", "welcome_message", "brand_name", "hitl_enabled", "require_identity_verification"):
        value = getattr(body, field)
        if value is not None:
            setattr(config, field, value)
    config.save()
    return _config_out(config)


@tenant_router.post("/reset-key", response={200: ResetKeyOut})
def reset_tenant_key(request):
    tenant = request.auth.tenant
    new_key = tenant.reset_key()
    return 200, {"new_tenant_key": new_key}


@tenant_router.patch("/slug/", response={200: SlugIn})
def update_slug(request, body: SlugIn):
    from ninja.errors import HttpError
    from apps.tenants.slug import is_valid_slug

    if not is_valid_slug(body.slug):
        raise HttpError(400, "Invalid slug format")
    tenant = request.auth.tenant
    if Tenant.objects.filter(slug=body.slug).exclude(id=tenant.id).exists():
        raise HttpError(400, "Slug already taken")
    tenant.slug = body.slug
    tenant.save(update_fields=["slug"])
    return 200, {"slug": tenant.slug}
