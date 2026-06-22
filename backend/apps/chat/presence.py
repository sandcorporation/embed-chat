"""세션 presence(활성=SSE 연결됨) 추적 — deep module (issue 138).

테넌트별 Redis sorted set(member=session_id, score=마지막 갱신 epoch초)로 "지금 누가
연결돼 있는지"를 자가치유 방식으로 둔다. SSE 스트림이 keepalive마다 mark_active로 score를
갱신하고, 연결이 끊겨 갱신이 멈추면 TTL(임계)을 넘겨 active_sessions에서 자연 소멸한다
(워커 비정상 종료에도 stale 활성이 남지 않는다). 진실의 원천이며 콘솔이 이를 조회한다.
"""
import time

PRESENCE_TTL_SECONDS = 20  # 이 시간 동안 갱신이 없으면 비활성으로 본다(keepalive 1s 대비 여유)


def _key(tenant_id: str) -> str:
    return f"presence:{tenant_id}"


def _redis():
    from apps.chat.sse import get_redis_client
    return get_redis_client()


def mark_active(tenant_id: str, session_id: str, now: float | None = None) -> None:
    """세션을 지금 활성으로 표시(또는 갱신)한다."""
    now = time.time() if now is None else now
    _redis().zadd(_key(tenant_id), {str(session_id): now})


def active_sessions(tenant_id: str, now: float | None = None) -> set[str]:
    """임계(TTL) 이내로 갱신된 활성 세션 id 집합. 조회 시 오래된 항목을 정리한다(자가치유)."""
    now = time.time() if now is None else now
    r = _redis()
    key = _key(tenant_id)
    r.zremrangebyscore(key, "-inf", now - PRESENCE_TTL_SECONDS)  # 임계 밖(stale) 제거
    return {m.decode() if isinstance(m, bytes) else m for m in r.zrange(key, 0, -1)}
