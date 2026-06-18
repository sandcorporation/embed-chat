from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0007_tenantconfig_require_identity_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="hitl_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
