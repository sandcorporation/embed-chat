"""권한 비트 인가 (PRD-tenant-self-signup-permissions, issue 208, ADR-0025).

인가는 역할이 아니라 Permission 비트로 검사한다. Admin=전체, Member=전체−{조직 단위 3종},
Tenant(=TENANT_KEY 인증 주체)=Admin 등가. 순수 매핑이라 DB 불필요(실 객체 in-memory).
"""
from apps.tenants import permissions as P
from apps.tenants.models import Tenant, TenantAgent


def test_admin_has_all_permissions():
    admin = TenantAgent(role=P.ROLE_ADMIN)
    assert P.has_permission(admin, P.AGENTS_MANAGE)
    assert P.has_permission(admin, P.TENANT_KEY_ROTATE)
    assert P.has_permission(admin, P.SLUG_CHANGE)


def test_member_lacks_the_three_admin_only_bits():
    member = TenantAgent(role=P.ROLE_MEMBER)
    assert not P.has_permission(member, P.AGENTS_MANAGE)
    assert not P.has_permission(member, P.TENANT_KEY_ROTATE)
    assert not P.has_permission(member, P.SLUG_CHANGE)


def test_member_has_all_other_permissions():
    member = TenantAgent(role=P.ROLE_MEMBER)
    # 일상 운영(문서·HITL·조회 등)은 Member도 전부
    assert P.has_permission(member, "documents.manage")
    assert P.has_permission(member, "hitl.operate")
    assert P.has_permission(member, "anything.else")


def test_tenant_key_subject_is_admin_equivalent():
    # TENANT_KEY 인증 주체(Tenant)는 전체 허용 — break-glass·프로그램 프로비저닝 유지
    tenant = Tenant(name="X")
    assert P.has_permission(tenant, P.AGENTS_MANAGE)
    assert P.has_permission(tenant, P.TENANT_KEY_ROTATE)
    assert P.has_permission(tenant, P.SLUG_CHANGE)


# ── 엔드포인트 가드 (Admin 전용 3종) ─────────────────────────────────────────
import pytest

AGENTS = "/api/tenant/agents/"


def _hdr(tok):
    return {"HTTP_AUTHORIZATION": f"Bearer {tok}"}


@pytest.mark.django_db
def test_member_cannot_create_agent(client, tenant_member_token):
    r = client.post(AGENTS, {"username": "newbie"}, content_type="application/json", **_hdr(tenant_member_token))
    assert r.status_code == 403


@pytest.mark.django_db
def test_admin_creates_agent_defaulting_to_member(client, tenant_agent_token):
    from apps.tenants.models import TenantAgent
    r = client.post(AGENTS, {"username": "newbie"}, content_type="application/json", **_hdr(tenant_agent_token))
    assert r.status_code == 201
    assert TenantAgent.objects.get(username="newbie").role == "member"


@pytest.mark.django_db
def test_admin_can_create_agent_with_admin_role(client, tenant_agent_token):
    from apps.tenants.models import TenantAgent
    r = client.post(AGENTS, {"username": "boss", "role": "admin"}, content_type="application/json",
                    **_hdr(tenant_agent_token))
    assert r.status_code == 201
    assert TenantAgent.objects.get(username="boss").role == "admin"


@pytest.mark.django_db
def test_tenant_key_can_create_agent(client, tenant_with_key):
    _, raw_key = tenant_with_key
    r = client.post(AGENTS, {"username": "viakey"}, content_type="application/json", **_hdr(raw_key))
    assert r.status_code == 201


@pytest.mark.django_db
def test_list_agents_includes_role(client, tenant_agent_token):
    r = client.get(AGENTS, **_hdr(tenant_agent_token))
    assert r.status_code == 200
    assert all("role" in a for a in r.json())


@pytest.mark.django_db
def test_member_cannot_reset_key(client, tenant_member_token):
    r = client.post("/api/tenant/reset-key", **_hdr(tenant_member_token))
    assert r.status_code == 403


@pytest.mark.django_db
def test_admin_can_reset_key(client, tenant_agent_token):
    r = client.post("/api/tenant/reset-key", **_hdr(tenant_agent_token))
    assert r.status_code == 200


@pytest.mark.django_db
def test_member_cannot_change_slug(client, tenant_member_token):
    r = client.patch("/api/tenant/slug/", {"slug": "my-shop"}, content_type="application/json",
                     **_hdr(tenant_member_token))
    assert r.status_code == 403
