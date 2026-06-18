"""CommunityBuilder — Tenant Knowledge Graph의 Community 탐지 + LLM 요약 (배치/트리거).

Community는 Entity-관계 그래프의 연결 요소(connected component)로 정의한다(외부 GDS 없이 결정적).
요약은 `apps/agent/llm` 경계(complete_text)를 통해 생성하므로 테스트에서 Fake로 교체된다.
"""
from django.conf import settings
from langchain_core.messages import HumanMessage

from apps.agent import llm as llm_boundary
from apps.rag.graph_store import GraphStore


def _connected_components(entity_names, relations):
    """union-find로 Entity를 연결 요소(community)로 묶는다."""
    parent = {n: n for n in entity_names}

    def find(x):
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        parent[find(a)] = find(b)

    for r in relations:
        s, t = r.get("source"), r.get("target")
        if s and t:
            parent.setdefault(s, s)
            parent.setdefault(t, t)
            union(s, t)

    comps = {}
    for n in list(parent.keys()):
        comps.setdefault(find(n), []).append(n)
    return list(comps.values())


def rebuild_communities(tenant_id: str) -> int:
    """Tenant 그래프의 Community를 재탐지하고 요약을 다시 생성한다. 생성된 Community 수 반환."""
    from apps.rag.ingesters import get_embeddings
    from apps.tenants.models import TenantConfig
    from apps.agent.providers import embedding_provider

    gs = GraphStore(tenant_id)
    _ecfg = TenantConfig.objects.filter(tenant_id=tenant_id).first()
    _ep = embedding_provider(_ecfg) if _ecfg else None
    _edim = _ecfg.embed_dim if _ecfg else 1024
    gs.set_freshness("rebuilding")
    try:
        # 임베딩 없는(기능 이전에 생성된) Mention 백필 → 의미 검색 가능
        missing = gs.mentions_without_embedding()
        if missing:
            gs.ensure_mention_vector_index(dimensions=_edim)
            texts = [
                f"{m['name']}: {m['description']}".strip(": ") if m["description"] else m["name"]
                for m in missing
            ]
            for m, emb in zip(missing, get_embeddings(texts, provider=_ep)):
                gs.set_mention_embedding(m["mention_id"], emb)

        # Entity Resolution + Community를 Entity Mention 기준으로 수행한다(ADR-0010 / issue 80).
        # 같은 표기라도 맥락(임베딩)이 다른 Mention은 분리되어 동음이의가 별도 Community로 남는다.
        # SAME_AS는 연결요소 계산에 RELATED와 함께 union되어 동치 Mention이 같은 Community에 든다.
        from apps.rag.entity_resolver import resolve_equivalences

        mention_nodes = gs.query_mentions()
        name_by_mid = {m["mention_id"]: m["name"] for m in mention_nodes}
        mids = [m["mention_id"] for m in mention_nodes]
        mention_rels = gs.query_mention_relations()

        for a, b in resolve_equivalences(gs.mention_embeddings()):
            gs.upsert_mention_same_as(a, b)
        same_as = [{"source": a, "target": b} for a, b in gs.query_mention_same_as()]

        components = _connected_components(mids, mention_rels + same_as)

        from apps.tenants.models import TenantConfig
        from apps.agent.providers import extraction_provider
        _cfg = TenantConfig.objects.filter(tenant_id=tenant_id).first()
        _provider = extraction_provider(_cfg) if _cfg else None

        gs.clear_communities()
        for i, member_mids in enumerate(components):
            members = [name_by_mid.get(mid, mid) for mid in member_mids]
            prompt = (
                "Summarize this community of related entities in one sentence: "
                + ", ".join(members)
            )
            summary = llm_boundary.complete_text(
                _provider, [HumanMessage(content=prompt)]
            )
            gs.upsert_community(f"{tenant_id}:{i}", summary, members)

        gs.set_freshness("fresh")
        return len(components)
    except Exception:
        gs.set_freshness("stale")
        raise
