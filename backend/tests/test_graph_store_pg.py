"""GraphStore의 Postgres+pgvector 백엔드 (PRD-pgvector-graphstore, issue 162+).

flag=pg에서 실 Postgres+pgvector로 검증한다(결정적 인프라는 실제 객체 — CLAUDE.md). 벡터는
합성(결정적)이라 임베딩 provider가 불필요하다. per-Tenant 차원 라우팅·테넌트 격리를 본다.
"""
import uuid
import pytest


@pytest.fixture
def pg_backend(settings):
    """GraphStore를 pg 백엔드로 강제한다(이 슬라이스 개발 게이팅)."""
    settings.GRAPH_BACKEND = "pg"


def _tenant(dim=4):
    """주어진 임베딩 차원의 테넌트를 만든다(차원 라우팅 검증용)."""
    import secrets
    from apps.tenants.models import Tenant, TenantConfig
    t = Tenant.objects.create_with_key(name=f"T-{uuid.uuid4().hex[:6]}", raw_key=secrets.token_urlsafe(16))
    cfg = TenantConfig.objects.get(tenant=t)
    cfg.embed_dim = dim
    cfg.save()
    return t


@pytest.mark.django_db
def test_text_unit_upsert_and_vector_search(pg_backend):
    """flag=pg: TextUnit upsert 후 vector_search가 최근접 원문을 반환한다."""
    from apps.rag.graph_store import GraphStore
    t = _tenant(dim=3)
    gs = GraphStore(str(t.id))
    gs.ensure_vector_index(dimensions=3)
    gs.upsert_text_unit("u1", "빨강에 대한 문서", [1.0, 0.0, 0.0], source_document_id="d1")
    gs.upsert_text_unit("u2", "파랑에 대한 문서", [0.0, 0.0, 1.0], source_document_id="d1")

    hits = gs.vector_search([0.9, 0.1, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0]["content"] == "빨강에 대한 문서"   # [1,0,0]에 가장 가까움
    assert hits[0]["source_document_id"] == "d1"


@pytest.mark.django_db
def test_vector_search_is_tenant_scoped(pg_backend):
    """한 테넌트의 vector_search는 다른 테넌트의 벡터를 절대 반환하지 않는다(격리)."""
    from apps.rag.graph_store import GraphStore
    ta, tb = _tenant(dim=3), _tenant(dim=3)
    GraphStore(str(ta.id)).upsert_text_unit("ua", "A의 문서", [1.0, 0.0, 0.0])
    GraphStore(str(tb.id)).upsert_text_unit("ub", "B의 문서", [1.0, 0.0, 0.0])

    hits = GraphStore(str(ta.id)).vector_search([1.0, 0.0, 0.0], top_k=5)
    contents = [h["content"] for h in hits]
    assert "A의 문서" in contents
    assert "B의 문서" not in contents


@pytest.mark.django_db
def test_different_dim_tenants_isolated(pg_backend):
    """서로 다른 embed_dim 테넌트가 각자 차원 테이블에서 동작하고 섞이지 않는다."""
    from apps.rag.graph_store import GraphStore
    t3, t5 = _tenant(dim=3), _tenant(dim=5)
    GraphStore(str(t3.id)).upsert_text_unit("x", "3차원 문서", [1.0, 0.0, 0.0])
    GraphStore(str(t5.id)).upsert_text_unit("y", "5차원 문서", [1.0, 0.0, 0.0, 0.0, 0.0])

    h3 = GraphStore(str(t3.id)).vector_search([1.0, 0.0, 0.0], top_k=5)
    h5 = GraphStore(str(t5.id)).vector_search([1.0, 0.0, 0.0, 0.0, 0.0], top_k=5)
    assert [h["content"] for h in h3] == ["3차원 문서"]
    assert [h["content"] for h in h5] == ["5차원 문서"]


@pytest.mark.django_db
def test_query_text_units_by_document(pg_backend):
    """문서별 TextUnit을 chunk_index 순으로 반환한다."""
    from apps.rag.graph_store import GraphStore
    gs = GraphStore(str(_tenant(dim=2).id))
    gs.upsert_text_unit("u2", "둘째", [0.0, 1.0], source_document_id="doc", chunk_index=1)
    gs.upsert_text_unit("u1", "첫째", [1.0, 0.0], source_document_id="doc", chunk_index=0)

    units = gs.query_text_units("doc")
    assert [u["content"] for u in units] == ["첫째", "둘째"]


@pytest.mark.django_db
def test_vector_search_empty_when_no_data(pg_backend):
    """문서 미인제스트(테이블 미존재) 테넌트는 빈 결과(무중단)."""
    from apps.rag.graph_store import GraphStore
    assert GraphStore(str(_tenant(dim=3).id)).vector_search([1.0, 0.0, 0.0]) == []


@pytest.mark.django_db
def test_freshness_roundtrip(pg_backend):
    """freshness는 기본 fresh이고 set/get으로 왕복된다."""
    from apps.rag.graph_store import GraphStore
    gs = GraphStore(str(_tenant().id))
    assert gs.get_freshness() == "fresh"   # 메타 없음 → fresh
    gs.set_freshness("stale")
    assert gs.get_freshness() == "stale"


@pytest.mark.django_db
def test_ensure_vector_index_idempotent(pg_backend):
    """첫 인제스션 DDL은 멱등(IF NOT EXISTS) — 재호출해도 오류 없음."""
    from apps.rag.graph_store import GraphStore
    gs = GraphStore(str(_tenant(dim=3).id))
    gs.ensure_vector_index(dimensions=3)
    gs.ensure_vector_index(dimensions=3)  # 두 번째 호출도 안전
    gs.upsert_text_unit("u", "문서", [1.0, 0.0, 0.0])
    assert gs.vector_search([1.0, 0.0, 0.0], top_k=1)[0]["content"] == "문서"
