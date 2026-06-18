import pytest
from utils import get_redis_message


def _make_session(tenant):
    from apps.chat.models import ChatSession
    return ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-hitl",    )


# ── Issue 55: LLM 경계 Fake가 판정을 통제한다 (tracer bullet) ──────────────────

@pytest.mark.django_db
def test_fake_llm_verdict_drives_escalation(tenant_with_key, fake_chat_llm):
    """Fake가 needs_hitl=True를 강제하면 메시지 내용과 무관하게 Escalation이 생성된다.

    실제 LLM 판단이 아니라 우리 코드(escalation 경로)가 LLM 판정을 따른다는 것을 검증한다.
    """
    from apps.agent.graph import run_chat_agent
    from apps.agent.nodes import HITLResponse
    from apps.escalation.models import Escalation

    tenant, _ = tenant_with_key
    session = _make_session(tenant)

    # 평소라면 escalation 되지 않을 인사말이지만, Fake가 verdict를 강제한다
    fake_chat_llm.override = lambda messages: HITLResponse(
        response="", needs_hitl=True, hitl_reason="forced"
    )

    run_chat_agent(session, "안녕하세요")

    session.refresh_from_db()
    assert session.is_hitl is True
    assert Escalation.objects.filter(session=session, trigger_type="ai").exists()


@pytest.mark.django_db
def test_hitl_with_response_streams_transition_then_escalates(
    tenant_with_key, fake_chat_llm, redis_subscribe
):
    """needs_hitl=True여도 AI 전환 멘트가 있으면 먼저 사용자에게 스트리밍·저장된 뒤 escalation된다."""
    from apps.agent.graph import run_chat_agent
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatMessage
    from apps.escalation.models import Escalation

    tenant, _ = tenant_with_key
    session = _make_session(tenant)
    pubsub = redis_subscribe(f"session:{session.id}")
    fake_chat_llm.override = lambda m: HITLResponse(
        response="상담원에게 연결해 드리겠습니다.", needs_hitl=True, hitl_reason="불확실"
    )

    run_chat_agent(session, "FCB1010 전원 사양 알려줘")

    # 전환 멘트가 먼저 token으로 스트리밍된다 (escalation 이벤트보다 앞서)
    first = get_redis_message(pubsub)
    assert first is not None and first["type"] == "token", f"전환 멘트 스트리밍 안 됨: {first}"
    assert first["content"] == "상담원에게 연결해 드리겠습니다."
    # 전환 멘트가 ChatMessage로도 저장된다
    assert ChatMessage.objects.filter(
        session=session, role=ChatMessage.ROLE_ASSISTANT,
        content="상담원에게 연결해 드리겠습니다.",
    ).exists()
    # 그 뒤 escalation
    session.refresh_from_db()
    assert session.is_hitl is True
    assert Escalation.objects.filter(session=session).exists()


# ── Issue 88: HITL 토글 (불리언으로 그래프 분기) ──────────────────────────────

@pytest.mark.django_db
def test_hitl_disabled_never_escalates_and_answers(tenant_with_key, fake_chat_llm):
    """hitl_enabled=False면 fake가 needs_hitl을 강제해도 escalation 없이 AI가 답한다.

    그래프 토폴로지가 escalation 분기 없이 로드되어 needs_hitl을 구조적으로 무시한다.
    """
    from apps.agent.graph import run_chat_agent
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatSession, ChatMessage
    from apps.escalation.models import Escalation
    from apps.tenants.models import TenantConfig

    tenant, _ = tenant_with_key
    config = TenantConfig.objects.get(tenant=tenant)
    config.hitl_enabled = False
    config.save()

    session = _make_session(tenant)
    # 평소라면 escalation 될 강제 verdict지만, HITL-OFF 그래프는 무시해야 한다
    fake_chat_llm.override = lambda m: HITLResponse(
        response="제가 도와드리겠습니다", needs_hitl=True, hitl_reason="forced"
    )

    run_chat_agent(session, "상담원 연결해 주세요")

    session.refresh_from_db()
    assert session.is_hitl is False
    assert not Escalation.objects.filter(session=session).exists()
    assert ChatMessage.objects.filter(
        session=session, role=ChatMessage.ROLE_ASSISTANT, content="제가 도와드리겠습니다"
    ).exists()


