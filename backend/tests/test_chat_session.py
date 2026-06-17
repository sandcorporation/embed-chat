import pytest


@pytest.mark.django_db
def test_langgraph_checkpoint_table_exists(db):
    """PostgresSaver.setup()이 checkpoint 테이블을 DB에 생성한다."""
    from apps.agent.graph import _create_checkpointer
    saver, conn = _create_checkpointer()
    conn.close()

    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='checkpoints'"
        )
        count = cursor.fetchone()[0]
    assert count == 1


@pytest.mark.django_db
def test_issue_embed_token_and_get_session_id(client, tenant_with_key):
    tenant, raw_key = tenant_with_key

    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-001", "visitor_context": {"name": "Test User"}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    assert token_resp.status_code == 200
    embed_token = token_resp.json()["embed_token"]

    stream_resp = client.get(f"/api/chat/stream?token={embed_token}")
    assert stream_resp.status_code == 200
    assert stream_resp["Content-Type"] == "text/event-stream"
    assert "X-Session-Id" in stream_resp


@pytest.mark.django_db
def test_stream_expired_token_rejected(client):
    from apps.chat.embed_token import create_embed_token

    expired = create_embed_token("some-tenant", "v-001", {}, ttl_seconds=-1)
    response = client.get(f"/api/chat/stream?token={expired}")
    assert response.status_code == 401


@pytest.mark.django_db
def test_stream_sends_connected_event_first(client, tenant_with_key):
    import json

    tenant, raw_key = tenant_with_key
    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-connected", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]
    stream_resp = client.get(f"/api/chat/stream?token={embed_token}")

    # 첫 번째 청크가 'connected' 이벤트여야 한다
    first_chunk = next(stream_resp.streaming_content).decode()
    assert "event: connected" in first_chunk
    payload = json.loads(first_chunk.split("data: ", 1)[1])
    assert "session_id" in payload


@pytest.mark.django_db
def test_chatsession_created_on_stream(client, tenant_with_key):
    from apps.chat.models import ChatSession

    tenant, raw_key = tenant_with_key
    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-session-test", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]
    client.get(f"/api/chat/stream?token={embed_token}")

    assert ChatSession.objects.filter(visitor_id="v-session-test").exists()


@pytest.mark.django_db
def test_send_message_via_api_saves_user_message(client, tenant_with_key):
    """POST /api/chat/message → 202 반환 + user 메시지 DB 저장."""
    from apps.chat.models import ChatSession, ChatMessage

    tenant, raw_key = tenant_with_key
    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-post-msg", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]
    stream_resp = client.get(f"/api/chat/stream?token={embed_token}")
    session_id = stream_resp["X-Session-Id"]

    resp = client.post(
        "/api/chat/message",
        {"session_id": session_id, "content": "안녕하세요"},
        content_type="application/json",
    )
    assert resp.status_code == 202

    session = ChatSession.objects.get(id=session_id)
    assert ChatMessage.objects.filter(
        session=session, role=ChatMessage.ROLE_USER, content="안녕하세요"
    ).exists()


