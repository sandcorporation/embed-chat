from django.db import migrations


class Migration(migrations.Migration):
    """GraphStore(pgvector) 메타 스키마 — Django 모델이 아닌 raw SQL 테이블(ADR-0021).

    pgvector 확장과 kg_* 메타 테이블을 만든다. 실제 임베딩 벡터 테이블은 per-Tenant 가변 차원이라
    런타임에 GraphStore가 동적 생성한다(여긴 메타데이터/관계/원문 테이블만).
    """

    dependencies = [
        ("rag", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE EXTENSION IF NOT EXISTS vector;

            CREATE TABLE IF NOT EXISTS kg_graph_meta (
                tenant_id text PRIMARY KEY,
                freshness text,
                embed_dim int
            );

            CREATE TABLE IF NOT EXISTS kg_relation (
                tenant_id text NOT NULL,
                source_id text NOT NULL,
                target_id text NOT NULL,
                description text DEFAULT '',
                source_document_id text DEFAULT '',
                PRIMARY KEY (tenant_id, source_id, target_id)
            );
            CREATE INDEX IF NOT EXISTS kg_relation_tenant ON kg_relation (tenant_id);

            CREATE TABLE IF NOT EXISTS kg_same_as (
                tenant_id text NOT NULL,
                a text NOT NULL,
                b text NOT NULL,
                PRIMARY KEY (tenant_id, a, b)
            );
            CREATE INDEX IF NOT EXISTS kg_same_as_tenant ON kg_same_as (tenant_id);

            CREATE TABLE IF NOT EXISTS kg_text_unit (
                tenant_id text NOT NULL,
                unit_id text NOT NULL,
                content text,
                source_document_id text DEFAULT '',
                chunk_index int DEFAULT 0,
                PRIMARY KEY (tenant_id, unit_id)
            );
            CREATE INDEX IF NOT EXISTS kg_text_unit_doc ON kg_text_unit (tenant_id, source_document_id);

            CREATE TABLE IF NOT EXISTS kg_mention (
                tenant_id text NOT NULL,
                mention_id text NOT NULL,
                name text,
                entity_type text DEFAULT '',
                description text DEFAULT '',
                source_document_id text DEFAULT '',
                PRIMARY KEY (tenant_id, mention_id)
            );
            CREATE INDEX IF NOT EXISTS kg_mention_tenant ON kg_mention (tenant_id);
            CREATE INDEX IF NOT EXISTS kg_mention_doc ON kg_mention (tenant_id, source_document_id);
            CREATE INDEX IF NOT EXISTS kg_mention_name ON kg_mention (tenant_id, name);
            """,
            reverse_sql="""
            DROP TABLE IF EXISTS kg_mention;
            DROP TABLE IF EXISTS kg_text_unit;
            DROP TABLE IF EXISTS kg_same_as;
            DROP TABLE IF EXISTS kg_relation;
            DROP TABLE IF EXISTS kg_graph_meta;
            """,
        ),
    ]
