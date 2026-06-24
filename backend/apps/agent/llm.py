"""LLM 호출 경계 (deep module).

per-Tenant Provider(ADR-0012)로 해석된 클라이언트를 통해 LLM에 접근한다. 호출부는 항상
이 모듈을 통하며, 단위 테스트는 이 경계를 결정적 Fake로 교체한다. 첫 인자는 LLMProvider다.
"""
from typing import TypeVar, cast

from pydantic import BaseModel

from apps.agent.providers import build_llm_client, PROVIDER_ANTHROPIC
from apps.usage.instrument import UsageRecordingCallback
from apps.usage.context import override_call_type

T = TypeVar("T", bound=BaseModel)

# 모든 LLM 호출에 토큰 사용량 콜백을 부착한다(UsageContext로 tenant·call_type 귀속). 스테이트리스라 공유.
_USAGE_CONFIG = {"callbacks": [UsageRecordingCallback()]}


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
    result = build_llm_client(provider).with_structured_output(schema).invoke(messages, config=_USAGE_CONFIG)
    return cast(T, result)


def complete_text(provider, messages) -> str:
    """LLM 응답 본문(문자열)을 반환한다."""
    return cast(str, build_llm_client(provider).invoke(messages, config=_USAGE_CONFIG).content)


def stream_structured(provider, messages, schema):
    """구조화 출력을 토큰 단위로 스트리밍한다 — 누적 dict를 점진 yield한다.

    스키마 필드 순서가 '제어필드 먼저'면, 노드가 response를 흘리기 전에 라우팅(폴백)을 판정할 수
    있다. provider가 부분 스트리밍을 안 하면 최종 1청크만 와도 되며(노드가 one-shot으로 저하),
    호출부는 항상 dict를 받는다(아직 안 온 필드는 키 부재 — Pydantic 기본값 함정 회피).
    """
    messages = _mark_cache_breakpoint(provider, messages)
    client = build_llm_client(provider).with_structured_output(schema)
    for chunk in client.stream(messages, config=_USAGE_CONFIG):
        if isinstance(chunk, dict):
            yield chunk
        elif hasattr(chunk, "model_dump"):
            yield chunk.model_dump()
        else:
            yield dict(chunk)


# OCR 전사 가드레일(ADR-0009): vision 모델은 생성형이라 환각할 수 있으므로, '보이는 텍스트만
# 그대로 전사'로 강하게 제약하고 temperature 0으로 결정성을 높인다. citation 원문성을 지킨다.
_OCR_TRANSCRIBE_PROMPT = (
    "이미지에 보이는 텍스트를 그대로 전사하세요. "
    "추론·번역·요약·교정·설명을 하지 말고, 보이는 문자만 출력하세요. "
    "표는 읽는 순서대로 텍스트로 옮기세요. 판독 불가하면 아무것도 출력하지 마세요."
)


def transcribe_image(provider, image_bytes: bytes, mime_type: str = "image/png") -> str:
    """vision 모델로 이미지의 텍스트를 그대로 전사한다(OCR 경계).

    provider-agnostic 이미지 content block을 써서 openai/anthropic/custom이 한 코드로 동작한다.
    비결정 외부 경계이므로 테스트는 이 함수를 Fake로 교체한다(complete_text와 분리해 격리).
    """
    import base64
    from langchain_core.messages import HumanMessage

    b64 = base64.b64encode(image_bytes).decode()
    message = HumanMessage(content=[
        {"type": "text", "text": _OCR_TRANSCRIBE_PROMPT},
        {"type": "image", "source_type": "base64", "data": b64, "mime_type": mime_type},
    ])
    with override_call_type("ocr"):
        result = build_llm_client(provider).bind(temperature=0).invoke([message], config=_USAGE_CONFIG)
    return cast(str, result.content)
