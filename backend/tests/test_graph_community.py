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
