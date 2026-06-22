"""console-bridge 소비자 핸들러 (issue 148).

HITL 라이프사이클 내구 이벤트를 소비해 어드민 세션 콘솔의 라이브 델타를 hitl:{tenant}에
발행한다. 콘솔 스냅샷은 GET /tenant/sessions/(권위 DB) 그대로 — 이 핸들러는 델타만.
"""
from apps.events.consumer import register_handler
from apps.events.types import (
    GROUP_CONSOLE_BRIDGE, SESSION_ESCALATED, SESSION_TAKEN_OVER,
    ESCALATION_CLAIMED, ESCALATION_RESOLVED,
)

# 라이프사이클 이벤트 → HitlTab이 이미 이해하는 델타 타입(목록 갱신 트리거).
_DELTA = {
    SESSION_ESCALATED: "hitl_new",
    SESSION_TAKEN_OVER: "hitl_new",
    ESCALATION_CLAIMED: "hitl_claimed",
    ESCALATION_RESOLVED: "hitl_resolved",
}


def handle(envelope: dict) -> None:
    from apps.chat.sse import publish_console_delta

    delta = _DELTA.get(envelope.get("type") or "")
    if not delta:
        return
    publish_console_delta(envelope["tenant_id"], delta, envelope["aggregate_id"])


register_handler(GROUP_CONSOLE_BRIDGE, handle)
