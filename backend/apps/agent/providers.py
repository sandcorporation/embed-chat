"""ProviderResolver (deep module).

Tenant provider 설정(타입·base_url·키·model)을 LLM 클라이언트로 해석한다(ADR-0012).
타입 분기: openai/custom → OpenAI-호환 클라이언트, anthropic → Anthropic 네이티브.
LLM 경계가 전역 settings 대신 이 리졸버로 per-Tenant 클라이언트를 얻는다.
"""
import contextvars
from dataclasses import dataclass

PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_CUSTOM = "custom"


@dataclass
class LLMProvider:
    type: str          # openai | anthropic | custom | "" (플랫폼 기본)
    model: str
    base_url: str = ""
    api_key: str = ""


def build_llm_client(provider: LLMProvider):
    if provider.type == PROVIDER_ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=provider.model, api_key=provider.api_key or None)

    # openai / custom / "" → OpenAI-호환
    from langchain_openai import ChatOpenAI

    kwargs = {"model": provider.model}
    if provider.api_key:
        kwargs["api_key"] = provider.api_key
    if provider.base_url:
        kwargs["base_url"] = provider.base_url
    # 플랫폼 기본(OpenRouter)은 구조화 출력 시 provider가 파라미터를 강제 준수하게 한다.
    if provider.type == "":
        kwargs["extra_body"] = {"provider": {"require_parameters": True}}
    return ChatOpenAI(**kwargs)


def _provider_from_config(config, model: str) -> LLMProvider:
    """TenantConfig + 모델명 → LLMProvider. type이 비면 플랫폼 기본(OpenRouter)으로 폴백."""
    if config.llm_provider_type:
        from apps.tenants.crypto import decrypt_secret

        return LLMProvider(
            type=config.llm_provider_type,
            model=model,
            base_url=config.llm_base_url,
            api_key=decrypt_secret(config.llm_api_key),
        )
    from django.conf import settings

    return LLMProvider(
        type="", model=model,
        base_url=settings.OPEN_ROUTER_BASE_URL, api_key=settings.OPEN_ROUTER_API_KEY,
    )


def chat_provider(config) -> LLMProvider:
    """챗·메모리용 LLM provider (모델 = config.model_id)."""
    return _provider_from_config(config, config.model_id)


# 챗 그래프 노드가 쓸 chat provider를 흘리는 contextvar. 비밀키를 LangGraph state에
# 넣으면 Checkpoint(Postgres)에 영속되므로, state 대신 호출 컨텍스트로 전달한다.
_current_chat_provider = contextvars.ContextVar("chat_provider", default=None)


def set_chat_provider(provider: LLMProvider) -> None:
    _current_chat_provider.set(provider)


def get_chat_provider():
    return _current_chat_provider.get()


def extraction_provider(config) -> LLMProvider:
    """GraphRAG 추출용 LLM provider (모델 = extraction_model 또는 플랫폼 기본)."""
    from django.conf import settings

    return _provider_from_config(config, config.extraction_model or settings.GRAPH_EXTRACTION_MODEL)
