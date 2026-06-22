# pyright: reportOptionalSubscript=false
"""GraphRAG Local Search — 미스 기반 원문(TextUnit) 폴백 (issues 118-119).

LLM은 결정적 Fake(CLAUDE.md). Neo4j·임베딩·vector_search는 실제로 검증한다.
"""
import pytest


# ── Issue 118: context_sufficient 신호 ────────────────────────────────────────

@pytest.mark.django_db
def test_context_sufficient_flows_to_checkpoint(tenant_with_key, fake_chat_llm):
    """call_llm이 context_sufficient(Self-RAG ISSUP 경량 신호)를 상태로 흘려 체크포인트에 노출한다.

    이 슬라이스는 신호만 노출한다(폴백 라우팅은 #119).
    """
    from apps.agent.graph import run_chat_agent, _create_checkpointer
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatSession

    # 근거 부족을 표시 — Fake가 context_sufficient=False를 낸다.
    fake_chat_llm.override = lambda messages: HITLResponse(
        response="죄송합니다, 해당 정보를 찾지 못했습니다.",
        needs_hitl=False, hitl_reason="", context_sufficient=False,
    )
    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-ctx")
    run_chat_agent(session, "지원하는 모니터의 해상도")

    saver, conn = _create_checkpointer()
    try:
        cp = saver.get({"configurable": {"thread_id": str(session.id)}})
    finally:
        conn.close()
    assert cp is not None
    assert cp["channel_values"]["context_sufficient"] is False


# ── Issue 119: 원문 TextUnit 폴백 ─────────────────────────────────────────────

@pytest.mark.django_db
def test_local_search_falls_back_to_source_text(tenant_with_key, fake_chat_llm):
    """그래프엔 없고 TextUnit(원문)에만 있는 사실을, miss 시 원문 폴백으로 답한다.

    그래프엔 해당 Mention(엔티티)을 만들지 않으므로 local_search는 비고, context_sufficient=False
    → source_search가 vector_search로 원문 청크를 보강 → 재호출에서 답한다.
    """
    from apps.agent.graph import run_chat_agent
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatSession
    from apps.rag.graph_store import GraphStore
    from apps.rag.ingesters import get_embeddings

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    fact = "이 모니터는 1920 x 1080 FHD 해상도를 지원합니다."
    gs.ensure_vector_index(dimensions=1024)
    emb = get_embeddings([fact], provider=gs._embedding_provider())[0]
    gs.upsert_text_unit("u-res", fact, emb, source_document_id="d1", chunk_index=0)

    # Fake: 근거(조립된 메시지)에 '1920'이 있으면 답 가능(True), 없으면 불가(False) → 폴백 유발.
    # RAG는 캐시 친화 재배치로 뒤쪽 사용자 턴에 실리므로 전체 메시지를 훑는다(#133).
    def fake(messages):
        joined = " ".join(getattr(m, "content", "") for m in messages)
        if "1920" in joined:
            return HITLResponse(response="지원 해상도는 1920x1080(FHD)입니다.",
                                needs_hitl=False, hitl_reason="", context_sufficient=True)
        return HITLResponse(response="", needs_hitl=False, hitl_reason="", context_sufficient=False)
    fake_chat_llm.override = fake

    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-res")
    answer = run_chat_agent(session, "지원하는 모니터의 해상도")
    assert "1920" in answer  # 원문 폴백으로 답함(HITL/모름 아님)


