"""GraphStore pg 백엔드: 차원 무관 메타데이터 테이블 (PRD-pgvector-graphstore, issue 165).

가변 임베딩 차원을 다루기 위해 메타데이터(content·name, 차원 무관)와 임베딩(차원별 vector 테이블)을
분리한다. 임베딩 차원이 바뀌어도(reembed) 메타데이터는 보존되고, 임베딩만 새 차원 vec 테이블로
재기록한다. vec 테이블(kg_*_vec_d{dim})은 런타임에 IF NOT EXISTS로 생성된다.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rag", "0006_graphstore_pgvector"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
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
            """,
        ),
    ]
