"""Entity Mention 노드 — name-MERGE Entity와 공존(dual-write). ADR-0010 / issue 78.

Mention은 mention_id로 식별되어 같은 표기라도 출처가 다르면 별개 노드다(동음이의 기반).
"""
import io

import pytest


@pytest.mark.django_db
def test_same_name_different_source_creates_separate_mentions(tenant_with_key):
    """같은 표기라도 출처(mention_id)가 다르면 별개 Mention으로 저장된다."""
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    gs.upsert_mention("docA:다리", "다리", source_document_id="docA")  # 한강 대교
    gs.upsert_mention("docB:다리", "다리", source_document_id="docB")  # 신체 부위

    same_name = [m for m in gs.query_mentions() if m["name"] == "다리"]
    assert len(same_name) == 2


@pytest.mark.django_db
def test_ingest_creates_mentions_alongside_entities(client, tenant_agent_token, tenant_with_key):
    """문서 ingest가 Entity와 함께 Mention 노드를 생성한다 (dual-write). 기존 Entity 경로 유지."""
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    f = io.BytesIO(b"The FCB1010 has footswitches and expression pedals.")
    f.name = "fcb.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    gs = GraphStore(str(tenant.id))
    assert len(gs.query_mentions()) > 0   # Mention 생성됨
    assert len(gs.query_entities()) > 0   # Entity도 여전히 존재(dual-write)
