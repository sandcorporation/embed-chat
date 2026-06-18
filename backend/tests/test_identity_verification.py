import pytest
from utils import open_stream


# ── Issue 86: Identity Verification — opt-in HMAC ─────────────────────────────

@pytest.mark.django_db
def test_operator_hmac_api_returns_verifiable_hash(client, tenant_with_key):
    """TENANT_KEY 인증 HMAC API가 visitor_id의 검증 가능한 해시를 발급한다."""
    from apps.chat.identity import verify_identity

    tenant, raw_key = tenant_with_key
    resp = client.post(
        "/api/chat/identity",
        {"visitor_id": "member-777"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    assert resp.status_code == 200
    h = resp.json()["hash"]

    assert verify_identity(str(tenant.id), "member-777", h) is True
    assert verify_identity(str(tenant.id), "someone-else", h) is False
    assert verify_identity(str(tenant.id), "member-777", "forged") is False


@pytest.mark.django_db
def test_stream_requires_valid_hash_when_verification_enabled(client, tenant_with_key):
    """신원검증 토글 ON이면 stream은 유효 해시를 요구한다(누락·위조 거부, 유효 허용)."""
    from apps.tenants.models import TenantConfig
    from apps.chat.identity import compute_identity_hash

    tenant, _ = tenant_with_key
    tenant.slug = "secure-shop"
    tenant.save(update_fields=["slug"])
    config = TenantConfig.objects.get(tenant=tenant)
    config.require_identity_verification = True
    config.save()

    # 해시 누락 → 거부
    r1 = client.get("/api/chat/stream?slug=secure-shop&visitor_id=member-1")
    assert r1.status_code == 401

    # 위조 해시 → 거부
    r2 = client.get("/api/chat/stream?slug=secure-shop&visitor_id=member-1&hash=forged")
    assert r2.status_code == 401

    # 유효 해시 → 허용
    h = compute_identity_hash(str(tenant.id), "member-1")
    r3 = client.get(f"/api/chat/stream?slug=secure-shop&visitor_id=member-1&hash={h}")
    assert r3.status_code == 200
