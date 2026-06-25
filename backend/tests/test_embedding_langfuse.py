"""임베딩→Langfuse 계측 (PRD-embedding-langfuse-observability, issue 203).

임베딩 호출마다 Langfuse generation을 발행한다(LLM과 대칭). Langfuse는 비결정 외부 경계라 Fake
client로 교체해 발행 payload를 검증한다(CLAUDE.md). TokenUsage(DB)는 실제로 검증한다.
"""
import pytest


class _FakeGen:
    def end(self):
        pass

    def update(self, **kw):
        pass


class _FakeLangfuse:
    def __init__(self):
        self.generations = []

    def start_generation(self, **kw):
        self.generations.append(kw)
        return _FakeGen()


class _RaisingLangfuse:
    def start_generation(self, **kw):
        raise RuntimeError("langfuse down")


_RESP = {"data": [{"embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 7, "total_tokens": 7}}


def test_records_generation_with_model_tokens_and_tenant(monkeypatch):
    from apps.usage import langfuse_client

    fake = _FakeLangfuse()
    monkeypatch.setattr(langfuse_client, "get_langfuse_client", lambda: fake)
    langfuse_client.record_embedding_langfuse(
        _RESP, "tnt-1", "text-embedding-3-small", ["안녕"], call_type="embedding")

    assert len(fake.generations) == 1
    g = fake.generations[0]
    assert g["name"] == "embedding"
    assert g["model"] == "text-embedding-3-small"
    assert g["usage_details"] == {"input": 7}
    assert g["metadata"]["tenant_id"] == "tnt-1"
    assert g["metadata"]["call_type"] == "embedding"


def test_noop_when_langfuse_disabled(monkeypatch):
    from apps.usage import langfuse_client

    monkeypatch.setattr(langfuse_client, "get_langfuse_client", lambda: None)
    # 예외 없이 조용히 통과(발행 대상 없음)
    langfuse_client.record_embedding_langfuse(_RESP, "tnt-1", "m", ["x"])


def test_exception_safe_does_not_propagate(monkeypatch):
    from apps.usage import langfuse_client

    monkeypatch.setattr(langfuse_client, "get_langfuse_client", lambda: _RaisingLangfuse())
    # Fake가 던져도 호출자에게 전파되지 않는다(best-effort)
    langfuse_client.record_embedding_langfuse(_RESP, "tnt-1", "m", ["x"])


def test_input_masked_when_capture_content_off(monkeypatch):
    from apps.usage import langfuse_client

    fake = _FakeLangfuse()
    monkeypatch.setattr(langfuse_client, "get_langfuse_client", lambda: fake)
    monkeypatch.setattr(langfuse_client, "_capture_content", lambda: False)
    langfuse_client.record_embedding_langfuse(_RESP, "tnt-1", "m", ["민감한 텍스트"])

    g = fake.generations[0]
    assert "민감한 텍스트" not in str(g["input"])


@pytest.mark.django_db
def test_get_embeddings_emits_both_sinks(monkeypatch, tenant_with_key):
    """get_embeddings 1회 → TokenUsage 1행 + Langfuse generation 1개(이중 sink)."""
    import httpx
    from apps.usage import langfuse_client
    from apps.usage.context import set_usage_context
    from apps.usage.models import TokenUsage
    from apps.rag.ingesters import get_embeddings

    tenant, _ = tenant_with_key

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.1]}], "usage": {"prompt_tokens": 5, "total_tokens": 5}}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())
    fake = _FakeLangfuse()
    monkeypatch.setattr(langfuse_client, "get_langfuse_client", lambda: fake)

    set_usage_context(str(tenant.id), "chat")
    get_embeddings(["테스트 문장"])  # provider=None → 플랫폼 기본(httpx mock으로 결정적)

    assert TokenUsage.objects.filter(tenant_id=tenant.id, call_type="embedding").count() == 1
    assert len(fake.generations) == 1
    assert fake.generations[0]["usage_details"] == {"input": 5}
