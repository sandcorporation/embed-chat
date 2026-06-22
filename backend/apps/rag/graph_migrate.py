"""GraphStore 데이터 이전: Neo4j → Postgres+pgvector (PRD-pgvector-graphstore, issue 166).

기존 테넌트 그래프(노드·엣지·임베딩)를 임베딩 재계산 없이 pg 스토어로 옮긴다. 읽기는 Neo4j 백엔드의
export_* (Cypher), 쓰기는 pg 백엔드의 공개 upsert로 — 둘 다 멱등(ON CONFLICT)이라 재실행 안전.
import 측(write_export_to_pg)은 합성 export로 테스트 가능하다(Neo4j 불필요).
"""


def read_neo4j_export(tenant_id: str) -> dict:
    """한 테넌트의 그래프를 Neo4j에서 읽어 export 딕셔너리로 반환한다(임베딩 포함)."""
    from apps.rag.graph_store import _Neo4jGraphStore

    neo = _Neo4jGraphStore(str(tenant_id))
    return {
        "text_units": neo.export_text_units(),
        "mentions": neo.export_mentions(),
        "relations": neo.export_relations(),
        "same_as": neo.query_mention_same_as(),
        "freshness": neo.get_freshness(),
    }


def write_export_to_pg(tenant_id: str, export: dict) -> dict:
    """export 딕셔너리를 pg 스토어에 기록한다(임베딩 보존, 멱등). 기록 건수를 반환한다."""
    from apps.rag.graph_store import _PgGraphStore

    pg = _PgGraphStore(str(tenant_id))
    for u in export.get("text_units", []):
        if u.get("embedding") is None:
            continue  # 임베딩 없는 TextUnit은 그래프에 없음(스킵)
        pg.upsert_text_unit(
            u["unit_id"], u.get("content", ""), u["embedding"],
            u.get("source_document_id", ""), u.get("chunk_index", 0),
        )
    for m in export.get("mentions", []):
        pg.upsert_mention(
            m["mention_id"], m.get("name", ""), m.get("entity_type", ""),
            m.get("description", ""), m.get("source_document_id", ""), embedding=m.get("embedding"),
        )
    for r in export.get("relations", []):
        pg.upsert_mention_relation(
            r["source_id"], r["target_id"], r.get("description", ""), r.get("source_document_id", ""),
        )
    for a, b in export.get("same_as", []):
        pg.upsert_mention_same_as(a, b)
    if export.get("freshness"):
        pg.set_freshness(export["freshness"])
    return {
        "text_units": len(export.get("text_units", [])),
        "mentions": len(export.get("mentions", [])),
        "relations": len(export.get("relations", [])),
        "same_as": len(export.get("same_as", [])),
    }


def migrate_tenant(tenant_id: str) -> dict:
    """한 테넌트의 그래프를 Neo4j에서 읽어 pg로 이전한다(임베딩 재계산 없음)."""
    return write_export_to_pg(tenant_id, read_neo4j_export(tenant_id))
