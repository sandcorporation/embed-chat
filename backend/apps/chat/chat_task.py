"""chat 1턴 taskiq 태스크 + dispatch 어댑터 (issue 194, ADR-0024).

기존 Celery run_chat_agent_task의 async 대응. 세션 직렬화(락)·하드 timeout·at-most-once·예외 시
publish_error는 여기서, graceful/백프레셔는 taskiq가 제공. 뷰는 dispatch_chat만 안다(전송·큐 구현
교체가 국소적).
"""
import asyncio

from config.taskiq_broker import broker

CHAT_HARD_TIMEOUT = 120  # session_lock TTL과 정렬


@broker.task
async def chat_task(session_id: str, user_message: str) -> None:
    from asgiref.sync import sync_to_async

    from apps.chat.models import ChatSession
    from apps.chat.session_lock import aacquire, arelease
    from apps.agent.graph import run_chat_agent_async
    from apps.chat.sse import apublish_error

    if not await aacquire(session_id):
        return  # 같은 세션이 이미 실행 중(직렬화) — 드롭. at-most-once.
    try:
        session = await sync_to_async(ChatSession.objects.get)(id=session_id)
        await asyncio.wait_for(run_chat_agent_async(session, user_message), timeout=CHAT_HARD_TIMEOUT)
    except Exception:  # noqa: BLE001 — 비멱등 스트리밍이라 재시도 안 함, 사용자에게 알리고 재전송 유도
        await apublish_error(session_id, "응답 생성 중 오류가 발생했습니다. 다시 시도해 주세요.")
    finally:
        await arelease(session_id)


async def dispatch_chat(session_id: str, user_message: str) -> None:
    """뷰가 호출하는 dispatch 어댑터 — chat 1턴을 taskiq 워커로 enqueue한다."""
    await chat_task.kiq(session_id, user_message)
