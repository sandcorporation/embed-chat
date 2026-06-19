"""Issue 114 — ProviderModels 딥모듈(모델 조회 + 기능호출 검증).

provider HTTP는 외부 경계이므로 결정적 Fake로 교체한다(CLAUDE.md). DB 불필요.
"""
import pytest


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=None)


# ── Tracer: OpenAI-호환 /models ───────────────────────────────────────────────

def test_list_openai_compatible_models(monkeypatch):
    from apps.agent import provider_models

    def fake_get(url, headers=None, timeout=None):
        assert url.endswith("/models")
        assert headers["Authorization"] == "Bearer sk-x"
        return _FakeResp(200, {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]})

    monkeypatch.setattr(provider_models.httpx, "get", fake_get)

    models = provider_models.list_provider_models("llm", "openai", "https://api.openai.com/v1", "sk-x")
    assert models == ["gpt-4o", "gpt-4o-mini"]


def test_list_anthropic_models(monkeypatch):
    from apps.agent import provider_models

    def fake_get(url, headers=None, timeout=None):
        assert "anthropic" in url and url.endswith("/models")
        assert headers["x-api-key"] == "sk-ant"
        assert headers["anthropic-version"]
        return _FakeResp(200, {"data": [{"id": "claude-opus-4"}, {"id": "claude-haiku"}]})

    monkeypatch.setattr(provider_models.httpx, "get", fake_get)
    models = provider_models.list_provider_models("llm", "anthropic", "", "sk-ant")
    assert models == ["claude-opus-4", "claude-haiku"]


def test_list_ollama_tags_for_platform_embed(monkeypatch):
    from apps.agent import provider_models

    def fake_get(url, headers=None, timeout=None):
        assert url.endswith("/api/tags")  # /v1 떼고 /api/tags
        return _FakeResp(200, {"models": [{"name": "bge-m3"}, {"name": "nomic-embed"}]})

    monkeypatch.setattr(provider_models.httpx, "get", fake_get)
    models = provider_models.list_provider_models("embed", "", "http://ollama:11434/v1", "ollama")
    assert models == ["bge-m3", "nomic-embed"]


def test_list_models_raises_provider_error_on_failure(monkeypatch):
    from apps.agent import provider_models

    def fake_get(url, headers=None, timeout=None):
        return _FakeResp(401, {})  # 키 오류

    monkeypatch.setattr(provider_models.httpx, "get", fake_get)
    with pytest.raises(provider_models.ProviderError):
        provider_models.list_provider_models("llm", "openai", "https://api.openai.com/v1", "bad")


def test_validate_llm_uses_model_list(monkeypatch):
    from apps.agent import provider_models

    calls = {"get": 0}

    def fake_get(url, headers=None, timeout=None):
        calls["get"] += 1
        return _FakeResp(200, {"data": [{"id": "m"}]})

    monkeypatch.setattr(provider_models.httpx, "get", fake_get)
    provider_models.validate_provider("llm", "openai", "https://x/v1", "sk", "m")  # 통과
    assert calls["get"] == 1

    def fail_get(url, headers=None, timeout=None):
        return _FakeResp(403, {})

    monkeypatch.setattr(provider_models.httpx, "get", fail_get)
    with pytest.raises(provider_models.ProviderError):
        provider_models.validate_provider("llm", "openai", "https://x/v1", "bad", "m")


def test_validate_embed_uses_real_embedding_call(monkeypatch):
    from apps.agent import provider_models

    def fake_post(url, json=None, headers=None, timeout=None):
        assert url.endswith("/embeddings")
        assert json["input"] == ["ok"]
        return _FakeResp(200, {"data": [{"embedding": [0.1]}]})

    monkeypatch.setattr(provider_models.httpx, "post", fake_post)
    provider_models.validate_provider("embed", "openai", "https://x/v1", "sk", "text-embedding-3-small")

    def fail_post(url, json=None, headers=None, timeout=None):
        return _FakeResp(401, {})

    monkeypatch.setattr(provider_models.httpx, "post", fail_post)
    with pytest.raises(provider_models.ProviderError):
        provider_models.validate_provider("embed", "openai", "https://x/v1", "bad", "m")
