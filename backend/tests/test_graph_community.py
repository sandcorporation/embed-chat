import io

import pytest


def _upload(client, token, name=b"x", filename="doc.txt"):
    f = io.BytesIO(name)
    f.name = filename
    return client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


# ── Issue 64: Community + Global Search + Graph Freshness ─────────────────────

@pytest.mark.django_db
def test_ingest_sets_graph_freshness_stale(client, tenant_agent_token, tenant_with_key):
    """문서 업로드 시 Graph Freshness가 stale이 된다 (Community 재구축 필요)."""
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    _upload(client, tenant_agent_token, b"The FCB1010 has footswitches.", "fcb.txt")
    assert GraphStore(str(tenant.id)).get_freshness() == "stale"


@pytest.mark.django_db
def test_rebuild_creates_communities_and_sets_fresh(client, tenant_agent_token, tenant_with_key):
    """재구축하면 Community가 생성되고 Graph Freshness가 fresh가 된다."""
    from apps.rag.graph_store import GraphStore
    from apps.rag.community_builder import rebuild_communities

    tenant, _ = tenant_with_key
    _upload(client, tenant_agent_token, b"The FCB1010 has footswitches and pedals.", "fcb.txt")

    rebuild_communities(str(tenant.id))

    gs = GraphStore(str(tenant.id))
    assert gs.get_freshness() == "fresh"
    assert len(gs.query_community_summaries()) >= 1


@pytest.mark.django_db
def test_global_search_returns_community_summaries(client, tenant_agent_token, tenant_with_key):
    """Global Search 노드는 Community 요약을 근거로 반환한다."""
    from apps.rag.community_builder import rebuild_communities
    from apps.agent.nodes import global_search_node

    tenant, _ = tenant_with_key
    _upload(client, tenant_agent_token, b"footswitch and pedal doc", "g.txt")
    rebuild_communities(str(tenant.id))

    out = global_search_node({"tenant_id": str(tenant.id)})
    assert len(out["rag_chunks"]) >= 1


