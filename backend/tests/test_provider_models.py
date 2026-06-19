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


# ── 엔드포인트 POST /api/tenant/providers/models (issue 115) ───────────────────

def _patch_get(monkeypatch, payload, status=200, capture=None):
    from apps.agent import provider_models

    def fake_get(url, headers=None, timeout=None):
        if capture is not None:
            capture["headers"] = headers or {}
        return _FakeResp(status, payload)

    monkeypatch.setattr(provider_models.httpx, "get", fake_get)


@pytest.mark.django_db
def test_provider_models_endpoint_returns_models(client, tenant_agent_token, monkeypatch):
    _patch_get(monkeypatch, {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]})
    resp = client.post(
        "/api/tenant/providers/models",
        {"kind": "llm", "type": "openai", "base_url": "https://api.openai.com/v1", "api_key": "sk-x"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["models"] == ["gpt-4o", "gpt-4o-mini"]
    assert "api_key" not in data and "sk-x" not in resp.content.decode()


@pytest.mark.django_db
def test_provider_models_endpoint_masked_key_uses_stored(client, tenant_agent_token, tenant_with_key, monkeypatch):
    from apps.tenants.models import TenantConfig
    from apps.tenants.crypto import encrypt_secret

    tenant, _ = tenant_with_key
    config = TenantConfig.objects.get(tenant=tenant)
    config.llm_api_key = encrypt_secret("real-stored-key")
    config.save()

    cap = {}
    _patch_get(monkeypatch, {"data": [{"id": "m"}]}, capture=cap)
    resp = client.post(
        "/api/tenant/providers/models",
        {"kind": "llm", "type": "openai", "base_url": "https://x/v1", "api_key": "********"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 200
    assert cap["headers"]["Authorization"] == "Bearer real-stored-key"


@pytest.mark.django_db
def test_provider_models_endpoint_failure_is_4xx(client, tenant_agent_token, monkeypatch):
    _patch_get(monkeypatch, {}, status=401)
    resp = client.post(
        "/api/tenant/providers/models",
        {"kind": "llm", "type": "openai", "base_url": "https://x/v1", "api_key": "bad"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


@pytest.mark.django_db
def test_provider_models_endpoint_requires_auth(client):
    resp = client.post(
        "/api/tenant/providers/models",
        {"kind": "llm", "type": "openai", "base_url": "https://x/v1", "api_key": "x"},
        content_type="application/json",
    )
    assert resp.status_code == 401


# ── update_config provider 검증 (issue 116) ──────────────────────────────────

def _patch_validate(monkeypatch, get_status=200, get_payload=None, counter=None):
    """provider HTTP(get/post)를 Fake로 — validate_provider가 이걸 친다."""
    from apps.agent import provider_models

    def fake_get(url, headers=None, timeout=None):
        if counter is not None:
            counter["n"] += 1
        return _FakeResp(get_status, get_payload if get_payload is not None else {"data": []})

    def fake_post(url, json=None, headers=None, timeout=None):
        if counter is not None:
            counter["n"] += 1
        return _FakeResp(get_status, {"data": [{"embedding": [0.1]}]})

    monkeypatch.setattr(provider_models.httpx, "get", fake_get)
    monkeypatch.setattr(provider_models.httpx, "post", fake_post)


def _patch_config(client, token, body):
    return client.patch(
        "/api/tenant/config/", body, content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


@pytest.mark.django_db
def test_update_config_rejects_invalid_provider(client, tenant_agent_token, monkeypatch):
    _patch_validate(monkeypatch, get_status=401)  # provider 연결 실패
    resp = _patch_config(client, tenant_agent_token, {
        "llm_provider_type": "openai", "llm_base_url": "https://x/v1", "llm_api_key": "bad-key",
    })
    assert resp.status_code == 400
    # 저장되지 않아야 한다(롤백)
    g = client.get("/api/tenant/config/", HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}").json()
    assert g["llm_provider_type"] == ""


@pytest.mark.django_db
def test_update_config_saves_when_provider_valid(client, tenant_agent_token, monkeypatch):
    _patch_validate(monkeypatch, get_status=200, get_payload={"data": [{"id": "m"}]})
    resp = _patch_config(client, tenant_agent_token, {
        "llm_provider_type": "openai", "llm_base_url": "https://x/v1", "llm_api_key": "sk-new",
    })
    assert resp.status_code == 200
    assert resp.json()["llm_provider_type"] == "openai"


@pytest.mark.django_db
def test_update_config_skips_validation_when_provider_unchanged(client, tenant_agent_token, monkeypatch):
    counter = {"n": 0}
    _patch_validate(monkeypatch, counter=counter)
    resp = _patch_config(client, tenant_agent_token, {"system_prompt": "새 프롬프트"})
    assert resp.status_code == 200
    assert counter["n"] == 0  # provider 미변경 → 검증(HTTP) 미호출
    assert resp.json()["system_prompt"] == "새 프롬프트"
