from django.db import migrations, models
import django.db.models.deletion
import pgvector.django
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS vector;"),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField()),
                ("name", models.CharField(max_length=255)),
                ("mime_type", models.CharField(max_length=100)),
                ("status", models.CharField(default="pending", max_length=20)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "documents"},
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["tenant_id"], name="doc_tenant_idx"),
        ),
        migrations.CreateModel(
            name="DocumentChunk",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="rag.document")),
                ("tenant_id", models.UUIDField()),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(dimensions=384)),
                ("chunk_index", models.IntegerField(default=0)),
            ],
            options={"db_table": "document_chunks"},
        ),
        migrations.AddIndex(
            model_name="documentchunk",
            index=models.Index(fields=["tenant_id"], name="chunk_tenant_idx"),
        ),
    ]
