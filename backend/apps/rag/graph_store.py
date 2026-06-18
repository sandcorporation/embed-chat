"""GraphStore — Knowledge Graph(Neo4j) 접근 경계 (deep module).

모든 그래프 접근은 이 모듈을 통하며, 생성자에서 받은 tenant_id를 모든 쿼리에
강제로 주입한다. tenant_id 없이는 그래프에 닿을 수 없으므로 테넌트 누수를 구조적으로 막는다.
"""
from django.conf import settings
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

_driver = None


def _get_driver():
    """프로세스 단위로 Neo4j 드라이버를 재사용한다."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


VECTOR_INDEX = "text_unit_embedding"
ENTITY_VECTOR_INDEX = "entity_embedding"


class GraphStore:
    def __init__(self, tenant_id: str):
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self.tenant_id = str(tenant_id)

    def ensure_vector_index(self, dimensions: int = 1024) -> None:
        """TextUnit.embedding에 대한 Neo4j 벡터 인덱스를 보장하고 ONLINE까지 대기한다."""
        create = (
            f"CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS "
            "FOR (t:TextUnit) ON (t.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}"
        )
        with _get_driver().session() as session:
            session.run(create, dim=dimensions)
            session.run("CALL db.awaitIndexes(30000)")

    def upsert_text_unit(
        self,
        unit_id: str,
        content: str,
        embedding: list,
        source_document_id: str = "",
        chunk_index: int = 0,
    ) -> None:
        """Text Unit 노드를 임베딩과 함께 upsert한다."""
        query = (
            "MERGE (t:TextUnit {tenant_id: $tenant_id, unit_id: $unit_id}) "
            "SET t.content = $content, t.embedding = $embedding, "
            "t.source_document_id = $source_document_id, t.chunk_index = $chunk_index"
        )
        with _get_driver().session() as session:
            session.run(
                query,
                tenant_id=self.tenant_id,
                unit_id=unit_id,
                content=content,
                embedding=embedding,
                source_document_id=source_document_id,
                chunk_index=chunk_index,
            )

    def query_text_units(self, document_id: str) -> list:
        """특정 Document의 Text Unit을 chunk_index 순으로 반환한다 (tenant 스코프)."""
        query = (
            "MATCH (t:TextUnit {tenant_id: $tenant_id, source_document_id: $doc}) "
            "RETURN coalesce(t.chunk_index, 0) AS chunk_index, t.content AS content "
            "ORDER BY chunk_index"
        )
        with _get_driver().session() as session:
            result = session.run(query, tenant_id=self.tenant_id, doc=document_id)
            return [dict(record) for record in result]

    def vector_search(self, query_embedding: list, top_k: int = 5) -> list:
        """쿼리 임베딩으로 이 tenant의 최근접 Text Unit을 반환한다 (tenant 스코프)."""
        query = (
            "CALL db.index.vector.queryNodes($idx, $probe, $emb) YIELD node, score "
            "WHERE node.tenant_id = $tenant_id "
            "RETURN node.content AS content, "
            "node.source_document_id AS source_document_id, score "
            "ORDER BY score DESC LIMIT $top_k"
        )
        try:
            with _get_driver().session() as session:
                result = session.run(
                    query,
                    idx=VECTOR_INDEX,
                    probe=max(top_k * 5, 10),
                    emb=query_embedding,
                    tenant_id=self.tenant_id,
                    top_k=top_k,
                )
                return [dict(record) for record in result]
        except Neo4jError:
            # 벡터 인덱스가 아직 없음(문서 미인제스트 tenant 등) → 근거 없음
            return []

    # ── Graph Freshness ──────────────────────────────────────────────────────
    def set_freshness(self, state: str) -> None:
        with _get_driver().session() as session:
            session.run(
                "MERGE (m:GraphMeta {tenant_id: $tenant_id}) SET m.freshness = $state",
                tenant_id=self.tenant_id,
                state=state,
            )

    def get_freshness(self) -> str:
        with _get_driver().session() as session:
            rec = session.run(
                "MATCH (m:GraphMeta {tenant_id: $tenant_id}) RETURN m.freshness AS f",
                tenant_id=self.tenant_id,
            ).single()
            # 그래프가 비어 있으면(메타 없음) 재구축할 것이 없으므로 fresh로 본다
            return rec["f"] if rec and rec["f"] else "fresh"

    # ── Community ────────────────────────────────────────────────────────────
    def clear_communities(self) -> None:
        with _get_driver().session() as session:
            session.run(
                "MATCH (c:Community {tenant_id: $tenant_id}) DETACH DELETE c",
                tenant_id=self.tenant_id,
            )

    def upsert_community(self, community_id: str, summary: str, members: list) -> None:
        with _get_driver().session() as session:
            session.run(
                "MERGE (c:Community {tenant_id: $tenant_id, community_id: $cid}) "
                "SET c.summary = $summary, c.members = $members",
                tenant_id=self.tenant_id,
                cid=community_id,
                summary=summary,
                members=members,
            )

    def query_community_summaries(self) -> list:
        with _get_driver().session() as session:
            result = session.run(
                "MATCH (c:Community {tenant_id: $tenant_id}) "
                "RETURN c.summary AS summary, coalesce(c.members, []) AS members",
                tenant_id=self.tenant_id,
            )
            return [dict(record) for record in result]

    def reseed_document_label(self, document_id: str, new_label: str) -> None:
        """문서의 대표(레이블) Entity 이름을 새 레이블로 시드한다. 그래프는 stale로 표시."""
        self.upsert_entity(
            name=new_label,
            entity_type="document",
            description=f"Source document: {new_label}",
            source_document_id=document_id,
        )
        self.set_freshness("stale")

    # ── 문서 삭제: 출처 집합에서 제거 후 고아 prune ─────────────────────────────
    def delete_document(self, document_id: str) -> None:
        """문서를 노드/관계의 출처 집합에서 제거하고, 출처가 빈 것만 prune한다.
        공유 Entity(다른 문서도 출처)는 보존된다. 그래프는 stale로 표시."""
        prune_relations = (
            "MATCH (:Entity {tenant_id: $tenant_id})-[r:RELATED {tenant_id: $tenant_id}]->"
            "(:Entity {tenant_id: $tenant_id}) "
            "WHERE $doc IN coalesce(r.source_document_ids, []) "
            "SET r.source_document_ids = [x IN r.source_document_ids WHERE x <> $doc] "
            "WITH r WHERE size(r.source_document_ids) = 0 DELETE r"
        )
        prune_entities = (
            "MATCH (e:Entity {tenant_id: $tenant_id}) "
            "WHERE $doc IN coalesce(e.source_document_ids, []) "
            "SET e.source_document_ids = [x IN e.source_document_ids WHERE x <> $doc] "
            "WITH e WHERE size(e.source_document_ids) = 0 DETACH DELETE e"
        )
        delete_text_units = (
            "MATCH (t:TextUnit {tenant_id: $tenant_id, source_document_id: $doc}) DELETE t"
        )
        with _get_driver().session() as session:
            session.run(prune_relations, tenant_id=self.tenant_id, doc=document_id)
            session.run(prune_entities, tenant_id=self.tenant_id, doc=document_id)
            session.run(delete_text_units, tenant_id=self.tenant_id, doc=document_id)
        self.set_freshness("stale")

    def ensure_entity_vector_index(self, dimensions: int = 1024) -> None:
        """Entity.embedding에 대한 Neo4j 벡터 인덱스를 보장하고 ONLINE까지 대기한다."""
        create = (
            f"CREATE VECTOR INDEX {ENTITY_VECTOR_INDEX} IF NOT EXISTS "
            "FOR (e:Entity) ON (e.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}"
        )
        with _get_driver().session() as session:
            session.run(create, dim=dimensions)
            session.run("CALL db.awaitIndexes(30000)")

    def upsert_entity(
        self,
        name: str,
        entity_type: str = "",
        description: str = "",
        source_document_id: str = "",
        embedding: list = None,
    ) -> None:
        """Entity를 upsert한다. (tenant_id, name)로 식별하며 출처 Document를 누적한다.
        embedding이 주어지면 의미 검색용 임베딩을 갱신한다(None이면 기존 유지)."""
        query = (
            "MERGE (e:Entity {tenant_id: $tenant_id, name: $name}) "
            "SET e.entity_type = $entity_type, e.description = $description, "
            "e.embedding = CASE WHEN $embedding IS NULL THEN e.embedding ELSE $embedding END "
            "WITH e "
            "FOREACH (_ IN CASE WHEN $source_document_id <> '' THEN [1] ELSE [] END | "
            "  SET e.source_document_ids = "
            "    CASE WHEN $source_document_id IN coalesce(e.source_document_ids, []) "
            "      THEN e.source_document_ids "
            "      ELSE coalesce(e.source_document_ids, []) + $source_document_id END)"
        )
        with _get_driver().session() as session:
            session.run(
                query,
                tenant_id=self.tenant_id,
                name=name,
                entity_type=entity_type,
                description=description,
                source_document_id=source_document_id,
                embedding=embedding,
            )

    def entities_without_embedding(self) -> list:
        """임베딩이 없는 Entity(name, description)를 반환한다 (백필 대상)."""
        query = (
            "MATCH (e:Entity {tenant_id: $tenant_id}) WHERE e.embedding IS NULL "
            "RETURN e.name AS name, coalesce(e.description, '') AS description"
        )
        with _get_driver().session() as session:
            return [dict(r) for r in session.run(query, tenant_id=self.tenant_id)]

    def set_entity_embedding(self, name: str, embedding: list) -> None:
        """Entity의 임베딩만 설정한다(type/description 등 다른 속성은 보존)."""
        with _get_driver().session() as session:
            session.run(
                "MATCH (e:Entity {tenant_id: $tenant_id, name: $name}) SET e.embedding = $embedding",
                tenant_id=self.tenant_id,
                name=name,
                embedding=embedding,
            )

    def query_entities(self) -> list:
        """이 tenant의 Entity 목록을 반환한다."""
        query = (
            "MATCH (e:Entity {tenant_id: $tenant_id}) "
            "RETURN e.name AS name, e.entity_type AS entity_type, "
            "e.description AS description, "
            "coalesce(e.source_document_ids, []) AS source_document_ids"
        )
        with _get_driver().session() as session:
            result = session.run(query, tenant_id=self.tenant_id)
            return [dict(record) for record in result]

    def search_entities(self, term: str, top_k: int = 10) -> list:
        """하이브리드 엔티티 검색 — 어휘 부분일치 ∪ 의미(벡터) top-k, 이름 키로 dedup.

        어휘는 정확/부분 일치(문서 레이블·정확 이름)를 보장하고, 벡터는 다국어/동의어
        질의(예: '메뉴'→'OSD Menu')를 보강한다. 둘 다 tenant 스코프.
        """
        lexical_q = (
            "MATCH (e:Entity {tenant_id: $tenant_id}) "
            "WHERE toLower(e.name) CONTAINS toLower($term) "
            "   OR toLower(coalesce(e.description, '')) CONTAINS toLower($term) "
            "RETURN e.name AS name, e.entity_type AS entity_type, "
            "e.description AS description, "
            "coalesce(e.source_document_ids, []) AS source_document_ids"
        )
        vector_q = (
            "CALL db.index.vector.queryNodes($idx, $probe, $emb) YIELD node, score "
            "WHERE node.tenant_id = $tenant_id "
            "RETURN node.name AS name, node.entity_type AS entity_type, "
            "node.description AS description, "
            "coalesce(node.source_document_ids, []) AS source_document_ids "
            "ORDER BY score DESC LIMIT $top_k"
        )
        by_name = {}
        with _get_driver().session() as session:
            for rec in session.run(lexical_q, tenant_id=self.tenant_id, term=term):
                by_name[rec["name"]] = dict(rec)

            # 의미(벡터) 보강 — 인덱스/임베딩이 없으면 어휘만으로 무중단
            try:
                from apps.rag.ingesters import get_embeddings
                query_embedding = get_embeddings([term])[0]
                for rec in session.run(
                    vector_q,
                    idx=ENTITY_VECTOR_INDEX,
                    probe=max(top_k * 5, 10),
                    emb=query_embedding,
                    tenant_id=self.tenant_id,
                    top_k=top_k,
                ):
                    by_name.setdefault(rec["name"], dict(rec))
            except Neo4jError:
                pass

        return list(by_name.values())

    def neighbors(self, name: str) -> dict:
        """해당 Entity와 1홉 이웃, 그 사이 관계를 {nodes, edges}로 반환한다 (tenant 스코프)."""
        nodes_q = (
            "MATCH (e:Entity {tenant_id: $tenant_id, name: $name}) "
            "OPTIONAL MATCH (e)-[:RELATED {tenant_id: $tenant_id}]-(n:Entity {tenant_id: $tenant_id}) "
            "WITH collect(DISTINCT e) + collect(DISTINCT n) AS ns "
            "UNWIND ns AS node "
            "WITH DISTINCT node WHERE node IS NOT NULL "
            "RETURN node.name AS name, node.entity_type AS entity_type, "
            "node.description AS description, "
            "coalesce(node.source_document_ids, []) AS source_document_ids"
        )
        edges_q = (
            "MATCH (a:Entity {tenant_id: $tenant_id})-[r:RELATED {tenant_id: $tenant_id}]->"
            "(b:Entity {tenant_id: $tenant_id}) "
            "WHERE a.name = $name OR b.name = $name "
            "RETURN a.name AS source, b.name AS target, r.description AS description"
        )
        with _get_driver().session() as session:
            nodes = [dict(rec) for rec in session.run(nodes_q, tenant_id=self.tenant_id, name=name)]
            edges = [dict(rec) for rec in session.run(edges_q, tenant_id=self.tenant_id, name=name)]
        return {"nodes": nodes, "edges": edges}

    def upsert_relation(
        self,
        source: str,
        target: str,
        description: str = "",
        source_document_id: str = "",
    ) -> None:
        """source→target 관계를 upsert한다. 양 끝 Entity가 없으면 함께 생성하고 출처를 누적한다."""
        query = (
            "MERGE (a:Entity {tenant_id: $tenant_id, name: $source}) "
            "MERGE (b:Entity {tenant_id: $tenant_id, name: $target}) "
            "MERGE (a)-[r:RELATED {tenant_id: $tenant_id}]->(b) "
            "SET r.description = $description "
            "FOREACH (_ IN CASE WHEN $source_document_id <> '' THEN [1] ELSE [] END | "
            "  SET r.source_document_ids = "
            "    CASE WHEN $source_document_id IN coalesce(r.source_document_ids, []) "
            "      THEN r.source_document_ids "
            "      ELSE coalesce(r.source_document_ids, []) + $source_document_id END)"
        )
        with _get_driver().session() as session:
            session.run(
                query,
                tenant_id=self.tenant_id,
                source=source,
                target=target,
                description=description,
                source_document_id=source_document_id,
            )

    def query_relations(self) -> list:
        """이 tenant의 관계 목록을 반환한다."""
        query = (
            "MATCH (a:Entity {tenant_id: $tenant_id})-[r:RELATED {tenant_id: $tenant_id}]->"
            "(b:Entity {tenant_id: $tenant_id}) "
            "RETURN a.name AS source, b.name AS target, r.description AS description, "
            "coalesce(r.source_document_ids, []) AS source_document_ids"
        )
        with _get_driver().session() as session:
            result = session.run(query, tenant_id=self.tenant_id)
            return [dict(record) for record in result]
