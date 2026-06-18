from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0005_alter_operator_managers_alter_operator_date_joined_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="slug",
            field=models.CharField(max_length=63, null=True, blank=True, unique=True),
        ),
    ]
