import uuid

import pytest

from apps.usage.models import TokenUsage
from apps.usage.recording import record_usage


@pytest.mark.django_db
def test_record_usage_increments_rollup():
    """같은 키로 여러 번 기록하면 토큰·count가 누적된다(원자적 upsert)."""
    tid = uuid.uuid4()
    record_usage(tid, TokenUsage.CALL_CHAT, "gpt-4o-mini", input_tokens=10, output_tokens=5)
    record_usage(tid, TokenUsage.CALL_CHAT, "gpt-4o-mini", input_tokens=20, output_tokens=7)

    row = TokenUsage.objects.get(tenant_id=tid, call_type="chat", model="gpt-4o-mini")
    assert row.input_tokens == 30
    assert row.output_tokens == 12
    assert row.total_tokens == 42
    assert row.request_count == 2


@pytest.mark.django_db
def test_record_usage_isolates_by_key():
    """키(tenant·call_type·model)별로 격리 — 다른 키에 영향 없음."""
    a, b = uuid.uuid4(), uuid.uuid4()
    record_usage(a, TokenUsage.CALL_CHAT, "m1", input_tokens=10)
    record_usage(b, TokenUsage.CALL_CHAT, "m1", input_tokens=99)
    record_usage(a, TokenUsage.CALL_EMBEDDING, "m2", input_tokens=3)

    assert TokenUsage.objects.get(tenant_id=a, call_type="chat", model="m1").input_tokens == 10
    assert TokenUsage.objects.get(tenant_id=b, call_type="chat", model="m1").input_tokens == 99
    assert TokenUsage.objects.get(tenant_id=a, call_type="embedding", model="m2").input_tokens == 3
    assert TokenUsage.objects.count() == 3
