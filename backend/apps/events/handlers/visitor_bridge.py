"""visitor-bridge 소비자 핸들러 (issue 147).

HITL 라이프사이클 내구 이벤트를 소비해 방문자에게 실시간 신호를 발행한다 — 방문자 SSE의 단일
원천. Escalated/TakenOver → hitl_start, Resolved → hitl_end (기존 위젯 계약 그대로).
"""
from apps.events.consumer import register_handler
from apps.events.types import (
    GROUP_VISITOR_BRIDGE, SESSION_ESCALATED, SESSION_TAKEN_OVER, ESCALATION_RESOLVED,
)


def handle(envelope: dict) -> None:
    from apps.chat.sse import publish_hitl_start, publish_hitl_end

    session_id = envelope["aggregate_id"]
    event_type = envelope.get("type")
    if event_type in (SESSION_ESCALATED, SESSION_TAKEN_OVER):
        publish_hitl_start(session_id)
    elif event_type == ESCALATION_RESOLVED:
        publish_hitl_end(session_id)


register_handler(GROUP_VISITOR_BRIDGE, handle)
