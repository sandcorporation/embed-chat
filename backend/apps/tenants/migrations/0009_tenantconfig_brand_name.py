from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0008_tenantconfig_hitl_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="brand_name",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
    ]
