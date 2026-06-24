"""taskiq 브로커 — chat 태스크 전용 큐 (ADR-0024). 배치는 Celery 유지(공존).

테스트는 TASKIQ_INMEMORY=1로 InMemoryBroker(kiq 인라인 실행)를 쓴다 — 추가 인프라·워커 없이
결정적. prod는 redis broker(taskiq 워커가 소비).
"""
import os

from taskiq import InMemoryBroker

if os.environ.get("TASKIQ_INMEMORY") == "1":
    # await_inplace=True: kiq가 task를 그 자리에서 await 완료한다(테스트 결정성 — dispatch가
    # fire-and-forget이어도 enqueue 시점에 실행이 끝나 있음).
    broker = InMemoryBroker(await_inplace=True)
else:
    from taskiq_redis import ListQueueBroker

    broker = ListQueueBroker(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
