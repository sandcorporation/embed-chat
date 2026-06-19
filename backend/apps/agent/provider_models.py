"""ProviderModels (deep module) — provider API에서 모델 목록 조회 + 연결 검증 (issue 114).

provider HTTP는 외부 경계다. 타입별로 모델 목록 엔드포인트를 정규화하고, 저장 전 연결을
provider의 실제 기능 호출로 검증한다(ADR-0012 확장).
"""
import httpx

DEFAULT_TIMEOUT = 15.0
ANTHROPIC_DEFAULT_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"


class ProviderError(Exception):
    """provider 조회·검증 실패(연결 불가·키 오류 등). 사람이 읽는 메시지."""


def _ollama_tags(base_url: str) -> list[str]:
    # 플랫폼 기본 임베딩(dev ollama)은 /api/tags. base_url 끝의 /v1를 떼어낸다.
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    r = httpx.get(f"{base}/api/tags", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def _anthropic_models(base_url: str, api_key: str) -> list[str]:
    r = httpx.get(
        f"{(base_url or ANTHROPIC_DEFAULT_BASE).rstrip('/')}/models",
        headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
        timeout=DEFAULT_TIMEOUT,
    )
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


def _openai_models(base_url: str, api_key: str) -> list[str]:
    r = httpx.get(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key or 'x'}"},
        timeout=DEFAULT_TIMEOUT,
    )
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


def list_provider_models(kind: str, type: str, base_url: str, api_key: str) -> list[str]:
    """provider의 모델 id 목록을 정규화해 반환한다. 실패 시 ProviderError.

    type="" 플랫폼 기본은 kind로 분기한다: embed→ollama /api/tags, llm→OpenRouter /models.
    """
    try:
        if type == "anthropic":
            return _anthropic_models(base_url, api_key)
        if type == "" and kind == "embed":
            return _ollama_tags(base_url)
        # openai / custom / "" (llm, OpenAI-호환) → /models
        return _openai_models(base_url, api_key)
    except httpx.HTTPError as e:
        raise ProviderError(f"모델 조회 실패: {e}") from e


def validate_provider(kind: str, type: str, base_url: str, api_key: str, model: str) -> None:
    """provider 연결을 실제 기능 호출로 검증한다. 실패 시 ProviderError.

    kind=embed는 1-텍스트 임베딩 호출(provider 실제 용도), kind=llm은 모델 목록 조회로
    연결+키를 확인한다. 특정 model 상장 여부는 강제하지 않는다(연결성만 검증).
    """
    if kind == "embed":
        try:
            r = httpx.post(
                f"{base_url.rstrip('/')}/embeddings",
                json={"model": model, "input": ["ok"]},
                headers={"Authorization": f"Bearer {api_key or 'x'}"},
                timeout=DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"임베딩 Provider 검증 실패: {e}") from e
        return
    # llm → 목록 조회 성공으로 연결 검증(실패 시 ProviderError 전파)
    list_provider_models(kind, type, base_url, api_key)