@pytest.mark.django_db
def test_send_message_unknown_session_returns_404(client):
    import uuid
    resp = client.post(
        "/api/chat/message",
        {"session_id": str(uuid.uuid4()), "content": "hello"},
        content_type="application/json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_get_session_checkpoint_returns_channel_values(client, tenant_with_key, tenant_agent_token):
    """run_chat_agent 실행 후 GET /api/tenant/sessions/{id}/checkpoint → channel_values JSON."""
    from apps.agent.graph import run_chat_agent
    from apps.chat.models import ChatSession

    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-checkpoint-api",
        visitor_context={},
    )
    run_chat_agent(session, "안녕하세요")

    resp = client.get(
        f"/api/tenant/sessions/{session.id}/checkpoint",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "messages" in data
    assert "rag_chunks" in data


@pytest.mark.django_db
def test_get_session_checkpoint_404_when_no_llm_call(client, tenant_with_key, tenant_agent_token):
    """LLM 호출이 없는 세션에 checkpoint 조회 시 404를 반환한다."""
    from apps.chat.models import ChatSession

    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-no-checkpoint",
        visitor_context={},
    )

    resp = client.get(
        f"/api/tenant/sessions/{session.id}/checkpoint",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_get_session_checkpoint_404_for_other_tenant(client, tenant_agent_token):
    """다른 Tenant의 session_id로 checkpoint 조회 시 404를 반환한다."""
    import secrets
    from apps.tenants.models import Tenant
    from apps.chat.models import ChatSession

    raw_key2 = secrets.token_urlsafe(32)
    other_tenant = Tenant.objects.create_with_key(name="OtherCo CP", raw_key=raw_key2)
    other_session = ChatSession.objects.create(
        tenant_id=other_tenant.id, visitor_id="v-other-cp", visitor_context={}
    )

    resp = client.get(
        f"/api/tenant/sessions/{other_session.id}/checkpoint",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_checkpoint_has_messages_but_not_lc_messages(tenant_with_key):
    """Checkpoint channel_values에 대화는 messages로만 남고 lc_messages(프롬프트 조립물)는 없다.

    lc_messages가 남아 있으면 어드민 Checkpoint 뷰에서 대화가 두 형식으로 중복 표시된다.
    """
    from apps.agent.graph import run_chat_agent, _create_checkpointer
    from apps.chat.models import ChatSession

    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-lc-messages",
        visitor_context={},
    )
    run_chat_agent(session, "안녕하세요")
    run_chat_agent(session, "또 질문이요")

    saver, conn = _create_checkpointer()
    try:
        cp = saver.get({"configurable": {"thread_id": str(session.id)}})
    finally:
        conn.close()

    cv = cp["channel_values"]
    assert "messages" in cv
    assert "lc_messages" not in cv, f"lc_messages가 checkpoint에 남아있음: {sorted(cv.keys())}"

    # 시간순 + 중복 없음
    roles = [m["role"] for m in cv["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"], roles


@pytest.mark.django_db
def test_multi_turn_creates_multiple_assistant_replies(tenant_with_key):
    """agent를 두 번 실행하면 각각 assistant 메시지가 저장되고 히스토리가 누적된다."""
    from apps.agent.graph import run_chat_agent
    from apps.chat.models import ChatSession, ChatMessage

    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-multiturn",
        visitor_context={},
    )

    run_chat_agent(session, "안녕하세요")
    assert ChatMessage.objects.filter(session=session, role=ChatMessage.ROLE_ASSISTANT).count() == 1

    run_chat_agent(session, "감사합니다")
    assert ChatMessage.objects.filter(session=session, role=ChatMessage.ROLE_ASSISTANT).count() == 2


@pytest.mark.django_db
def test_hitl_session_blocks_message_post(client, tenant_with_key):
    """is_hitl=True인 세션에 메시지를 보내면 202를 반환하되 agent를 실행하지 않는다."""
    from apps.chat.models import ChatSession, ChatMessage

    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-hitl-block-post",
        visitor_context={},
        is_hitl=True,
    )

    resp = client.post(
        "/api/chat/message",
        {"session_id": str(session.id), "content": "아직 거기 있나요?"},
        content_type="application/json",
    )
    assert resp.status_code == 202
    assert ChatMessage.objects.filter(session=session, role=ChatMessage.ROLE_USER).exists()
    assert not ChatMessage.objects.filter(session=session, role=ChatMessage.ROLE_ASSISTANT).exists()


@pytest.mark.django_db
def test_stream_reconnect_reuses_same_session(client, tenant_with_key):
    """동일 embed_token으로 두 번 stream 요청해도 같은 ChatSession을 재사용한다."""
    from apps.chat.models import ChatSession

    tenant, raw_key = tenant_with_key
    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-reconnect", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]

    resp1 = client.get(f"/api/chat/stream?token={embed_token}")
    session_id_1 = resp1["X-Session-Id"]

    resp2 = client.get(f"/api/chat/stream?token={embed_token}")
    session_id_2 = resp2["X-Session-Id"]

    assert session_id_1 == session_id_2
    assert ChatSession.objects.filter(visitor_id="v-reconnect").count() == 1


