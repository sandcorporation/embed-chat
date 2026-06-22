import uuid
from typing import TYPE_CHECKING
from django.db import models

if TYPE_CHECKING:
    from apps.escalation.models import Escalation


class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    visitor_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_hitl = models.BooleanField(default=False)

    # 역참조 매니저(related_name) — django-types는 역참조를 추론하지 못하므로 명시 주석한다.
    if TYPE_CHECKING:
        messages: "models.Manager[ChatMessage]"
        escalations: "models.Manager[Escalation]"

    class Meta:
        db_table = "chat_sessions"
        indexes = [
            models.Index(fields=["tenant_id", "visitor_id"]),
        ]


class ChatMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_HUMAN_AGENT = "human_agent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at"]
