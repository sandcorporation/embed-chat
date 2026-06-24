import uuid

import pytest

from apps.usage.models import TokenUsage
from apps.usage.recording import record_usage, record_embedding_usage


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


@pytest.mark.django_db
def test_callback_records_usage_from_langchain_response():
    """UsageRecordingCallback이 langchain 응답의 usage_metadata를 UsageContext 귀속으로 기록한다."""
    from langchain_core.outputs import LLMResult, ChatGeneration
    from langchain_core.messages import AIMessage
    from apps.usage.context import set_usage_context
    from apps.usage.instrument import UsageRecordingCallback

    tid = uuid.uuid4()
    set_usage_context(tid, TokenUsage.CALL_CHAT, session_id="s1")

    msg = AIMessage(content="안녕", usage_metadata={"input_tokens": 12, "output_tokens": 8, "total_tokens": 20})
    result = LLMResult(generations=[[ChatGeneration(message=msg)]], llm_output={"model_name": "gpt-4o-mini"})
    UsageRecordingCallback().on_llm_end(result)

    row = TokenUsage.objects.get(tenant_id=tid, call_type="chat", model="gpt-4o-mini")
    assert (row.input_tokens, row.output_tokens, row.total_tokens, row.request_count) == (12, 8, 20, 1)


@pytest.mark.django_db
def test_callback_noop_without_context():
    """UsageContext가 없으면(테넌트 미상) 기록하지 않는다(안전)."""
    from langchain_core.outputs import LLMResult, ChatGeneration
    from langchain_core.messages import AIMessage
    from apps.usage.context import _current
    from apps.usage.instrument import UsageRecordingCallback

    _current.set(None)
    msg = AIMessage(content="x", usage_metadata={"input_tokens": 5, "output_tokens": 1, "total_tokens": 6})
    UsageRecordingCallback().on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]))
    assert TokenUsage.objects.count() == 0


@pytest.mark.django_db
def test_record_embedding_usage_from_response():
    """OpenAI-호환 임베딩 응답의 usage를 embedding 사용량으로 기록(없으면 생략)."""
    tid = uuid.uuid4()
    record_embedding_usage({"usage": {"prompt_tokens": 42, "total_tokens": 42}}, tid, "text-embedding-3-small")
    row = TokenUsage.objects.get(tenant_id=tid, call_type="embedding")
    assert row.total_tokens == 42 and row.request_count == 1

    record_embedding_usage({}, tid, "text-embedding-3-small")   # usage 없음 → 생략
    assert TokenUsage.objects.filter(tenant_id=tid, call_type="embedding").count() == 1


@pytest.mark.django_db
def test_tenant_usage_endpoint_returns_only_own(client, tenant_with_key, tenant_agent_token):
    """테넌트 usage 엔드포인트는 자기 데이터만(다른 테넌트 0)."""
    tenant, _ = tenant_with_key
    other = uuid.uuid4()
    record_usage(tenant.id, "chat", "gpt-4o-mini", input_tokens=10, output_tokens=5)
    record_usage(tenant.id, "embedding", "text-embedding-3-small", input_tokens=7)
    record_usage(other, "chat", "gpt-4o-mini", input_tokens=999)  # 다른 테넌트 — 보이면 안 됨

    resp = client.get("/api/tenant/usage/", HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tokens"] == 15 + 7
    call_types = {b["call_type"] for b in data["by_call_type"]}
    assert call_types == {"chat", "embedding"}


@pytest.mark.django_db
def test_operator_usage_endpoint_returns_all_tenants(client, tenant_with_key, operator_token):
    """오퍼레이터 usage 엔드포인트는 전체 테넌트를 테넌트별로 집계."""
    tenant, _ = tenant_with_key
    other = uuid.uuid4()
    record_usage(tenant.id, "chat", "m", input_tokens=10, output_tokens=5)
    record_usage(other, "chat", "m", input_tokens=20, output_tokens=0)

    resp = client.get("/api/operator/usage/", HTTP_AUTHORIZATION=f"Bearer {operator_token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tokens"] == 35
    tids = {row["tenant_id"] for row in data["by_tenant"]}
    assert str(tenant.id) in tids and str(other) in tids


@pytest.mark.django_db
def test_tenant_usage_requires_auth(client):
    """인증 없으면 401."""
    assert client.get("/api/tenant/usage/").status_code == 401
