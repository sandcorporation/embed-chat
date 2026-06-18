import uuid

import pytest


# ── Issue 94: per-Tenant 가변차원 벡터 인덱스 격리 ────────────────────────────

@pytest.mark.django_db
def test_per_tenant_text_unit_index_isolated_variable_dim(db):
    """서로 다른 차원의 두 Tenant가 각자 인덱스에서 정확히 검색되고 교차 오염이 없다."""
    from apps.rag.graph_store import GraphStore

    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    A, B = GraphStore(a), GraphStore(b)

    A.ensure_vector_index(dimensions=4)
    B.ensure_vector_index(dimensions=8)

    A.upsert_text_unit("a1", "alpha content here", [0.1, 0.2, 0.3, 0.4], source_document_id="d")
    B.upsert_text_unit("b1", "beta content here", [0.5] * 8, source_document_id="d")

    ra = A.vector_search([0.1, 0.2, 0.3, 0.4], top_k=3)
    rb = B.vector_search([0.5] * 8, top_k=3)

    assert any("alpha" in r["content"] for r in ra), ra
    assert any("beta" in r["content"] for r in rb), rb
    # 교차 격리: A의 검색은 B(다른 차원·인덱스)의 내용을 반환하지 않는다
    assert all("beta" not in r["content"] for r in ra), ra
