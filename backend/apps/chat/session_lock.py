"""세션 단위 직렬화 락 (deep module).

같은 thread_id(=session_id)로 두 chat 태스크가 동시에 graph.invoke하면 PostgresSaver
lost update·토큰 인터리빙이 발생한다. Redis의 원자적 SETNX+TTL로 세션당 하나만 실행되게 한다.
외부 의존은 Redis 하나뿐이라 결정적으로 단위 테스트할 수 있다.
"""
from apps.chat.sse import get_redis_client

# TTL은 chat 태스크 하드 타임리밋과 정렬: 워커가 락을 쥔 채 크래시해도 세션이 영구
# 데드락되지 않고 만료 후 자가치유된다.
LOCK_TTL_SECONDS = 120

_LOCK_KEY = "chat:lock:{}"


def acquire(session_id: str, ttl: int = LOCK_TTL_SECONDS) -> bool:
    """세션 락을 시도한다. 획득하면 True, 이미 다른 실행이 쥐고 있으면 False."""
    r = get_redis_client()
    return bool(r.set(_LOCK_KEY.format(session_id), "1", nx=True, ex=ttl))


def release(session_id: str) -> None:
    """세션 락을 해제한다. 해제 실패(미보유 등)는 TTL로 자가치유되므로 무시한다."""
    r = get_redis_client()
    r.delete(_LOCK_KEY.format(session_id))
