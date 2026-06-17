import uuid
from django.db import models
from pgvector.django import VectorField


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


class DocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    tenant_id = models.UUIDField()
    content = models.TextField()
    embedding = VectorField(dimensions=1024)
    chunk_index = models.IntegerField(default=0)

    class Meta:
        db_table = "document_chunks"
        indexes = [
            models.Index(fields=["tenant_id"]),
        ]
