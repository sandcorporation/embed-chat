import io

import pytest


def _upload(client, token, filename):
    f = io.BytesIO(b"The FCB1010 has footswitches and expression pedals.")
    f.name = filename
    return client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


# ── Issue 65: 문서 삭제 — 출처 prune (공유 Entity 보존) ───────────────────────

@pytest.mark.django_db
def test_delete_preserves_shared_entity_removes_unique(client, tenant_agent_token, tenant_with_key):
    """문서 삭제 시 공유 Entity는 보존되고, 그 문서에만 속한 것(레이블 Entity)은 제거된다."""
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    r1 = _upload(client, tenant_agent_token, "alpha.txt")
    doc1 = r1.json()["id"]
    _upload(client, tenant_agent_token, "beta.txt")  # 같은 Fake 추출 → FOOTSWITCH 공유

    client.delete(
        f"/api/tenant/documents/{doc1}",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    names = [e["name"] for e in GraphStore(str(tenant.id)).query_entities()]
    # 두 문서가 공유하는 Entity는 살아남는다
    assert "FOOTSWITCH" in names
    # doc1에만 있던 레이블 Entity는 제거된다
    assert "alpha.txt" not in names
    # doc2의 레이블 Entity는 유지된다
    assert "beta.txt" in names


@pytest.mark.django_db
def test_delete_sets_graph_stale(client, tenant_agent_token, tenant_with_key):
    """문서 삭제 후 Graph Freshness가 stale이 된다."""
    from apps.rag.graph_store import GraphStore
    from apps.rag.community_builder import rebuild_communities

    tenant, _ = tenant_with_key
    r = _upload(client, tenant_agent_token, "gamma.txt")
    doc = r.json()["id"]
    rebuild_communities(str(tenant.id))  # fresh
    assert GraphStore(str(tenant.id)).get_freshness() == "fresh"

    client.delete(
        f"/api/tenant/documents/{doc}",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert GraphStore(str(tenant.id)).get_freshness() == "stale"
