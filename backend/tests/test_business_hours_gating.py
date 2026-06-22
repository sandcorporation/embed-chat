"""영업시간으로 그래프를 가르는 게이팅 (issue 136).

is_open의 결과에 따라 그래프 선택(escalation 가능/불가)과 시간 외 안내 주입을 검증한다.
is_open 자체의 정확성은 test_business_hours.py가 담당하므로, 여기선 게이트를 monkeypatch로
고정해 시간 의존성을 제거하고 '게이팅 동작'만 본다(LLM은 결정적 Fake).
"""
import pytest


@pytest.mark.django_db
def test_off_hours_uses_plain_graph_no_escalation(tenant_with_key, fake_chat_llm, monkeypatch):
    """시간 외(is_open=False)면 plain 그래프 → '상담원' 요청에도 escalation이 생기지 않는다."""
    from apps.tenants import business_hours
    from apps.agent import graph as graph_mod
    from apps.agent.graph import run_chat_agent
    from apps.agent.nodes import PlainResponse
    from apps.chat.models import ChatSession
    from apps.escalation.models import Escalation

    monkeypatch.setattr(business_hours, "is_open", lambda config, now: False)

    captured = {}
    def fake(messages):
        captured["joined"] = " ".join(getattr(m, "content", "") for m in messages)
        return PlainResponse(response="현재는 AI가 답변드립니다.", context_sufficient=True)
    fake_chat_llm.override = fake

    tenant, _ = tenant_with_key  # hitl_enabled 기본 True
    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-off")
    answer = run_chat_agent(session, "상담원 연결해줘")

    assert not Escalation.objects.filter(session=session).exists()  # 시간 외 → escalation 없음
    assert answer  # plain 그래프가 답함
    assert "운영 안내" in captured["joined"]  # 시간 외 운영 안내가 trailing 컨텍스트로 주입됨


@pytest.mark.django_db
def test_open_hours_allows_escalation(tenant_with_key, fake_chat_llm, monkeypatch):
    """상담시간 내(is_open=True)면 structured 그래프 → '상담원' 요청이 escalation을 만든다."""
    from apps.tenants import business_hours
    from apps.agent.graph import run_chat_agent
    from apps.chat.models import ChatSession
    from apps.escalation.models import Escalation

    monkeypatch.setattr(business_hours, "is_open", lambda config, now: True)

    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-on")
    run_chat_agent(session, "상담원 연결해줘")  # 기본 Fake: '상담원' → needs_hitl=True

    assert Escalation.objects.filter(session=session).exists()  # 시간 내 → escalation 생성


@pytest.mark.django_db
def test_off_hours_no_notice_when_hitl_disabled(tenant_with_key, fake_chat_llm, monkeypatch):
    """HITL 자체가 꺼진 테넌트는 시간 외 안내를 주입하지 않는다(사람 전환을 제공하지 않으므로)."""
    from apps.tenants import business_hours
    from apps.tenants.models import TenantConfig
    from apps.agent.graph import run_chat_agent
    from apps.agent.nodes import PlainResponse
    from apps.chat.models import ChatSession

    monkeypatch.setattr(business_hours, "is_open", lambda config, now: False)
    tenant, _ = tenant_with_key
    config = TenantConfig.objects.get(tenant=tenant)
    config.hitl_enabled = False
    config.save()

    captured = {}
    def fake(messages):
        captured["joined"] = " ".join(getattr(m, "content", "") for m in messages)
        return PlainResponse(response="안녕하세요", context_sufficient=True)
    fake_chat_llm.override = fake

    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-disabled")
    run_chat_agent(session, "상담원 연결해줘")
    assert "운영 안내" not in captured["joined"]
