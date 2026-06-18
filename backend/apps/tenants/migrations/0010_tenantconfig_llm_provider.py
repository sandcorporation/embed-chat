from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0009_tenantconfig_brand_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="llm_provider_type",
            field=models.CharField(max_length=20, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="llm_base_url",
            field=models.CharField(max_length=500, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="llm_api_key",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="extraction_model",
            field=models.CharField(max_length=255, blank=True, default=""),
        ),
    ]
