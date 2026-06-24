"""LLM async 경계 (issue 191) — acomplete/astream이 async로 동작하고 Fake 교체 가능.

chat 경로(192~)가 쓰는 async 경계. sync 경계(complete_structured 등)는 인제스션·추출이 유지(공존).
"""
from pydantic import BaseModel

from apps.agent import llm


class _Resp(BaseModel):
    context_sufficient: bool = True
    response: str = ""


async def test_acomplete_structured_returns_async(fake_chat_llm):
    """acomplete_structured가 await로 구조화 결과를 반환한다(Fake 경계)."""
    fake_chat_llm.override = lambda messages: _Resp(response="async-ok")
    out = await llm.acomplete_structured(None, [], _Resp)
    assert out.response == "async-ok"


async def test_astream_structured_yields_async(fake_chat_llm):
    """astream_structured가 async generator로 누적 청크를 yield한다."""
    fake_chat_llm.override = lambda messages: _Resp(context_sufficient=True, response="hello")
    chunks = [c async for c in llm.astream_structured(None, [], _Resp)]
    assert chunks and chunks[-1].get("response") == "hello"
