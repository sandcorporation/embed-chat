from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("chat", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Escalation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("trigger_type", models.CharField(choices=[("ai", "AI"), ("visitor", "Visitor")], max_length=10)),
                ("reason", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("claimed", "Claimed"), ("resolved", "Resolved")], default="pending", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="escalations", to="chat.chatsession")),
            ],
            options={"db_table": "escalations"},
        ),
        migrations.CreateModel(
            name="EscalationClaim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("claimed_by", models.CharField(max_length=150)),
                ("claimed_at", models.DateTimeField(auto_now_add=True)),
                ("escalation", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="claim", to="escalation.escalation")),
            ],
            options={"db_table": "escalation_claims"},
        ),
    ]
