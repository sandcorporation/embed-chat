"""이벤트 저장 모델 (issue 143).

event_store = 영구 append-only 감사(삭제·published 없음). outbox = 전송 큐(relay가 발행 후
prune). 상태 전이 트랜잭션에서 record_event가 둘 다 기록해 dual-write를 없앤다(PRD).
"""
import uuid
from django.db import models


class EventStore(models.Model):
    """HITL/세션 라이프사이클 도메인 이벤트의 영구 감사 기록."""
    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=64)  # session_id
    tenant_id = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    schema_version = models.IntegerField(default=1)
    payload = models.JSONField(default=dict)

    class Meta:
        db_table = "event_store"
        indexes = [
            models.Index(fields=["aggregate_id", "id"]),
            models.Index(fields=["tenant_id", "id"]),
        ]


class Outbox(models.Model):
    """발행 대기 이벤트(자기완결 봉투). relay가 발행 성공 후 prune한다."""
    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(unique=True)
    topic = models.CharField(max_length=100)
    key = models.CharField(max_length=64)
    envelope = models.JSONField()
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_outbox"
        indexes = [
            # 미발행 행만 인덱싱(relay 드레인 조회용 부분 인덱스).
            models.Index(
                fields=["id"], name="outbox_unpublished_idx",
                condition=models.Q(published_at__isnull=True),
            ),
        ]


class ProcessedEvent(models.Model):
    """소비자 멱등(at-least-once 중복 방지) — (consumer_group, event_id) 유일 (issue 145)."""
    id = models.BigAutoField(primary_key=True)
    consumer_group = models.CharField(max_length=100)
    event_id = models.UUIDField()
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_processed"
        constraints = [
            models.UniqueConstraint(fields=["consumer_group", "event_id"], name="uq_processed_group_event"),
        ]
