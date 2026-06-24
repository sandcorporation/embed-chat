"""LLM 호출 계측 — langchain 응답에서 토큰 사용량을 추출해 record_usage에 귀속한다.

UsageRecordingCallback을 LLM 경계(llm.py)의 invoke/stream config에 부착한다. with_structured_output을
써도 콜백은 내부 LLM 호출에서 발화하므로 토큰을 잡는다. UsageContext에서 tenant/call_type을 읽는다.
"""
from langchain_core.callbacks import BaseCallbackHandler

from .context import get_usage_context
from .recording import record_usage


def _extract(response) -> tuple[str, int, int]:
    """LLMResult에서 (model, input_tokens, output_tokens)를 뽑는다. 실패해도 안전(0)."""
    try:
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        um = getattr(msg, "usage_metadata", None) if msg is not None else None
        if um:
            input_t = um.get("input_tokens", 0)
            output_t = um.get("output_tokens", 0)
        else:
            tu = (response.llm_output or {}).get("token_usage", {}) or {}
            input_t = tu.get("prompt_tokens", 0)
            output_t = tu.get("completion_tokens", 0)
        meta = getattr(msg, "response_metadata", {}) if msg is not None else {}
        model = (response.llm_output or {}).get("model_name") or (meta or {}).get("model_name") or "unknown"
        return str(model), int(input_t or 0), int(output_t or 0)
    except Exception:
        return "unknown", 0, 0


class UsageRecordingCallback(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs) -> None:
        ctx = get_usage_context()
        if not ctx or not ctx.tenant_id:
            return
        model, input_t, output_t = _extract(response)
        if input_t or output_t:
            record_usage(ctx.tenant_id, ctx.call_type, model, input_t, output_t)
