"""Global Search 제거 (issues 120-121).

챗은 항상 Local Search로 직결되고, Community 서브시스템은 제거된다.
엔티티 해소(SAME_AS)는 잔존한다(Local search가 의존).
"""
import pytest


# ── Issue 120: 챗에서 router/global 제거 ──────────────────────────────────────

@pytest.mark.django_db
def test_chat_routes_directly_to_local_no_global_scope(tenant_with_key, fake_chat_llm):
    """'공통/요약' 류 질의도 별도 분기 없이 local로 처리되고, 체크포인트에 search_scope 채널이 없다."""
    from apps.agent.graph import run_chat_agent, _create_checkpointer
    from apps.chat.models import ChatSession

    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-noglobal")
    # 과거 'global'로 라우팅되던 키워드 질의 — 이제도 정상 응답해야 한다.
    answer = run_chat_agent(session, "모든 문서에서 공통으로 권장하는 설정 요약해줘")
    assert answer

    saver, conn = _create_checkpointer()
    try:
        cv = saver.get({"configurable": {"thread_id": str(session.id)}})["channel_values"]
    finally:
        conn.close()
    assert "search_scope" not in cv  # 라우터/스코프 채널 제거됨
