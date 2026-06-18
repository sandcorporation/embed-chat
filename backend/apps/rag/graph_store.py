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
MENTION_VECTOR_INDEX = "mention_embedding"


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
        """문서의 대표(레이블) Mention을 새 레이블로 시드한다. 그래프는 stale로 표시."""
        self.upsert_mention(
            f"{document_id}:{new_label}",
            new_label,
            "document",
            f"Source document: {new_label}",
            source_document_id=document_id,
        )
        self.set_freshness("stale")

    # ── 문서 삭제: Mention/Text Unit 제거 (Mention은 문서 전용이라 통째 삭제) ──────
    def delete_document(self, document_id: str) -> None:
        """문서의 Entity Mention과 Text Unit을 삭제한다. 그래프는 stale로 표시."""
        delete_text_units = (
            "MATCH (t:TextUnit {tenant_id: $tenant_id, source_document_id: $doc}) DELETE t"
        )
        delete_mentions = (
            "MATCH (m:Mention {tenant_id: $tenant_id, source_document_id: $doc}) DETACH DELETE m"
        )
        with _get_driver().session() as session:
            session.run(delete_text_units, tenant_id=self.tenant_id, doc=document_id)
            session.run(delete_mentions, tenant_id=self.tenant_id, doc=document_id)
        self.set_freshness("stale")

    # ── Entity Mention (mention_id 식별 — ADR-0010) ──────────────────────────
    def upsert_mention(
        self,
        mention_id: str,
        name: str,
        entity_type: str = "",
        description: str = "",
        source_document_id: str = "",
        embedding: list = None,
    ) -> None:
        """Entity Mention을 upsert한다. (tenant_id, mention_id)로 식별하므로 같은 표기라도
        출처/맥락이 다르면 별개 노드다(동음이의 보존)."""
        query = (
            "MERGE (m:Mention {tenant_id: $tenant_id, mention_id: $mention_id}) "
            "SET m.name = $name, m.entity_type = $entity_type, m.description = $description, "
            "m.source_document_id = $source_document_id, "
            "m.embedding = CASE WHEN $embedding IS NULL THEN m.embedding ELSE $embedding END"
        )
        with _get_driver().session() as session:
            session.run(
                query,
                tenant_id=self.tenant_id,
                mention_id=mention_id,
                name=name,
                entity_type=entity_type,
                description=description,
                source_document_id=source_document_id,
                embedding=embedding,
            )

    def query_mentions(self) -> list:
        """이 tenant의 Entity Mention 목록을 반환한다."""
        query = (
            "MATCH (m:Mention {tenant_id: $tenant_id}) "
            "RETURN m.mention_id AS mention_id, m.name AS name, "
            "m.entity_type AS entity_type, m.description AS description, "
            "m.source_document_id AS source_document_id"
        )
        with _get_driver().session() as session:
            return [dict(r) for r in session.run(query, tenant_id=self.tenant_id)]

    def mention_embeddings(self) -> list:
        """임베딩을 가진 Mention의 (mention_id, embedding)을 반환한다 (resolution 입력용)."""
        query = (
            "MATCH (m:Mention {tenant_id: $tenant_id}) WHERE m.embedding IS NOT NULL "
            "RETURN m.mention_id AS mention_id, m.embedding AS embedding"
        )
        with _get_driver().session() as session:
            return [dict(r) for r in session.run(query, tenant_id=self.tenant_id)]

    def mentions_without_embedding(self) -> list:
        """임베딩이 없는 Mention(mention_id, name, description)을 반환한다 (백필 대상)."""
        query = (
            "MATCH (m:Mention {tenant_id: $tenant_id}) WHERE m.embedding IS NULL "
            "RETURN m.mention_id AS mention_id, m.name AS name, "
            "coalesce(m.description, '') AS description"
        )
        with _get_driver().session() as session:
            return [dict(r) for r in session.run(query, tenant_id=self.tenant_id)]

    def set_mention_embedding(self, mention_id: str, embedding: list) -> None:
        """Mention의 임베딩만 설정한다 (다른 속성은 보존)."""
        with _get_driver().session() as session:
            session.run(
                "MATCH (m:Mention {tenant_id: $tenant_id, mention_id: $mid}) SET m.embedding = $embedding",
                tenant_id=self.tenant_id, mid=mention_id, embedding=embedding,
            )

    def upsert_mention_relation(
        self, source_id: str, target_id: str, description: str = "", source_document_id: str = ""
    ) -> None:
        """두 Mention 사이 RELATED 관계를 upsert한다 (양 끝 Mention이 없으면 생성)."""
        query = (
            "MERGE (a:Mention {tenant_id: $tenant_id, mention_id: $source_id}) "
            "MERGE (b:Mention {tenant_id: $tenant_id, mention_id: $target_id}) "
            "MERGE (a)-[r:RELATED {tenant_id: $tenant_id}]->(b) "
            "SET r.description = $description, r.source_document_id = $source_document_id"
        )
        with _get_driver().session() as session:
            session.run(
                query, tenant_id=self.tenant_id, source_id=source_id, target_id=target_id,
                description=description, source_document_id=source_document_id,
            )

    def query_mention_relations(self) -> list:
        """Mention 간 RELATED 관계 [{source, target}]을 반환한다 (mention_id 기준)."""
        query = (
            "MATCH (a:Mention {tenant_id: $tenant_id})-[:RELATED {tenant_id: $tenant_id}]->"
            "(b:Mention {tenant_id: $tenant_id}) "
            "RETURN a.mention_id AS source, b.mention_id AS target"
        )
        with _get_driver().session() as session:
            return [dict(r) for r in session.run(query, tenant_id=self.tenant_id)]

    def upsert_mention_same_as(self, id_a: str, id_b: str) -> None:
        """두 Mention을 비파괴 SAME_AS 동치 엣지로 잇는다 (mention_id 기준)."""
        query = (
            "MATCH (a:Mention {tenant_id: $tenant_id, mention_id: $a}) "
            "MATCH (b:Mention {tenant_id: $tenant_id, mention_id: $b}) "
            "MERGE (a)-[:SAME_AS {tenant_id: $tenant_id}]-(b)"
        )
        with _get_driver().session() as session:
            session.run(query, tenant_id=self.tenant_id, a=id_a, b=id_b)

    def query_mention_same_as(self) -> list:
        """Mention 간 SAME_AS 동치 쌍 [(id_a, id_b)]을 반환한다."""
        query = (
            "MATCH (a:Mention {tenant_id: $tenant_id})-[:SAME_AS {tenant_id: $tenant_id}]-"
            "(b:Mention {tenant_id: $tenant_id}) WHERE a.mention_id < b.mention_id "
            "RETURN a.mention_id AS source, b.mention_id AS target"
        )
        with _get_driver().session() as session:
            return [(r["source"], r["target"]) for r in session.run(query, tenant_id=self.tenant_id)]

    def ensure_mention_vector_index(self, dimensions: int = 1024) -> None:
        """Mention.embedding에 대한 Neo4j 벡터 인덱스를 보장하고 ONLINE까지 대기한다."""
        create = (
            f"CREATE VECTOR INDEX {MENTION_VECTOR_INDEX} IF NOT EXISTS "
            "FOR (m:Mention) ON (m.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}"
        )
        with _get_driver().session() as session:
            session.run(create, dim=dimensions)
            session.run("CALL db.awaitIndexes(30000)")

    def search_entities(self, term: str, top_k: int = 10) -> list:
        """resolved Entity 검색 — Mention을 어휘 ∪ 의미(벡터)로 찾아 SAME_AS 클러스터로 dedup한다.

        표기변이(동치)는 하나의 Entity로, 동음이의(맥락 다름)는 별개로 반환한다(ADR-0010).
        어휘는 정확/부분 일치를, 벡터는 다국어/동의어 질의(예: '메뉴'→'OSD Menu')를 보강한다.
        """
        lexical_q = (
            "MATCH (m:Mention {tenant_id: $tenant_id}) "
            "WHERE toLower(m.name) CONTAINS toLower($term) "
            "   OR toLower(coalesce(m.description, '')) CONTAINS toLower($term) "
            "RETURN m.mention_id AS mention_id, m.name AS name, m.entity_type AS entity_type, "
            "m.description AS description, m.source_document_id AS source_document_id"
        )
        vector_q = (
            "CALL db.index.vector.queryNodes($idx, $probe, $emb) YIELD node, score "
            "WHERE node.tenant_id = $tenant_id "
            "RETURN node.mention_id AS mention_id, node.name AS name, "
            "node.entity_type AS entity_type, node.description AS description, "
            "node.source_document_id AS source_document_id "
            "ORDER BY score DESC LIMIT $top_k"
        )
        by_mid = {}
        with _get_driver().session() as session:
            for rec in session.run(lexical_q, tenant_id=self.tenant_id, term=term):
                by_mid[rec["mention_id"]] = dict(rec)

            # 의미(벡터) 보강 — 인덱스/임베딩이 없으면 어휘만으로 무중단
            try:
                from apps.rag.ingesters import get_embeddings
                query_embedding = get_embeddings([term])[0]
                for rec in session.run(
                    vector_q,
                    idx=MENTION_VECTOR_INDEX,
                    probe=max(top_k * 5, 10),
                    emb=query_embedding,
                    tenant_id=self.tenant_id,
                    top_k=top_k,
                ):
                    by_mid.setdefault(rec["mention_id"], dict(rec))
            except Neo4jError:
                pass

        # SAME_AS 클러스터로 dedup — 동치 Mention들이 하나의 resolved Entity가 된다.
        parent = {}

        def _find(x):
            parent.setdefault(x, x)
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        for a, b in self.query_mention_same_as():
            parent.setdefault(a, a)
            parent.setdefault(b, b)
            parent[_find(a)] = _find(b)

        by_cluster = {}
        for mid, data in by_mid.items():
            by_cluster.setdefault(_find(mid), data)
        return list(by_cluster.values())

    def neighbors(self, name: str) -> dict:
        """해당 이름의 Mention과 1홉 이웃, 그 사이 관계를 {nodes, edges}로 반환한다 (tenant 스코프)."""
        nodes_q = (
            "MATCH (m:Mention {tenant_id: $tenant_id, name: $name}) "
            "OPTIONAL MATCH (m)-[:RELATED {tenant_id: $tenant_id}]-(n:Mention {tenant_id: $tenant_id}) "
            "WITH collect(DISTINCT m) + collect(DISTINCT n) AS ns "
            "UNWIND ns AS node "
            "WITH DISTINCT node WHERE node IS NOT NULL "
            "RETURN node.name AS name, node.entity_type AS entity_type, "
            "node.description AS description, node.source_document_id AS source_document_id"
        )
        edges_q = (
            "MATCH (a:Mention {tenant_id: $tenant_id})-[r:RELATED {tenant_id: $tenant_id}]->"
            "(b:Mention {tenant_id: $tenant_id}) "
            "WHERE a.name = $name OR b.name = $name "
            "RETURN a.name AS source, b.name AS target, r.description AS description"
        )
        with _get_driver().session() as session:
            nodes = [dict(rec) for rec in session.run(nodes_q, tenant_id=self.tenant_id, name=name)]
            edges = [dict(rec) for rec in session.run(edges_q, tenant_id=self.tenant_id, name=name)]
        return {"nodes": nodes, "edges": edges}
