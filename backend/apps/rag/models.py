import uuid
from django.db import models


class Document(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default=STATUS_PENDING)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "documents"
        indexes = [
            models.Index(fields=["tenant_id"]),
        ]
