"""LLM 호출 경계 (deep module).

OpenRouter(외부 API) 호출을 좁은 인터페이스 뒤로 캡슐화한다. 호출부는 항상
이 모듈을 통해 LLM에 접근하며, 단위 테스트는 이 경계를 결정적 Fake로 교체한다.
"""
from django.conf import settings
from langchain_openai import ChatOpenAI


def _client(model_id, **extra):
    return ChatOpenAI(
        model=model_id,
        api_key=settings.OPEN_ROUTER_API_KEY,
        base_url=settings.OPEN_ROUTER_BASE_URL,
        **extra,
    )


def complete_structured(model_id, messages, schema):
    """구조화 출력을 반환한다 (schema 인스턴스)."""
    llm = _client(model_id, extra_body={"provider": {"require_parameters": True}})
    return llm.with_structured_output(schema).invoke(messages)


def complete_text(model_id, messages):
    """LLM 응답 본문(문자열)을 반환한다."""
    return _client(model_id).invoke(messages).content
