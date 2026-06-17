from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_tenant_agent"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="agent_display_name",
            field=models.CharField(default="상담원", max_length=100),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="webhook_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="webhook_type",
            field=models.CharField(blank=True, choices=[("slack", "Slack"), ("discord", "Discord"), ("generic", "Generic")], default="", max_length=10),
        ),
    ]
