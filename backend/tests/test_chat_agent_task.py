import pytest
from utils import get_redis_message, open_stream


def _open_session(client, tenant, visitor_id):
    """slug 기반 stream으로 세션을 만들고 session_id를 반환한다 (issue 85)."""
    return open_stream(client, tenant, visitor_id)["X-Session-Id"]


# ── Issue 81: 에이전트 실행을 Celery 태스크로 (gevent 스레드 제거) ──────────────

@pytest.mark.django_db
def test_send_message_runs_agent_via_task_and_saves_assistant(client, tenant_with_key):
    """non-hitl 메시지를 보내면 에이전트가 태스크로 실행되어 assistant 응답이 저장된다.

    Celery EAGER로 태스크가 뷰 응답 전에 인라인 실행되므로, POST가 끝난 직후
    assistant ChatMessage가 결정적으로 존재한다 (daemon 스레드의 비결정성 제거).
    """
    from apps.chat.models import ChatSession, ChatMessage

    tenant, raw_key = tenant_with_key
    session_id = _open_session(client, tenant, "v-task-wiring")

    resp = client.post(
        "/api/chat/message",
        {"session_id": session_id, "content": "안녕하세요"},
        content_type="application/json",
    )
    assert resp.status_code == 202

    session = ChatSession.objects.get(id=session_id)
    assert ChatMessage.objects.filter(
        session=session, role=ChatMessage.ROLE_ASSISTANT
    ).exists(), "에이전트 태스크가 인라인 실행되어 assistant 메시지를 남겨야 한다"


@pytest.mark.django_db
def test_agent_failure_publishes_error_and_saves_no_assistant(
    client, tenant_with_key, fake_chat_llm, redis_subscribe
):
    """에이전트 실행이 실패하면 사용자에게 error 이벤트가 발행되고, 부분 저장은 없다.

    at-most-once: 실패는 조용한 무응답 대신 error로 알려 재전송을 유도하며,
    절반 실행된 assistant 메시지를 남기지 않는다.
    """
    from apps.chat.models import ChatSession, ChatMessage

    tenant, raw_key = tenant_with_key
    session_id = _open_session(client, tenant, "v-task-error")
    pubsub = redis_subscribe(f"session:{session_id}")

    def _boom(messages):
        raise RuntimeError("LLM exploded")

    fake_chat_llm.override = _boom

    client.post(
        "/api/chat/message",
        {"session_id": session_id, "content": "안녕하세요"},
        content_type="application/json",
    )

    msg = get_redis_message(pubsub)
    assert msg is not None and msg["type"] == "error", f"실패 시 error 이벤트가 와야 한다: {msg}"

    session = ChatSession.objects.get(id=session_id)
    assert not ChatMessage.objects.filter(
        session=session, role=ChatMessage.ROLE_ASSISTANT
    ).exists(), "실패 시 assistant 메시지를 남기면 안 된다"


# ── Issue 83: 세션 단위 직렬화가 태스크에 통합된다 ─────────────────────────────

@pytest.mark.django_db
def test_locked_session_does_not_run_agent_but_reenqueues(settings, tenant_with_key):
    """이미 다른 실행이 세션 락을 쥐고 있으면, 태스크는 에이전트를 돌리지 않고 뒤로 재-enqueue한다.

    같은 세션 동시 실행에 의한 PostgresSaver lost update·토큰 인터리빙을 막는다.
    EAGER를 끄면 재-enqueue가 인라인 재귀하지 않고 브로커로 나가므로 결정적으로 관찰된다.
    """
    import redis as redis_lib
    import os
    from apps.chat import session_lock
    from apps.chat.tasks import run_chat_agent_task
    from apps.chat.models import ChatSession, ChatMessage

    settings.CELERY_TASK_ALWAYS_EAGER = False
    tenant, _ = tenant_with_key
    session = ChatSession.objects.create(
        tenant_id=tenant.id, visitor_id="v-locked"    )
    sid = str(session.id)

    r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

    def _pending():
        return r.llen("celery") + r.llen("chat")

    assert session_lock.acquire(sid) is True  # 외부에서 세션을 점유
    before = _pending()
    try:
        run_chat_agent_task(sid, "안녕하세요")  # 태스크 본문 직접 실행

        assert not ChatMessage.objects.filter(
            session=session, role=ChatMessage.ROLE_ASSISTANT
        ).exists(), "락이 잡힌 세션에서 에이전트가 돌면 안 된다"
        assert _pending() > before, "처리되지 못한 메시지는 드롭되지 않고 재-enqueue되어야 한다"
    finally:
        session_lock.release(sid)
        r.close()


@pytest.mark.django_db
def test_lock_released_on_failure_so_session_not_deadlocked(
    client, tenant_with_key, fake_chat_llm
):
    """에이전트가 실패해도 세션 락은 finally로 해제되어 다음 메시지가 막히지 않는다."""
    from apps.chat import session_lock

    tenant, raw_key = tenant_with_key
    session_id = _open_session(client, tenant, "v-fail-unlock")

    fake_chat_llm.override = lambda m: (_ for _ in ()).throw(RuntimeError("boom"))

    client.post(
        "/api/chat/message",
        {"session_id": session_id, "content": "안녕하세요"},
        content_type="application/json",
    )

    # 실패 후 락이 풀려 있어야 한다 → 외부에서 즉시 획득 가능
    assert session_lock.acquire(session_id) is True, "실패 시 락이 해제되어야 한다(데드락 금지)"
    session_lock.release(session_id)


# ── Issue 82: chat 전용 큐 격리 + soft time limit ─────────────────────────────

def test_chat_task_routes_to_dedicated_chat_queue():
    """chat 태스크는 배치와 분리된 전용 'chat' 큐로 라우팅된다(무거운 배치에 굶지 않게)."""
    from config.celery import app
    from apps.chat.tasks import run_chat_agent_task

    route = app.amqp.router.route({}, run_chat_agent_task.name)
    queue = route.get("queue")
    queue_name = getattr(queue, "name", queue)
    assert queue_name == "chat", f"chat 태스크가 전용 큐로 가야 한다: {queue_name}"


@pytest.mark.django_db
def test_soft_time_limit_is_reported_as_error(client, tenant_with_key, fake_chat_llm, redis_subscribe):
    """soft time limit 초과(SoftTimeLimitExceeded)도 사용자에게 error로 전달되고 정리된다."""
    from celery.exceptions import SoftTimeLimitExceeded

    tenant, raw_key = tenant_with_key
    session_id = _open_session(client, tenant, "v-soft-timeout")
    pubsub = redis_subscribe(f"session:{session_id}")

    def _timeout(messages):
        raise SoftTimeLimitExceeded()

    fake_chat_llm.override = _timeout

    client.post(
        "/api/chat/message",
        {"session_id": session_id, "content": "안녕하세요"},
        content_type="application/json",
    )

    msg = get_redis_message(pubsub)
    assert msg is not None and msg["type"] == "error", f"타임아웃도 error로 알려야 한다: {msg}"
