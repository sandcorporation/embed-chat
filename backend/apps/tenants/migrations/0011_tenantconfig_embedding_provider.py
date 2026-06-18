from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0010_tenantconfig_llm_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="embed_provider_type",
            field=models.CharField(max_length=20, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="embed_base_url",
            field=models.CharField(max_length=500, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="embed_api_key",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="embed_model",
            field=models.CharField(max_length=255, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="embed_dim",
            field=models.IntegerField(default=1024),
        ),
    ]
