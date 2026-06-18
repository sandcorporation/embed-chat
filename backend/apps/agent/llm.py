"""LLM 호출 경계 (deep module).

per-Tenant Provider(ADR-0012)로 해석된 클라이언트를 통해 LLM에 접근한다. 호출부는 항상
이 모듈을 통하며, 단위 테스트는 이 경계를 결정적 Fake로 교체한다. 첫 인자는 LLMProvider다.
"""
from apps.agent.providers import build_llm_client


def complete_structured(provider, messages, schema):
    """구조화 출력을 반환한다 (schema 인스턴스)."""
    return build_llm_client(provider).with_structured_output(schema).invoke(messages)


def complete_text(provider, messages):
    """LLM 응답 본문(문자열)을 반환한다."""
    return build_llm_client(provider).invoke(messages).content
