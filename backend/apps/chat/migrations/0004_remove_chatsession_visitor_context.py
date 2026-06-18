from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0003_rename_chat_sess_tenant_visitor_idx_chat_sessio_tenant__f3ac56_idx"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="chatsession",
            name="visitor_context",
        ),
    ]
