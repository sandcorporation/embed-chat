import pytest
import time


@pytest.mark.django_db
def test_issue_embed_token(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    response = client.post(
        "/api/embed/token",
        {"visitor_id": "user-123", "visitor_context": {"name": "홍길동", "plan": "premium"}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    assert response.status_code == 200
    assert "embed_token" in response.json()


@pytest.mark.django_db
def test_embed_token_contains_visitor_context(client, tenant_with_key):
    from apps.chat.embed_token import verify_embed_token

    tenant, raw_key = tenant_with_key
    response = client.post(
        "/api/embed/token",
        {"visitor_id": "user-abc", "visitor_context": {"name": "홍길동"}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    token = response.json()["embed_token"]
    payload = verify_embed_token(token)
    assert payload["visitor_context"]["name"] == "홍길동"
    assert payload["visitor_id"] == "user-abc"


@pytest.mark.django_db
def test_embed_token_wrong_key(client):
    response = client.post(
        "/api/embed/token",
        {"visitor_id": "user-123", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer invalid-key",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_embed_token_suspended_tenant(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    tenant.is_active = False
    tenant.save()

    response = client.post(
        "/api/embed/token",
        {"visitor_id": "user-123", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_stream_suspended_tenant_returns_401(client, tenant_with_key):
    """정지된 Tenant의 embed_token으로 stream 요청 시 401을 반환한다."""
    tenant, raw_key = tenant_with_key

    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-suspended-stream", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]

    tenant.is_active = False
    tenant.save()

    resp = client.get(f"/api/chat/stream?token={embed_token}")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_expired_embed_token_rejected(tenant_with_key):
    from apps.chat.embed_token import create_embed_token, verify_embed_token

    tenant, _ = tenant_with_key
    token = create_embed_token(
        tenant_id=str(tenant.id),
        visitor_id="user-exp",
        visitor_context={},
        ttl_seconds=-1,
    )
    result = verify_embed_token(token)
    assert result is None
