"""Langfuse 연동 (가드형) — env 설정 시에만 langchain CallbackHandler를 제공한다.

LANGFUSE_PUBLIC_KEY/SECRET_KEY 미설정이면 None을 반환해 dev/test에선 완전 no-op이다(외부 경계라
테스트는 Langfuse를 치지 않는다). 본문 캡처는 LANGFUSE_CAPTURE_CONTENT(기본 on)로 끈다 — off면
입력/출력을 마스킹한다. import·생성 실패도 no-op으로 흡수한다(배포 환경 차이에 견고).
"""
import functools
import os


def langfuse_enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def _capture_content() -> bool:
    return os.environ.get("LANGFUSE_CAPTURE_CONTENT", "true").lower() == "true"


@functools.lru_cache(maxsize=1)
def get_langfuse_handler():
    """설정됐으면 Langfuse langchain CallbackHandler를, 아니면 None을 반환(캐시)."""
    if not langfuse_enabled():
        return None
    try:
        if not _capture_content():
            # 본문 캡처 off — 전역 클라이언트에 마스크를 걸어 입력/출력을 가린다(킬스위치).
            try:
                from langfuse import Langfuse
                Langfuse(mask=lambda data=None, **_: "[REDACTED]")
            except Exception:
                pass
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception:
        return None


@functools.lru_cache(maxsize=1)
def get_langfuse_client():
    """Langfuse v3 클라이언트(싱글톤) — 설정 시 인스턴스, 아니면 None. import·생성 실패는 no-op로 흡수.

    임베딩은 httpx 직접 호출이라 langchain 콜백이 못 잡는다(ADR/PRD-embedding-langfuse). 그래서
    이 클라이언트로 generation을 수동 발행한다. LLM 트레이스와 같은 전역 클라이언트라 flush를 공유한다.
    """
    if not langfuse_enabled():
        return None
    try:
        from langfuse import Langfuse
        return Langfuse()
    except Exception:
        return None


def record_embedding_langfuse(resp_json: dict, tenant_id, model: str, inputs, call_type: str = "embedding") -> None:
    """임베딩 응답을 Langfuse generation으로 발행한다(LLM 호출과 대칭, deep module).

    미설정/무tenant면 no-op, 발행 예외는 흡수한다(임베딩/인제스션/chat를 절대 안 깸 — best-effort).
    토큰은 응답 usage(provider 실측)에서 읽고, 입력 텍스트는 LANGFUSE_CAPTURE_CONTENT off면 마스킹한다.
    """
    if not tenant_id:
        return
    client = get_langfuse_client()
    if client is None:
        return
    try:
        usage = (resp_json or {}).get("usage") or {}
        total = int(usage.get("total_tokens") or usage.get("prompt_tokens") or 0)
        payload_input = inputs if _capture_content() else "[REDACTED]"
        gen = client.start_generation(
            name="embedding",
            model=model,
            input=payload_input,
            usage_details={"input": total},
            metadata={"tenant_id": str(tenant_id), "call_type": call_type},
        )
        gen.end()
    except Exception:
        pass