@pytest.mark.django_db
def test_graph_rebuild_and_status_endpoints(client, tenant_agent_token, tenant_with_key):
    """어드민 graph status/rebuild 엔드포인트: stale → rebuild → fresh."""
    _upload(client, tenant_agent_token, b"endpoint doc", "e.txt")

    r1 = client.get(
        "/api/tenant/documents/graph/status",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert r1.status_code == 200
    assert r1.json()["freshness"] == "stale"

    r2 = client.post(
        "/api/tenant/documents/graph/rebuild",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert r2.status_code == 202

    r3 = client.get(
        "/api/tenant/documents/graph/status",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert r3.json()["freshness"] == "fresh"


# ── Entity Resolution 공백 특성화 (diagnose) ─────────────────────────────────
# 버그 수정이 아니라 "현재 동작"을 결정적으로 고정하는 특성화 테스트다.
# 메커니즘: Entity는 (tenant_id, name) 정확일치로 MERGE(이름 다르면 별도 노드),
# Community는 union-find 연결요소(각 노드는 정확히 한 Community).
#   - 의미상 같은 대상이라도 표기가 다르면 별도 노드 → Community 파편화(과소병합).
#   - 무관한 대상이라도 같은 (일반)이름이면 한 노드 → Community 부당 통합(과대병합).
# Entity Resolution이 도입되면 아래 단언이 깨지며 '고쳐졌다'는 신호가 된다.

_EMB = [0.1] * 1024  # 더미 임베딩(같은 맥락 가정)


def _seed_mention_doc(gs, label, entity, doc_id, label_emb=None, entity_emb=None):
    """문서 레이블 Mention이 추출 Mention을 RELATED로 잇는, ingest dual-write와 동일한 형태로 시드."""
    gs.upsert_mention(f"{doc_id}:{label}", label, "document",
                      embedding=label_emb or _EMB, source_document_id=doc_id)
    gs.upsert_mention(f"{doc_id}:{entity}", entity, "Product",
                      embedding=entity_emb or _EMB, source_document_id=doc_id)
    gs.upsert_mention_relation(f"{doc_id}:{label}", f"{doc_id}:{entity}", "mentions", doc_id)


@pytest.mark.django_db
def test_synonym_entities_resolve_into_one_community(tenant_with_key):
    """표기변이(유사 임베딩)는 SAME_AS로 묶여 한 Community가 된다 (과소병합 해결, ADR-0010)."""
    from apps.rag.graph_store import GraphStore
    from apps.rag.community_builder import rebuild_communities

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    # 표기변이 두 제품은 유사 임베딩(동치), 문서 레이블은 서로/제품과 다른 임베딩.
    p, p2 = [1.0, 0.0, 0.0], [0.98, 0.02, 0.0]   # cos>0.95 → 동치
    ea, eb = [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
    _seed_mention_doc(gs, "Manual A", "FCB1010", "docA", ea, p)
    _seed_mention_doc(gs, "Manual B", "FCB-1010", "docB", eb, p2)

    rebuild_communities(str(tenant.id))
    # 표기변이가 SAME_AS로 동치되어 두 문서가 한 Community로 통합.
    assert len(gs.query_community_summaries()) == 1


@pytest.mark.django_db
def test_unrelated_entities_are_not_resolved(tenant_with_key):
    """임베딩이 다른 무관 Entity는 SAME_AS로 묶이지 않아 별도 Community로 남는다 (보수성)."""
    from apps.rag.graph_store import GraphStore
    from apps.rag.community_builder import rebuild_communities

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    _seed_mention_doc(gs, "Doc A", "Apple", "docA", [0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
    _seed_mention_doc(gs, "Doc B", "Zebra", "docB", [0.7, 0.7, 0.0], [0.0, 0.0, 1.0])

    rebuild_communities(str(tenant.id))
    assert gs.query_mention_same_as() == []  # 무관하므로 동치 없음
    assert len(gs.query_community_summaries()) == 2  # 별도 Community 유지


@pytest.mark.django_db
def test_identical_mentions_resolve_into_one_community(tenant_with_key):
    """같은 표기·같은 맥락의 Mention은 동치(SAME_AS)로 묶여 두 문서가 한 Community가 된다."""
    from apps.rag.graph_store import GraphStore
    from apps.rag.community_builder import rebuild_communities

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    _seed_mention_doc(gs, "Manual A", "FCB1010", "docA")  # 같은 표기·같은 맥락(_EMB)
    _seed_mention_doc(gs, "Manual B", "FCB1010", "docB")

    rebuild_communities(str(tenant.id))
    assert len(gs.query_community_summaries()) == 1


@pytest.mark.django_db
def test_homonym_mentions_stay_separate(tenant_with_key):
    """같은 표기·다른 맥락(동음이의 '다리')은 별개 Mention으로 분리되어 별도 Community로 남는다.

    과대병합 해결(ADR-0010): name이 아니라 맥락(임베딩)이 정체성이므로,
    같은 표기라도 임베딩이 다르면 동치되지 않아 한 Community로 합쳐지지 않는다.
    """
    from apps.rag.graph_store import GraphStore
    from apps.rag.community_builder import rebuild_communities

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    bridge, leg = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]  # 직교 → 다른 맥락
    _seed_mention_doc(gs, "Bridge Doc", "다리", "docA", [0.0, 0.0, 1.0], bridge)  # 한강 대교
    _seed_mention_doc(gs, "Injury Doc", "다리", "docB", [0.6, 0.0, 0.8], leg)     # 신체 부위

    rebuild_communities(str(tenant.id))
    # 동음이의는 분리되어야 한다 — 두 "다리"가 동치되면 1, 분리되면 2.
    assert len(gs.query_community_summaries()) == 2
