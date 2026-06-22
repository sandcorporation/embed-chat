"""세션 presence + SSE 연결/해제 이벤트 (issue 138).

실 Redis로 검증한다(CLAUDE.md: 결정적 인프라는 실제 사용). 시간은 now 주입으로 결정화.
"""
import json
import pytest


def _read_event(pubsub, want_type=None, tries=20):
    """pubsub에서 다음 'message'를 읽어 파싱한다(원하면 특정 type까지 스킵)."""
    for _ in range(tries):
        msg = pubsub.get_message(timeout=0.5)
        if not msg or msg["type"] != "message":
            continue
        data = json.loads(msg["data"])
        if want_type is None or data.get("type") == want_type:
            return data
    return None


@pytest.mark.django_db
def test_mark_active_lists_session(tenant_with_key):
    """mark_active한 세션이 active_sessions에 나타난다."""
    from apps.chat import presence
    tenant, _ = tenant_with_key
    presence.mark_active(str(tenant.id), "s-live", now=1000.0)
    assert "s-live" in presence.active_sessions(str(tenant.id), now=1000.0)


@pytest.mark.django_db
def test_stale_session_expires(tenant_with_key):
    """갱신이 TTL을 넘기면 active_sessions에서 자연 소멸한다(자가치유)."""
    from apps.chat import presence
    tenant, _ = tenant_with_key
    presence.mark_active(str(tenant.id), "s-stale", now=1000.0)
    later = 1000.0 + presence.PRESENCE_TTL_SECONDS + 1
    assert "s-stale" not in presence.active_sessions(str(tenant.id), now=later)


def _consume_presence_for(bus, group, session_id, want_type, tries=10):
    from apps.events.types import PRESENCE_TOPIC
    for _ in range(tries):
        for m in bus.consume(PRESENCE_TOPIC, group, "c", count=20, block_ms=200):
            bus.ack(PRESENCE_TOPIC, group, m.msg_id)
            if m.payload.get("type") == want_type and m.payload.get("aggregate_id") == session_id:
                return True
    return False


@pytest.mark.django_db
def test_reconnect_keeps_session_active_no_premature_disconnect(tenant_with_key):
    """새로고침(재연결): 옛 연결이 닫혀도 새 연결이 살아있으면 '마지막 종료'가 아니다.

    presence를 연결 단위로 참조 계수한다 — 0→1 전이만 '첫 연결', 1→0 전이만 '마지막 종료'.
    이래야 새로고침으로 옛 연결이 늦게 닫혀도 콘솔이 유휴로 뒤집히지 않는다.
    """
    from apps.chat import presence
    tenant, _ = tenant_with_key
    t, sid = str(tenant.id), "s-refresh"

    assert presence.register_connection(t, sid, "conn-old") is True   # 0→1: 첫 연결
    assert presence.register_connection(t, sid, "conn-new") is False  # 1→2: 이미 활성
    assert presence.unregister_connection(t, sid, "conn-old") is False  # 2→1: 새 연결 살아있음
    assert presence.unregister_connection(t, sid, "conn-new") is True   # 1→0: 진짜 종료


@pytest.mark.django_db
def test_overlapping_sse_connections_suppress_premature_disconnect(tenant_with_key):
    """두 SSE 연결이 겹칠 때, 먼저 닫힌 옛 연결은 VisitorDisconnected를 내지 않는다(재연결 race)."""
    import uuid
    from apps.chat.sse import sse_event_stream
    from apps.events.bus import RedisStreamsBus
    from apps.events.types import PRESENCE_TOPIC, VISITOR_DISCONNECTED

    tenant, _ = tenant_with_key
    sid = f"sess-{uuid.uuid4().hex}"
    bus = RedisStreamsBus()
    group = f"t-{uuid.uuid4().hex}"
    bus.ensure_group(PRESENCE_TOPIC, group)

    g1 = sse_event_stream(sid, tenant_id=str(tenant.id)); next(g1)  # conn1: 첫 연결
    g2 = sse_event_stream(sid, tenant_id=str(tenant.id)); next(g2)  # conn2: 이미 활성(연결 이벤트 없음)

    g1.close()  # 옛 연결 종료 — 새 연결이 살아있으니 disconnect 억제
    assert not _consume_presence_for(bus, group, sid, VISITOR_DISCONNECTED, tries=3)

    g2.close()  # 마지막 연결 종료 — 이제 disconnect
    assert _consume_presence_for(bus, group, sid, VISITOR_DISCONNECTED)


@pytest.mark.django_db
def test_sse_marks_presence_and_emits_visitor_events(tenant_with_key):
    """SSE 시작 시 presence 직접 mark + VisitorConnected 이벤트, 종료 시 VisitorDisconnected를
    EventBus presence 스트림에 발행한다(issue 150 — 직접 pub/sub 대신 이벤트화)."""
    import uuid
    from apps.chat.sse import sse_event_stream
    from apps.chat import presence
    from apps.events.bus import RedisStreamsBus
    from apps.events.types import PRESENCE_TOPIC, VISITOR_CONNECTED, VISITOR_DISCONNECTED

    tenant, _ = tenant_with_key
    sid = f"sess-{uuid.uuid4().hex}"
    bus = RedisStreamsBus()
    group = f"t-{uuid.uuid4().hex}"
    bus.ensure_group(PRESENCE_TOPIC, group)  # 이후 발행분만 본다

    gen = sse_event_stream(sid, tenant_id=str(tenant.id))
    first = next(gen)  # connected yield + 직접 mark_active + VisitorConnected 발행
    assert "event: connected" in first
    assert sid in presence.active_sessions(str(tenant.id))  # 하트비트(직접 ZADD) 유지
    assert _consume_presence_for(bus, group, sid, VISITOR_CONNECTED)

    gen.close()  # finally → VisitorDisconnected 발행
    assert _consume_presence_for(bus, group, sid, VISITOR_DISCONNECTED)
