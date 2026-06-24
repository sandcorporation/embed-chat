"""async send_message 뷰 (issue 195) — POST /chat/message가 taskiq dispatch로 1턴을 돌린다."""
import pytest
from asgiref.sync import sync_to_async


def _make_session(tenant):
    from apps.chat.models import ChatSession
    return ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-msg")


@pytest.mark.django_db(transaction=True)
async def test_send_message_dispatches_and_answers(tenant_with_key, fake_chat_llm):
    """non-hitl: POST /message → dispatch_chat(InMemory) → assistant 저장, 202 반환."""
    from django.test import AsyncClient
    from apps.chat.models import ChatMessage
    from apps.agent.nodes import HITLResponse

    tenant, _ = tenant_with_key
    session = await sync_to_async(_make_session)(tenant)
    fake_chat_llm.override = lambda m: HITLResponse(response="api 비동기 답변", needs_hitl=False)

    client = AsyncClient()
    resp = await client.post(
        "/api/chat/message",
        data={"session_id": str(session.id), "content": "안녕"},
        content_type="application/json",
    )
    assert resp.status_code == 202

    contents = await sync_to_async(
        lambda: [m.content for m in ChatMessage.objects.filter(session=session, role="assistant")]
    )()
    assert any("api 비동기 답변" in c for c in contents)
