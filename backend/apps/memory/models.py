import uuid
from django.db import models


class VisitorMemory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    visitor_id = models.CharField(max_length=255)
    key = models.CharField(max_length=255)
    value = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "visitor_memories"
        unique_together = [("tenant_id", "visitor_id", "key")]
        indexes = [
            models.Index(fields=["tenant_id", "visitor_id"]),
        ]
