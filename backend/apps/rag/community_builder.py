"""그래프 재구축 — Tenant Knowledge Graph의 엔티티 해소(SAME_AS) (배치/트리거).

ADR-0016에서 Community/Global Search를 제거하면서, 이 잡은 더 이상 Community를 만들지 않고
**엔티티 해소만** 수행한다. 유사 임베딩 Mention을 비파괴 SAME_AS로 잇고(ADR-0010), Local
search(search_entities)가 그 SAME_AS 클러스터로 dedup한다. 함수명은 태스크/엔드포인트 와이어
호환을 위해 보존한다(이제 community를 만들지 않음).
"""
from apps.rag.graph_store import GraphStore


def rebuild_communities(tenant_id: str) -> int:
    """Tenant 그래프의 엔티티 해소(SAME_AS)를 재수행한다. 생성된 동치 쌍 수를 반환한다.

    Community 탐지/요약은 제거됨(ADR-0016). 임베딩 백필 + resolve_equivalences + SAME_AS만.
    """
    from apps.rag.ingesters import get_embeddings
    from apps.tenants.models import TenantConfig
    from apps.agent.providers import embedding_provider
    from apps.rag.entity_resolver import resolve_equivalences

    gs = GraphStore(tenant_id)
    _ecfg = TenantConfig.objects.filter(tenant_id=tenant_id).first()
    _ep = embedding_provider(_ecfg) if _ecfg else None
    _edim = _ecfg.embed_dim if _ecfg else 1024
    gs.set_freshness("rebuilding")
    try:
        # 임베딩 없는(기능 이전에 생성된) Mention 백필 → 의미 기반 동치 가능
        missing = gs.mentions_without_embedding()
        if missing:
            gs.ensure_mention_vector_index(dimensions=_edim)
            texts = [
                f"{m['name']}: {m['description']}".strip(": ") if m["description"] else m["name"]
                for m in missing
            ]
            for m, emb in zip(missing, get_embeddings(texts, provider=_ep)):
                gs.set_mention_embedding(m["mention_id"], emb)

        # Entity Resolution — 유사 임베딩 Mention을 비파괴 SAME_AS로 잇는다(ADR-0010).
        # 같은 표기라도 맥락(임베딩)이 다르면 동치되지 않아 동음이의가 분리된다.
        pairs = resolve_equivalences(gs.mention_embeddings())
        for a, b in pairs:
            gs.upsert_mention_same_as(a, b)

        gs.set_freshness("fresh")
        return len(pairs)
    except Exception:
        gs.set_freshness("stale")
        raise
