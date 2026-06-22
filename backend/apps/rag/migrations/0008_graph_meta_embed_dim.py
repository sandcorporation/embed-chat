"""kg_graph_meta에 embed_dim 추적 컬럼 추가 (PRD-pgvector-graphstore, issue 167).

벡터 테이블은 임베딩 길이로 라우팅하되(config 아님 — Neo4j의 명시 차원 동작과 동일), 임베딩 없는
read(mention_embeddings 등)가 테넌트의 현 차원을 알 수 있도록 데이터에 차원을 기록한다.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rag", "0007_graphstore_metadata_tables"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE kg_graph_meta ADD COLUMN IF NOT EXISTS embed_dim int;",
            reverse_sql="ALTER TABLE kg_graph_meta DROP COLUMN IF EXISTS embed_dim;",
        ),
    ]
