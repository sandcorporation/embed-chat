"""LLM 호출 경계 (deep module).

per-Tenant Provider(ADR-0012)로 해석된 클라이언트를 통해 LLM에 접근한다. 호출부는 항상
이 모듈을 통하며, 단위 테스트는 이 경계를 결정적 Fake로 교체한다. 첫 인자는 LLMProvider다.
"""
from typing import TypeVar, cast

from pydantic import BaseModel

from apps.agent.providers import build_llm_client, PROVIDER_ANTHROPIC

T = TypeVar("T", bound=BaseModel)


def _mark_cache_breakpoint(provider, messages):
    """anthropic provider면 안정 system 블록 끝에 cache_control(ephemeral) 분기점을 주입한다.

    Anthropic은 명시적 마커가 필요하다 — 안정 prefix(tools+system)의 마지막 system 콘텐츠
    블록에 cache_control을 달면 그 앞(tool 스키마 포함)까지 캐시된다(issue 134). 콘텐츠를
    langchain_anthropic의 블록 리스트 형식([{"type":"text","text":...,"cache_control":...}])으로
    바꾼다. OpenAI/custom/플랫폼기본(OpenRouter)은 자동 prefix 캐싱이라 마커를 붙이지 않는다
    (붙이면 무효/오류). prefix가 provider 최소 임계 미만이면 캐시는 조용한 no-op이다.
    """
    from langchain_core.messages import SystemMessage

    if provider.type != PROVIDER_ANTHROPIC:
        return messages

    out = []
    marked = False
    for m in messages:
        if not marked and isinstance(m, SystemMessage) and isinstance(m.content, str):
            out.append(SystemMessage(content=[
                {"type": "text", "text": m.content, "cache_control": {"type": "ephemeral"}}
            ]))
            marked = True
        else:
            out.append(m)
    return out


def complete_structured(provider, messages, schema: type[T]) -> T:
    """구조화 출력을 반환한다 (schema 인스턴스). 제네릭이라 호출부가 schema의 필드에 타입 안전하게 접근한다."""
    messages = _mark_cache_breakpoint(provider, messages)
    result = build_llm_client(provider).with_structured_output(schema).invoke(messages)
    return cast(T, result)


def complete_text(provider, messages) -> str:
    """LLM 응답 본문(문자열)을 반환한다."""
    return cast(str, build_llm_client(provider).invoke(messages).content)
