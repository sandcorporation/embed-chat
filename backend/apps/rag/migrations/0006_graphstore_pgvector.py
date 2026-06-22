"""GraphStore의 Postgres+pgvector 백엔드 정적 스키마 (PRD-pgvector-graphstore).

vector extension + 차원 무관 정적 공유 테이블(엣지·meta)을 만든다. 차원별 텍스트유닛/멘션
테이블·HNSW는 런타임에 IF NOT EXISTS로 생성된다(per-Tenant 차원 라우팅).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rag", "0005_document_source"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE EXTENSION IF NOT EXISTS vector;

            CREATE TABLE IF NOT EXISTS kg_graph_meta (
                tenant_id text PRIMARY KEY,
                freshness text
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
            """,
            reverse_sql="""
            DROP TABLE IF EXISTS kg_same_as;
            DROP TABLE IF EXISTS kg_relation;
            DROP TABLE IF EXISTS kg_graph_meta;
            """,
        ),
    ]
