from config.celery import app

# 락 경합 시 재-enqueue 지연(초). 즉시 재시도하면 락이 풀릴 때까지 busy-loop이 되므로
# 짧게 미뤄 첫 실행 뒤에 줄세운다.
RE_ENQUEUE_DELAY_SECONDS = 1


# soft 90s: SoftTimeLimitExceeded로 잡아 publish_error+정리, hard 120s: 매달린 LLM이
# prefork 프로세스를 영구 점유하지 못하게 하는 백스톱(LLM 경계에 앱 타임아웃 없음).
@app.task(
    max_retries=0,
    acks_late=False,
    ignore_result=True,
    soft_time_limit=90,
    time_limit=120,
)
def run_chat_agent_task(session_id: str, user_message: str):
    """Visitor chat 1턴을 실행하는 Celery 태스크.

    gevent web 워커의 hub를 얼리지 않도록 에이전트 실행을 별도 prefork 풀로 격리한다.
    스트리밍은 비멱등(이미 나간 토큰 회수 불가)이라 at-most-once다:
    자동 재시도 없음(max_retries=0), 크래시 시 재배달 없음(acks_late=False).
    실패 시 사용자에게 publish_error로 알리고 재전송을 유도한다.

    같은 세션 동시 실행은 PostgresSaver lost update·토큰 인터리빙을 부르므로 세션 락으로
    직렬화한다. 락을 못 잡으면 프로세스를 점유하지 않고 뒤로 재-enqueue한다.

    JSON 직렬화 경계라 ORM 객체가 아니라 session_id(str)만 받아 내부에서 재조회한다.
    """
    from apps.chat import session_lock
    from apps.chat.models import ChatSession
    from apps.agent.graph import run_chat_agent
    from apps.chat.sse import publish_error

    if not session_lock.acquire(session_id):
        # 다른 실행이 같은 세션을 처리 중 — 뒤에 줄세운다(프로세스 점유·메시지 드롭 없이).
        run_chat_agent_task.apply_async(
            (session_id, user_message), countdown=RE_ENQUEUE_DELAY_SECONDS
        )
        return

    try:
        session = ChatSession.objects.get(id=session_id)
        run_chat_agent(session, user_message)
    except Exception as e:
        publish_error(session_id, str(e))
    finally:
        # 정상·예외 무관하게 해제해 다음 메시지가 막히지 않게 한다(미해제도 TTL로 자가치유).
        session_lock.release(session_id)
