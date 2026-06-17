from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="VisitorMemory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField()),
                ("visitor_id", models.CharField(max_length=255)),
                ("key", models.CharField(max_length=255)),
                ("value", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "visitor_memories"},
        ),
        migrations.AlterUniqueTogether(
            name="visitormemory",
            unique_together={("tenant_id", "visitor_id", "key")},
        ),
        migrations.AddIndex(
            model_name="visitormemory",
            index=models.Index(fields=["tenant_id", "visitor_id"], name="mem_tenant_visitor_idx"),
        ),
    ]
