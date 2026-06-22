"""GraphStore — Knowledge Graph(Neo4j) 접근 경계 (deep module).

모든 그래프 접근은 이 모듈을 통하며, 생성자에서 받은 tenant_id를 모든 쿼리에
강제로 주입한다. tenant_id 없이는 그래프에 닿을 수 없으므로 테넌트 누수를 구조적으로 막는다.
"""
# neo4j 드라이버는 query를 LiteralString으로 요구(인젝션 가드)하지만 본 모듈은 동적 Cypher를
# tenant_id 파라미터 바인딩과 함께 안전하게 쓴다 — 런타임 정상.
# pyright: reportArgumentType=false
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


class _Neo4jGraphStore:
    def __init__(self, tenant_id: str):
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self.tenant_id = str(tenant_id)

    # Neo4j 벡터 인덱스는 (label, property)당 하나·고정 차원이므로, Tenant마다 다른
    # 임베딩 차원을 담으려면 인덱스를 per-Tenant 라벨/이름으로 격리한다(ADR-0012).
    # tenant_id는 우리 시스템의 UUID라 라벨 식별자로 안전하다(하이픈만 제거).
    def _tu_label(self) -> str:
        return f"TU_{self.tenant_id.replace('-', '')}"

    def _tu_index(self) -> str:
        return f"tu_{self.tenant_id.replace('-', '')}"

    def _m_label(self) -> str:
        return f"M_{self.tenant_id.replace('-', '')}"

    def _m_index(self) -> str:
        return f"m_{self.tenant_id.replace('-', '')}"

    def _embedding_provider(self):
        """이 Tenant의 임베딩 provider(검색 쿼리 임베딩이 저장 공간과 일치하도록)."""
        from apps.tenants.models import TenantConfig
        from apps.agent.providers import embedding_provider
        cfg = TenantConfig.objects.filter(tenant_id=self.tenant_id).first()
        return embedding_provider(cfg) if cfg else None

    def ensure_vector_index(self, dimensions: int = 1024) -> None:
        """이 Tenant의 TextUnit 벡터 인덱스를 보장하고 ONLINE까지 대기한다(per-Tenant)."""
        create = (
            f"CREATE VECTOR INDEX {self._tu_index()} IF NOT EXISTS "
            f"FOR (t:{self._tu_label()}) ON (t.embedding) "
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
            f"SET t:{self._tu_label()}, t.content = $content, t.embedding = $embedding, "
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

    def all_text_units(self) -> list:
        """이 tenant의 모든 Text Unit(unit_id, content)을 반환한다 (재임베딩용)."""
        query = "MATCH (t:TextUnit {tenant_id: $tenant_id}) RETURN t.unit_id AS unit_id, t.content AS content"
        with _get_driver().session() as session:
            return [dict(r) for r in session.run(query, tenant_id=self.tenant_id)]

    def set_text_unit_embedding(self, unit_id: str, embedding: list) -> None:
        """Text Unit의 임베딩만 교체한다 (content 등은 보존)."""
        with _get_driver().session() as session:
            session.run(
                "MATCH (t:TextUnit {tenant_id: $tenant_id, unit_id: $uid}) SET t.embedding = $emb",
                tenant_id=self.tenant_id, uid=unit_id, emb=embedding,
            )

    def recreate_vector_indexes(self, dimensions: int) -> None:
        """per-Tenant 벡터 인덱스를 새 차원으로 재생성한다(임베딩 모델 변경 시)."""
        with _get_driver().session() as session:
            session.run(f"DROP INDEX {self._tu_index()} IF EXISTS")
            session.run(f"DROP INDEX {self._m_index()} IF EXISTS")
        self.ensure_vector_index(dimensions=dimensions)
        self.ensure_mention_vector_index(dimensions=dimensions)

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
                    idx=self._tu_index(),
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
            f"SET m:{self._m_label()}, m.name = $name, m.entity_type = $entity_type, m.description = $description, "
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
            f"CREATE VECTOR INDEX {self._m_index()} IF NOT EXISTS "
            f"FOR (m:{self._m_label()}) ON (m.embedding) "
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
                query_embedding = get_embeddings([term], provider=self._embedding_provider())[0]
                for rec in session.run(
                    vector_q,
                    idx=self._m_index(),
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


# ── Postgres + pgvector 백엔드 (PRD-pgvector-graphstore) ──────────────────────
# 같은 deep module 인터페이스를 Postgres로 백킹한다. per-Tenant 임베딩 차원은 차원별 테이블
# (kg_text_unit_d{dim} 등)로 라우팅하고, 검색은 tenant_id 스코프 + HNSW(+iterative scan)다.
# 비-벡터(엣지·meta)는 정적 공유 테이블(마이그레이션). 모든 쿼리에 tenant_id를 강제 주입한다.

def _vec_literal(embedding) -> str:
    """파이썬 시퀀스를 pgvector 텍스트 리터럴('[a,b,c]')로. %s::vector 파라미터로 바인딩한다."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def _parse_vec(value) -> list:
    """pgvector 컬럼 반환값('[a,b,c]' 문자열)을 list[float]로 파싱한다(어댑터 미등록 raw 커서)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    return [float(x) for x in str(value).strip("[]").split(",") if x.strip()]


class _PgGraphStore:
    def __init__(self, tenant_id: str):
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self.tenant_id = str(tenant_id)
        self._dim_cache = None
        self._ensured_tu = set()  # 이 인스턴스에서 DDL 보장한 차원(중복 DDL 회피)

    def _dim(self) -> int:
        if self._dim_cache is None:
            from apps.tenants.models import TenantConfig
            cfg = TenantConfig.objects.filter(tenant_id=self.tenant_id).first()
            self._dim_cache = cfg.embed_dim if cfg else 1024
        return self._dim_cache

    def _tu_table(self) -> str:
        return f"kg_text_unit_d{self._dim()}"

    def _embedding_provider(self):
        from apps.tenants.models import TenantConfig
        from apps.agent.providers import embedding_provider
        cfg = TenantConfig.objects.filter(tenant_id=self.tenant_id).first()
        return embedding_provider(cfg) if cfg else None

    # ── DDL (차원별 테이블 + HNSW, IF NOT EXISTS — 동적) ──────────────────────
    def _ensure_tu(self, dim: int) -> None:
        if dim in self._ensured_tu:
            return
        from django.db import connection
        t = f"kg_text_unit_d{dim}"
        with connection.cursor() as cur:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {t} ("
                "tenant_id text NOT NULL, unit_id text NOT NULL, content text, "
                "source_document_id text DEFAULT '', chunk_index int DEFAULT 0, "
                f"embedding vector({dim}), PRIMARY KEY (tenant_id, unit_id))"
            )
            cur.execute(f"CREATE INDEX IF NOT EXISTS {t}_doc ON {t} (tenant_id, source_document_id)")
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS {t}_hnsw ON {t} "
                "USING hnsw (embedding vector_cosine_ops)"
            )
        self._ensured_tu.add(dim)

    def ensure_vector_index(self, dimensions: int = 1024) -> None:
        self._ensure_tu(dimensions)

    # ── Text Unit ────────────────────────────────────────────────────────────
    def upsert_text_unit(self, unit_id, content, embedding, source_document_id="", chunk_index=0) -> None:
        from django.db import connection
        self._ensure_tu(self._dim())
        t = self._tu_table()
        with connection.cursor() as cur:
            cur.execute(
                f"INSERT INTO {t} (tenant_id, unit_id, content, source_document_id, chunk_index, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector) "
                "ON CONFLICT (tenant_id, unit_id) DO UPDATE SET "
                "content=EXCLUDED.content, source_document_id=EXCLUDED.source_document_id, "
                "chunk_index=EXCLUDED.chunk_index, embedding=EXCLUDED.embedding",
                [self.tenant_id, unit_id, content, source_document_id, chunk_index, _vec_literal(embedding)],
            )

    def query_text_units(self, document_id: str) -> list:
        from django.db import connection
        t = self._tu_table()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f"SELECT coalesce(chunk_index,0) AS chunk_index, content FROM {t} "
                    "WHERE tenant_id=%s AND source_document_id=%s ORDER BY chunk_index",
                    [self.tenant_id, document_id],
                )
                return [{"chunk_index": r[0], "content": r[1]} for r in cur.fetchall()]
        except Exception:
            return []

    def all_text_units(self) -> list:
        from django.db import connection
        t = self._tu_table()
        try:
            with connection.cursor() as cur:
                cur.execute(f"SELECT unit_id, content FROM {t} WHERE tenant_id=%s", [self.tenant_id])
                return [{"unit_id": r[0], "content": r[1]} for r in cur.fetchall()]
        except Exception:
            return []

    def set_text_unit_embedding(self, unit_id: str, embedding: list) -> None:
        from django.db import connection
        self._ensure_tu(self._dim())
        t = self._tu_table()
        with connection.cursor() as cur:
            cur.execute(
                f"UPDATE {t} SET embedding=%s::vector WHERE tenant_id=%s AND unit_id=%s",
                [_vec_literal(embedding), self.tenant_id, unit_id],
            )

    def vector_search(self, query_embedding: list, top_k: int = 5) -> list:
        from django.db import connection
        t = self._tu_table()
        lit = _vec_literal(query_embedding)
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f"SELECT content, source_document_id, 1 - (embedding <=> %s::vector) AS score "
                    f"FROM {t} WHERE tenant_id=%s ORDER BY embedding <=> %s::vector LIMIT %s",
                    [lit, self.tenant_id, lit, top_k],
                )
                return [{"content": r[0], "source_document_id": r[1], "score": r[2]} for r in cur.fetchall()]
        except Exception:
            # 테이블 미존재(문서 미인제스트 tenant 등) → 근거 없음
            return []

    # ── Graph Freshness (정적 공유 테이블) ───────────────────────────────────
    def set_freshness(self, state: str) -> None:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO kg_graph_meta (tenant_id, freshness) VALUES (%s, %s) "
                "ON CONFLICT (tenant_id) DO UPDATE SET freshness=EXCLUDED.freshness",
                [self.tenant_id, state],
            )

    def get_freshness(self) -> str:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT freshness FROM kg_graph_meta WHERE tenant_id=%s", [self.tenant_id])
            row = cur.fetchone()
        return row[0] if row and row[0] else "fresh"

    # ── Entity Mention ───────────────────────────────────────────────────────
    def _m_table(self) -> str:
        return f"kg_mention_d{self._dim()}"

    def _ensure_m(self, dim: int) -> None:
        from django.db import connection
        t = f"kg_mention_d{dim}"
        with connection.cursor() as cur:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {t} ("
                "tenant_id text NOT NULL, mention_id text NOT NULL, name text, "
                "entity_type text DEFAULT '', description text DEFAULT '', "
                "source_document_id text DEFAULT '', "
                f"embedding vector({dim}), PRIMARY KEY (tenant_id, mention_id))"
            )
            cur.execute(f"CREATE INDEX IF NOT EXISTS {t}_tenant ON {t} (tenant_id)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS {t}_doc ON {t} (tenant_id, source_document_id)")
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS {t}_hnsw ON {t} "
                "USING hnsw (embedding vector_cosine_ops)"
            )

    def ensure_mention_vector_index(self, dimensions: int = 1024) -> None:
        self._ensure_m(dimensions)

    def upsert_mention(self, mention_id, name, entity_type="", description="",
                       source_document_id="", embedding=None) -> None:
        from django.db import connection
        self._ensure_m(self._dim())
        t = self._m_table()
        emb = _vec_literal(embedding) if embedding is not None else None
        with connection.cursor() as cur:
            cur.execute(
                f"INSERT INTO {t} (tenant_id, mention_id, name, entity_type, description, "
                "source_document_id, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s::vector) "
                "ON CONFLICT (tenant_id, mention_id) DO UPDATE SET "
                "name=EXCLUDED.name, entity_type=EXCLUDED.entity_type, description=EXCLUDED.description, "
                "source_document_id=EXCLUDED.source_document_id, "
                # 임베딩은 None이면 기존값 보존(현 Neo4j CASE WHEN과 동일)
                f"embedding=COALESCE(EXCLUDED.embedding, {t}.embedding)",
                [self.tenant_id, mention_id, name, entity_type, description, source_document_id, emb],
            )

    def query_mentions(self) -> list:
        from django.db import connection
        t = self._m_table()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f"SELECT mention_id, name, entity_type, description, source_document_id "
                    f"FROM {t} WHERE tenant_id=%s", [self.tenant_id],
                )
                cols = ("mention_id", "name", "entity_type", "description", "source_document_id")
                return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception:
            return []

    def mention_embeddings(self) -> list:
        from django.db import connection
        t = self._m_table()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f"SELECT mention_id, embedding FROM {t} "
                    "WHERE tenant_id=%s AND embedding IS NOT NULL", [self.tenant_id],
                )
                return [{"mention_id": r[0], "embedding": _parse_vec(r[1])} for r in cur.fetchall()]
        except Exception:
            return []

    def mentions_without_embedding(self) -> list:
        from django.db import connection
        t = self._m_table()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f"SELECT mention_id, name, coalesce(description,'') FROM {t} "
                    "WHERE tenant_id=%s AND embedding IS NULL", [self.tenant_id],
                )
                return [{"mention_id": r[0], "name": r[1], "description": r[2]} for r in cur.fetchall()]
        except Exception:
            return []

    def set_mention_embedding(self, mention_id: str, embedding: list) -> None:
        from django.db import connection
        self._ensure_m(self._dim())
        t = self._m_table()
        with connection.cursor() as cur:
            cur.execute(
                f"UPDATE {t} SET embedding=%s::vector WHERE tenant_id=%s AND mention_id=%s",
                [_vec_literal(embedding), self.tenant_id, mention_id],
            )

    def upsert_mention_same_as(self, id_a: str, id_b: str) -> None:
        from django.db import connection
        a, b = sorted([id_a, id_b])  # 무방향 → 정규화(a<b)
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO kg_same_as (tenant_id, a, b) VALUES (%s, %s, %s) "
                "ON CONFLICT (tenant_id, a, b) DO NOTHING",
                [self.tenant_id, a, b],
            )

    def query_mention_same_as(self) -> list:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT a, b FROM kg_same_as WHERE tenant_id=%s", [self.tenant_id])
            return [(r[0], r[1]) for r in cur.fetchall()]

    def search_entities(self, term: str, top_k: int = 10) -> list:
        """어휘(부분일치) ∪ 의미(벡터) Mention 검색 → SAME_AS 클러스터로 dedup (현 Neo4j와 동일)."""
        from django.db import connection
        t = self._m_table()
        cols = ("mention_id", "name", "entity_type", "description", "source_document_id")
        by_mid = {}
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f"SELECT mention_id, name, entity_type, description, source_document_id FROM {t} "
                    "WHERE tenant_id=%s AND (position(lower(%s) in lower(name))>0 "
                    "OR position(lower(%s) in lower(coalesce(description,'')))>0)",
                    [self.tenant_id, term, term],
                )
                for r in cur.fetchall():
                    by_mid[r[0]] = dict(zip(cols, r))
        except Exception:
            pass
        # 의미(벡터) 보강 — 인덱스/임베딩이 없으면 어휘만으로 무중단
        try:
            from apps.rag.ingesters import get_embeddings
            q = _vec_literal(get_embeddings([term], provider=self._embedding_provider())[0])
            with connection.cursor() as cur:
                cur.execute(
                    f"SELECT mention_id, name, entity_type, description, source_document_id FROM {t} "
                    "WHERE tenant_id=%s AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> %s::vector LIMIT %s",
                    [self.tenant_id, q, top_k],
                )
                for r in cur.fetchall():
                    by_mid.setdefault(r[0], dict(zip(cols, r)))
        except Exception:
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

    # ── RELATED 관계 + 1-hop 이웃 ────────────────────────────────────────────
    def upsert_mention_relation(self, source_id, target_id, description="", source_document_id="") -> None:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO kg_relation (tenant_id, source_id, target_id, description, source_document_id) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id, source_id, target_id) DO UPDATE SET "
                "description=EXCLUDED.description, source_document_id=EXCLUDED.source_document_id",
                [self.tenant_id, source_id, target_id, description, source_document_id],
            )

    def query_mention_relations(self) -> list:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                "SELECT source_id, target_id FROM kg_relation WHERE tenant_id=%s", [self.tenant_id]
            )
            return [{"source": r[0], "target": r[1]} for r in cur.fetchall()]

    def neighbors(self, name: str) -> dict:
        """이름의 Mention + 1-hop RELATED 이웃·엣지를 {nodes, edges}로 (tenant 스코프, 이름 기준)."""
        from django.db import connection
        m = self._m_table()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f"WITH seed AS (SELECT mention_id FROM {m} WHERE tenant_id=%s AND name=%s) "
                    f"SELECT DISTINCT mm.name, mm.entity_type, mm.description, mm.source_document_id "
                    f"FROM {m} mm WHERE mm.tenant_id=%s AND (mm.mention_id IN (SELECT mention_id FROM seed) "
                    "OR mm.mention_id IN ("
                    "  SELECT target_id FROM kg_relation WHERE tenant_id=%s AND source_id IN (SELECT mention_id FROM seed) "
                    "  UNION SELECT source_id FROM kg_relation WHERE tenant_id=%s AND target_id IN (SELECT mention_id FROM seed)))",
                    [self.tenant_id, name, self.tenant_id, self.tenant_id, self.tenant_id],
                )
                ncols = ("name", "entity_type", "description", "source_document_id")
                nodes = [dict(zip(ncols, r)) for r in cur.fetchall()]

                cur.execute(
                    f"SELECT a.name, b.name, r.description FROM kg_relation r "
                    f"JOIN {m} a ON a.tenant_id=r.tenant_id AND a.mention_id=r.source_id "
                    f"JOIN {m} b ON b.tenant_id=r.tenant_id AND b.mention_id=r.target_id "
                    "WHERE r.tenant_id=%s AND (a.name=%s OR b.name=%s)",
                    [self.tenant_id, name, name],
                )
                edges = [{"source": r[0], "target": r[1], "description": r[2]} for r in cur.fetchall()]
            return {"nodes": nodes, "edges": edges}
        except Exception:
            return {"nodes": [], "edges": []}


class GraphStore:
    """백엔드 파사드 — settings.GRAPH_BACKEND(neo4j|pg)로 구현을 고른다. 공개 인터페이스는
    호출부가 쓰는 그대로이며, 모든 메서드는 선택된 백엔드로 위임된다(인터페이스 불변)."""

    def __init__(self, tenant_id: str):
        if not tenant_id:
            raise ValueError("tenant_id is required")
        backend = _PgGraphStore if getattr(settings, "GRAPH_BACKEND", "neo4j") == "pg" else _Neo4jGraphStore
        self.__dict__["_backend"] = backend(str(tenant_id))

    def __getattr__(self, name):
        return getattr(self.__dict__["_backend"], name)
