"""재임베딩 재구축 (ADR-0012).

Embedding Provider가 바뀌면 저장된 벡터가 새 모델의 공간과 호환되지 않으므로, 그래프
구조(Entity·관계·Community)는 보존한 채 모든 Text Unit·Mention을 새 모델로 다시 임베딩하고
per-Tenant 인덱스를 새 차원으로 재생성한다. LLM Provider 변경은 이 흐름을 트리거하지 않는다.

옛 벡터는 인덱스 재생성 전까지 서빙되고, 인덱스가 없는 짧은 구간엔 어휘 검색이 무중단으로
받친다(vector_search는 인덱스 부재 시 빈 결과로 graceful). Graph Freshness=rebuilding으로 표시.
"""


def reembed_tenant(tenant_id: str) -> None:
    from apps.rag.ingesters import get_embeddings
    from apps.rag.graph_store import GraphStore
    from apps.tenants.models import TenantConfig
    from apps.agent.providers import embedding_provider

    gs = GraphStore(tenant_id)
    config = TenantConfig.objects.filter(tenant_id=tenant_id).first()
    ep = embedding_provider(config) if config else None
    edim = config.embed_dim if config else 1024

    gs.set_freshness("rebuilding")
    try:
        # 1) 새 임베딩 계산 (구조는 건드리지 않음)
        mentions = gs.query_mentions()
        m_texts = [
            f"{m['name']}: {m['description']}".strip(": ") if m["description"] else m["name"]
            for m in mentions
        ]
        m_embs = get_embeddings(m_texts, provider=ep) if m_texts else []

        units = gs.all_text_units()
        u_embs = get_embeddings([u["content"] for u in units], provider=ep) if units else []

        # 2) 인덱스를 새 차원으로 재생성 후 3) 새 임베딩 기록 (atomic-ish swap)
        gs.recreate_vector_indexes(edim)
        for m, e in zip(mentions, m_embs):
            gs.set_mention_embedding(m["mention_id"], e)
        for u, e in zip(units, u_embs):
            gs.set_text_unit_embedding(u["unit_id"], e)

        gs.set_freshness("fresh")
    except Exception:
        gs.set_freshness("stale")
        raise
