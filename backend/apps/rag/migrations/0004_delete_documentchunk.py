from django.db import migrations


class Migration(migrations.Migration):
    """GraphRAG 전환: 벡터 청크(DocumentChunk)를 제거한다.

    임베딩은 Neo4j 벡터 인덱스(Text Unit)로 이전됨 (ADR-0007).
    """

    dependencies = [
        ("rag", "0003_rename_doc_tenant_idx_documents_tenant__ad8c7d_idx_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="DocumentChunk"),
    ]
