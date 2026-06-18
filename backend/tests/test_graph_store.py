import uuid

import pytest


# ── Issue 60: GraphStore 경계 + 테넌트 격리 ──────────────────────────────────

@pytest.fixture
def tenant_ids():
    return str(uuid.uuid4()), str(uuid.uuid4())


def test_graphstore_upserts_and_queries_entity_for_tenant(tenant_ids):
    """GraphStore로 Entity를 upsert하면 같은 tenant로 조회 시 반환된다."""
    from apps.rag.graph_store import GraphStore

    tenant_a, _ = tenant_ids
    doc_id = str(uuid.uuid4())

    GraphStore(tenant_a).upsert_entity(
        name="ZX900PRO",
        entity_type="product",
        description="A MIDI foot controller",
        source_document_id=doc_id,
    )

    entities = GraphStore(tenant_a).query_entities()
    names = [e["name"] for e in entities]
    assert "ZX900PRO" in names


def test_graphstore_isolates_entities_by_tenant(tenant_ids):
    """한 tenant의 Entity는 다른 tenant 조회에 절대 나타나지 않는다 (격리)."""
    from apps.rag.graph_store import GraphStore

    tenant_a, tenant_b = tenant_ids
    doc_id = str(uuid.uuid4())

    GraphStore(tenant_a).upsert_entity(
        name="SECRET-ENTITY",
        entity_type="product",
        description="tenant A only",
        source_document_id=doc_id,
    )

    b_entities = GraphStore(tenant_b).query_entities()
    assert all(e["name"] != "SECRET-ENTITY" for e in b_entities), (
        f"tenant B가 tenant A의 Entity를 봄: {b_entities}"
    )


# ── Issue 61: GraphIngester — 업로드 → 그래프 Entity/관계 (Fake 추출) ──────────

import io


@pytest.mark.django_db
def test_upload_builds_graph_entities_with_provenance(client, tenant_agent_token, tenant_with_key):
    """문서 업로드 → 추출된 Entity/관계가 그래프에 생기고 출처 Document가 기록된다.

    추출 LLM은 conftest Fake로 결정적 처리(bring-up은 별도로 실제 OpenRouter 검증).
    """
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    content = b"The unit offers ten assignable footswitches and two expression pedals."
    f = io.BytesIO(content)
    f.name = "ZX900PRO.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    gs = GraphStore(str(tenant.id))
    entities = {e["name"]: e for e in gs.query_entities()}

    # 본문에 제품명이 없어도 레이블이 대표 Entity로 시드됨
    assert "ZX900PRO.txt" in entities
    assert doc_id in entities["ZX900PRO.txt"]["source_document_ids"]

    # Fake 추출이 반환한 Entity/관계가 그래프에 기록됨 (출처 포함)
    assert "FOOTSWITCH" in entities
    assert doc_id in entities["FOOTSWITCH"]["source_document_ids"]

    relations = gs.query_relations()
    assert any(
        r["source"] == "FOOTSWITCH" and r["target"] == "EXPRESSION_PEDAL"
        for r in relations
    ), f"추출된 관계가 그래프에 없음: {relations}"


@pytest.mark.django_db
def test_upload_graph_is_tenant_isolated(client, tenant_agent_token, tenant_with_key):
    """업로드로 만들어진 그래프가 다른 Tenant에게 보이지 않는다."""
    import secrets
    from apps.tenants.models import Tenant, TenantAgent
    from apps.tenants.auth import create_tenant_agent_token
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    f = io.BytesIO(b"footswitch spec doc")
    f.name = "ISOLATED-DOC.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    raw2 = secrets.token_urlsafe(32)
    tenant2 = Tenant.objects.create_with_key(name="Graph Iso Co", raw_key=raw2)
    names2 = [e["name"] for e in GraphStore(str(tenant2.id)).query_entities()]
    assert "ISOLATED-DOC.txt" not in names2
