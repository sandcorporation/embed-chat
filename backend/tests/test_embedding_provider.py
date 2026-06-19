import pytest


# ── Issue 93: get_embeddings를 OpenAI-호환 /v1/embeddings로 ───────────────────

def test_get_embeddings_uses_provider_v1_endpoint():
    """get_embeddings가 EmbeddingProvider의 OpenAI-호환 /v1/embeddings로 임베딩을 얻는다."""
    from django.conf import settings
    from apps.rag.ingesters import get_embeddings
    from apps.agent.providers import EmbeddingProvider

    prov = EmbeddingProvider(
        type="custom",
        base_url=f"{settings.OLLAMA_BASE_URL}/v1",
        api_key="ollama",
        model=settings.OLLAMA_EMBED_MODEL,
        dim=1024,
    )
    embs = get_embeddings(["hello world"], provider=prov)
    assert len(embs) == 1
    assert len(embs[0]) == 1024  # bge-m3 차원


def test_get_embeddings_default_platform_still_works():
    """provider 미지정 시 플랫폼 기본(ollama /v1)으로 동작한다(기존 호출부 호환)."""
    from apps.rag.ingesters import get_embeddings

    embs = get_embeddings(["another text"])
    assert len(embs[0]) == 1024


@pytest.mark.django_db
def test_embedding_provider_independent_config_key_encrypted(client, tenant_agent_token, tenant_with_key):
    """Embedding Provider는 LLM과 독립 설정되고, 키는 암호화·마스킹된다."""
    from apps.tenants.models import TenantConfig
    from apps.tenants.crypto import decrypt_secret
    from apps.agent.providers import embedding_provider

    tenant, _ = tenant_with_key
    r = client.patch(
        "/api/tenant/config/",
        {
            "embed_provider_type": "openai",
            "embed_base_url": "https://api.openai.com/v1",
            "embed_api_key": "sk-embed-secret",
            "embed_model": "text-embedding-3-small",
            "embed_dim": 1536,
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert r.status_code == 200

    g = client.get("/api/tenant/config/", HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}").json()
    assert g["embed_provider_type"] == "openai"
    assert g["embed_dim"] == 1536
    assert g["embed_api_key"] != "sk-embed-secret"  # 마스킹

    config = TenantConfig.objects.get(tenant=tenant)
    assert decrypt_secret(config.embed_api_key) == "sk-embed-secret"

    ep = embedding_provider(config)
    assert ep.type == "openai" and ep.model == "text-embedding-3-small" and ep.dim == 1536
    assert ep.api_key == "sk-embed-secret"  # 복호화 전달


@pytest.mark.django_db
def test_embedding_provider_dev_fallback_and_prod_required(tenant_with_key, settings):
    """미설정 시 dev는 ollama 폴백, prod(폴백 비활성)는 Tenant 설정을 강제(거부)."""
    from apps.tenants.models import TenantConfig
    from apps.agent.providers import embedding_provider

    tenant, _ = tenant_with_key
    config = TenantConfig.objects.get(tenant=tenant)  # embed provider 미설정

    settings.PLATFORM_DEFAULT_PROVIDERS_ENABLED = True
    assert embedding_provider(config).type == ""  # dev 폴백(ollama)

    settings.PLATFORM_DEFAULT_PROVIDERS_ENABLED = False
    with pytest.raises(ValueError):
        embedding_provider(config)  # prod는 거부
