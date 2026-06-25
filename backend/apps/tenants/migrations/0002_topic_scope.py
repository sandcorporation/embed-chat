from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="topic_scope_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tenantconfig",
            name="scope_description",
            field=models.TextField(blank=True, default=""),
        ),
    ]
