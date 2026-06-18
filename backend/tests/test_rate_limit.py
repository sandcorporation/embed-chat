import uuid

import pytest


# ── Issue 87: ChatRateLimiter — 공개 URL 남용 가드 ────────────────────────────

def test_allows_within_limit_then_blocks_per_visitor():
    """(tenant, visitor)당 한도 내 메시지는 허용, 초과는 거부된다."""
    from apps.chat.rate_limit import allow_message

    t, v = str(uuid.uuid4()), "visitor-a"
    assert allow_message(t, v, per_visitor=2, per_tenant=100) is True
    assert allow_message(t, v, per_visitor=2, per_tenant=100) is True
    assert allow_message(t, v, per_visitor=2, per_tenant=100) is False


def test_visitors_are_counted_independently():
    """서로 다른 visitor는 독립적으로 카운트된다."""
    from apps.chat.rate_limit import allow_message

    t = str(uuid.uuid4())
    assert allow_message(t, "a", per_visitor=1, per_tenant=100) is True
    assert allow_message(t, "a", per_visitor=1, per_tenant=100) is False
    assert allow_message(t, "b", per_visitor=1, per_tenant=100) is True


def test_per_tenant_cap_blocks_flood_across_visitors():
    """per-tenant 상한은 여러 visitor에 걸친 폭주를 차단한다."""
    from apps.chat.rate_limit import allow_message

    t = str(uuid.uuid4())
    assert allow_message(t, "x", per_visitor=100, per_tenant=2) is True
    assert allow_message(t, "y", per_visitor=100, per_tenant=2) is True
    assert allow_message(t, "z", per_visitor=100, per_tenant=2) is False


@pytest.mark.django_db
def test_message_over_rate_limit_returns_429_and_not_processed(client, tenant_with_key, settings):
    """레이트리밋 초과 시 메시지가 429로 거부되고 처리되지 않는다."""
    from apps.chat.models import ChatSession, ChatMessage

    settings.CHAT_RATE_LIMIT_PER_VISITOR = 1
    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-rl-int")

    r1 = client.post(
        "/api/chat/message",
        {"session_id": str(session.id), "content": "1"},
        content_type="application/json",
    )
    assert r1.status_code == 202

    r2 = client.post(
        "/api/chat/message",
        {"session_id": str(session.id), "content": "2"},
        content_type="application/json",
    )
    assert r2.status_code == 429

    # 초과 메시지는 처리되지 않음 (user 메시지 1개만 저장)
    assert ChatMessage.objects.filter(session=session, role=ChatMessage.ROLE_USER).count() == 1
