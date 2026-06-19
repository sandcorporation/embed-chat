"""Issue 98/99/100 — 어드민 access/refresh 엔드포인트 (ADR-0013).

실제 Ninja 엔드포인트·실제 DB. 쿠키(Set-Cookie)와 401 동작을 외부에서 검증한다.
"""
import pytest


def _make_operator(client, username="admin", password="pw123456"):
    from apps.tenants.models import Operator
    op = Operator.objects.create(username=username)
    op.set_password(password)
    op.save()
    return op


def _operator_login(client, username="admin", password="pw123456"):
    return client.post(
        "/api/operator/auth/login",
        {"username": username, "password": password},
        content_type="application/json",
    )


# ── Tracer: Operator 로그인이 access + refresh 쿠키를 발급 ─────────────────────

@pytest.mark.django_db
def test_operator_login_sets_httponly_refresh_cookie(client):
    _make_operator(client)
    resp = _operator_login(client)

    assert resp.status_code == 200
    assert "access_token" in resp.json()
    assert "op_refresh" in resp.cookies
    cookie = resp.cookies["op_refresh"]
    assert cookie.value  # refresh 원문이 쿠키에 담김
    assert cookie["httponly"]
    assert cookie["samesite"].lower() == "strict"


@pytest.mark.django_db
def test_operator_refresh_rotates_cookie_and_returns_new_access(client):
    _make_operator(client)
    _operator_login(client)
    old = client.cookies["op_refresh"].value

    r = client.post("/api/operator/auth/refresh")

    assert r.status_code == 200
    assert "access_token" in r.json()
    assert client.cookies["op_refresh"].value != old  # 회전됨


@pytest.mark.django_db
def test_operator_refresh_without_cookie_rejected(client):
    r = client.post("/api/operator/auth/refresh")
    assert r.status_code == 401


@pytest.mark.django_db
def test_operator_refresh_reuse_is_rejected(client):
    _make_operator(client)
    _operator_login(client)
    old = client.cookies["op_refresh"].value
    client.post("/api/operator/auth/refresh")  # 회전 → old 소비됨

    client.cookies["op_refresh"] = old  # 옛 쿠키 재생
    r = client.post("/api/operator/auth/refresh")

    assert r.status_code == 401


# ── TenantAgent access/refresh (issue 99) ─────────────────────────────────────

def _make_agent(tenant, username="alice", password="secret123"):
    from apps.tenants.models import TenantAgent
    a = TenantAgent(tenant=tenant, username=username)
    a.set_password(password)
    a.save()
    return a


def _agent_login(client, tenant, username="alice", password="secret123"):
    return client.post(
        "/api/tenant/agents/auth/login",
        {"tenant_name": tenant.name, "username": username, "password": password},
        content_type="application/json",
    )


@pytest.mark.django_db
def test_agent_login_sets_httponly_refresh_cookie(client, tenant_with_key):
    tenant, _ = tenant_with_key
    _make_agent(tenant)

    resp = _agent_login(client, tenant)

    assert resp.status_code == 200
    assert "access_token" in resp.json()
    assert "agent_refresh" in resp.cookies
    cookie = resp.cookies["agent_refresh"]
    assert cookie["httponly"]
    assert cookie["samesite"].lower() == "strict"


@pytest.mark.django_db
def test_agent_refresh_rotates_cookie_and_returns_new_access(client, tenant_with_key):
    tenant, _ = tenant_with_key
    _make_agent(tenant)
    _agent_login(client, tenant)
    old = client.cookies["agent_refresh"].value

    r = client.post("/api/tenant/agents/auth/refresh")

    assert r.status_code == 200
    assert "access_token" in r.json()
    assert client.cookies["agent_refresh"].value != old


@pytest.mark.django_db
def test_agent_refresh_without_cookie_rejected(client):
    r = client.post("/api/tenant/agents/auth/refresh")
    assert r.status_code == 401
