"""E2E용 결정적 Fake LLM (OpenAI Chat Completions 호환).

실제 추론 없이 규칙 기반으로 응답한다. E2E 스택에서 비결정적인 qwen 대신 사용해
HITL/chat 단언을 결정적으로 만든다. 절대 외부 호출을 하지 않는다.

판정 규칙:
- 마지막 사용자(role=user) 메시지에 인간 상담원 키워드('상담원')가 있으면 needs_hitl=true.
- system 프롬프트는 판정에서 제외(상담원 안내문이 포함될 수 있으므로).

응답 형식:
- 요청 response_format.type == "json_schema" (langchain with_structured_output) →
  스키마 JSON을 message.content 문자열로 반환.
- 그 외(일반 .invoke) → message.content에 카난 텍스트(기본 빈 facts "{}").
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HUMAN_AGENT_KEYWORD = os.environ.get("FAKE_LLM_HITL_KEYWORD", "상담원")
NORMAL_REPLY = os.environ.get(
    "FAKE_LLM_NORMAL_REPLY", "안녕하세요! 무엇을 도와드릴까요?"
)


def _last_user_message(messages):
    texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
    return texts[-1] if texts else ""


def build_completion(body: dict) -> dict:
    """OpenAI chat.completions 요청 dict → 응답 dict (결정적)."""
    messages = body.get("messages", []) or []
    last_user = _last_user_message(messages)
    needs_hitl = HUMAN_AGENT_KEYWORD in (last_user or "")

    response_format = body.get("response_format") or {}
    is_structured = response_format.get("type") == "json_schema"

    if is_structured:
        content = json.dumps(
            {
                "response": "" if needs_hitl else NORMAL_REPLY,
                "needs_hitl": needs_hitl,
                "hitl_reason": "상담원 요청" if needs_hitl else "",
            },
            ensure_ascii=False,
        )
    else:
        # 일반 completion (예: Visitor Memory 추출) — 결정적 빈 facts
        content = "{}"

    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 0,
        "model": body.get("model", "fake-llm"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            self._send_json(200, {"status": "ok"})
        elif self.path.rstrip("/") == "/v1/models":
            self._send_json(200, {"object": "list", "data": [{"id": "fake-llm", "object": "model"}]})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            body = {}
        if self.path.rstrip("/").endswith("/chat/completions"):
            self._send_json(200, build_completion(body))
        else:
            self._send_json(404, {"error": "not found"})


def main():
    port = int(os.environ.get("PORT", "8090"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