@pytest.mark.django_db
def test_fallback_streams_answer_once(tenant_with_key, fake_chat_llm, monkeypatch):
    """폴백으로 call_llm이 2회 실행돼도 응답은 1번만 스트리밍된다(중복 AI 메시지 방지).

    1패스가 비어있지 않은 '모름' 응답을 내는 실세계 케이스를 재현한다(기존 폴백 테스트는
    1패스 응답을 ''로 둬 이 버그를 못 잡았다).
    """
    from apps.agent import nodes
    from apps.agent.graph import run_chat_agent, _create_checkpointer
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatSession
    from apps.rag.graph_store import GraphStore
    from apps.rag.ingesters import get_embeddings

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    fact = "이 모니터는 1920 x 1080 FHD 해상도를 지원합니다."
    gs.ensure_vector_index(dimensions=1024)
    emb = get_embeddings([fact], provider=gs._embedding_provider())[0]
    gs.upsert_text_unit("u-res", fact, emb, source_document_id="d1", chunk_index=0)

    def fake(messages):
        joined = " ".join(getattr(m, "content", "") for m in messages)
        if "1920" in joined:  # 2패스: 원문 보강됨 → 답
            return HITLResponse(response="지원 해상도는 1920x1080(FHD)입니다.",
                                needs_hitl=False, hitl_reason="", context_sufficient=True)
        # 1패스: 근거 없음 → 비어있지 않은 '모름' 응답 + context_sufficient=False
        return HITLResponse(response="죄송합니다, 정보를 찾지 못했습니다.",
                            needs_hitl=False, hitl_reason="", context_sufficient=False)
    fake_chat_llm.override = fake

    dones = {"n": 0}
    monkeypatch.setattr(nodes, "publish_done", lambda *a, **k: dones.__setitem__("n", dones["n"] + 1))
    monkeypatch.setattr(nodes, "publish_token", lambda *a, **k: None)

    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-dup")
    answer = run_chat_agent(session, "지원하는 모니터의 해상도")

    saver, conn = _create_checkpointer()
    try:
        cv = saver.get({"configurable": {"thread_id": str(session.id)}})["channel_values"]
    finally:
        conn.close()
    assistants = [m for m in (cv.get("messages") or []) if m.get("role") == "assistant"]

    assert "1920" in answer
    assert dones["n"] == 1, f"publish_done가 {dones['n']}회 호출됨(중복 스트리밍)"
    assert len(assistants) == 1, f"checkpoint messages에 assistant {len(assistants)}개(중복)"


@pytest.mark.django_db
def test_transient_rag_chunks_not_retained_in_resting_checkpoint(tenant_with_key, fake_chat_llm):
    """휴지 체크포인트는 대화(messages)만 보존하고 턴 한정 검색 산출물(rag_chunks)은 비운다.

    rag_chunks는 그래프 근거 + 원문 폴백 청크(원문 수백 단어)로 채워지는 임시 산출물인데,
    그래프 채널로 두면 매 super-step 스냅샷에 영구 저장돼 Checkpoint(어드민 뷰어)가 비대해진다.
    """
    from apps.agent.graph import run_chat_agent, _create_checkpointer
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatSession
    from apps.rag.graph_store import GraphStore
    from apps.rag.ingesters import get_embeddings

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    fact = "이 모니터는 1920 x 1080 FHD 해상도를 지원합니다."
    gs.ensure_vector_index(dimensions=1024)
    emb = get_embeddings([fact], provider=gs._embedding_provider())[0]
    gs.upsert_text_unit("u-res", fact, emb, source_document_id="d1", chunk_index=0)

    def fake(messages):
        joined = " ".join(getattr(m, "content", "") for m in messages)
        if "1920" in joined:
            return HITLResponse(response="지원 해상도는 1920x1080(FHD)입니다.",
                                needs_hitl=False, hitl_reason="", context_sufficient=True)
        return HITLResponse(response="", needs_hitl=False, hitl_reason="", context_sufficient=False)
    fake_chat_llm.override = fake

    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-slim")
    run_chat_agent(session, "지원하는 모니터의 해상도")  # 원문 폴백으로 rag_chunks가 채워졌다 비워진다

    saver, conn = _create_checkpointer()
    try:
        cv = saver.get({"configurable": {"thread_id": str(session.id)}})["channel_values"]
    finally:
        conn.close()

    assert cv.get("rag_chunks") == []        # 임시 검색 산출물은 휴지 상태에 남지 않음
    assert cv.get("visitor_memories") == []  # 휘발성 컨텍스트도 비움
    # 대화는 보존된다(체크포인트의 본래 역할).
    assert len([m for m in (cv.get("messages") or []) if m.get("role") == "assistant"]) >= 1


@pytest.mark.django_db
def test_no_source_fallback_when_graph_answers(tenant_with_key, fake_chat_llm):
    """그래프로 답한 happy path(context_sufficient=True)에선 원문 폴백을 타지 않는다(토큰 가드).

    source_text_tried가 False로 남고 rag_chunks가 보강되지 않음을 체크포인트로 확인.
    """
    from apps.agent.graph import run_chat_agent, _create_checkpointer
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatSession

    tenant, _ = tenant_with_key
    fake_chat_llm.override = lambda messages: HITLResponse(
        response="안녕하세요!", needs_hitl=False, hitl_reason="", context_sufficient=True)

    session = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-happy")
    answer = run_chat_agent(session, "안녕")
    assert answer == "안녕하세요!"

    saver, conn = _create_checkpointer()
    try:
        cv = saver.get({"configurable": {"thread_id": str(session.id)}})["channel_values"]
    finally:
        conn.close()
    assert cv.get("source_text_tried") is False  # 폴백 노드 미실행
    assert cv.get("rag_chunks") == []            # 원문 미보강(토큰 추가 0)