# ── Issue 42: session restoration in connected event ─────────────────────────

@pytest.mark.django_db
def test_stream_reconnect_includes_history_in_connected_event(client, tenant_with_key):
    """기존 메시지가 있는 세션에 재연결하면 connected 이벤트 payload에 history가 포함된다."""
    import json
    from apps.chat.models import ChatSession, ChatMessage

    tenant, raw_key = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-history-restore",
        visitor_context={},
    )
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="안녕하세요")
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="무엇을 도와드릴까요?")

    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-history-restore", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]
    stream_resp = client.get(f"/api/chat/stream?token={embed_token}")
    first_chunk = next(stream_resp.streaming_content).decode()

    assert "event: connected" in first_chunk
    payload = json.loads(first_chunk.split("data: ", 1)[1])
    assert "history" in payload
    assert len(payload["history"]) == 2
    assert payload["history"][0] == {"role": "user", "content": "안녕하세요"}
    assert payload["history"][1] == {"role": "assistant", "content": "무엇을 도와드릴까요?"}


@pytest.mark.django_db
def test_stream_reconnect_is_hitl_true_included_in_connected_event(client, tenant_with_key):
    """is_hitl=True인 기존 세션에 재연결하면 connected 이벤트에 is_hitl: true가 포함된다."""
    import json
    from apps.chat.models import ChatSession, ChatMessage

    tenant, raw_key = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-hitl-restore",
        visitor_context={},
        is_hitl=True,
    )
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="상담원 연결해 주세요")

    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-hitl-restore", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]
    stream_resp = client.get(f"/api/chat/stream?token={embed_token}")
    first_chunk = next(stream_resp.streaming_content).decode()
    payload = json.loads(first_chunk.split("data: ", 1)[1])

    assert payload.get("is_hitl") is True


@pytest.mark.django_db
def test_stream_reconnect_no_welcome_message_for_existing_session(client, tenant_with_key):
    """기존 메시지가 있는 세션에 재연결하면 connected 이벤트에 welcome_message가 없다."""
    import json
    from apps.chat.models import ChatSession, ChatMessage
    from apps.tenants.models import TenantConfig

    tenant, raw_key = tenant_with_key
    config = TenantConfig.objects.get(tenant=tenant)
    config.welcome_message = "안녕하세요! 무엇을 도와드릴까요?"
    config.save()

    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-no-welcome-repeat",
        visitor_context={},
    )
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="첫 메시지")

    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-no-welcome-repeat", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]
    stream_resp = client.get(f"/api/chat/stream?token={embed_token}")
    first_chunk = next(stream_resp.streaming_content).decode()
    payload = json.loads(first_chunk.split("data: ", 1)[1])

    assert "welcome_message" not in payload


@pytest.mark.django_db
def test_stream_new_session_no_history_in_connected_event(client, tenant_with_key):
    """신규 세션(ChatMessage 없음)에서 connected 이벤트에 history가 없고 welcome_message가 있다."""
    import json
    from apps.tenants.models import TenantConfig

    tenant, raw_key = tenant_with_key
    config = TenantConfig.objects.get(tenant=tenant)
    config.welcome_message = "신규 방문자 환영합니다!"
    config.save()

    token_resp = client.post(
        "/api/embed/token",
        {"visitor_id": "v-new-no-history", "visitor_context": {}},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    embed_token = token_resp.json()["embed_token"]
    stream_resp = client.get(f"/api/chat/stream?token={embed_token}")
    first_chunk = next(stream_resp.streaming_content).decode()
    payload = json.loads(first_chunk.split("data: ", 1)[1])

    assert payload.get("welcome_message") == "신규 방문자 환영합니다!"
    assert "history" not in payload
    assert "is_hitl" not in payload
