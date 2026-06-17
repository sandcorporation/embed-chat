from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0003_tenantconfig_hitl_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="welcome_message",
            field=models.TextField(blank=True, default=""),
        ),
    ]
