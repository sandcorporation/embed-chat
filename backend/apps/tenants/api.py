import secrets
from typing import List
from ninja import Router, Schema
from django.contrib.auth import authenticate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from apps.tenants.auth import (
    create_operator_token, create_tenant_agent_token,
    operator_auth, tenant_key_auth, tenant_agent_auth,
)
from apps.tenants.auth_cookies import (
    set_refresh_cookie, clear_refresh_cookie, cookie_name, OPERATOR, TENANT_AGENT,
)
from apps.tenants.refresh_tokens import (
    issue_session, rotate, revoke_all, revoke_session, RefreshRejected,
)
from apps.tenants.models import Operator, Tenant, TenantConfig, TenantAgent

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
    created_at: str


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
    llm_provider_type: str
    llm_base_url: str
    llm_api_key: str
    extraction_model: str
    embed_provider_type: str
    embed_base_url: str
    embed_api_key: str
    embed_model: str
    embed_dim: int
    # 서버 capability(저장 필드 아님): dev에서만 플랫폼 기본(OpenRouter/ollama) Provider 폴백이
    # 켜진다. 어드민 UI는 이 값이 false면 "기본" Provider 옵션을 숨긴다(ADR-0012).
    platform_default_providers_enabled: bool


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
    llm_provider_type: str = None
    llm_base_url: str = None
    llm_api_key: str = None
    extraction_model: str = None
    embed_provider_type: str = None
    embed_base_url: str = None
    embed_api_key: str = None
    embed_model: str = None
    embed_dim: int = None


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
def agent_login(request, body: AgentLoginIn, response: HttpResponse):
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
    set_refresh_cookie(response, agent, issue_session(agent))
    return 200, {"access_token": create_tenant_agent_token(agent)}


@agent_router.post("/auth/refresh", response={200: AgentLoginOut, 401: dict}, auth=None)
def agent_refresh(request, response: HttpResponse):
    raw = request.COOKIES.get(cookie_name(TENANT_AGENT))
    if not raw:
        return 401, {"detail": "No refresh token"}
    try:
        subject, new_raw = rotate(raw)
    except RefreshRejected:
        return 401, {"detail": "Invalid refresh token"}
    if not isinstance(subject, TenantAgent) or not subject.is_active:
        return 401, {"detail": "Invalid refresh token"}
    set_refresh_cookie(response, subject, new_raw)
    return 200, {"access_token": create_tenant_agent_token(subject)}


@agent_router.post("/auth/logout", response={200: dict}, auth=None)
def agent_logout(request, response: HttpResponse):
    raw = request.COOKIES.get(cookie_name(TENANT_AGENT))
    if raw:
        revoke_session(raw)  # 이 기기 Family만 폐기
    clear_refresh_cookie(response, TENANT_AGENT)
    return 200, {"detail": "logged out"}


@agent_router.post("/auth/logout-all", response={200: dict}, auth=tenant_agent_auth)
def agent_logout_all(request, response: HttpResponse):
    revoke_all(request.auth)  # 주체의 전 기기 Family 폐기
    clear_refresh_cookie(response, TENANT_AGENT)
    return 200, {"detail": "logged out everywhere"}


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
    revoke_all(agent)  # 비번 변경 시 기존 모든 세션의 refresh 폐기(침해 대응)
    return 200, {"detail": "비밀번호가 변경되었습니다."}


@operator_router.post("/auth/login", response={200: LoginOut, 401: dict}, auth=None)
def login(request, body: LoginIn, response: HttpResponse):
    user = authenticate(username=body.username, password=body.password)
    if not user:
        return 401, {"detail": "Invalid credentials"}
    set_refresh_cookie(response, user, issue_session(user))
    return 200, {"access_token": create_operator_token(user)}


@operator_router.post("/auth/refresh", response={200: LoginOut, 401: dict}, auth=None)
def operator_refresh(request, response: HttpResponse):
    raw = request.COOKIES.get(cookie_name(OPERATOR))
    if not raw:
        return 401, {"detail": "No refresh token"}
    try:
        subject, new_raw = rotate(raw)
    except RefreshRejected:
        return 401, {"detail": "Invalid refresh token"}
    if not isinstance(subject, Operator):
        return 401, {"detail": "Invalid refresh token"}
    set_refresh_cookie(response, subject, new_raw)
    return 200, {"access_token": create_operator_token(subject)}


@operator_router.post("/auth/logout", response={200: dict}, auth=None)
def operator_logout(request, response: HttpResponse):
    raw = request.COOKIES.get(cookie_name(OPERATOR))
    if raw:
        revoke_session(raw)  # 이 기기 Family만 폐기
    clear_refresh_cookie(response, OPERATOR)
    return 200, {"detail": "logged out"}


@operator_router.post("/auth/logout-all", response={200: dict}, auth=operator_auth)
def operator_logout_all(request, response: HttpResponse):
    revoke_all(request.auth)  # 주체의 전 기기 Family 폐기
    clear_refresh_cookie(response, OPERATOR)
    return 200, {"detail": "logged out everywhere"}


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
        {"id": str(t.id), "name": t.name, "is_active": t.is_active, "created_at": t.created_at.isoformat()}
        for t in Tenant.objects.all()
    ]