@pytest.mark.django_db
def test_hitl_enabled_toggle_settable_via_config_api(client, tenant_agent_token):
    """Tenant가 어드민 config API로 hitl_enabled를 끄고 다시 조회할 수 있다(기본 True)."""
    g0 = client.get("/api/tenant/config/", HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}")
    assert g0.json()["hitl_enabled"] is True

    r = client.patch(
        "/api/tenant/config/",
        {"hitl_enabled": False},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert r.status_code == 200

    g1 = client.get("/api/tenant/config/", HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}")
    assert g1.json()["hitl_enabled"] is False


# ── Issue 21: Escalation 모델 + LangGraph Structured Output ───────────────


@pytest.mark.django_db
def test_needs_hitl_true_creates_escalation(tenant_with_key):
    from apps.agent.graph import run_chat_agent
    from apps.escalation.models import Escalation

    tenant, _ = tenant_with_key
    session = _make_session(tenant)

    run_chat_agent(session, "상담원 연결해 주세요")

    session.refresh_from_db()
    assert session.is_hitl is True
    assert Escalation.objects.filter(session=session, trigger_type="ai").exists()


@pytest.mark.django_db
def test_needs_hitl_false_saves_assistant_message(tenant_with_key):
    from apps.agent.graph import run_chat_agent
    from apps.chat.models import ChatMessage
    from apps.escalation.models import Escalation

    tenant, _ = tenant_with_key
    session = _make_session(tenant)

    run_chat_agent(session, "안녕하세요")

    session.refresh_from_db()
    assert session.is_hitl is False
    assert not Escalation.objects.filter(session=session).exists()
    assert ChatMessage.objects.filter(
        session=session, role=ChatMessage.ROLE_ASSISTANT
    ).exists()


@pytest.mark.django_db
def test_hitl_start_sse_published_on_escalation(tenant_with_key, redis_subscribe):
    from apps.agent.graph import run_chat_agent

    tenant, _ = tenant_with_key
    session = _make_session(tenant)

    # Subscribe BEFORE the agent runs so we don't miss the event
    pubsub = redis_subscribe(f"session:{session.id}")

    run_chat_agent(session, "상담원 연결해 주세요")

    data = get_redis_message(pubsub)
    assert data is not None, "hitl_start 이벤트가 Redis에 발행되지 않았습니다"
    assert data["type"] == "hitl_start"


# ── Issue 22: Chat API HITL 모드 차단 ────────────────────────────────────


@pytest.mark.django_db
def test_ai_resumes_after_hitl_resolved(client, tenant_with_key, tenant_agent_token):
    """Escalation이 resolved되면 is_hitl=False로 전환되어 AI 응답이 재개된다."""
    from apps.agent.graph import run_chat_agent
    from apps.chat.models import ChatSession, ChatMessage
    from apps.escalation.models import Escalation

    tenant, _ = tenant_with_key
    session = _make_session(tenant)

    run_chat_agent(session, "상담원 연결해 주세요")
    session.refresh_from_db()
    assert session.is_hitl is True

    esc = Escalation.objects.get(session=session)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {tenant_agent_token}"
    resp = client.post(f"/api/tenant/escalations/{esc.id}/resolve")
    assert resp.status_code == 200

    session.refresh_from_db()
    assert session.is_hitl is False

    run_chat_agent(session, "다시 질문드려요")
    assert ChatMessage.objects.filter(
        session=session, role=ChatMessage.ROLE_ASSISTANT
    ).count() >= 1


@pytest.mark.django_db
def test_hitl_mode_session_does_not_invoke_agent(client, tenant_with_key):
    from apps.chat.models import ChatSession, ChatMessage

    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id,
        visitor_id="v-hitl-block",        is_hitl=True,
    )

    response = client.post(
        "/api/chat/message",
        {"session_id": str(session.id), "content": "아직 거기 있나요?"},
        content_type="application/json",
    )

    assert response.status_code == 202
    assert ChatMessage.objects.filter(session=session, role=ChatMessage.ROLE_USER).exists()
    # is_hitl=True이면 agent 스레드가 시작되지 않으므로 assistant 메시지 없음
    assert not ChatMessage.objects.filter(
        session=session, role=ChatMessage.ROLE_ASSISTANT
    ).exists()
