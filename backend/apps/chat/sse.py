import json
from typing import Any

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


# ── async 포트 (issue 193) — taskiq chat 워커·ASGI SSE가 쓴다. 채널·payload는 sync와 동일. ──
def get_async_redis_client():
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL)


async def apublish_token(session_id: str, content: str) -> None:
    r = get_async_redis_client()
    try:
        await r.publish(f"session:{session_id}", json.dumps({"type": "token", "content": content}))
    finally:
        await r.aclose()


async def apublish_done(session_id: str) -> None:
    r = get_async_redis_client()
    try:
        await r.publish(f"session:{session_id}", json.dumps({"type": "done"}))
    finally:
        await r.aclose()


async def apublish_error(session_id: str, message: str) -> None:
    r = get_async_redis_client()
    try:
        await r.publish(f"session:{session_id}", json.dumps({"type": "error", "message": message}))
    finally:
        await r.aclose()


async def asubscribe(session_id: str):
    """session 채널을 async 구독해 메시지(dict)를 yield한다(ASGI SSE generator용)."""
    r = get_async_redis_client()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"session:{session_id}")
    try:
        async for message in pubsub.listen():
            if message.get("type") == "message":
                yield json.loads(message["data"])
    finally:
        await pubsub.unsubscribe(f"session:{session_id}")
        await pubsub.aclose()
        await r.aclose()


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
    import uuid
    from apps.chat import presence

    r = get_redis_client()
    pubsub = r.pubsub()
    pubsub.subscribe(f"session:{session_id}")
    connected_payload: dict[str, Any]
    # presence: 이 연결을 참조 계수로 등록(직접 ZADD = 하트비트, 진실원천). VisitorConnected는
    # 세션의 '첫' 연결(0→1)에서만 발행한다 — 새로고침으로 옛/새 연결이 겹쳐도 콘솔이 유휴로
    # 뒤집히지 않게(EventBus ephemeral → presence-bridge가 콘솔 델타로 — issue 150).
    conn_id = uuid.uuid4().hex
    if tenant_id:
        from apps.events.signals import publish_presence
        from apps.events.types import VISITOR_CONNECTED

        if presence.register_connection(tenant_id, session_id, conn_id):
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
                    presence.touch_connection(tenant_id, session_id, conn_id)  # 하트비트 + 연결 TTL 갱신
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

            # 세션의 '마지막' 연결(1→0)에서만 disconnect를 낸다 — 새로고침으로 옛 연결이
            # 늦게 닫혀도 새 연결이 살아있으면 콘솔을 유휴로 뒤집지 않는다.
            if presence.unregister_connection(tenant_id, session_id, conn_id):
                publish_presence(VISITOR_DISCONNECTED, tenant_id, session_id)
