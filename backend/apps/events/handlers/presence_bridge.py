"""presence-bridge 소비자 핸들러 (issue 150).

ephemeral presence 전이(VisitorConnected/Disconnected)를 소비해 어드민 콘솔 채널(hitl:{tenant})에
session_connected/disconnected 델타를 발행한다. presence sorted-set의 진실원천은 SSE 프로세스의
직접 mark_active(하트비트)가 유지하므로, 이 브리지는 콘솔 라이브 델타만 담당한다.
"""
from apps.events.consumer import register_handler
from apps.events.types import GROUP_PRESENCE_BRIDGE, VISITOR_CONNECTED, VISITOR_DISCONNECTED


def handle(envelope: dict) -> None:
    from apps.chat.sse import publish_session_connected, publish_session_disconnected

    event_type = envelope.get("type")
    tenant_id, session_id = envelope["tenant_id"], envelope["aggregate_id"]
    if event_type == VISITOR_CONNECTED:
        publish_session_connected(tenant_id, session_id)
    elif event_type == VISITOR_DISCONNECTED:
        publish_session_disconnected(tenant_id, session_id)


register_handler(GROUP_PRESENCE_BRIDGE, handle)
