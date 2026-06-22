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


@pytest.mark.django_db
def test_sse_marks_presence_and_emits_connect_disconnect(tenant_with_key, redis_subscribe):
    """SSE 시작 시 presence 표시 + session_connected, 종료 시 session_disconnected를 publish한다."""
    from apps.chat.sse import sse_event_stream
    from apps.chat import presence
    tenant, _ = tenant_with_key
    pubsub = redis_subscribe(f"hitl:{tenant.id}")

    gen = sse_event_stream("sess-1", tenant_id=str(tenant.id))
    first = next(gen)  # connected 이벤트 yield + presence mark + connect publish
    assert "event: connected" in first
    assert "sess-1" in presence.active_sessions(str(tenant.id))
    assert _read_event(pubsub, "session_connected")["session_id"] == "sess-1"

    gen.close()  # GeneratorExit → finally → disconnect publish
    assert _read_event(pubsub, "session_disconnected")["session_id"] == "sess-1"
