import uuid
from typing import TYPE_CHECKING
from django.db import models
from apps.chat.models import ChatSession


class Escalation(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CLAIMED = "claimed"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    TRIGGER_AI = "ai"
    TRIGGER_VISITOR = "visitor"
    TRIGGER_AGENT = "agent"  # 상담원이 임의 세션을 직접 잡은 수동 takeover (issue 140)
    TRIGGER_CHOICES = [
        (TRIGGER_AI, "AI"),
        (TRIGGER_VISITOR, "Visitor"),
        (TRIGGER_AGENT, "Agent"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="escalations")
    if TYPE_CHECKING:
        session_id: uuid.UUID  # FK _id 접근자 — django-types가 추론 못 함
    trigger_type = models.CharField(max_length=10, choices=TRIGGER_CHOICES)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "escalations"


class EscalationClaim(models.Model):
    escalation = models.OneToOneField(Escalation, on_delete=models.CASCADE, related_name="claim")
    claimed_by = models.CharField(max_length=150)
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "escalation_claims"