@operator_router.patch("/tenants/{tenant_id}/suspend", response={200: TenantOut}, auth=operator_auth)
def suspend_tenant(request, tenant_id: str):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.is_active = False
    tenant.save()
    return {"id": str(tenant.id), "name": tenant.name, "is_active": tenant.is_active, "created_at": tenant.created_at.isoformat()}


@operator_router.delete("/tenants/{tenant_id}", response={204: None}, auth=operator_auth)
def delete_tenant(request, tenant_id: str):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.delete()
    return 204, None


# GET 응답에서 암호화 키를 가리는 마스크. 이 값으로 되돌아오면 변경 없음으로 본다.
_KEY_MASK = "********"


def _config_out(config):
    from django.conf import settings

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
        "llm_provider_type": config.llm_provider_type,
        "llm_base_url": config.llm_base_url,
        # 키는 평문·암호문 모두 노출하지 않고 설정 여부만 마스킹으로 알린다.
        "llm_api_key": _KEY_MASK if config.llm_api_key else "",
        "extraction_model": config.extraction_model,
        "embed_provider_type": config.embed_provider_type,
        "embed_base_url": config.embed_base_url,
        "embed_api_key": _KEY_MASK if config.embed_api_key else "",
        "embed_model": config.embed_model,
        "embed_dim": config.embed_dim,
        "platform_default_providers_enabled": getattr(
            settings, "PLATFORM_DEFAULT_PROVIDERS_ENABLED", False
        ),
    }


@tenant_router.get("/config/", response=TenantConfigOut)
def get_config(request):
    return _config_out(request.auth.tenant.config)


def _embed_signature(config):
    # 벡터 공간을 정하는 요소들. 키 변경만으로는 재임베딩하지 않는다.
    return (config.embed_provider_type, config.embed_base_url, config.embed_model, config.embed_dim)


@tenant_router.patch("/config/", response=TenantConfigOut)
def update_config(request, body: TenantConfigIn):
    config = request.auth.tenant.config
    _old_embed = _embed_signature(config)
    for field in ("model_id", "system_prompt", "agent_display_name", "webhook_url", "webhook_type", "welcome_message", "brand_name", "hitl_enabled", "require_identity_verification", "llm_provider_type", "llm_base_url", "extraction_model", "embed_provider_type", "embed_base_url", "embed_model", "embed_dim"):
        value = getattr(body, field)
        if value is not None:
            setattr(config, field, value)
    # API 키는 평문으로 받아 암호화 저장한다(write-only). 단, GET이 돌려준 마스크 값을
    # 그대로 되돌려 보낸 경우(어드민 round-trip)는 무시해 실제 키를 보존한다.
    from apps.tenants.crypto import encrypt_secret
    if body.llm_api_key is not None and body.llm_api_key != _KEY_MASK:
        config.llm_api_key = encrypt_secret(body.llm_api_key)
    if body.embed_api_key is not None and body.embed_api_key != _KEY_MASK:
        config.embed_api_key = encrypt_secret(body.embed_api_key)
    config.save()

    # Embedding Provider(벡터 공간) 변경 시 재임베딩 재구축을 트리거한다(LLM 변경은 제외).
    if _embed_signature(config) != _old_embed:
        from apps.rag.tasks import reembed_tenant_task
        reembed_tenant_task.delay(str(config.tenant_id))
    return _config_out(config)


class ProviderModelsIn(Schema):
    kind: str            # "llm" | "embed"
    type: str            # "" | openai | anthropic | custom
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class ProviderModelsOut(Schema):
    models: List[str]


@tenant_router.post("/providers/models", response={200: ProviderModelsOut, 400: dict})
def provider_models(request, body: ProviderModelsIn):
    """폼의 현재 provider 값으로 모델 목록을 조회한다(어드민 "모델 불러오기").

    마스크 키(********)면 저장된 키를 복호화해 쓰고, type=""(플랫폼 기본)은 kind로
    base_url/api_key를 해석한다. 응답엔 모델 id만(키 미노출). 실패 시 400 + 메시지.
    """
    from django.conf import settings
    from apps.agent.provider_models import list_provider_models, ProviderError

    config = request.auth.tenant.config
    type_, base_url, api_key = body.type, body.base_url, body.api_key

    if type_ == "":
        if not getattr(settings, "PLATFORM_DEFAULT_PROVIDERS_ENABLED", False):
            return 400, {"detail": "플랫폼 기본 Provider가 비활성화되어 있습니다"}
        if body.kind == "embed":
            base_url, api_key = f"{settings.OLLAMA_BASE_URL}/v1", "ollama"
        else:
            base_url, api_key = settings.OPEN_ROUTER_BASE_URL, settings.OPEN_ROUTER_API_KEY
    elif api_key == _KEY_MASK:
        from apps.tenants.crypto import decrypt_secret
        stored = config.embed_api_key if body.kind == "embed" else config.llm_api_key
        api_key = decrypt_secret(stored) if stored else ""

    try:
        models = list_provider_models(body.kind, type_, base_url, api_key)
    except ProviderError as e:
        return 400, {"detail": str(e)}
    return 200, {"models": models}


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
