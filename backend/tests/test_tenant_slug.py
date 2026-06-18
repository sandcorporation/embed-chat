import pytest


# ── Issue 84: Tenant Slug — 공개 URL용 고유·URL-safe 식별자 ────────────────────

@pytest.mark.django_db
def test_tenant_sets_slug_via_api(client, tenant_with_key, tenant_agent_token):
    """Tenant가 어드민에서 유효한 slug를 설정하면 저장된다 (표시명과 독립)."""
    tenant, _ = tenant_with_key

    resp = client.patch(
        "/api/tenant/slug/",
        {"slug": "abc-shop"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 200

    tenant.refresh_from_db()
    assert tenant.slug == "abc-shop"
    assert tenant.name == "Test Corp"  # 표시명은 그대로


@pytest.mark.django_db
def test_invalid_slug_format_rejected(client, tenant_with_key, tenant_agent_token):
    """형식 위반(대문자·공백·특수문자·선후행/연속 하이픈)은 거부되고 저장되지 않는다."""
    tenant, _ = tenant_with_key

    for bad in ["ABC", "ab c", "a@b", "-abc", "abc-", "a--b", ""]:
        resp = client.patch(
            "/api/tenant/slug/",
            {"slug": bad},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
        )
        assert resp.status_code == 400, f"{bad!r} 는 거부되어야 한다 (got {resp.status_code})"

    tenant.refresh_from_db()
    assert tenant.slug is None  # 아무것도 저장되지 않음


@pytest.mark.django_db
def test_reserved_slug_rejected(client, tenant_with_key, tenant_agent_token):
    """예약어(admin·api·chatbot 등)는 라우트 충돌 방지를 위해 거부된다."""
    tenant, _ = tenant_with_key

    for reserved in ["admin", "api", "chatbot"]:
        resp = client.patch(
            "/api/tenant/slug/",
            {"slug": reserved},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
        )
        assert resp.status_code == 400, f"{reserved!r} 예약어는 거부되어야 한다"

    tenant.refresh_from_db()
    assert tenant.slug is None


def _second_tenant_token():
    """별도 Tenant + 그 TenantAgent 토큰을 만든다 (전역 unique 테스트용)."""
    import secrets
    from apps.tenants.models import Tenant, TenantAgent
    from apps.tenants.auth import create_tenant_agent_token

    t2 = Tenant.objects.create_with_key(name="Other Co", raw_key=secrets.token_urlsafe(32))
    agent = TenantAgent(tenant=t2, username="agent2")
    agent.set_password("pass")
    agent.save()
    return t2, create_tenant_agent_token(agent)


@pytest.mark.django_db
def test_duplicate_slug_rejected_globally(client, tenant_with_key, tenant_agent_token):
    """이미 다른 Tenant가 쓰는 slug는 전역 고유성으로 거부된다."""
    tenant1, _ = tenant_with_key
    resp1 = client.patch(
        "/api/tenant/slug/",
        {"slug": "shared-name"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp1.status_code == 200

    tenant2, token2 = _second_tenant_token()
    resp2 = client.patch(
        "/api/tenant/slug/",
        {"slug": "shared-name"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token2}",
    )
    assert resp2.status_code == 400, "중복 slug는 거부되어야 한다"

    tenant2.refresh_from_db()
    assert tenant2.slug is None


@pytest.mark.django_db
def test_slug_resolves_to_active_tenant(client, tenant_with_key, tenant_agent_token):
    """slug로 활성 Tenant를 조회한다. 미존재·정지된 Tenant는 None (85 연결 경로가 사용)."""
    from apps.tenants.models import Tenant

    tenant, _ = tenant_with_key
    client.patch(
        "/api/tenant/slug/",
        {"slug": "abc-shop"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    resolved = Tenant.resolve_slug("abc-shop")
    assert resolved is not None and resolved.id == tenant.id

    assert Tenant.resolve_slug("nonexistent") is None

    tenant.is_active = False
    tenant.save(update_fields=["is_active"])
    assert Tenant.resolve_slug("abc-shop") is None, "정지된 Tenant는 해석되지 않아야 한다"
