import uuid

import pytest


# ── Issue 72: 엔티티 의미 검색 (다국어 하이브리드) ────────────────────────────

@pytest.mark.django_db
def test_search_entities_matches_across_language(tenant_with_key):
    """'메뉴'(한글) 검색이 'OSD Menu'(영문) 엔티티를 의미적으로 찾는다."""
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    gs.ensure_entity_vector_index()

    from apps.rag.ingesters import get_embeddings
    emb = get_embeddings(["OSD Menu: on-screen display settings menu"])[0]
    gs.upsert_entity(
        "OSD Menu", "feature", "on-screen display settings menu",
        source_document_id=str(uuid.uuid4()), embedding=emb,
    )

    matched = gs.search_entities("메뉴")
    names = [e["name"] for e in matched]
    assert "OSD Menu" in names, f"의미 검색이 'OSD Menu'를 못 찾음: {names}"


@pytest.mark.django_db
def test_search_entities_still_matches_lexically(tenant_with_key):
    """정확/부분 일치(어휘)는 임베딩 없이도 그대로 동작한다 (하이브리드)."""
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    gs.upsert_entity("HP모니터.txt", "document", "Source document", source_document_id=str(uuid.uuid4()))

    matched = gs.search_entities("모니터")
    assert any(e["name"] == "HP모니터.txt" for e in matched)


@pytest.mark.django_db
def test_ingested_entities_are_semantically_searchable(
    client, tenant_agent_token, tenant_with_key, fake_chat_llm
):
    """업로드 → 추출 엔티티가 임베딩되어, 다국어 의미 질의로 검색된다 (인제스션 배선)."""
    import io
    from apps.rag.graph_ingester import GraphExtraction, GraphEntity
    from apps.rag.graph_store import GraphStore

    tenant, _ = tenant_with_key
    fake_chat_llm.extraction = GraphExtraction(
        entities=[GraphEntity(name="Brightness Control", type="setting",
                              description="adjusts screen brightness level")],
        relations=[],
    )

    f = io.BytesIO(b"This monitor lets you adjust screen brightness.")
    f.name = "spec.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    # '밝기'(한글)는 'Brightness Control'에 어휘로는 안 맞지만 의미로는 맞아야 한다
    matched = GraphStore(str(tenant.id)).search_entities("밝기")
    assert any(e["name"] == "Brightness Control" for e in matched), (
        f"인제스트된 엔티티가 의미 검색에 안 잡힘: {[e['name'] for e in matched]}"
    )


# ── Issue 73: 재구축 시 기존(임베딩 없는) 엔티티 백필 ─────────────────────────

@pytest.mark.django_db
def test_rebuild_backfills_missing_entity_embeddings(tenant_with_key):
    """임베딩 없이 존재하던 엔티티가 재구축 후 의미 검색으로 잡힌다."""
    from apps.rag.graph_store import GraphStore
    from apps.rag.community_builder import rebuild_communities

    tenant, _ = tenant_with_key
    gs = GraphStore(str(tenant.id))
    # 이 기능 이전처럼 임베딩 없이 생성된 엔티티
    gs.upsert_entity(
        "Brightness Control", "setting", "adjusts screen brightness level",
        source_document_id=str(uuid.uuid4()),
    )

    # 백필 전: 의미 검색에 안 잡힘 (임베딩 없음, '밝기'는 어휘로도 불일치)
    before = [e["name"] for e in gs.search_entities("밝기")]
    assert "Brightness Control" not in before

    rebuild_communities(str(tenant.id))

    after = [e["name"] for e in gs.search_entities("밝기")]
    assert "Brightness Control" in after, f"재구축 백필 후에도 의미 검색 실패: {after}"
