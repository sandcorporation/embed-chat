import json
import redis
from django.conf import settings


def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL)


def publish_token(session_id: str, content: str) -> None:
    r = get_redis_client()
    r.publish(f"session:{session_id}", json.dumps({"type": "token", "content": content}))


def publish_done(session_id: str) -> None:
    r = get_redis_client()
    r.publish(f"session:{session_id}", json.dumps({"type": "done"}))


def publish_error(session_id: str, message: str) -> None:
    r = get_redis_client()
    r.publish(f"session:{session_id}", json.dumps({"type": "error", "message": message}))


def publish_hitl_start(session_id: str) -> None:
    r = get_redis_client()
    r.publish(f"session:{session_id}", json.dumps({"type": "hitl_start"}))


def publish_hitl_message(session_id: str, content: str, agent_display_name: str = "상담원") -> None:
    r = get_redis_client()
    r.publish(f"session:{session_id}", json.dumps({
        "type": "hitl_message",
        "content": content,
        "agent_display_name": agent_display_name,
    }))


def publish_hitl_end(session_id: str) -> None:
    r = get_redis_client()
    r.publish(f"session:{session_id}", json.dumps({"type": "hitl_end"}))


def publish_hitl_new(tenant_id: str, session_id: str, reason: str = "") -> None:
    r = get_redis_client()
    r.publish(f"hitl:{tenant_id}", json.dumps({"type": "hitl_new", "session_id": session_id, "reason": reason}))


def publish_visitor_message(tenant_id: str, session_id: str, content: str) -> None:
    r = get_redis_client()
    r.publish(f"hitl:{tenant_id}", json.dumps({
        "type": "visitor_message",
        "session_id": session_id,
        "content": content,
    }))


def publish_console_delta(tenant_id: str, delta_type: str, session_id: str) -> None:
    """어드민 세션 콘솔의 라이브 갱신 델타를 발행한다(console-bridge 소비자용 — issue 148).

    HitlTab이 이미 구독하는 hitl_new/hitl_claimed/hitl_resolved 형태라 목록을 재정렬·갱신한다.
    """
    r = get_redis_client()
    r.publish(f"hitl:{tenant_id}", json.dumps({"type": delta_type, "session_id": session_id}))


def publish_session_connected(tenant_id: str, session_id: str) -> None:
    """방문자 SSE 연결 시작을 어드민 콘솔에 알린다(presence 실시간 push — issue 138)."""
    r = get_redis_client()
    r.publish(f"hitl:{tenant_id}", json.dumps({"type": "session_connected", "session_id": session_id}))


def publish_session_disconnected(tenant_id: str, session_id: str) -> None:
    """방문자 SSE 연결 종료를 어드민 콘솔에 알린다(presence 실시간 push — issue 138)."""
    r = get_redis_client()
    r.publish(f"hitl:{tenant_id}", json.dumps({"type": "session_disconnected", "session_id": session_id}))


def sse_event_stream(session_id: str, welcome_message: str = "", history=None, is_hitl: bool = False, brand_name: str = "", tenant_id: str = ""):
    from apps.chat import presence

    r = get_redis_client()
    pubsub = r.pubsub()
    pubsub.subscribe(f"session:{session_id}")
    # presence: 연결 시작을 표시(직접 ZADD = 하트비트, 진실원천) + VisitorConnected 이벤트 발행
    # (EventBus ephemeral → presence-bridge가 콘솔 델타로 — issue 150). 하트비트는 직접 유지.
    if tenant_id:
        from apps.events.signals import publish_presence
        from apps.events.types import VISITOR_CONNECTED

        presence.mark_active(tenant_id, session_id)
        publish_presence(VISITOR_CONNECTED, tenant_id, session_id)
    connected_payload = {"session_id": session_id}
    # 브랜드 텍스트는 신규/재연결 무관하게 항상 헤더에 표시한다.
    if brand_name:
        connected_payload["brand_name"] = brand_name
    if history is not None:
        connected_payload["history"] = history
        if is_hitl:
            connected_payload["is_hitl"] = True
    elif welcome_message:
        connected_payload["welcome_message"] = welcome_message
    try:
        yield f"event: connected\ndata: {json.dumps(connected_payload)}\n\n"
        while True:
            message = pubsub.get_message(timeout=1.0)
            if message is None:
                # keepalive: SSE comment (ignored by clients). If client disconnected,
                # this yield raises BrokenPipeError, freeing the gunicorn worker.
                if tenant_id:
                    presence.mark_active(tenant_id, session_id)  # 연결 살아있는 동안 presence 갱신
                yield ": keepalive\n\n"
                continue
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            event_type = data.get("type", "token")
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    except (GeneratorExit, BrokenPipeError, OSError):
        pass
    finally:
        pubsub.unsubscribe(f"session:{session_id}")
        pubsub.close()
        if tenant_id:
            from apps.events.signals import publish_presence
            from apps.events.types import VISITOR_DISCONNECTED

            publish_presence(VISITOR_DISCONNECTED, tenant_id, session_id)  # 연결 종료 → 이벤트
