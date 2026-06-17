from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ChatSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField()),
                ("visitor_id", models.CharField(max_length=255)),
                ("visitor_context", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "chat_sessions"},
        ),
        migrations.AddIndex(
            model_name="chatsession",
            index=models.Index(fields=["tenant_id", "visitor_id"], name="chat_sess_tenant_visitor_idx"),
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="chat.chatsession")),
                ("role", models.CharField(max_length=20)),
                ("content", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "chat_messages", "ordering": ["created_at"]},
        ),
    ]
