"""Tenant Self-Signup (PRD-tenant-self-signup-permissions, issue 209, ADR-0025).

공개 가입으로 Tenant + 첫 Tenant Admin을 만든다. 조직 이름은 전역 unique(대소문자·공백 무시)한
로그인 식별자다. 실 객체·실 DB(외부 경계 없음).
"""
import pytest


@pytest.mark.django_db
def test_register_tenant_creates_tenant_and_first_admin():
    from apps.tenants.registration import register_tenant
    from apps.tenants.models import Tenant, TenantAgent, TenantConfig

    tenant, agent = register_tenant("Acme Corp", "owner", "pw12345678")

    assert Tenant.objects.filter(id=tenant.id).exists()
    assert TenantConfig.objects.filter(tenant=tenant).exists()
    assert tenant.tenant_key_hash  # 가입 시 TENANT_KEY 발급
    assert agent.tenant_id == tenant.id
    assert agent.username == "owner"
    assert agent.role == TenantAgent.ROLE_ADMIN  # 첫 agent는 Admin
    assert agent.check_password("pw12345678")


@pytest.mark.django_db
def test_register_rejects_duplicate_name_case_and_space_insensitive():
    from apps.tenants.registration import register_tenant, DuplicateOrgName
    register_tenant("Acme", "a", "pw12345678")
    with pytest.raises(DuplicateOrgName):
        register_tenant("  acme ", "b", "pw12345678")


SIGNUP = "/api/tenant/agents/auth/signup"
LOGIN = "/api/tenant/agents/auth/login"


@pytest.mark.django_db
def test_signup_endpoint_creates_admin_and_returns_token(client):
    from apps.tenants.models import TenantAgent
    r = client.post(SIGNUP, {"tenant_name": "NewCo", "username": "owner", "password": "pw12345678"},
                    content_type="application/json")
    assert r.status_code == 201
    assert r.json().get("access_token")
    assert TenantAgent.objects.get(username="owner").role == TenantAgent.ROLE_ADMIN


@pytest.mark.django_db
def test_signup_then_login_is_case_insensitive_on_org_name(client):
    client.post(SIGNUP, {"tenant_name": "NewCo", "username": "owner", "password": "pw12345678"},
                content_type="application/json")
    r = client.post(LOGIN, {"tenant_name": "newco", "username": "owner", "password": "pw12345678"},
                    content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("access_token")


@pytest.mark.django_db
def test_signup_duplicate_org_name_returns_409(client):
    # 두 가입은 서로 다른 IP에서 — 레이트리밋(같은 IP 1회)이 아니라 중복 이름(409)을 검증하려는 것.
    client.post(SIGNUP, {"tenant_name": "Dup", "username": "a", "password": "pw12345678"},
                content_type="application/json", HTTP_X_FORWARDED_FOR="192.0.2.1")
    r = client.post(SIGNUP, {"tenant_name": " dup ", "username": "b", "password": "pw12345678"},
                    content_type="application/json", HTTP_X_FORWARDED_FOR="192.0.2.2")
    assert r.status_code == 409
